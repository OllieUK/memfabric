#!/usr/bin/env python3
"""migrate_wp100_schema.py — Align knowledge-layer node properties with ADR-002 (WP-100).

Renames properties and deletes obsolete edge types introduced before the ADR-002
schema was finalised:

  Framework:   name  → title  (remove description)
  Norm:        name  → title,  text → body  (remove status, effective_date)
  Chunk:       text  → body   (set status = "unmatched" where missing,
                               set heading/section_ref = null where missing)
  Document:    doc_type → policy_level

  Edges deleted:
    (Norm)-[:IMPLEMENTS]→()   — wrong edge type; replaced by MAPS_TO
    (Norm)-[:SOURCED_FROM]→() — wrong edge type; replaced by REFERENCES

Usage:
    python scripts/migrate_wp100_schema.py [--dry-run]

Flags:
    --dry-run    Count and report only — no mutations
"""
from __future__ import annotations

import argparse
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict
from neo4j import GraphDatabase


class MigrateSettings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# Count helpers (always called before any mutation)
# ---------------------------------------------------------------------------


def count_nodes_with_property(session, label: str, prop: str) -> int:
    result = session.run(
        f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL RETURN count(n) AS n"
    )
    rec = result.single()
    return rec["n"] if rec else 0


def count_edges(session, edge_type: str, src_label: str) -> int:
    result = session.run(
        f"MATCH (:{src_label})-[r:{edge_type}]->() RETURN count(r) AS n"
    )
    rec = result.single()
    return rec["n"] if rec else 0


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def rename_property(session, label: str, old_prop: str, new_prop: str) -> None:
    """Copy old_prop to new_prop then remove old_prop on all matching nodes."""
    session.run(
        f"MATCH (n:{label}) WHERE n.{old_prop} IS NOT NULL "
        f"SET n.{new_prop} = n.{old_prop} REMOVE n.{old_prop}"
    )


def remove_property(session, label: str, prop: str) -> None:
    """Remove a property from all nodes of the given label where it exists."""
    session.run(
        f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL REMOVE n.{prop}"
    )


def set_default_property(session, label: str, prop: str, value) -> None:
    """Set prop = value on all nodes of the given label where the property is missing."""
    session.run(
        f"MATCH (n:{label}) WHERE n.{prop} IS NULL SET n.{prop} = $value",
        value=value,
    )


