#!/usr/bin/env python3
"""
scripts/seed_w100_ict_taxonomy.py — Seed W100 ICT Business Attributes taxonomy.

Reads data/frameworks/business-attributes-w100-ict.yaml and seeds:
  Pass 1: 7 ict-group nodes  → POST /knowledge/business-attributes
  Pass 2: ~86 ict-leaf nodes → POST /knowledge/business-attributes
  Pass 3: CONTAINS edges, leaf → group (each leaf belongs to its group)
  Pass 4: CONTAINS edges, group → Tier-1 primitive root (where mapped)

Idempotent: HTTP 200 (updated) and HTTP 201 (created) are both accepted.
Exits 1 on any other status code.

Usage:
    python scripts/seed_w100_ict_taxonomy.py
    python scripts/seed_w100_ict_taxonomy.py --dry-run
    python scripts/seed_w100_ict_taxonomy.py --api-url https://memfabric.carr-it.net
"""

import argparse
import sys
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.script_utils import ApiSettings, get_api_client

_DATA_FILE = _PROJECT_ROOT / "data" / "frameworks" / "business-attributes-w100-ict.yaml"
_BA_ENDPOINT = "/knowledge/business-attributes"
_CONTAINS_ENDPOINT = "/knowledge/contains"

# Group id prefix used in the YAML
_GROUP_ID_PREFIX = "ba-group-"

# Mapping from BA_GROUPS kebab-case value → group node id
_GROUP_NODE_ID = {
    "user": "ba-group-user",
    "management": "ba-group-management",
    "operational": "ba-group-operational",
    "risk-management": "ba-group-risk-management",
    "legal-regulatory": "ba-group-legal-regulatory",
    "technical-strategy": "ba-group-technical-strategy",
    "business-strategy": "ba-group-business-strategy",
}


def _load_data() -> tuple[list[dict], list[dict]]:
    """Return (groups, leaves) from the YAML file."""
    raw = yaml.safe_load(_DATA_FILE.read_text(encoding="utf-8"))
    groups = raw.get("groups", [])
    leaves = raw.get("leaves", [])
    return groups, leaves


def _seed_ba(client, entry: dict, dry_run: bool) -> None:
    label = entry["id"]
    # Strip extra fields not in the API schema (maps_to_primitive_root)
    payload = {
        "id": entry["id"],
        "name": entry["name"],
        "description": entry.get("description"),
        "source_ref": entry.get("source_ref"),
        "status": entry.get("status", "active"),
        "superseded_by": entry.get("superseded_by"),
        "tier": entry["tier"],
        "group": entry.get("group"),
        "t100_stereotype": entry.get("t100_stereotype"),
    }
    if dry_run:
        print(f"  [dry-run] POST {_BA_ENDPOINT} {label}")
        return
    resp = client.post(_BA_ENDPOINT, json=payload)
    if resp.status_code in (200, 201):
        action = "created" if resp.status_code == 201 else "updated"
        print(f"  [ok] {label} — {action}")
    else:
        print(f"  [ERROR] {label} — HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)


def _seed_contains(client, parent_id: str, child_id: str, rationale: str, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] CONTAINS {parent_id} → {child_id}")
        return
    payload = {"parent_id": parent_id, "child_id": child_id, "rationale": rationale}
    resp = client.post(_CONTAINS_ENDPOINT, json=payload)
    if resp.status_code in (200, 201):
        action = "created" if resp.status_code == 201 else "updated"
        print(f"  [ok] CONTAINS {parent_id} → {child_id} — {action}")
    else:
        print(
            f"  [ERROR] CONTAINS {parent_id} → {child_id} — HTTP {resp.status_code}: {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed W100 ICT Business Attributes taxonomy")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--api-url", help="Override API base URL")
    args = parser.parse_args()

    settings = ApiSettings()
    if args.api_url:
        settings = ApiSettings(api_base_url=args.api_url)

    groups, leaves = _load_data()
    print(f"Loaded {len(groups)} groups + {len(leaves)} leaves from {_DATA_FILE.name}")

    with get_api_client(settings) as client:
        print("\nPass 1 — seed 7 ict-group nodes:")
        for group in groups:
            _seed_ba(client, group, args.dry_run)

        print(f"\nPass 2 — seed {len(leaves)} ict-leaf nodes:")
        for leaf in leaves:
            _seed_ba(client, leaf, args.dry_run)

        print(f"\nPass 3 — CONTAINS edges: each leaf → its group:")
        for leaf in leaves:
            group_key = leaf.get("group")
            if not group_key:
                print(f"  [skip] {leaf['id']} has no group", file=sys.stderr)
                continue
            group_node_id = _GROUP_NODE_ID.get(group_key)
            if not group_node_id:
                print(f"  [ERROR] unknown group key '{group_key}' for leaf {leaf['id']}", file=sys.stderr)
                sys.exit(1)
            _seed_contains(
                client,
                parent_id=group_node_id,
                child_id=leaf["id"],
                rationale=f"W100 Figure 4: '{leaf['name']}' is an ICT Business Attribute under the {group_key} group",
                dry_run=args.dry_run,
            )

        print("\nPass 4 — CONTAINS edges: group → Tier-1 primitive root (where mapped):")
        for group in groups:
            root_id = group.get("maps_to_primitive_root")
            if not root_id:
                print(f"  [skip] {group['id']} — no Tier-1 root mapping (correct per curation)")
                continue
            _seed_contains(
                client,
                parent_id=root_id,
                child_id=group["id"],
                rationale=(
                    f"W100 ICT group '{group['name']}' converges on the {root_id} "
                    f"architectural primitive (curated WP-113 Phase 3)"
                ),
                dry_run=args.dry_run,
            )

    group_count = len(groups)
    leaf_count = len(leaves)
    mapped_groups = sum(1 for g in groups if g.get("maps_to_primitive_root"))
    leaf_edges = leaf_count
    root_edges = mapped_groups
    print(
        f"\nDone. {group_count} groups, {leaf_count} leaves, "
        f"{leaf_edges} leaf→group edges, {root_edges} group→root edges."
    )


if __name__ == "__main__":
    main()
