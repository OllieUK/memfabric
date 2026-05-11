#!/usr/bin/env python3
"""scripts/ingest_sp800_53_attack_mappings.py — Create MITIGATES edges from SP 800-53 Rev 5
controls to ATT&CK techniques using CTID attack-control-framework-mappings STIX bundles.

Uses two CTID files:
  - ctid-sp800-53-r5-controls.json: course-of-action objects mapping STIX IDs -> control IDs
  - ctid-sp800-53-r5-attack-mappings.json: relationship objects (mitigates)

Enhancement controls (e.g. AC-2(1)) are stripped to their base control (AC-2) so that
base control nodes accumulate the full union of MITIGATES edges.

ID scheme:
    SP 800-53 source -> sp800-53r5.AC-3
    ATT&CK target    -> attack-enterprise.T1548

Usage:
    python3 scripts/ingest_sp800_53_attack_mappings.py
    python3 scripts/ingest_sp800_53_attack_mappings.py --dry-run

Reads NEO4J_URI from .env (default: bolt://localhost:7687).
Idempotent: safe to re-run; uses MERGE.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from mitreattack.stix20 import MitreAttackData
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CONTROLS_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "ctid-sp800-53-r5-controls.json"
DEFAULT_MAPPINGS_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "ctid-sp800-53-r5-attack-mappings.json"
DEFAULT_ATTACK_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "enterprise-attack-17.0.json"

_ENHANCEMENT_RE = re.compile(r'\(\d+\)$')


class ETLSettings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_enhancement(external_id: str) -> str:
    """Strip enhancement suffix from SP 800-53 control ID.

    'AC-2(1)' -> 'AC-2'
    'AC-2'    -> 'AC-2'
    """
    return _ENHANCEMENT_RE.sub('', external_id).strip()


def _node_id_sp800_53(external_id: str) -> str:
    return f"sp800-53r5.{external_id.upper()}"


_NIST_SOURCE_NAMES = {"NIST 800-53 Revision 5", "NIST_SP-800-53_rev5"}


def _get_nist_external_id(stix_obj: dict) -> str | None:
    for ref in stix_obj.get("external_references", []):
        if ref.get("source_name") in _NIST_SOURCE_NAMES:
            return ref.get("external_id")
    return None


def _build_control_stix_map(objects: list[dict]) -> dict[str, str]:
    """Build {stix_id: node_id} map from CTID controls STIX bundle objects.

    Only processes course-of-action objects with a NIST_SP-800-53_rev5 external reference.
    Enhancement controls (e.g. AC-2(1)) are stripped to their base control node ID (AC-2).
    """
    result = {}
    for obj in objects:
        if obj.get("type") != "course-of-action":
            continue
        ext_id = _get_nist_external_id(obj)
        if not ext_id:
            continue
        base_id = _strip_enhancement(ext_id)
        result[obj["id"]] = _node_id_sp800_53(base_id)
    return result


def _build_technique_stix_map(data: MitreAttackData) -> dict[str, str]:
    """Build {stix_id: node_id} map for all ATT&CK technique/sub-technique objects."""
    all_techniques = data.get_techniques(
        remove_revoked_deprecated=True,
        include_subtechniques=True,
    )
    result: dict[str, str] = {}
    for tech in all_techniques:
        for ref in tech.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                ext_id = ref.get("external_id")
                if ext_id:
                    result[tech["id"]] = f"attack-enterprise.{ext_id}"
    return result


def _resolve_mitigates_pairs(
    rel_objects: list[dict],
    control_stix_map: dict[str, str],
    technique_stix_map: dict[str, str],
) -> list[tuple[str, str]]:
    """Resolve STIX relationship objects to (sp800-53_node_id, attack_node_id) pairs.

    Only relationship_type='mitigates' with both source and target in their
    respective maps are included. All others are silently skipped.
    """
    pairs = []
    for rel in rel_objects:
        if rel.get("relationship_type") != "mitigates":
            continue
        src = control_stix_map.get(rel.get("source_ref", ""))
        dst = technique_stix_map.get(rel.get("target_ref", ""))
        if src and dst:
            pairs.append((src, dst))
    return pairs


def _write_mitigates_edges(
    driver,
    pairs: list[tuple[str, str]],
    now: str,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Write MITIGATES edges via Bolt using batched UNWIND. Returns (created, errors)."""
    if dry_run:
        print(f"  MITIGATES edges (dry-run): {len(pairs)} pairs would be written")
        return 0, 0

    cypher = (
        "UNWIND $pairs AS pair "
        "MATCH (src:Framework {id: pair[0]}), (dst:Framework {id: pair[1]}) "
        "MERGE (src)-[r:MITIGATES]->(dst) "
        "ON CREATE SET r.created_at = $now "
        "RETURN count(r) AS cnt"
    )
    _BATCH_SIZE = 500
    created = 0
    errors = 0
    with driver.session() as session:
        for i in range(0, len(pairs), _BATCH_SIZE):
            batch = [[src, dst] for src, dst in pairs[i : i + _BATCH_SIZE]]
            try:
                result = session.run(cypher, pairs=batch, now=now)
                row = result.single()
                if row is not None:
                    created += row["cnt"]
            except Exception as exc:  # noqa: BLE001
                print(f"  [ERR] batch {i}-{i + len(batch)}: {exc}", file=sys.stderr)
                errors += len(batch)
    print(f"  MITIGATES edges: {created} created, {errors} errors (from {len(pairs)} pairs)")
    return created, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--controls-file", default=None)
    parser.add_argument("--mappings-file", default=None)
    parser.add_argument("--stix-file", default=None, help="Path to enterprise-attack STIX bundle.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = ETLSettings()

    controls_path = Path(args.controls_file) if args.controls_file else DEFAULT_CONTROLS_PATH
    mappings_path = Path(args.mappings_file) if args.mappings_file else DEFAULT_MAPPINGS_PATH
    attack_path = Path(args.stix_file) if args.stix_file else DEFAULT_ATTACK_PATH

    for p in (controls_path, mappings_path, attack_path):
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    print(f"Loading CTID controls: {controls_path.name}")
    controls_bundle = json.loads(controls_path.read_text(encoding="utf-8"))
    controls_objects = controls_bundle.get("objects", [])
    print(f"  {len(controls_objects)} objects in controls bundle")

    print(f"Loading CTID mappings: {mappings_path.name}")
    mappings_bundle = json.loads(mappings_path.read_text(encoding="utf-8"))
    rel_objects = mappings_bundle.get("objects", [])
    print(f"  {len(rel_objects)} relationship objects in mappings bundle")

    print(f"Loading ATT&CK STIX bundle: {attack_path.name}")
    attack_data = MitreAttackData(str(attack_path))

    control_stix_map = _build_control_stix_map(controls_objects)
    print(f"  {len(control_stix_map)} SP 800-53 controls mapped (including enhancements -> base)")
    if not control_stix_map:
        print("[ERR] No SP 800-53 controls resolved — check CTID controls file format", file=sys.stderr)
        sys.exit(1)

    technique_stix_map = _build_technique_stix_map(attack_data)
    print(f"  {len(technique_stix_map)} ATT&CK techniques mapped")

    pairs = _resolve_mitigates_pairs(rel_objects, control_stix_map, technique_stix_map)
    print(f"  Resolved {len(pairs)} MITIGATES pairs")

    if args.dry_run:
        print(f"\nDry run: {len(pairs)} MITIGATES edges would be written")
        return

    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=("", ""),
    )
    try:
        now = datetime.now(timezone.utc).isoformat()
        _write_mitigates_edges(driver, pairs, now, dry_run=False)
    finally:
        driver.close()

    print(f"\nDone: {len(pairs)} SP 800-53 -> ATT&CK MITIGATES edges processed")


if __name__ == "__main__":
    main()
