#!/usr/bin/env python3
"""scripts/ingest_attack_mitigations.py — Ingest MITRE ATT&CK M-Series mitigations into the knowledge layer.

Parses course-of-action STIX objects from the enterprise ATT&CK bundle,
creates Framework nodes at level=mitigation, links them to the ATT&CK root
with CONTAINS edges, and writes MITIGATES edges to targeted techniques
directly via the neo4j driver.

ID scheme:
    mitigation → attack-enterprise.M1017

Usage:
    python3 scripts/ingest_attack_mitigations.py
    python3 scripts/ingest_attack_mitigations.py --stix-file data/frameworks/enterprise-attack-17.0.json
    python3 scripts/ingest_attack_mitigations.py --dry-run

Reads API_BASE_URL, NEO4J_URI from .env (defaults: http://localhost:8000, bolt://localhost:7687).
Idempotent: safe to re-run; all writes use MERGE.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from mitreattack.stix20 import MitreAttackData
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_STIX_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "enterprise-attack-17.0.json"
DOMAIN = "enterprise"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class ETLSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_external_id(stix_obj) -> Optional[str]:
    """Return the ATT&CK external ID (e.g. M1017) from external_references."""
    for ref in stix_obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def _node_id(external_id: str) -> str:
    """Map ATT&CK M-Series external ID to our Framework node ID.

    M1017 → attack-enterprise.M1017
    """
    return f"attack-enterprise.{external_id}"


def _root_id(version: str) -> str:
    """Return root node ID from version string like '17.0'."""
    major = version.split(".")[0]
    return f"attack-enterprise-v{major}"


def _upsert(client: httpx.Client, body: dict, label: str, dry_run: bool) -> str:
    """POST /knowledge/frameworks; return 'created', 'already existed', or 'error'."""
    if dry_run:
        return "dry-run"
    try:
        resp = client.post("/knowledge/frameworks", json=body)
        resp.raise_for_status()
        return "created"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            return "already existed"
        print(f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}",
              file=sys.stderr)
        return "error"
    except httpx.HTTPError as exc:
        print(f"  [ERR] {label}: {exc}", file=sys.stderr)
        return "error"


def _parse_mitigation(obj) -> Optional[dict]:
    """Parse a course-of-action STIX object into an ingestion payload dict.

    Returns None if the object is revoked, deprecated, or has no M-Series external_id.
    """
    if obj.get("revoked"):
        return None
    if obj.get("x_mitre_deprecated"):
        return None

    ext_id = _get_external_id(obj)
    if not ext_id:
        return None

    node_id = _node_id(ext_id)

    desc = obj.get("description", "")
    first_para = desc.split("\n\n")[0].strip() if desc else ""

    return {
        "id": node_id,
        "title": obj["name"],
        "external_id": ext_id,
        "body": first_para[:2000] if first_para else "",
        "stix_id": obj["id"],
    }


def _resolve_mitigates_pairs(
    relationships: list,
    mitigation_stix_to_node: dict[str, str],
    technique_stix_to_node: dict[str, str],
) -> list[tuple[str, str]]:
    """Resolve STIX relationship objects to (src_node_id, dst_node_id) pairs.

    Only relationships where:
      - relationship_type == 'mitigates'
      - source_ref is a known M-Series course-of-action STIX ID
      - target_ref is a known technique STIX ID
    are returned. All others are silently skipped.
    """
    pairs = []
    for rel in relationships:
        if rel.get("relationship_type") != "mitigates":
            continue
        src_stix = rel.get("source_ref", "")
        dst_stix = rel.get("target_ref", "")
        src_node = mitigation_stix_to_node.get(src_stix)
        dst_node = technique_stix_to_node.get(dst_stix)
        if src_node and dst_node:
            pairs.append((src_node, dst_node))
    return pairs


# ---------------------------------------------------------------------------
# Ingestion steps
# ---------------------------------------------------------------------------

def ingest_mitigations(
    client: httpx.Client,
    data: MitreAttackData,
    root_id: str,
    dry_run: bool,
) -> dict[str, str]:
    """Create M-Series Framework nodes. Returns {stix_id: node_id} map."""
    raw_objects = data.get_objects_by_type("course-of-action")
    parsed = []
    for obj in raw_objects:
        result = _parse_mitigation(obj)
        if result is not None:
            parsed.append((obj, result))

    ok = 0
    stix_to_node: dict[str, str] = {}

    for obj, payload in parsed:
        stix_to_node[obj["id"]] = payload["id"]

        body = {
            "id": payload["id"],
            "title": payload["title"],
            "level": "mitigation",
            "external_id": payload["external_id"],
            "domain": DOMAIN,
            "parent_id": root_id,
        }
        if payload["body"]:
            body["body"] = payload["body"]

        status = _upsert(client, body, f"mitigation/{payload['external_id']}", dry_run)
        if status != "error":
            ok += 1

    print(f"  Mitigations: {ok}/{len(parsed)} upserted (from {len(raw_objects)} total course-of-action objects)")
    return stix_to_node


def build_technique_stix_map(data: MitreAttackData) -> dict[str, str]:
    """Build a {stix_id: node_id} map for all technique/sub-technique objects."""
    all_techniques = data.get_techniques(
        remove_revoked_deprecated=True,
        include_subtechniques=True,
    )
    stix_to_node: dict[str, str] = {}
    for tech in all_techniques:
        ext_id = _get_external_id(tech)
        if ext_id:
            stix_to_node[tech["id"]] = _node_id(ext_id)
    return stix_to_node


def write_mitigates_edges(
    driver,
    pairs: list[tuple[str, str]],
    dry_run: bool,
    now: str,
) -> tuple[int, int]:
    """Write MITIGATES edges directly via neo4j driver.

    Returns (created_count, error_count).
    """
    if dry_run:
        print(f"  MITIGATES edges (dry-run): {len(pairs)} pairs would be written")
        return 0, 0

    # Batch writes via UNWIND to avoid N+1 round-trips to Memgraph.
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
                print(f"  [ERR] MITIGATES batch {i}–{i + len(batch)}: {exc}", file=sys.stderr)
                errors += len(batch)

    print(f"  MITIGATES edges: {created} created, {errors} errors (from {len(pairs)} pairs)")
    return created, errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--stix-file",
        default=None,
        help="Path to local STIX 2.1 JSON bundle.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse STIX and report counts without writing to the graph.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = ETLSettings()

    stix_path = Path(args.stix_file) if args.stix_file else DEFAULT_STIX_PATH
    if not stix_path.exists():
        print(f"Error: STIX file not found: {stix_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading STIX bundle: {stix_path.name}")
    data = MitreAttackData(str(stix_path))

    collections = data.get_objects_by_type("x-mitre-collection")
    version = collections[0].get("x_mitre_version", "17.0") if collections else "17.0"
    root = _root_id(version)
    print(f"ATT&CK Enterprise version: {version}  (root id: {root})")

    raw_mitigations = data.get_objects_by_type("course-of-action")
    active_mitigations = [
        obj for obj in raw_mitigations
        if not obj.get("revoked") and not obj.get("x_mitre_deprecated") and _get_external_id(obj)
    ]

    all_relationships = data.get_objects_by_type("relationship")
    mitigates_rels = [r for r in all_relationships if r.get("relationship_type") == "mitigates"]

    print(f"Mitigations to ingest: {len(active_mitigations)} (from {len(raw_mitigations)} total)")
    print(f"MITIGATES relationships found: {len(mitigates_rels)}")

    if args.dry_run:
        print("\nDry run: no API calls made.")
        return

    now = datetime.now(timezone.utc).isoformat()

    print()
    with httpx.Client(base_url=cfg.api_base_url, timeout=60.0) as client:
        mitigation_stix_map = ingest_mitigations(client, data, root, dry_run=False)

    technique_stix_map = build_technique_stix_map(data)

    pairs = _resolve_mitigates_pairs(
        all_relationships,
        mitigation_stix_map,
        technique_stix_map,
    )
    print(f"  Resolved {len(pairs)} MITIGATES pairs (skipped unresolved targets)")

    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
        auth=("", ""),
    )
    try:
        write_mitigates_edges(driver, pairs, dry_run=False, now=now)
    finally:
        driver.close()

    print(f"\nDone: {len(active_mitigations)} M-Series nodes, {len(pairs)} MITIGATES edges")


if __name__ == "__main__":
    main()
