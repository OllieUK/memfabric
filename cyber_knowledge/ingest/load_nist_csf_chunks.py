#!/usr/bin/env python3
"""load_nist_csf_chunks.py — Load reviewed NIST CSF 2.0 YAML into the knowledge graph.

Reads the reviewed YAML produced by the pdf-ingest pipeline and:
  1. Creates/upserts the root Framework node
  2. Creates/upserts all Framework hierarchy nodes with statement_type classification
  3. Creates INFORMS edges for ISO 27001 cross-references via direct Cypher

Usage:
    python3 -m scripts.load_nist_csf_chunks \
        [--yaml scripts/nist_csf_inspection.yaml] \
        [--xrefs scripts/nist_csf_iso27001_xrefs.yaml] \
        [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone

import httpx
import yaml
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Map YAML type → graph level
_LEVEL_MAP: dict[str, str] = {
    "function":               "function",
    "category":               "category",
    "subcategory":            "subcategory",
    "implementation_example": "example",
}


def _post(client: httpx.Client, endpoint: str, body: dict, label: str) -> str:
    try:
        r = client.post(endpoint, json=body)
        if r.status_code == 409:
            return "exists"
        r.raise_for_status()
        return "ok"
    except httpx.HTTPStatusError as exc:
        print(
            f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}",
            file=sys.stderr,
        )
        return "error"


def _classify_statement_type(text: str | None) -> str:
    """CSF outcomes are aspirational — use informative when text present, structural otherwise."""
    return "informative" if text else "structural"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yaml", default="scripts/nist_csf_inspection.yaml")
    parser.add_argument("--xrefs", default="scripts/nist_csf_iso27001_xrefs.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only — no API calls")
    args = parser.parse_args()

    cfg = LoadSettings()

    # --- Load YAML files ---
    with open(args.yaml, encoding="utf-8") as f:
        entries: list[dict] = yaml.safe_load(f)

    with open(args.xrefs, encoding="utf-8") as f:
        xrefs: list[dict] = yaml.safe_load(f)

    type_counts = Counter(e["type"] for e in entries)
    print(f"Loaded {len(entries)} entries from {args.yaml}")
    print(
        f"  Functions: {type_counts['function']}, "
        f"Categories: {type_counts['category']}, "
        f"Subcategories: {type_counts['subcategory']}, "
        f"Implementation examples: {type_counts['implementation_example']}"
    )
    print(f"Loaded {len(xrefs)} cross-reference entries from {args.xrefs}")

    if args.dry_run:
        print("\nDry run — no changes made.")
        return

    root_id = "nist-csf-2.0"

    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:

        # 1. Root Framework node
        print("\n1. Root Framework node")
        s = _post(
            client,
            "/knowledge/frameworks",
            {
                "id": root_id,
                "title": "NIST Cybersecurity Framework",
                "version": "2.0",
                "level": "framework",
                "body": (
                    "The NIST Cybersecurity Framework (CSF) 2.0 provides guidance to industry, "
                    "government agencies, and other organizations to manage cybersecurity risks."
                ),
                "statement_type": "structural",
            },
            root_id,
        )
        print(f"   {root_id}: {s}")

        # 2. Framework hierarchy
        print(f"\n2. Framework hierarchy ({len(entries)} entries)")

        ok = err = 0
        PREVIEW = 3

        for i, e in enumerate(entries):
            fw_id: str = e["id"]
            entry_type: str = e["type"]
            level = _LEVEL_MAP.get(entry_type, "subcategory")
            text: str | None = e.get("text") or None
            heading: str = e.get("heading") or fw_id

            # Functions have no parent_id in the YAML — always attach to root
            parent_id: str | None
            if entry_type == "function":
                parent_id = root_id
            else:
                parent_id = e.get("parent_id") or None

            payload: dict = {
                "id": fw_id,
                "title": heading,
                "level": level,
                "statement_type": _classify_statement_type(text),
            }
            if text:
                payload["body"] = text
            if parent_id:
                payload["parent_id"] = parent_id

            status = _post(client, "/knowledge/frameworks", payload, fw_id)

            if status == "error":
                err += 1
            else:
                ok += 1

            if i < PREVIEW:
                print(f"   {fw_id}: {status}")
            elif i == PREVIEW:
                print("   ...")

        print(f"   Summary: {ok} ok, {err} errors")

        # 3. Cross-reference edges via direct Cypher
        print(f"\n3. Cross-reference edges ({len(xrefs)} entries)")
        print(f"   Connecting to Memgraph at {cfg.memgraph_host}:{cfg.memgraph_port} ...")

        driver = GraphDatabase.driver(
            f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
            auth=("", ""),
        )

        xref_ok = xref_skipped = xref_err = 0
        now = datetime.now(timezone.utc).isoformat()

        cypher = (
            "MATCH (src:Framework {id: $src_id}), (dst:Framework {id: $dst_id}) "
            "MERGE (src)-[r:INFORMS]->(dst) "
            "ON CREATE SET r.source = 'nist-csf-2.0-reference-tool', r.created_at = $now "
            "RETURN type(r) AS rel_type"
        )

        with driver.session() as session:
            for i, xref in enumerate(xrefs):
                src_id: str = xref["source_id"]
                dst_id: str = xref["dest_id"]

                # Verify both endpoints exist before creating edge
                check = session.run(
                    "MATCH (n:Framework {id: $id}) RETURN n.id AS id",
                    id=src_id,
                ).single()
                if not check:
                    if i < PREVIEW:
                        print(f"   {src_id} → {dst_id}: skipped (src not found)")
                    xref_skipped += 1
                    continue

                check = session.run(
                    "MATCH (n:Framework {id: $id}) RETURN n.id AS id",
                    id=dst_id,
                ).single()
                if not check:
                    if i < PREVIEW:
                        print(f"   {src_id} → {dst_id}: skipped (dst not found)")
                    xref_skipped += 1
                    continue

                try:
                    result = session.run(cypher, src_id=src_id, dst_id=dst_id, now=now)
                    row = result.single()
                    status_str = "ok" if row else "no-match"
                    xref_ok += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"   [ERR] {src_id} → {dst_id}: {exc}", file=sys.stderr)
                    xref_err += 1
                    status_str = "error"

                if i < PREVIEW:
                    print(f"   {src_id} → {dst_id}: {status_str}")
                elif i == PREVIEW:
                    print("   ...")

        driver.close()
        print(f"   Summary: {xref_ok} ok, {xref_skipped} skipped (missing nodes), {xref_err} errors")

    print("\nDone.")


if __name__ == "__main__":
    main()
