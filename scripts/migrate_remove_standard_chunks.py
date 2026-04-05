#!/usr/bin/env python3
"""migrate_remove_standard_chunks.py — Remove Chunk nodes that were created for standard/framework text.

Standard text (ISO 27001 clauses, Annex A controls, etc.) now lives directly on Framework nodes
via the `body` property. Chunk nodes that duplicate this content are redundant and should be
removed to avoid double-indexing and confusion.

This script:
  1. Finds all Chunk nodes where doc_id matches a standard document pattern
  2. Reports the count of chunks and edges to be removed
  3. Deletes the Chunks (and their SUPPORTS / HAS_CHUNK edges) via DETACH DELETE
  4. Optionally deletes the corresponding Document node
  5. Verifies Framework nodes still have body and embedding after cleanup

Usage:
    python scripts/migrate_remove_standard_chunks.py [--doc-id iso-27001-2022-pdf] [--dry-run] [--delete-document]

Flags:
    --doc-id DOC_ID       Document ID whose chunks to remove (default: iso-27001-2022-pdf)
    --dry-run             Count and report only — no deletions
    --delete-document     Also delete the Document node for this doc_id
"""
from __future__ import annotations

import argparse
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict
from neo4j import GraphDatabase


DEFAULT_DOC_ID = "iso-27001-2022-pdf"


class MigrateSettings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def count_chunks(session, doc_id: str) -> int:
    """Return the number of Chunk nodes with the given doc_id."""
    result = session.run(
        "MATCH (c:Chunk {doc_id: $doc_id}) RETURN count(c) AS n",
        doc_id=doc_id,
    )
    record = result.single()
    return record["n"] if record else 0


def count_edges(session, doc_id: str) -> dict[str, int]:
    """Return counts of SUPPORTS and HAS_CHUNK edges attached to these Chunk nodes."""
    supports_result = session.run(
        "MATCH (c:Chunk {doc_id: $doc_id})-[r:SUPPORTS]->() RETURN count(r) AS n",
        doc_id=doc_id,
    )
    has_chunk_result = session.run(
        "MATCH ()-[r:HAS_CHUNK]->(c:Chunk {doc_id: $doc_id}) RETURN count(r) AS n",
        doc_id=doc_id,
    )
    supports_rec = supports_result.single()
    has_chunk_rec = has_chunk_result.single()
    return {
        "SUPPORTS": supports_rec["n"] if supports_rec else 0,
        "HAS_CHUNK": has_chunk_rec["n"] if has_chunk_rec else 0,
    }


def document_exists(session, doc_id: str) -> bool:
    """Check whether a Document node with this id exists."""
    result = session.run(
        "MATCH (d:Document {id: $doc_id}) RETURN count(d) AS n",
        doc_id=doc_id,
    )
    record = result.single()
    return bool(record and record["n"] > 0)


def delete_chunks(session, doc_id: str) -> None:
    """Delete all Chunk nodes (and their edges) for this doc_id.

    NOTE: DETACH DELETE does not support RETURN in Memgraph — count before deleting.
    """
    session.run(
        "MATCH (c:Chunk {doc_id: $doc_id}) DETACH DELETE c",
        doc_id=doc_id,
    )


def delete_document(session, doc_id: str) -> None:
    """Delete the Document node for this doc_id (and its edges)."""
    session.run(
        "MATCH (d:Document {id: $doc_id}) DETACH DELETE d",
        doc_id=doc_id,
    )


def verify_framework_nodes(session) -> tuple[int, int]:
    """Return (total_framework_nodes, nodes_with_body_and_embedding) counts."""
    total_result = session.run("MATCH (f:Framework) RETURN count(f) AS n")
    total_rec = total_result.single()
    total = total_rec["n"] if total_rec else 0

    ok_result = session.run(
        "MATCH (f:Framework) WHERE f.body IS NOT NULL AND f.embedding IS NOT NULL RETURN count(f) AS n"
    )
    ok_rec = ok_result.single()
    ok = ok_rec["n"] if ok_rec else 0

    return total, ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--doc-id",
        default=DEFAULT_DOC_ID,
        metavar="DOC_ID",
        help=f"Document ID whose Chunk nodes to remove (default: {DEFAULT_DOC_ID})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count and report only — no deletions",
    )
    parser.add_argument(
        "--delete-document",
        action="store_true",
        help="Also delete the Document node for this doc_id after removing its chunks",
    )
    args = parser.parse_args()

    settings = MigrateSettings()
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"

    print(f"Connecting to Memgraph at {uri} ...")
    try:
        driver = GraphDatabase.driver(uri, auth=("", ""))
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Could not connect to Memgraph: {exc}", file=sys.stderr)
        return 1

    print(f"Target document: '{args.doc_id}'")
    if args.dry_run:
        print("[DRY RUN] No deletions will be performed.")

    try:
        with driver.session() as session:
            # 1. Count what we're about to remove
            chunk_count = count_chunks(session, args.doc_id)
            edge_counts = count_edges(session, args.doc_id)
            doc_exists = document_exists(session, args.doc_id)

            print(f"\nFound:")
            print(f"  {chunk_count} Chunk node(s) with doc_id='{args.doc_id}'")
            print(f"  {edge_counts['SUPPORTS']} SUPPORTS edge(s)")
            print(f"  {edge_counts['HAS_CHUNK']} HAS_CHUNK edge(s)")
            print(f"  Document node present: {doc_exists}")

            if chunk_count == 0:
                print("\nNothing to delete — no matching Chunk nodes found.")
                if args.delete_document and doc_exists:
                    print(f"\nDocument node '{args.doc_id}' exists.")
                    if not args.dry_run:
                        delete_document(session, args.doc_id)
                        print(f"Deleted Document node '{args.doc_id}'.")
                    else:
                        print("[DRY RUN] Would delete Document node.")
                driver.close()
                return 0

            if args.dry_run:
                print("\n[DRY RUN] No changes made.")
                driver.close()
                return 0

            # 2. Delete the chunks (DETACH DELETE handles edges automatically)
            print(f"\nDeleting {chunk_count} Chunk node(s) and their edges ...")
            delete_chunks(session, args.doc_id)
            print("  Chunks deleted.")

            # 3. Optionally delete the Document node
            if args.delete_document:
                if doc_exists:
                    delete_document(session, args.doc_id)
                    print(f"  Document node '{args.doc_id}' deleted.")
                else:
                    print(f"  Document node '{args.doc_id}' not found — skipping.")

            # 4. Verify Framework nodes are intact
            print("\nVerifying Framework nodes ...")
            total_fw, ok_fw = verify_framework_nodes(session)
            print(f"  Total Framework nodes: {total_fw}")
            print(f"  Framework nodes with body + embedding: {ok_fw}")
            if ok_fw < total_fw:
                print(
                    f"  [WARN] {total_fw - ok_fw} Framework node(s) have no body or embedding "
                    f"— this may be expected for structural nodes (e.g. category/section)."
                )

        print("\nMigration complete.")

    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}", file=sys.stderr)
        driver.close()
        return 1

    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
