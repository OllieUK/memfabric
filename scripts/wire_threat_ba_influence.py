#!/usr/bin/env python3
"""
scripts/wire_threat_ba_influence.py — Wire Threat→BA INFLUENCE edges via embedding similarity.

For each active ICT-leaf BusinessAttribute, searches the Threat index by semantic similarity
and creates INFLUENCE {polarity: 'negative', status: 'auto-inferred-embedding'} edges above
the chosen threshold.

Acceptance gate: ≥50 INFLUENCE {polarity: 'negative'} edges written.

Calibration baseline (2026-05-07):
  top-k=50 sample: p90=0.370, p95=0.413, max=0.570
  threshold=0.40 yields ~271 pairs (6.3%) — well above the ≥50 gate.

Usage:
    python scripts/wire_threat_ba_influence.py --dry-run --report
    python scripts/wire_threat_ba_influence.py --report
    python scripts/wire_threat_ba_influence.py --threshold 0.40 --top-k 20
    python scripts/wire_threat_ba_influence.py --api-url https://memfabric.carr-it.net
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.script_utils import fetch_ict_leaves, get_api_client, make_settings, search_threats

_INFLUENCE_ENDPOINT = "/knowledge/influence"

_POLARITY = "negative"
_STATUS = "auto-inferred-embedding"
_ACCEPTANCE_GATE = 50


def _build_rationale(ba_name: str, threat_text: str, similarity: float) -> str:
    snippet = threat_text[:80].rstrip()
    return (
        f"Embedding similarity ({similarity:.3f}) between BA '{ba_name}' "
        f"and Threat '{snippet}...'"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wire Threat→BA INFLUENCE edges via embedding similarity"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    parser.add_argument("--report", action="store_true", help="Print group coverage report")
    parser.add_argument("--api-url", help="Override API base URL")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.40,
        help="Minimum similarity to wire an edge (default: 0.40, calibrated 2026-05-07)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Threat candidates to retrieve per BA query (default: 20)",
    )
    args = parser.parse_args()

    with get_api_client(make_settings(args.api_url)) as client:
        print("Fetching ICT-leaf BusinessAttribute nodes...")
        leaves = fetch_ict_leaves(client)
        print(f"  {len(leaves)} ICT-leaf BAs fetched")

        group_ba_count: dict[str, int] = defaultdict(int)
        group_edges: dict[str, int] = defaultdict(int)
        no_match: list[str] = []
        total_edges = 0
        total_errors = 0

        print(f"\nWiring Threat→BA INFLUENCE edges (threshold={args.threshold}, top_k={args.top_k}):")

        for ba in leaves:
            ba_id = ba["id"]
            ba_name = ba["name"]
            group = ba.get("group", "ungrouped")

            candidates = [
                (h, 1.0 - h["distance"])
                for h in search_threats(client, ba_name, args.top_k)
                if 1.0 - h["distance"] >= args.threshold
            ]

            if not candidates:
                no_match.append(ba_id)
                continue

            group_ba_count[group] += 1

            for hit, similarity in candidates:
                threat_id = hit["id"]
                rationale = _build_rationale(ba_name, hit["text"], similarity)

                if args.dry_run:
                    print(f"  [dry-run] {threat_id} -[INFLUENCE neg]-> {ba_id} (sim={similarity:.3f})")
                    group_edges[group] += 1
                    total_edges += 1
                    continue

                resp = client.post(
                    _INFLUENCE_ENDPOINT,
                    json={
                        "source_id": threat_id,
                        "target_id": ba_id,
                        "polarity": _POLARITY,
                        "rationale": rationale,
                        "status": _STATUS,
                    },
                )
                if resp.status_code in (200, 201):
                    print(f"  [ok] {threat_id} -[INFLUENCE neg]-> {ba_id} (sim={similarity:.3f})")
                    group_edges[group] += 1
                    total_edges += 1
                else:
                    print(
                        f"  [ERROR] {threat_id} → {ba_id}: HTTP {resp.status_code} {resp.text}",
                        file=sys.stderr,
                    )
                    total_errors += 1

        if args.report:
            all_groups = sorted({b.get("group", "ungrouped") for b in leaves})
            covered = [g for g in all_groups if g in group_ba_count]
            coverage_pct = len(covered) / len(all_groups) * 100 if all_groups else 0

            print("\n" + "=" * 60)
            print("COVERAGE REPORT — W100 ICT Group Coverage")
            print("=" * 60)
            for g in all_groups:
                count = group_ba_count.get(g, 0)
                edges = group_edges.get(g, 0)
                status = "✓" if count else "✗ GAP"
                print(f"  {status}  {g:<25} {count:>3} BAs covered, {edges:>4} edges")
            print()
            print(f"Coverage: {len(covered)}/{len(all_groups)} groups = {coverage_pct:.0f}%")

            if no_match:
                print(f"\nBAs with no Threat match above threshold ({len(no_match)}):")
                for ba_id in no_match:
                    print(f"  {ba_id}")

        suffix = " (dry-run, no edges written)" if args.dry_run else ""
        print(f"\nDone. {total_edges} edges{suffix}, {total_errors} errors.")

        gate = "PASS" if total_edges >= _ACCEPTANCE_GATE else "FAIL"
        print(f"Acceptance gate (≥{_ACCEPTANCE_GATE} edges): {gate}")

        if total_errors > 0:
            sys.exit(1)
        if not args.dry_run and total_edges < _ACCEPTANCE_GATE:
            sys.exit(2)


if __name__ == "__main__":
    main()
