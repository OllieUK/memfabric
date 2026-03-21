#!/usr/bin/env python3
"""
scripts/migrate_fact_so_what.py

Migrate existing Memory nodes from the legacy single `text` field to the
new `fact` / `so_what` split.

Protocol (JSON lines):
  stdout: {"id": "<uuid>", "text": "<current text>"}   — one per node without `fact`
  stdin:  {"id": "<uuid>", "fact": "<fact>", "so_what": "<so_what or null>"}

The calling process reads stdout lines and responds on stdin. This script then
writes the fact/so_what split back to Memgraph and recomputes the embedding.

Usage:
    python scripts/migrate_fact_so_what.py [--dry-run] [--batch-size N]

Flags:
    --dry-run       Print JSON lines to stdout but do not read stdin or write.
    --batch-size N  Number of nodes to fetch per Memgraph query (default 100).
"""

import json
import sys
import argparse

from memory_service.config import Settings, get_driver
from memory_service.embeddings import get_embedding


def fetch_batch(session, batch_size: int) -> list[dict]:
    # Always fetch from SKIP 0: as nodes are migrated (m.fact set), they leave
    # the WHERE m.fact IS NULL result set, so offset-based pagination is incorrect.
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE m.fact IS NULL
        RETURN m.id AS id, m.text AS text
        ORDER BY m.created_at
        LIMIT $limit
        """,
        limit=batch_size,
    )
    return [{"id": r["id"], "text": r["text"]} for r in result]


def write_node(session, node_id: str, fact: str, so_what: str | None) -> None:
    text = fact + (" " + so_what if so_what else "")
    embedding = get_embedding(text)
    session.run(
        """
        MATCH (m:Memory {id: $id})
        SET m.fact = $fact,
            m.so_what = $so_what,
            m.text = $text,
            m.embedding = $embedding
        """,
        id=node_id,
        fact=fact,
        so_what=so_what,
        text=text,
        embedding=embedding,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Memory nodes to fact/so_what split")
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not write")
    parser.add_argument("--batch-size", type=int, default=100, help="Nodes per batch")
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)
    total = 0

    while True:
        with driver.session() as session:
            # Always fetch from SKIP 0: migrated nodes leave the WHERE m.fact IS NULL
            # result set, so offset-based pagination would skip unmigrated nodes.
            batch = fetch_batch(session, args.batch_size)
        if not batch:
            break

        for node in batch:
            print(json.dumps({"id": node["id"], "text": node["text"]}), flush=True)
            total += 1

            if not args.dry_run:
                line = sys.stdin.readline()
                if not line:
                    print("[migrate] stdin closed — stopping", file=sys.stderr)
                    driver.close()
                    sys.exit(1)
                answer = json.loads(line.strip())
                fact = answer["fact"]
                so_what = answer.get("so_what") or None
                with driver.session() as session:
                    write_node(session, node["id"], fact, so_what)

    driver.close()
    print(f"[migrate] done — processed {total} nodes", file=sys.stderr)


if __name__ == "__main__":
    main()
