#!/usr/bin/env python3
"""scripts/seed_companion_anchors.py

One-time idempotent script: create ABOUT edges from companion identity memories
(in specified strands) to the companion's identity node.

After this script runs, GET /memory/wake-up will include those memories in
companion_anchors because they are reachable via ABOUT → {id: agent_id}.

Usage:
    python3 scripts/seed_companion_anchors.py
    python3 scripts/seed_companion_anchors.py --agent-id mara
    python3 scripts/seed_companion_anchors.py --agent-id mara --strand-ids strand-companion-ai-anchor,strand-companion-protocols-systems
"""
import argparse
import sys

from memory_service.config import Settings, get_driver


def seed_companion_anchors(agent_id: str, strand_ids: list[str]) -> None:
    settings = Settings()
    driver = get_driver(settings)
    try:
        with driver.session() as session:
            # 1. Ensure identity node exists (label-agnostic MERGE)
            session.run("MERGE (n {id: $agent_id})", agent_id=agent_id)
            print(f"Identity node ensured: id={agent_id!r}")

            # 2. Count already-linked memories
            result = session.run(
                "MATCH (m:Memory)-[:ABOUT]->(n {id: $agent_id}) RETURN count(m) AS n",
                agent_id=agent_id,
            )
            existing = result.single()["n"]
            print(f"Already linked: {existing} memories")

            # 3. Find memories in the target strands with no existing ABOUT edge
            result = session.run(
                """
                MATCH (m:Memory)-[:IN_STRAND]->(s:Strand)
                WHERE s.id IN $strand_ids
                  AND (m.status IS NULL OR m.status = 'active')
                OPTIONAL MATCH (m)-[:ABOUT]->(existing {id: $agent_id})
                WITH m, existing
                WHERE existing IS NULL
                RETURN m.id AS id, m.text AS text
                """,
                strand_ids=strand_ids,
                agent_id=agent_id,
            )
            to_link = list(result)
            print(f"Memories to link: {len(to_link)}")

            if not to_link:
                print("Nothing to do.")
                return

            # 4. Create ABOUT edges
            created = 0
            for record in to_link:
                session.run(
                    """
                    MATCH (m:Memory {id: $mem_id})
                    MATCH (n {id: $agent_id})
                    CREATE (m)-[:ABOUT]->(n)
                    """,
                    mem_id=record["id"],
                    agent_id=agent_id,
                )
                preview = record["text"][:60] if record["text"] else "(no text)"
                print(f"  Linked {record['id'][:8]}… — {preview}")
                created += 1

            print(f"\nDone. Created {created} ABOUT edge(s).")
    finally:
        driver.close()


def main() -> int:
    settings = Settings()
    parser = argparse.ArgumentParser(
        description="Seed ABOUT edges from companion identity memories to identity node.",
    )
    parser.add_argument(
        "--agent-id",
        default=settings.agent_id,
        help=f"Identity node id (default: settings.agent_id = {settings.agent_id!r})",
    )
    parser.add_argument(
        "--strand-ids",
        default="strand-companion-ai-anchor",
        help="Comma-separated strand IDs to search (default: strand-companion-ai-anchor)",
    )
    args = parser.parse_args()
    strand_ids = [s.strip() for s in args.strand_ids.split(",") if s.strip()]
    try:
        seed_companion_anchors(args.agent_id, strand_ids)
        return 0
    except Exception as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
