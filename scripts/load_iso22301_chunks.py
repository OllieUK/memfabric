#!/usr/bin/env python3
"""load_iso22301_chunks.py — Load reviewed iso22301_inspection.yaml into the knowledge graph.

Reads the reviewed YAML produced by inspect_iso22301.py and:
  1. Creates/upserts the root Framework node
  2. Creates/upserts all Framework hierarchy nodes with statement_type classification

Usage:
    python3 -m scripts.load_iso22301_chunks [--yaml scripts/iso22301_inspection.yaml]
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


def _classify_statement_type(fw_id: str, body: str | None) -> str | None:
    """Rule-based statement type classification for ISO 22301 clauses."""
    if not body:
        return "structural"

    parts = fw_id.split(".")
    # Clauses 1-3 are reference/definitional
    if len(parts) >= 2:
        clause_num = parts[1]
        if clause_num in ("1", "2"):
            return "reference"
        if clause_num == "3":
            return "definitional"

    text_lower = body.lower().strip()

    # NOTEs are informative
    if text_lower.startswith("note"):
        return "informative"

    # Text containing "shall" or "must" is normative
    if " shall " in text_lower or text_lower.startswith("shall ") or " must " in text_lower or text_lower.startswith("must "):
        return "normative"

    # Text containing "should" is guidance
    if " should " in text_lower or text_lower.startswith("should "):
        return "guidance"

    return None  # unclassified — for human review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yaml", default="scripts/iso22301_inspection.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only — no API calls")
    args = parser.parse_args()

    cfg = LoadSettings()

    with open(args.yaml, encoding="utf-8") as f:
        entries = yaml.safe_load(f)

    clauses = [e for e in entries if e["type"] == "clause"]
    print(f"Loaded {len(entries)} entries: {len(clauses)} clauses")

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    framework_id = "iso-22301-2019"

    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:

        # 1. Root Framework node
        print("\n1. Framework")
        s = _post(client, "/knowledge/frameworks", {
            "id": framework_id,
            "title": "ISO 22301",
            "version": "2019",
            "description": "Business continuity management systems requirements",
            "level": "framework",
        }, "framework")
        print(f"   iso-22301-2019: {s}")

        # 2. Framework hierarchy nodes
        print("\n2. Framework hierarchy nodes")

        ok = err = 0

        def _load_entry(fw_id: str, name: str, body: str | None, parent_id: str | None) -> None:
            nonlocal ok, err
            parts = fw_id.split(".")
            if len(parts) == 2:
                level = "clause"       # Top-level clause: iso-22301-2019.6
            elif len(parts) == 3:
                level = "sub-clause"   # iso-22301-2019.6.1
            else:
                level = "sub-clause"   # Deep sub-clause / statement node

            st = _classify_statement_type(fw_id, body)
            payload: dict = {"id": fw_id, "title": name, "level": level}
            if body:
                payload["body"] = body
            if parent_id:
                payload["parent_id"] = parent_id
            if st:
                payload["statement_type"] = st

            s = _post(client, "/knowledge/frameworks", payload, fw_id)
            if s == "error":
                err += 1
            else:
                ok += 1

        def _load_statements(stmts: list, parent_fw_id: str) -> None:
            """Recursively load normative sub-statement nodes (parent before child)."""
            for s in stmts:
                _load_entry(s["id"], s.get("label", s["id"]), s.get("body"), parent_fw_id)
                children = s.get("statements", [])
                if children:
                    _load_statements(children, s["id"])

        for e in entries:
            fw_id = e["suggested_control_id"]
            parts = fw_id.split(".")

            # Determine parent for top-level entry
            if len(parts) > 2:
                parent_id = ".".join(parts[:-1])
            elif len(parts) == 2:
                parent_id = framework_id
            else:
                parent_id = None

            _load_entry(fw_id, e["heading"], e.get("text") or None, parent_id)

            # Load statement sub-hierarchy (leaf normative obligations)
            stmts = e.get("statements", [])
            if stmts:
                _load_statements(stmts, fw_id)

        print(f"   {ok} upserted, {err} errors")

    print("\nDone.")


if __name__ == "__main__":
    main()
