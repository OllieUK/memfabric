#!/usr/bin/env python3
"""
scripts/seed_sabsa_cells.py — Seed SABSA 2018 matrix cell Framework nodes.

Reads data/frameworks/sabsa-cells.yaml and seeds 66 Framework leaf nodes:
  Pass 1: 36 main-matrix cells  (6 layers × 6 perspectives, cell_role=main-matrix-cell)
  Pass 2: 30 SM-matrix cells    (5 SM layers × 6 perspectives, cell_role=service-mgmt-cell)
  CONTAINS edges are wired automatically via parent_id on each POST.

Safety gate: refuses to seed any cell with description_status=draft-curated.
Run only after Oliver's review pass has set description_status=curated on each row.

Idempotent: HTTP 200 (updated) and HTTP 201 (created) are both accepted.
Exits 1 on any error.

Usage:
    python scripts/seed_sabsa_cells.py
    python scripts/seed_sabsa_cells.py --dry-run
    python scripts/seed_sabsa_cells.py --api-url https://memfabric.carr-it.net
    python scripts/seed_sabsa_cells.py --allow-draft   # bypass draft guard (review use only)
"""

import argparse
import sys
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cyber_knowledge.ingest.script_utils import ApiSettings, get_api_client

_DATA_FILE = _PROJECT_ROOT / "data" / "frameworks" / "sabsa-cells.yaml"
_FRAMEWORKS_ENDPOINT = "/knowledge/frameworks"


def _load_data() -> dict:
    return yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8"))


def _build_payload(cell: dict) -> dict:
    payload = {
        "id": cell["id"],
        "title": cell["title"],
        "level": cell.get("level", "framework"),
        "layer": cell["layer"],
        "perspective": cell["perspective"],
        "matrix": cell["matrix"],
        "cell_role": cell["cell_role"],
        "parent_id": cell["parent_id"],
    }
    if cell.get("body"):
        payload["body"] = cell["body"]
    if cell.get("external_id"):
        payload["external_id"] = cell["external_id"]
    return payload


def _seed_cell(client, cell: dict, dry_run: bool, allow_draft: bool) -> None:
    node_id = cell["id"]
    status = cell.get("description_status", "draft-curated")

    if status == "draft-curated" and not allow_draft:
        print(
            f"  [SKIP] {node_id} — description_status=draft-curated; "
            "run review pass first or use --allow-draft",
            file=sys.stderr,
        )
        sys.exit(1)

    if dry_run:
        print(f"  [dry-run] POST {_FRAMEWORKS_ENDPOINT} {node_id} ({status})")
        return

    payload = _build_payload(cell)
    resp = client.post(_FRAMEWORKS_ENDPOINT, json=payload)
    if resp.status_code in (200, 201):
        action = "created" if resp.status_code == 201 else "updated"
        print(f"  [ok] {node_id} — {action}")
    else:
        print(
            f"  [ERROR] {node_id} — HTTP {resp.status_code}: {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SABSA 2018 matrix cell Framework nodes")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--api-url", help="Override API base URL")
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="Bypass the draft-curated guard (for review tooling only)",
    )
    args = parser.parse_args()

    settings = ApiSettings()
    if args.api_url:
        settings = ApiSettings(api_base_url=args.api_url)

    data = _load_data()
    main_cells = data.get("main_matrix", [])
    sm_cells = data.get("service_management_matrix", [])

    print(
        f"Loaded from {_DATA_FILE.name}: "
        f"{len(main_cells)} main-matrix cells + {len(sm_cells)} SM-matrix cells "
        f"= {len(main_cells) + len(sm_cells)} total"
    )

    if not args.allow_draft:
        draft_ids = [
            c["id"]
            for c in (main_cells + sm_cells)
            if c.get("description_status", "draft-curated") == "draft-curated"
        ]
        if draft_ids:
            print(
                f"\n[ERROR] {len(draft_ids)} cell(s) still have description_status=draft-curated. "
                "Complete Oliver's review pass (set each row to description_status: curated) "
                "before seeding. Use --allow-draft only for review tooling.\n",
                file=sys.stderr,
            )
            sys.exit(1)

    with get_api_client(settings) as client:
        print(f"\nPass 1 — seed {len(main_cells)} main-matrix cells:")
        for cell in main_cells:
            _seed_cell(client, cell, args.dry_run, args.allow_draft)

        print(f"\nPass 2 — seed {len(sm_cells)} SM-matrix cells:")
        for cell in sm_cells:
            _seed_cell(client, cell, args.dry_run, args.allow_draft)

    total = len(main_cells) + len(sm_cells)
    print(f"\nDone. {total} cells seeded ({len(main_cells)} main + {len(sm_cells)} SM).")


if __name__ == "__main__":
    main()