def delete_edges(session, edge_type: str, src_label: str) -> None:
    """Delete all edges of the given type originating from src_label nodes.

    NOTE: DETACH DELETE does not support RETURN in Memgraph — count before deleting.
    """
    session.run(
        f"MATCH (:{src_label})-[r:{edge_type}]->() DELETE r"
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(session) -> list[str]:
    """Return a list of warning strings for any remaining old-schema properties."""
    warnings = []
    checks = [
        ("Framework", "name"),
        ("Framework", "description"),
        ("Norm", "name"),
        ("Norm", "text"),
        ("Norm", "status"),
        ("Norm", "effective_date"),
        ("Chunk", "text"),
        ("Document", "doc_type"),
    ]
    for label, prop in checks:
        n = count_nodes_with_property(session, label, prop)
        if n > 0:
            warnings.append(f"  [WARN] {n} {label} node(s) still have '{prop}' property")

    for edge_type in ("IMPLEMENTS", "SOURCED_FROM"):
        n = count_edges(session, edge_type, "Norm")
        if n > 0:
            warnings.append(f"  [WARN] {n} (Norm)-[:{edge_type}]->() edge(s) still exist")

    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count and report only — no mutations",
    )
    args = parser.parse_args()

    cfg = MigrateSettings()
    uri = f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}"

    print(f"Connecting to Memgraph at {uri} ...")
    try:
        driver = GraphDatabase.driver(uri, auth=("", ""))
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Could not connect to Memgraph: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("[DRY RUN] No mutations will be performed.\n")

    try:
        with driver.session() as session:
            # ------------------------------------------------------------------
            # Inventory — count what needs changing
            # ------------------------------------------------------------------
            print("Inventorying schema mismatches ...")
            counts = {
                "fw_name":         count_nodes_with_property(session, "Framework", "name"),
                "fw_description":  count_nodes_with_property(session, "Framework", "description"),
                "norm_name":       count_nodes_with_property(session, "Norm", "name"),
                "norm_text":       count_nodes_with_property(session, "Norm", "text"),
                "norm_status":     count_nodes_with_property(session, "Norm", "status"),
                "norm_effdate":    count_nodes_with_property(session, "Norm", "effective_date"),
                "chunk_text":      count_nodes_with_property(session, "Chunk", "text"),
                "doc_doctype":     count_nodes_with_property(session, "Document", "doc_type"),
                "norm_implements": count_edges(session, "IMPLEMENTS", "Norm"),
                "norm_sourced":    count_edges(session, "SOURCED_FROM", "Norm"),
            }

            print(f"  Framework nodes with 'name':               {counts['fw_name']}")
            print(f"  Framework nodes with 'description':        {counts['fw_description']}")
            print(f"  Norm nodes with 'name':                    {counts['norm_name']}")
            print(f"  Norm nodes with 'text':                    {counts['norm_text']}")
            print(f"  Norm nodes with 'status':                  {counts['norm_status']}")
            print(f"  Norm nodes with 'effective_date':          {counts['norm_effdate']}")
            print(f"  Chunk nodes with 'text':                   {counts['chunk_text']}")
            print(f"  Document nodes with 'doc_type':            {counts['doc_doctype']}")
            print(f"  (Norm)-[:IMPLEMENTS]->() edges:            {counts['norm_implements']}")
            print(f"  (Norm)-[:SOURCED_FROM]->() edges:          {counts['norm_sourced']}")

            if all(v == 0 for v in counts.values()):
                print("\nNothing to migrate — schema is already aligned with ADR-002.")
                driver.close()
                return 0

            if args.dry_run:
                print("\n[DRY RUN] No changes made.")
                driver.close()
                return 0

            # ------------------------------------------------------------------
            # Framework: name → title, remove description
            # ------------------------------------------------------------------
            if counts["fw_name"] > 0:
                print(f"\nRenaming Framework.name → Framework.title ({counts['fw_name']} nodes) ...")
                rename_property(session, "Framework", "name", "title")
                print("  Done.")

            if counts["fw_description"] > 0:
                print(f"Removing Framework.description ({counts['fw_description']} nodes) ...")
                remove_property(session, "Framework", "description")
                print("  Done.")

            # ------------------------------------------------------------------
            # Norm: name → title, text → body, remove status + effective_date
            # ------------------------------------------------------------------
            if counts["norm_name"] > 0:
                print(f"\nRenaming Norm.name → Norm.title ({counts['norm_name']} nodes) ...")
                rename_property(session, "Norm", "name", "title")
                print("  Done.")

            if counts["norm_text"] > 0:
                print(f"Renaming Norm.text → Norm.body ({counts['norm_text']} nodes) ...")
                rename_property(session, "Norm", "text", "body")
                print("  Done.")

            if counts["norm_status"] > 0:
                print(f"Removing Norm.status ({counts['norm_status']} nodes) ...")
                remove_property(session, "Norm", "status")
                print("  Done.")

            if counts["norm_effdate"] > 0:
                print(f"Removing Norm.effective_date ({counts['norm_effdate']} nodes) ...")
                remove_property(session, "Norm", "effective_date")
                print("  Done.")

            # ------------------------------------------------------------------
            # Chunk: text → body, set status/heading/section_ref defaults
            # ------------------------------------------------------------------
            if counts["chunk_text"] > 0:
                print(f"\nRenaming Chunk.text → Chunk.body ({counts['chunk_text']} nodes) ...")
                rename_property(session, "Chunk", "text", "body")
                print("  Done.")

            print("Setting Chunk.status = 'unmatched' where missing ...")
            set_default_property(session, "Chunk", "status", "unmatched")
            print("  Done.")

            # ------------------------------------------------------------------
            # Document: doc_type → policy_level
            # ------------------------------------------------------------------
            if counts["doc_doctype"] > 0:
                print(f"\nRenaming Document.doc_type → Document.policy_level ({counts['doc_doctype']} nodes) ...")
                rename_property(session, "Document", "doc_type", "policy_level")
                print("  Done.")

            # ------------------------------------------------------------------
            # Delete obsolete Norm edges
            # ------------------------------------------------------------------
            if counts["norm_implements"] > 0:
                print(f"\nDeleting {counts['norm_implements']} (Norm)-[:IMPLEMENTS]->() edges ...")
                delete_edges(session, "IMPLEMENTS", "Norm")
                print("  Done.")

            if counts["norm_sourced"] > 0:
                print(f"Deleting {counts['norm_sourced']} (Norm)-[:SOURCED_FROM]->() edges ...")
                delete_edges(session, "SOURCED_FROM", "Norm")
                print("  Done.")

            # ------------------------------------------------------------------
            # Verification
            # ------------------------------------------------------------------
            print("\nVerifying ...")
            warnings = verify(session)
            if warnings:
                for w in warnings:
                    print(w)
                print("\n[FAIL] Some properties were not fully migrated.")
                driver.close()
                return 1
            else:
                print("  All checks passed — schema is now ADR-002 aligned.")

    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}", file=sys.stderr)
        driver.close()
        return 1

    print("\nMigration complete.")
    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
