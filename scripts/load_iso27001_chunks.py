#!/usr/bin/env python3
"""load_iso27001_chunks.py — Load reviewed iso27001_inspection.yaml into the knowledge graph.

Reads the reviewed YAML produced by inspect_iso27001.py and:
  1. Creates/upserts the root Framework node
  2. Creates/upserts all Framework hierarchy nodes (clauses + Annex A controls)
     with level, body, and parent_id
  3. Creates a Document node for the PDF source
  4. Creates one Chunk per entry, linked to its Framework node via SUPPORTS

Usage:
    python3 -m scripts.load_iso27001_chunks [--yaml scripts/iso27001_inspection.yaml]
                                             [--dry-run]
"""
from __future__ import annotations

import argparse
import sys

import httpx
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _post(client: httpx.Client, endpoint: str, body: dict, label: str) -> str:
    try:
        r = client.post(endpoint, json=body)
        if r.status_code == 409:
            return "exists"
        r.raise_for_status()
        return "ok"
    except httpx.HTTPStatusError as exc:
        print(f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}", file=sys.stderr)
        return "error"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yaml", default="scripts/iso27001_inspection.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only — no API calls")
    args = parser.parse_args()

    cfg = LoadSettings()

    with open(args.yaml, encoding="utf-8") as f:
        entries = yaml.safe_load(f)

    clauses = [e for e in entries if e["type"] == "clause"]
    annex   = [e for e in entries if e["type"] == "annex_control"]
    print(f"Loaded {len(entries)} entries: {len(clauses)} clauses, {len(annex)} Annex A controls")

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    framework_id = "iso-27001-2022"
    doc_id       = "iso-27001-2022-pdf"

    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:

        # 1. Root Framework node
        print("\n1. Framework")
        s = _post(client, "/knowledge/frameworks", {
            "id": framework_id,
            "name": "ISO/IEC 27001",
            "version": "2022",
            "description": "Information security management systems requirements",
            "level": "framework",
        }, "framework")
        print(f"   iso-27001-2022: {s}")

        # 2. Framework hierarchy nodes
        print("\n2. Framework hierarchy nodes")

        # Annex A top-level and structural group nodes (not in inspection YAML)
        _post(client, "/knowledge/frameworks", {
            "id": "iso-27001-2022.a",
            "name": "Annex A — Information Security Controls",
            "level": "category",
            "parent_id": framework_id,
        }, "iso-27001-2022.a")

        annex_groups = {
            "iso-27001-2022.a.5": ("Organizational Controls", "iso-27001-2022.a"),
            "iso-27001-2022.a.6": ("People Controls",         "iso-27001-2022.a"),
            "iso-27001-2022.a.7": ("Physical Controls",       "iso-27001-2022.a"),
            "iso-27001-2022.a.8": ("Technological Controls",  "iso-27001-2022.a"),
        }
        for gid, (gname, gparent) in annex_groups.items():
            _post(client, "/knowledge/frameworks", {
                "id": gid,
                "name": gname,
                "level": "section",
                "parent_id": gparent,
            }, gid)

        ok = err = 0
        for e in entries:
            fw_id = e["suggested_control_id"]
            parts = fw_id.split(".")
            # Determine level from id structure
            if "a" in parts:
                level = "clause"   # Annex A controls
            elif len(parts) == 2:
                level = "clause"   # Top-level clause: iso-27001-2022.6
            else:
                level = "sub-clause"  # Sub-clause: iso-27001-2022.6.1.2

            payload: dict = {
                "id": fw_id,
                "name": e["heading"],
                "level": level,
            }
            if e.get("text"):
                payload["body"] = e["text"]

            # Parent linkage
            if len(parts) > 2:
                payload["parent_id"] = ".".join(parts[:-1])
            elif len(parts) == 2 and "a" not in parts:
                payload["parent_id"] = framework_id

            s = _post(client, "/knowledge/frameworks", payload, fw_id)
            if s == "error":
                err += 1
            else:
                ok += 1
        print(f"   {ok} upserted, {err} errors")

        # 3. Document
        print("\n3. Document")
        s = _post(client, "/knowledge/documents", {
            "id": doc_id,
            "title": "ISO/IEC 27001:2022",
            "doc_type": "standard",
        }, doc_id)
        print(f"   {doc_id}: {s}")

        # 4. Chunks — one per entry that has text
        print("\n4. Chunks")
        ok = err = skipped = 0
        seq = 0
        for e in entries:
            if not e.get("text"):
                skipped += 1
                continue
            fw_id    = e["suggested_control_id"]
            chunk_id = f"{doc_id}.{e['id']}"
            s = _post(client, "/knowledge/chunks", {
                "id": chunk_id,
                "doc_id": doc_id,
                "text": e["text"],
                "sequence": seq,
            }, chunk_id)
            if s == "error":
                err += 1
            else:
                ok += 1
                seq += 1
                _post(client, "/knowledge/chunk/supports", {
                    "chunk_id": chunk_id,
                    "framework_id": fw_id,
                    "confidence": 1.0,
                    "status": "human-reviewed",
                }, f"supports:{chunk_id}→{fw_id}")
        print(f"   {ok} created, {err} errors, {skipped} skipped (no text)")

    print("\nDone.")


if __name__ == "__main__":
    main()
