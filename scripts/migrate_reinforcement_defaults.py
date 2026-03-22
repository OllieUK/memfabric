#!/usr/bin/env python3
"""
scripts/migrate_reinforcement_defaults.py

Backfill reinforcement properties on existing Memory nodes and RELATED_TO/LEADS_TO edges.

Idempotent: skips nodes/edges that already have the properties set.

Usage:
    python scripts/migrate_reinforcement_defaults.py [--dry-run]
"""
import argparse
from datetime import datetime, timezone

from memory_service.config import Settings, get_driver


def backfill_nodes(session, now_iso: str, decay_rate: float, dry_run: bool) -> int:
    if dry_run:
        result = session.run(
            "MATCH (m:Memory) WHERE m.strength IS NULL RETURN count(m) AS n"
        )
        return result.single()["n"]

    result = session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NULL
        SET m.strength = m.importance / 5.0,
            m.recall_count = 0,
            m.reinforcement_count = 0,
            m.last_reinforced_at = $now,
            m.decay_rate = $decay_rate
        RETURN count(m) AS n
        """,
        now=now_iso,
        decay_rate=decay_rate,
    )
    return result.single()["n"]


def backfill_edges(session, now_iso: str, edge_decay_rate: float, dry_run: bool) -> int:
    if dry_run:
        result = session.run(
            """
            MATCH ()-[r:RELATED_TO|LEADS_TO]->()
            WHERE r.activation_count IS NULL
            RETURN count(r) AS n
            """
        )
        return result.single()["n"]

    result = session.run(
        """
        MATCH ()-[r:RELATED_TO|LEADS_TO]->()
        WHERE r.activation_count IS NULL
        SET r.activation_count = 0,
            r.last_activated_at = $now,
            r.decay_rate = $edge_decay_rate
        RETURN count(r) AS n
        """,
        now=now_iso,
        edge_decay_rate=edge_decay_rate,
    )
    return result.single()["n"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill reinforcement defaults on Memory nodes and edges")
    parser.add_argument("--dry-run", action="store_true", help="Count only, do not write")
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)
    now_iso = datetime.now(timezone.utc).isoformat()

    with driver.session() as session:
        nodes = backfill_nodes(session, now_iso, settings.memory_decay_rate, args.dry_run)
        edges = backfill_edges(session, now_iso, settings.edge_decay_rate, args.dry_run)

    driver.close()
    verb = "Would update" if args.dry_run else "Updated"
    print(f"[migrate] {verb} {nodes} Memory nodes, {edges} edges")


if __name__ == "__main__":
    main()
