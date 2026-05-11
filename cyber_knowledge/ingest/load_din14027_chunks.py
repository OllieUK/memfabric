#!/usr/bin/env python3
"""load_din14027_chunks.py — Load reviewed din14027_inspection.yaml into the knowledge graph.

Reads the reviewed YAML produced by inspect_din14027.py and:
  1. Creates/upserts the root Framework node
  2. Creates/upserts all Framework hierarchy nodes with statement_type classification

Usage:
    python3 -m scripts.load_din14027_chunks [--yaml scripts/din14027_inspection.yaml]
                                             [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata

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


def _classify_statement_type(body: str | None) -> str | None:
    """Rule-based statement type classification for DIN SPEC 14027 clauses.

    German normative keywords:
      - "soll" / "muss" → normative (shall/must)
      - "sollte" → informative (should — recommendation)
    """
    if not body:
        return "structural"

    # NFC-normalize to handle decomposed characters (e.g. u + combining diaeresis → ü)
    text_lower = unicodedata.normalize("NFC", body).lower().strip()

    # "muss" / "müssen" = must → normative
    if re.search(r'(^|\s)m[uü]ssen?\b', text_lower):
        return "normative"

    # "soll" / "sollen" = shall → normative (exclude "sollte" / "sollten")
    if re.search(r'(^|\s)soll(en)?\s', text_lower):
        return "normative"

    # "sollte" / "sollten" = should → informative
    if re.search(r'(^|\s)sollten?\b', text_lower):
        return "informative"

    return None  # unclassified


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yaml", default="scripts/din14027_inspection.yaml")
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

    framework_id = "din-spec-14027-2026"

    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:

        # 1. Root Framework node
        print("\n1. Framework")
        s = _post(client, "/knowledge/frameworks", {
            "id": framework_id,
            "title": "DIN SPEC 14027",
            "version": "2026-04",
            "description": "Corporate Security — Requirements for strengthening the physical resilience of organizations",
            "level": "framework",
        }, "framework")
        print(f"   {framework_id}: {s}")

        # 2. Framework hierarchy nodes
        print("\n2. Framework hierarchy nodes")

        ok = err = 0

        def _load_entry(fw_id: str, name: str, body: str | None, parent_id: str | None) -> None:
            nonlocal ok, err
            parts = fw_id.split(".")
            # fw_id = din-spec-14027-2026.5 → parts has framework prefix + clause parts
            # e.g. "din-spec-14027-2026.5" splits to ["din-spec-14027-2026", "5"] — len 2
            # "din-spec-14027-2026.5.1" → len 3
            if len(parts) == 2:
                level = "clause"
            elif len(parts) == 3:
                level = "sub-clause"
            else:
                level = "sub-clause"

            st = _classify_statement_type(body)
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
            for s in stmts:
                _load_entry(s["id"], s.get("label", s["id"]), s.get("body"), parent_fw_id)
                children = s.get("statements", [])
                if children:
                    _load_statements(children, s["id"])

        for e in clauses:
            fw_id = e["suggested_control_id"]
            parts = fw_id.split(".")

            # Parent: strip last segment; top-level clauses parent to framework root
            if len(parts) > 2:
                parent_id = ".".join(parts[:-1])
            elif len(parts) == 2:
                parent_id = framework_id
            else:
                parent_id = None

            _load_entry(fw_id, e["heading"], e.get("text") or None, parent_id)

            stmts = e.get("statements", [])
            if stmts:
                _load_statements(stmts, fw_id)

        print(f"   {ok} upserted, {err} errors")

    print("\nDone.")


if __name__ == "__main__":
    main()
