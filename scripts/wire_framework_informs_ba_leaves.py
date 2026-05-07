#!/usr/bin/env python3
"""
scripts/wire_framework_informs_ba_leaves.py — Wire Framework → BA-leaf INFORMS edges.

For each active W100 ICT-leaf BusinessAttribute, searches Framework nodes by
semantic similarity and creates INFORMS edges above the chosen threshold.

Primary output is a convergence report (--report): for each W100 ICT group, which
Framework leaves converge on its BA leaves. This surfaces taxonomy gaps: groups with
no Framework matches may indicate missing W100 ICT leaves.

Acceptance gate: ≥80% of W100 ICT groups (≥6 of 7) have ≥1 Framework→BA-leaf
INFORMS edge anchored at one of their leaves (re-derived O2 gate per Decision 6).

Usage:
    python scripts/wire_framework_informs_ba_leaves.py --dry-run --report
    python scripts/wire_framework_informs_ba_leaves.py --report
    python scripts/wire_framework_informs_ba_leaves.py --api-url https://memfabric.carr-it.net
    python scripts/wire_framework_informs_ba_leaves.py --threshold 0.55 --top-k 5
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.script_utils import ApiSettings, get_api_client

_BA_ENDPOINT = "/knowledge/business-attributes"
_SEARCH_ENDPOINT = "/knowledge/search/frameworks"
_INFORMS_BA_ENDPOINT = "/knowledge/informs/ba"

# Framework level filters: only wire from leaf-level nodes
_LEAF_LEVELS = {
    "annex_control", "clause", "subcategory", "category",
    "practice", "objective", "control", "mitigation",
    # SABSA cells are Framework nodes too but should not be wired to BA via embedding
    # (they have explicit coordinate properties); exclude by prefix below
}
_EXCLUDE_PREFIXES = ("sabsa-2018.",)


def _fetch_ict_leaves(client) -> list[dict]:
    """Fetch all active ICT-leaf BusinessAttribute nodes."""
    resp = client.get(f"{_BA_ENDPOINT}?limit=500")
    resp.raise_for_status()
    all_ba = resp.json()
    return [
        b for b in all_ba
        if b.get("tier") == "ict-leaf" and b.get("status") == "active"
    ]


def _search_frameworks(client, query: str, top_k: int) -> list[dict]:
    """Semantic search for Framework nodes matching a query string."""
    resp = client.post(_SEARCH_ENDPOINT, json={"query": query, "limit": top_k})
    resp.raise_for_status()
    return resp.json()


def _is_leaf(hit: dict) -> bool:
    """Return True if the Framework hit is at a leaf level and not a SABSA cell."""
    if hit.get("level") not in _LEAF_LEVELS:
        return False
    for prefix in _EXCLUDE_PREFIXES:
        if hit["id"].startswith(prefix):
            return False
    return True


def _build_rationale(ba_name: str, fw_title: str, similarity: float) -> str:
    return (
        f"Embedding similarity ({similarity:.3f}) between BA '{ba_name}' "
        f"and Framework leaf '{fw_title}'"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wire Framework → BA-leaf INFORMS edges via embedding similarity"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--report", action="store_true", help="Print convergence report by ICT group")
    parser.add_argument("--api-url", help="Override API base URL")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Minimum similarity score to wire an edge (default: 0.55)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Framework candidates to retrieve per BA query (default: 10)",
    )
    args = parser.parse_args()

    settings = ApiSettings()
    if args.api_url:
        settings = ApiSettings(api_base_url=args.api_url)

    with get_api_client(settings) as client:
        print("Fetching ICT-leaf BusinessAttribute nodes...")
        leaves = _fetch_ict_leaves(client)
        print(f"  {len(leaves)} ICT-leaf BAs fetched")

        # Track results per BA and per group for the convergence report
        group_coverage: dict[str, list[str]] = defaultdict(list)  # group → [ba_ids with ≥1 hit]
        group_edges: dict[str, int] = defaultdict(int)            # group → edge count
        taxonomy_gaps: list[str] = []
        total_edges = 0
        total_errors = 0

        print(f"\nSearching Framework leaves (threshold={args.threshold}, top_k={args.top_k}):")

        for ba in leaves:
            ba_id = ba["id"]
            ba_name = ba["name"]
            group = ba.get("group", "ungrouped")

            query = ba_name  # name alone is the semantic anchor
            hits = _search_frameworks(client, query, args.top_k)

            # Convert distance → similarity and filter
            candidates = []
            for h in hits:
                if not _is_leaf(h):
                    continue
                similarity = 1.0 - h["distance"]
                if similarity >= args.threshold:
                    candidates.append((h, similarity))

            if not candidates:
                taxonomy_gaps.append(ba_id)
                print(f"  [no match] {ba_id} — no Framework leaf above threshold {args.threshold}")
                continue

            group_coverage[group].append(ba_id)

            for hit, similarity in candidates:
                fw_id = hit["id"]
                fw_title = hit["title"]
                rationale = _build_rationale(ba_name, fw_title, similarity)

                if args.dry_run:
                    print(f"  [dry-run] {fw_id} -[INFORMS]-> {ba_id} (sim={similarity:.3f})")
                    group_edges[group] += 1
                    total_edges += 1
                    continue

                resp = client.post(
                    _INFORMS_BA_ENDPOINT,
                    json={
                        "framework_id": fw_id,
                        "ba_id": ba_id,
                        "rationale": rationale,
                        "similarity": round(similarity, 4),
                        "source": "embedding-similarity",
                    },
                )
                if resp.status_code in (200, 201):
                    print(f"  [ok] {fw_id} -[INFORMS]-> {ba_id} (sim={similarity:.3f})")
                    group_edges[group] += 1
                    total_edges += 1
                else:
                    print(
                        f"  [ERROR] {fw_id} → {ba_id}: HTTP {resp.status_code} {resp.text}",
                        file=sys.stderr,
                    )
                    total_errors += 1

        # ── Convergence report ────────────────────────────────────────────────
        if args.report:
            all_groups = sorted({b.get("group", "ungrouped") for b in leaves})
            covered = [g for g in all_groups if g in group_coverage]
            coverage_pct = len(covered) / len(all_groups) * 100 if all_groups else 0

            print("\n" + "=" * 60)
            print("CONVERGENCE REPORT — W100 ICT Group Coverage")
            print("=" * 60)
            for g in all_groups:
                ba_ids = group_coverage.get(g, [])
                edges = group_edges.get(g, 0)
                status = "✓" if ba_ids else "✗ GAP"
                print(f"  {status}  {g:<25} {len(ba_ids):>3} BAs covered, {edges:>4} edges")
            print()
            print(f"Coverage: {len(covered)}/{len(all_groups)} groups = {coverage_pct:.0f}%")
            gate = "PASS" if coverage_pct >= 80 else "FAIL"
            print(f"Acceptance gate (≥80%): {gate}")

            if taxonomy_gaps:
                print(f"\nTaxonomy gaps ({len(taxonomy_gaps)} BAs with no Framework match):")
                for ba_id in taxonomy_gaps:
                    print(f"  {ba_id}")

        suffix = " (dry-run, no edges written)" if args.dry_run else ""
        print(f"\nDone. {total_edges} edges{suffix}, {total_errors} errors.")

        if total_errors > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
