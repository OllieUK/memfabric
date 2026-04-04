#!/usr/bin/env python3
"""
restore_db.py — Restore Memory nodes and edges from a JSON snapshot.

Recognised edge types (allowlisted for replay):
  Memory layer:       RELATED_TO, LEADS_TO
  Knowledge layer:    MAPPED_TO, SUPPORTS, HAS_CHUNK, IMPLEMENTS,
                      ADDRESSES, OWNED_BY, APPLIES_IN, OPERATES_IN,
                      ABOUT_CONTROL, CITES_DOC, CONTAINS

Note: knowledge-layer *node* restoration (Standard, Control, Document, etc.)
is handled by the ETL scripts (WP-074), not by this script.  Knowledge-layer
edges present in the dump file are accepted by the allowlist so they are not
silently skipped, but they will only be replayed successfully once the
relevant nodes exist in the graph.

Usage:
    python scripts/restore_db.py --from snapshot.json [--dry-run]

WARNING: This MERGEs nodes and edges — it does NOT clear the DB first.
For a clean restore, drop all Memory nodes manually first:
    MATCH (m:Memory) DETACH DELETE m
Then run this script.
"""
import json
import sys
from pathlib import Path

from memory_service.config import Settings, get_driver

ALLOWED_EDGE_TYPES = frozenset({
    "RELATED_TO", "LEADS_TO",
    "MAPPED_TO", "SUPPORTS", "HAS_CHUNK",
    "IMPLEMENTS", "ADDRESSES", "OWNED_BY", "APPLIES_IN",
    "OPERATES_IN", "ABOUT_CONTROL", "CITES_DOC", "CONTAINS",
})


def restore_db(session, data: dict, dry_run: bool = False) -> dict:
    """Replay dump as MERGE statements. Returns summary dict."""
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if dry_run:
        return {"nodes_merged": len(nodes), "edges_merged": len(edges), "dry_run": True}

    # Restore nodes
    nodes_merged = 0
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        props = {k: v for k, v in node.items() if k != "id" and v is not None}
        if props:
            set_clause = "SET " + ", ".join(f"m.{k} = ${k}" for k in props)
        else:
            set_clause = ""
        session.run(
            f"MERGE (m:Memory {{id: $id}}) {set_clause}",
            id=node_id, **props,
        )
        nodes_merged += 1

    # Restore edges
    edges_merged = 0
    for edge in edges:
        src = edge.get("src")
        tgt = edge.get("tgt")
        etype = edge.get("type", "RELATED_TO")
        if not src or not tgt:
            continue
        # Allowlist guard — prevents injection if dump file is corrupted or edited
        if etype not in ALLOWED_EDGE_TYPES:
            print(f"  [SKIP] Unexpected edge type: {etype!r}")
            continue
        props = {k: v for k, v in edge.items() if k not in ("src", "tgt", "type") and v is not None}
        if props:
            set_clause = "SET " + ", ".join(f"r.{k} = ${k}" for k in props)
        else:
            set_clause = ""
        session.run(
            f"""
            MATCH (a:Memory {{id: $src}}), (b:Memory {{id: $tgt}})
            MERGE (a)-[r:{etype}]->(b)
            {set_clause}
            """,
            src=src, tgt=tgt, **props,
        )
        edges_merged += 1

    return {"nodes_merged": nodes_merged, "edges_merged": edges_merged, "dry_run": False}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Restore Memory graph from JSON dump")
    parser.add_argument("--from", dest="from_file", required=True, help="Path to dump file")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    dump_path = Path(args.from_file)
    if not dump_path.exists():
        print(f"[FAIL] File not found: {dump_path}")
        return 1

    data = json.loads(dump_path.read_text())
    settings = Settings()
    driver = get_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Cannot connect to Memgraph: {exc}")
        return 1

    try:
        with driver.session() as session:
            summary = restore_db(session, data, dry_run=args.dry_run)
    finally:
        driver.close()

    dr = " (dry-run)" if summary["dry_run"] else ""
    print(f"Restored{dr}: {summary['nodes_merged']} nodes, {summary['edges_merged']} edges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
