#!/usr/bin/env python3
"""scripts/ingest_sp800_53.py — Ingest NIST SP 800-53 Rev 5 base controls into the knowledge layer.

Parses NIST OSCAL JSON catalog, creates Framework nodes at level=control,
links them to a SP 800-53 root node with CONTAINS edges via the API's parent_id field.

ID scheme:
    control → sp800-53r5.AC-1, sp800-53r5.SI-7, etc.
    root    → sp800-53-r5

Usage:
    python3 scripts/ingest_sp800_53.py
    python3 scripts/ingest_sp800_53.py --catalog-file data/frameworks/sp800-53-r5-catalog.json
    python3 scripts/ingest_sp800_53.py --dry-run

Reads API_BASE_URL from .env (default: http://localhost:8000).
Idempotent: safe to re-run; all writes use MERGE via the API.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CATALOG_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "sp800-53-r5-catalog.json"
ROOT_ID = "sp800-53-r5"
ROOT_TITLE = "NIST SP 800-53 Rev 5"
DOMAIN = "federal"


class ETLSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _node_id(external_id: str) -> str:
    """Map SP 800-53 control ID to Framework node ID.

    'ac-1'  → 'sp800-53r5.AC-1'
    'AC-1'  → 'sp800-53r5.AC-1'
    """
    return f"sp800-53r5.{external_id.upper()}"


def _extract_statement_prose(control: dict) -> str:
    """Extract statement prose from OSCAL control parts.

    Looks for a part with name='statement'. Returns first 2000 chars.
    Some statements have direct 'prose'; others have sub-parts with prose.
    """
    for part in control.get("parts", []):
        if part.get("name") == "statement":
            prose = part.get("prose", "")
            if prose:
                return prose[:2000]
            sub_parts = part.get("parts", [])
            texts = [sp.get("prose", "") for sp in sub_parts if sp.get("prose")]
            if texts:
                return " ".join(texts)[:2000]
    return ""


def _parse_control(control: dict) -> Optional[dict]:
    """Parse an OSCAL control dict into an ingestion payload.

    Returns None if the control has no id or title.
    """
    ctrl_id = control.get("id", "")
    title = control.get("title", "")
    if not ctrl_id or not title:
        return None

    external_id = ctrl_id.upper()
    return {
        "id": _node_id(external_id),
        "external_id": external_id,
        "title": title,
        "body": _extract_statement_prose(control),
    }


def _extract_base_controls(catalog: dict) -> list[dict]:
    """Extract all base controls from an OSCAL catalog.

    Iterates catalog.groups[*].controls only — does NOT recurse into
    nested controls (enhancements). Silently skips unparseable controls.
    """
    results = []
    for group in catalog.get("catalog", {}).get("groups", []):
        for control in group.get("controls", []):
            parsed = _parse_control(control)
            if parsed is not None:
                results.append(parsed)
    return results


def _upsert(client: httpx.Client, body: dict, label: str, dry_run: bool) -> str:
    """POST /knowledge/frameworks; return 'created', 'already existed', or 'error'."""
    if dry_run:
        return "dry-run"
    try:
        resp = client.post("/knowledge/frameworks", json=body)
        resp.raise_for_status()
        return "created"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            return "already existed"
        print(f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}",
              file=sys.stderr)
        return "error"
    except httpx.HTTPError as exc:
        print(f"  [ERR] {label}: {exc}", file=sys.stderr)
        return "error"


def _ensure_root_node(client: httpx.Client, dry_run: bool) -> None:
    body = {
        "id": ROOT_ID,
        "title": ROOT_TITLE,
        "level": "framework-root",
        "domain": DOMAIN,
    }
    status = _upsert(client, body, "sp800-53-r5 root", dry_run)
    print(f"  Root node ({ROOT_ID}): {status}")


def _ingest_controls(client: httpx.Client, controls: list[dict], dry_run: bool) -> int:
    ok = 0
    for ctrl in controls:
        body = {
            "id": ctrl["id"],
            "title": ctrl["title"],
            "level": "control",
            "external_id": ctrl["external_id"],
            "domain": DOMAIN,
            "parent_id": ROOT_ID,
        }
        if ctrl["body"]:
            body["body"] = ctrl["body"]
        status = _upsert(client, body, ctrl["external_id"], dry_run)
        if status != "error":
            ok += 1
    return ok


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--catalog-file", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = ETLSettings()

    catalog_path = Path(args.catalog_file) if args.catalog_file else DEFAULT_CATALOG_PATH
    if not catalog_path.exists():
        print(f"Error: catalog file not found: {catalog_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading OSCAL catalog: {catalog_path.name}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    controls = _extract_base_controls(catalog)
    print(f"Base controls extracted: {len(controls)}")

    if args.dry_run:
        families: dict[str, int] = {}
        for c in controls:
            fam = c["external_id"].split("-")[0]
            families[fam] = families.get(fam, 0) + 1
        print("\nDry run: no API calls made.")
        for fam in sorted(families):
            print(f"  {fam}: {families[fam]} controls")
        return

    with httpx.Client(base_url=cfg.api_base_url, timeout=120.0) as client:
        _ensure_root_node(client, dry_run=False)
        ok = _ingest_controls(client, controls, dry_run=False)

    print(f"\nDone: {ok}/{len(controls)} SP 800-53 controls upserted")


if __name__ == "__main__":
    main()
