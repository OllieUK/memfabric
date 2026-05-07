#!/usr/bin/env python3
"""
scripts/seed_business_attributes.py — Seed Tier-1 BusinessAttribute roots.

Reads data/frameworks/business-attributes.yaml and POSTs each entry to
POST /knowledge/business-attributes.  Active entries are seeded first so that
superseded_by FK references always resolve when deprecated tombstones are
written in the second pass.

Idempotent: re-running updates existing nodes without errors.

Usage:
    python scripts/seed_business_attributes.py
    python scripts/seed_business_attributes.py --dry-run
    python scripts/seed_business_attributes.py --api-url http://localhost:8000
"""

import argparse
import sys
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.script_utils import ApiSettings, get_api_client

_DATA_FILE = _PROJECT_ROOT / "data" / "frameworks" / "business-attributes.yaml"
_ENDPOINT = "/knowledge/business-attributes"


def _load_entries() -> tuple[list[dict], list[dict]]:
    """Return (active_entries, deprecated_entries) from the YAML."""
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8"))
    entries = raw.get("business_attributes", [])
    active = [e for e in entries if e.get("status", "active") == "active"]
    deprecated = [e for e in entries if e.get("status") == "deprecated"]
    return active, deprecated


def _seed_entry(client, entry: dict, dry_run: bool) -> None:
    label = entry["id"]
    if dry_run:
        print(f"  [dry-run] would POST {label} (status={entry.get('status', 'active')})")
        return

    resp = client.post(_ENDPOINT, json=entry)
    if resp.status_code in (200, 201):
        action = "created" if resp.status_code == 201 else "updated"
        print(f"  [ok] {label} — {action}")
    else:
        print(f"  [ERROR] {label} — HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SABSA Tier-1 BusinessAttribute roots")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--api-url", help="Override API base URL")
    args = parser.parse_args()

    settings = ApiSettings()
    if args.api_url:
        settings = ApiSettings(api_base_url=args.api_url)

    active, deprecated = _load_entries()
    print(f"Loaded {len(active)} active + {len(deprecated)} deprecated from {_DATA_FILE.name}")

    with get_api_client(settings) as client:
        print("\nPass 1 — active entries:")
        for entry in active:
            _seed_entry(client, entry, args.dry_run)

        print("\nPass 2 — deprecated tombstones:")
        for entry in deprecated:
            _seed_entry(client, entry, args.dry_run)

    print(f"\nDone. {len(active)} active, {len(deprecated)} deprecated.")


if __name__ == "__main__":
    main()
