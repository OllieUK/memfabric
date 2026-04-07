#!/usr/bin/env python3
"""scripts/ingest_sp800_53_csf_crosswalk.py — Create INFORMS edges from SP 800-53 Rev 5 controls
to NIST CSF 2.0 subcategories using the NIST OLIR informative reference crosswalk.

These are structured/authoritative edges (source='nist-olir-sp800-53-csf2').

Crosswalk format: flat JSON list of {"csf_id": "GV.OC-01", "sp800_53_id": "PM-11"} records.
Edge direction: sp800-53r5.PM-11 →[INFORMS]→ nist-csf-2.0.GV.OC-01

Usage:
    python3 scripts/ingest_sp800_53_csf_crosswalk.py
    python3 scripts/ingest_sp800_53_csf_crosswalk.py --crosswalk-file data/frameworks/nist-sp800-53-r5-csf2-crosswalk.json
    python3 scripts/ingest_sp800_53_csf_crosswalk.py --dry-run

Reads NEO4J_URI from .env (default: bolt://localhost:7687).
Idempotent: safe to re-run; uses MERGE.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CROSSWALK_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "nist-sp800-53-r5-csf2-crosswalk.json"
_SP800_53_PREFIX = "sp800-53r5."
_EDGE_SOURCE = "nist-olir-sp800-53-csf2"


class ETLSettings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_id_sp800_53(control_id: str) -> str:
    return f"{_SP800_53_PREFIX}{control_id.upper()}"


_CSF_ID_PREFIX = "nist-csf-2.0."


def _build_csf_node_map(driver) -> dict[str, str]:
    """Fetch NIST CSF 2.0 subcategory nodes and return {csf_id_uppercase: node_id} map.

    Node IDs are stored lowercase (e.g. 'nist-csf-2.0.gv.oc-01').
    Crosswalk csf_id values use uppercase dots (e.g. 'GV.OC-01').
    We key the map by uppercasing the suffix so lookups work directly.
    """
    cypher = (
        "MATCH (f:Framework) "
        "WHERE f.id STARTS WITH 'nist-csf-2.0.' AND f.level = 'subcategory' "
        "RETURN f.id AS node_id"
    )
    result = {}
    with driver.session() as session:
        for record in session.run(cypher):
            node_id = record["node_id"]
            if node_id and node_id.startswith(_CSF_ID_PREFIX):
                suffix = node_id[len(_CSF_ID_PREFIX):]
                csf_key = suffix.upper()
                result[csf_key] = node_id
    return result


def _resolve_informs_pairs(
    crosswalk: list[dict],
    csf_node_map: dict[str, str],
) -> list[tuple[str, str]]:
    """Resolve crosswalk records to (sp800-53_node_id, csf_node_id) pairs.

    Each record: {"csf_id": "GV.OC-01", "sp800_53_id": "PM-11"}
    Direction: SP 800-53 control INFORMS NIST CSF 2.0 subcategory.
    Records with unknown CSF IDs are silently skipped.
    """
    pairs = []
    for item in crosswalk:
        ctrl_id = item.get("sp800_53_id", "")
        csf_id = item.get("csf_id", "")
        if not ctrl_id or not csf_id:
            continue
        csf_node = csf_node_map.get(csf_id)
        if csf_node is None:
            continue
        pairs.append((_node_id_sp800_53(ctrl_id), csf_node))
    return pairs


def _write_informs_edges(
    driver,
    pairs: list[tuple[str, str]],
    now: str,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Write INFORMS edges via Bolt using batched UNWIND. Returns (created, errors)."""
    if dry_run:
        print(f"  INFORMS edges (dry-run): {len(pairs)} pairs would be written")
        return 0, 0

    cypher = (
        "UNWIND $pairs AS pair "
        "MATCH (src:Framework {id: pair[0]}), (dst:Framework {id: pair[1]}) "
        "MERGE (src)-[r:INFORMS]->(dst) "
        "ON CREATE SET r.source = $source, r.created_at = $now "
        "RETURN count(r) AS cnt"
    )
    _BATCH_SIZE = 500
    created = 0
    errors = 0
    with driver.session() as session:
        for i in range(0, len(pairs), _BATCH_SIZE):
            batch = [[src, dst] for src, dst in pairs[i : i + _BATCH_SIZE]]
            try:
                result = session.run(cypher, pairs=batch, source=_EDGE_SOURCE, now=now)
                row = result.single()
                if row is not None:
                    created += row["cnt"]
            except Exception as exc:  # noqa: BLE001
                print(f"  [ERR] batch {i}–{i + len(batch)}: {exc}", file=sys.stderr)
                errors += len(batch)
    print(f"  INFORMS edges: {created} created, {errors} errors (from {len(pairs)} pairs)")
    return created, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crosswalk-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = ETLSettings()

    crosswalk_path = Path(args.crosswalk_file) if args.crosswalk_file else DEFAULT_CROSSWALK_PATH
    if not crosswalk_path.exists():
        print(f"Error: crosswalk file not found: {crosswalk_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading NIST OLIR crosswalk: {crosswalk_path.name}")
    raw = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print(f"[ERR] Expected a JSON list, got {type(raw).__name__}", file=sys.stderr)
        sys.exit(1)
    print(f"Crosswalk records: {len(raw)}")

    if args.dry_run:
        print(f"Dry run: {len(raw)} records would be processed")
        return

    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=("", ""),
    )
    try:
        print("Building NIST CSF 2.0 subcategory node map...")
        csf_node_map = _build_csf_node_map(driver)
        print(f"  {len(csf_node_map)} CSF 2.0 subcategory nodes found")

        if not csf_node_map:
            print("[ERR] No CSF 2.0 subcategory nodes found — run NIST CSF ingestion first", file=sys.stderr)
            sys.exit(1)

        pairs = _resolve_informs_pairs(raw, csf_node_map)
        print(f"  Resolved {len(pairs)} INFORMS pairs (skipped unknown CSF IDs)")

        now = datetime.now(timezone.utc).isoformat()
        _write_informs_edges(driver, pairs, now, dry_run=False)
    finally:
        driver.close()

    print(f"\nDone: {len(pairs)} SP 800-53 → NIST CSF 2.0 INFORMS edges processed")


if __name__ == "__main__":
    main()
