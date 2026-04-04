#!/usr/bin/env python3
"""
dump_db.py — Dump all Memory nodes and graph edges to a JSON snapshot.

Captured edge types:
  Memory layer:       RELATED_TO, LEADS_TO
  Knowledge layer:    MAPPED_TO, SUPPORTS, HAS_CHUNK, IMPLEMENTS,
                      ADDRESSES, OWNED_BY, APPLIES_IN, OPERATES_IN,
                      ABOUT_CONTROL, CITES_DOC, CONTAINS

Usage:
    python scripts/dump_db.py [--output path/to/snapshot.json]

The output file defaults to: dump_YYYYMMDD_HHMMSS.json in the current directory.
This snapshot is the v1 rollback mechanism before destructive maintenance runs.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from memory_service.config import Settings, get_driver


def dump_db(session, output_path: str) -> dict:
    """Dump Memory nodes and all known edge types to a JSON file.

    Covers both the memory layer (RELATED_TO, LEADS_TO) and the knowledge
    layer (MAPPED_TO, SUPPORTS, HAS_CHUNK, IMPLEMENTS, ADDRESSES,
    OWNED_BY, APPLIES_IN, OPERATES_IN, ABOUT_CONTROL, CITES_DOC, CONTAINS).

    Returns summary dict with node_count and edge_count.
    """
    node_rows = list(session.run(
        "MATCH (m:Memory) RETURN properties(m) AS props"
    ))
    nodes = []
    for r in node_rows:
        props = dict(r["props"])
        # Convert embedding list to plain list (should already be, but ensure serialisable)
        nodes.append(props)

    edge_rows = list(session.run(
        """
        MATCH (src)-[r]->(tgt)
        WHERE type(r) IN [
            'RELATED_TO', 'LEADS_TO',
            'MAPPED_TO', 'SUPPORTS', 'HAS_CHUNK',
            'IMPLEMENTS', 'ADDRESSES', 'OWNED_BY', 'APPLIES_IN',
            'OPERATES_IN', 'ABOUT_CONTROL', 'CITES_DOC', 'CONTAINS'
        ]
        RETURN src.id AS src, tgt.id AS tgt, type(r) AS type,
               properties(r) AS props
        """
    ))
    edges = []
    for r in edge_rows:
        edge = {"src": r["src"], "tgt": r["tgt"], "type": r["type"]}
        edge.update(dict(r["props"]))
        edges.append(edge)

    data = {
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "nodes": nodes,
        "edges": edges,
    }
    Path(output_path).write_text(json.dumps(data, indent=2, default=str))
    return {"node_count": len(nodes), "edge_count": len(edges)}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Dump Memory graph to JSON snapshot")
    parser.add_argument("--output", default=None, help="Output file path")
    args = parser.parse_args()

    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"dump_{ts}.json"

    settings = Settings()
    driver = get_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Cannot connect to Memgraph: {exc}")
        return 1

    try:
        with driver.session() as session:
            summary = dump_db(session, output_path)
    finally:
        driver.close()

    print(f"Dumped {summary['node_count']} nodes, {summary['edge_count']} edges → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
