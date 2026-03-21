#!/usr/bin/env python3
"""
scripts/migrate_person_nodes.py

Migrate existing Memory nodes to wire ABOUT edges to Person nodes.

Protocol (JSON lines):
  stdout: {"id": "<uuid>", "fact": "<current fact>"}  — one per node without ABOUT→Person edge
  stdin:  {"memory_id": "<uuid>", "person_ids": ["<person-id>", ...]}
          (empty person_ids list means skip this memory)

The calling process reads stdout lines and responds on stdin. This script then
creates the ABOUT edges and (optionally) the Person nodes.

Usage:
    python scripts/migrate_person_nodes.py [--dry-run] [--batch-size N] [--pre-created-persons]

Flags:
    --dry-run              Print JSON lines to stdout but do not read stdin or write.
    --batch-size N         Number of nodes to fetch per Memgraph query (default 100).
    --pre-created-persons  Assume Person nodes already exist (skip MERGE on Person).
"""

import json
import sys
import argparse

from memory_service.config import Settings, get_driver


def fetch_batch(session, batch_size: int) -> list[dict]:
    # Always fetch from SKIP 0: wired memories leave the WHERE NOT (m)-[:ABOUT]->(:Person) set
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE NOT (m)-[:ABOUT]->(:Person)
        RETURN m.id AS id, m.fact AS fact
        ORDER BY m.created_at
        LIMIT $limit
        """,
        limit=batch_size,
    )
    return [{"id": r["id"], "fact": r["fact"]} for r in result]


def id_to_name(person_id: str) -> str:
    """Convert kebab-case id to display name: 'oliver-james' -> 'Oliver James'."""
    return " ".join(w.capitalize() for w in person_id.split("-"))


def write_about_edge(session, memory_id: str, person_id: str, pre_created: bool = False) -> None:
    """Create ABOUT edge from Memory to Person. Optionally MERGE Person node."""
    if not pre_created:
        session.run(
            "MERGE (p:Person {id: $id}) SET p.name = coalesce(p.name, $name)",
            id=person_id,
            name=id_to_name(person_id),
        )
    session.run(
        """
        MATCH (m:Memory {id: $memory_id})
        MATCH (p:Person {id: $person_id})
        MERGE (m)-[:ABOUT]->(p)
        """,
        memory_id=memory_id,
        person_id=person_id,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Memory nodes to wire ABOUT->Person edges")
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not write")
    parser.add_argument("--batch-size", type=int, default=100, help="Nodes per batch")
    parser.add_argument(
        "--pre-created-persons",
        action="store_true",
        help="Assume Person nodes already exist; skip MERGE on Person",
    )
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)
    total = 0

    while True:
        with driver.session() as session:
            batch = fetch_batch(session, args.batch_size)
        if not batch:
            break

        for node in batch:
            print(json.dumps({"id": node["id"], "fact": node["fact"]}), flush=True)
            total += 1

            if not args.dry_run:
                line = sys.stdin.readline()
                if not line:
                    print("[migrate] stdin closed — stopping", file=sys.stderr)
                    driver.close()
                    sys.exit(1)
                answer = json.loads(line.strip())
                person_ids = answer.get("person_ids") or []
                if person_ids:
                    with driver.session() as session:
                        for person_id in person_ids:
                            write_about_edge(
                                session,
                                node["id"],
                                person_id,
                                pre_created=args.pre_created_persons,
                            )

    driver.close()
    print(f"[migrate] done — processed {total} nodes", file=sys.stderr)


if __name__ == "__main__":
    main()
