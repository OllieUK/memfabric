#!/usr/bin/env python3
"""
scripts/seed_sabsa_architecture.py — Seed SABSA 2018 matrix spine Framework nodes.

Reads data/frameworks/sabsa-architecture.yaml and seeds 15 Framework nodes:
  Pass 1: 1 root node           → POST /knowledge/frameworks
  Pass 2: 6 layer children      → POST /knowledge/frameworks
  Pass 3: 6 perspective children → POST /knowledge/frameworks
  Pass 4: 2 matrix children     → POST /knowledge/frameworks
  CONTAINS edges are wired automatically via the parent_id field
  on each child POST (passes 2–4). The /knowledge/frameworks endpoint
  creates CONTAINS edges when parent_id is supplied.

Idempotent: HTTP 200 (updated) and HTTP 201 (created) are both accepted.
Exits 1 on any other status code.

Usage:
    python scripts/seed_sabsa_architecture.py
    python scripts/seed_sabsa_architecture.py --dry-run
    python scripts/seed_sabsa_architecture.py --api-url https://memfabric.carr-it.net
"""

import argparse
import sys
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.script_utils import ApiSettings, get_api_client

_DATA_FILE = _PROJECT_ROOT / "data" / "frameworks" / "sabsa-architecture.yaml"
_FRAMEWORKS_ENDPOINT = "/knowledge/frameworks"


def _load_data() -> dict:
    return yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8"))


def _build_payload(entry: dict, parent_id: str | None = None) -> dict:
    payload = {
        "id": entry["id"],
        "title": entry["title"],
        "level": entry.get("level", "framework"),
    }
    if entry.get("body"):
        payload["body"] = entry["body"]
    if entry.get("external_id"):
        payload["external_id"] = entry["external_id"]
    if entry.get("layer"):
        payload["layer"] = entry["layer"]
    if entry.get("perspective"):
        payload["perspective"] = entry["perspective"]
    if entry.get("matrix"):
        payload["matrix"] = entry["matrix"]
    if parent_id:
        payload["parent_id"] = parent_id
    return payload


def _seed_framework(client, entry: dict, dry_run: bool, parent_id: str | None = None) -> None:
    node_id = entry["id"]
    payload = _build_payload(entry, parent_id=parent_id)
    if dry_run:
        print(f"  [dry-run] POST {_FRAMEWORKS_ENDPOINT} {node_id}")
        return
    resp = client.post(_FRAMEWORKS_ENDPOINT, json=payload)
    if resp.status_code in (200, 201):
        action = "created" if resp.status_code == 201 else "updated"
        print(f"  [ok] {node_id} — {action}")
    else:
        print(f"  [ERROR] {node_id} — HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed SABSA 2018 matrix spine Framework nodes")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--api-url", help="Override API base URL")
    args = parser.parse_args()

    settings = ApiSettings()
    if args.api_url:
        settings = ApiSettings(api_base_url=args.api_url)

    data = _load_data()
    root = data["root"]
    layers = data["layers"]
    perspectives = data["perspectives"]
    matrices = data["matrices"]

    print(
        f"Loaded from {_DATA_FILE.name}: "
        f"1 root + {len(layers)} layers + {len(perspectives)} perspectives + {len(matrices)} matrices"
    )

    with get_api_client(settings) as client:
        root_id = root["id"]

        print("\nPass 1 — seed root node:")
        _seed_framework(client, root, args.dry_run)

        print(f"\nPass 2 — seed {len(layers)} layer nodes (parent_id wires CONTAINS edge):")
        for entry in layers:
            _seed_framework(client, entry, args.dry_run, parent_id=root_id)

        print(f"\nPass 3 — seed {len(perspectives)} perspective nodes (parent_id wires CONTAINS edge):")
        for entry in perspectives:
            _seed_framework(client, entry, args.dry_run, parent_id=root_id)

        print(f"\nPass 4 — seed {len(matrices)} matrix nodes (parent_id wires CONTAINS edge):")
        for entry in matrices:
            _seed_framework(client, entry, args.dry_run, parent_id=root_id)

    total_nodes = 1 + len(layers) + len(perspectives) + len(matrices)
    total_edges = len(layers) + len(perspectives) + len(matrices)
    print(
        f"\nDone. {total_nodes} nodes seeded "
        f"(1 root + {len(layers)} layers + {len(perspectives)} perspectives + {len(matrices)} matrices). "
        f"{total_edges} CONTAINS edges wired via parent_id on each child POST."
    )


if __name__ == "__main__":
    main()
