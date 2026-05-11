#!/usr/bin/env python3
"""
scripts/calibrate_threat_ba_influence.py — Threat→BA similarity distribution calibration.

For each active ICT-leaf BusinessAttribute, queries the threat search index and collects
similarity scores. Prints a histogram and natural-gap analysis to inform the threshold
for wire_threat_ba_influence.py.

The search direction is BA→Threat (use BA name as query against the threat index).
This samples ~86 × top-k data points without a full Threat×BA cross-product.

Usage:
    python scripts/calibrate_threat_ba_influence.py
    python scripts/calibrate_threat_ba_influence.py --top-k 20 --bins 20
    python scripts/calibrate_threat_ba_influence.py --api-url https://memfabric.carr-it.net
"""

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from cyber_knowledge.ingest.script_utils import fetch_ict_leaves, get_api_client, make_settings, search_threats


def _histogram(scores: list[float], bins: int) -> str:
    if not scores:
        return "(no scores)"
    lo, hi = min(scores), max(scores)
    width = (hi - lo) / bins if hi > lo else 1.0
    buckets = [0] * bins
    for s in scores:
        idx = min(int((s - lo) / width), bins - 1)
        buckets[idx] += 1
    bar_max = max(buckets) if max(buckets) > 0 else 1
    lines = []
    for i, count in enumerate(buckets):
        bucket_lo = lo + i * width
        bar = "#" * int(count / bar_max * 40)
        lines.append(f"  [{bucket_lo:.3f}–{bucket_lo + width:.3f}]  {bar} ({count})")
    return "\n".join(lines)


def _find_gaps(sorted_scores: list[float], min_gap: float = 0.03) -> list[tuple[float, float]]:
    """Return (lower, upper) pairs where consecutive sorted scores have a gap >= min_gap."""
    if len(sorted_scores) < 2:
        return []
    gaps = [(a, b) for a, b in zip(sorted_scores, sorted_scores[1:]) if b - a >= min_gap]
    return sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate Threat→BA similarity distribution for INFLUENCE threshold selection"
    )
    parser.add_argument("--top-k", type=int, default=20, help="Threats to retrieve per BA query (default: 20)")
    parser.add_argument("--bins", type=int, default=20, help="Histogram bin count (default: 20)")
    parser.add_argument("--api-url", help="Override API base URL")
    args = parser.parse_args()

    with get_api_client(make_settings(args.api_url)) as client:
        print("Fetching ICT-leaf BusinessAttribute nodes...")
        leaves = fetch_ict_leaves(client)
        print(f"  {len(leaves)} ICT-leaf BAs fetched")

        all_scores: list[float] = []
        print(f"\nSampling Threat similarity scores (top_k={args.top_k} per BA)...")
        for ba in leaves:
            for h in search_threats(client, ba["name"], args.top_k):
                all_scores.append(1.0 - h["distance"])

        if not all_scores:
            print("No scores collected — check API connectivity.", file=sys.stderr)
            sys.exit(1)

        sorted_scores = sorted(all_scores)
        total = len(all_scores)
        lo, hi = sorted_scores[0], sorted_scores[-1]
        mean = sum(all_scores) / total
        median = sorted_scores[total // 2]

        print(f"\n{'=' * 60}")
        print(f"SIMILARITY DISTRIBUTION  ({total} BA×Threat pairs from {len(leaves)} BAs)")
        print(f"{'=' * 60}")
        print(f"  min:    {lo:.4f}")
        print(f"  max:    {hi:.4f}")
        print(f"  mean:   {mean:.4f}")
        print(f"  median: {median:.4f}")

        print()
        for pct in [50, 60, 65, 70, 75, 80, 85, 90, 95]:
            idx = int(pct / 100 * total)
            print(f"  p{pct:<3}: {sorted_scores[idx]:.4f}")

        print(f"\nHistogram ({args.bins} bins):")
        print(_histogram(all_scores, args.bins))

        print(f"\nTop natural gaps (≥0.03 between consecutive sorted scores):")
        gaps = _find_gaps(sorted_scores, min_gap=0.03)
        if gaps:
            for gap_lo, gap_hi in gaps[:10]:
                midpoint = (gap_lo + gap_hi) / 2
                pct_above = sum(1 for s in sorted_scores if s >= midpoint) / total * 100
                print(
                    f"  gap [{gap_lo:.4f} → {gap_hi:.4f}]  width={gap_hi - gap_lo:.4f}"
                    f"  midpoint={midpoint:.4f}  ({pct_above:.1f}% above midpoint)"
                )
        else:
            print("  No gaps ≥ 0.03 found — distribution is continuous")

        print(f"\nAt common thresholds:")
        for t in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
            above = sum(1 for s in all_scores if s >= t)
            print(f"  threshold={t:.2f}: {above:>5} pairs pass ({above / total * 100:.1f}%)")

        print(f"\n{'=' * 60}")
        print("Recommendation: pick a threshold just above the widest natural gap.")
        print("Use --top-k 50 for a denser sample if the distribution looks sparse.")


if __name__ == "__main__":
    main()
