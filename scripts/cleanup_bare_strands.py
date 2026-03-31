#!/usr/bin/env python3
"""
scripts/cleanup_bare_strands.py — One-off cleanup: remove bare Strand nodes.

Bare Strand nodes have an id but null name/description/category. They were
created by earlier versions of add_memory/patch_memory that used MERGE instead
of MATCH when linking strand_ids.

Usage:
    python scripts/cleanup_bare_strands.py [--dry-run]

Flags:
    --dry-run    Print bare node IDs but do not delete them.
"""

import argparse

from memory_service.config import Settings, get_driver


def find_bare_strands(session) -> list[str]:
    """Find all Strand nodes with null name."""
    result = session.run(
        "MATCH (s:Strand) WHERE s.name IS NULL RETURN s.id AS id"
    )
    return [r["id"] for r in result]


def delete_bare_strands(session) -> None:
    """Delete all Strand nodes with null name."""
    session.run(
        "MATCH (s:Strand) WHERE s.name IS NULL DETACH DELETE s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove bare Strand nodes from Memgraph")
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not delete")
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)

    with driver.session() as session:
        bare_ids = find_bare_strands(session)

    if not bare_ids:
        print("[cleanup] No bare Strand nodes found. Nothing to do.")
        driver.close()
        return

    print(f"[cleanup] Found {len(bare_ids)} bare Strand node(s):")
    for sid in bare_ids:
        print(f"  - {sid}")

    if args.dry_run:
        print("[cleanup] Dry-run: no changes made.")
        driver.close()
        return

    with driver.session() as session:
        delete_bare_strands(session)

    print(f"[cleanup] Deleted {len(bare_ids)} bare Strand node(s).")
    driver.close()


if __name__ == "__main__":
    main()
