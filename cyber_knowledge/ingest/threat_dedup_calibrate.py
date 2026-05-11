#!/usr/bin/env python3
"""
scripts/calibrate_threat_dedup.py — Calibrate the threat deduplication distance threshold.

Fetches all Threat node embeddings via direct Bolt, computes the full pairwise
distance matrix, classifies pairs by ATT&CK tag overlap, prints histograms,
and auto-recommends a threshold from the p90/p10 gap.

Usage:
    python scripts/calibrate_threat_dedup.py --histogram [--json]
    python scripts/calibrate_threat_dedup.py --histogram --technique-mode dominant-three [--json]
    python scripts/calibrate_threat_dedup.py --histogram --exclude-noise [--json]
    python scripts/calibrate_threat_dedup.py --recommend
    python scripts/calibrate_threat_dedup.py --verify [--json]
    python scripts/calibrate_threat_dedup.py --pair-rerun --threshold 0.28 [--json]
    python scripts/calibrate_threat_dedup.py --sample-for-review 5
"""

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory_service.config import Settings, get_driver
from memory_service import memory_repo

try:
    from create_cross_framework_informs import compute_histogram, cosine_similarity_matrix
except ImportError:
    from cyber_knowledge.ingest.cross_framework_informs import compute_histogram, cosine_similarity_matrix


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class RecommendResult:
    threshold: Optional[float]
    status: Literal["clean_gap", "no_gap_manual_required", "clamped"]
    clamped: bool
    warning: Optional[str]
    within_p90: float
    between_p10: float


# ---------------------------------------------------------------------------
# Bolt fetch helpers
# ---------------------------------------------------------------------------

def _fetch_all_threats(session) -> list[dict]:
    result = session.run(
        """
        MATCH (t:Threat)
        WHERE t.embedding IS NOT NULL
        RETURN t.id AS id, t.text AS text, t.tags AS tags,
               t.created_at AS created_at, t.embedding AS embedding
        """
    )
    rows = []
    for r in result:
        rows.append({
            "id": r["id"],
            "text": r["text"] or "",
            "tags": list(r["tags"] or []),
            "created_at": r["created_at"] or "",
            "embedding": list(r["embedding"]),
        })
    return rows


def _fetch_report_threats(session, report_ids: list[str]) -> list[dict]:
    result = session.run(
        """
        MATCH (tr:ThreatReport)-[:IDENTIFIES]->(t:Threat)
        WHERE tr.id IN $report_ids AND t.embedding IS NOT NULL
        RETURN DISTINCT t.id AS id, t.text AS text, t.tags AS tags,
                        t.created_at AS created_at, t.embedding AS embedding,
                        tr.id AS report_id
        """,
        report_ids=report_ids,
    )
    rows = []
    for r in result:
        rows.append({
            "id": r["id"],
            "text": r["text"] or "",
            "tags": list(r["tags"] or []),
            "created_at": r["created_at"] or "",
            "embedding": list(r["embedding"]),
            "report_id": r["report_id"],
        })
    return rows


# ---------------------------------------------------------------------------
# OCR noise heuristic
# ---------------------------------------------------------------------------

def _ocr_noise_heuristic(text: str) -> bool:
    if not text:
        return False
    window_has_digits = any(
        sum(c.isdigit() for c in text[i:i+10]) >= 3
        for i in range(max(1, len(text) - 9))
    )
    low_vowel_density = (
        len(text) > 10
        and not re.search(r'[aeiouAEIOU]{2}', text)
    )
    return window_has_digits or low_vowel_density


# ---------------------------------------------------------------------------
# Pure classification function (importable by tests)
# ---------------------------------------------------------------------------

_DEFAULT_DOMINANT_TAGS = frozenset({"T1486", "T1566", "T1110"})


def classify_pairs(
    threats: list[dict],
    mode: str = "tag-overlap",
    dominant_tags: frozenset = _DEFAULT_DOMINANT_TAGS,
) -> tuple[list[float], list[float]]:
    """Classify all upper-triangle pairs into within/between distance lists.

    Pure function — no I/O, no side effects.

    Returns:
        (within_distances, between_distances)
    """
    within, between, _, _ = _classify_pairs_with_indices(threats, mode, dominant_tags)
    return within, between


def _classify_pairs_with_indices(
    threats: list[dict],
    mode: str = "tag-overlap",
    dominant_tags: frozenset = _DEFAULT_DOMINANT_TAGS,
) -> tuple[list[float], list[float], list[tuple], list[tuple]]:
    """Classify all upper-triangle pairs; also returns (i, j, dist, threats) tuples for sampling."""
    n = len(threats)
    if n < 2:
        return [], [], [], []

    embeddings = np.array([t["embedding"] for t in threats], dtype=np.float32)
    sim = cosine_similarity_matrix(embeddings, embeddings)
    dist = 1.0 - sim

    rows, cols = np.triu_indices(n, k=1)
    tag_sets = [set(t["tags"]) for t in threats]  # Precomputed once; each set used O(n) times

    within: list[float] = []
    between: list[float] = []
    within_pairs: list[tuple] = []
    between_pairs: list[tuple] = []

    for i, j in zip(rows, cols):
        i, j = int(i), int(j)
        d = float(dist[i, j])
        tags_i = tag_sets[i]
        tags_j = tag_sets[j]

        if mode == "tag-overlap":
            if not tags_i or not tags_j:
                between.append(d)
                between_pairs.append((i, j, d, threats))
            elif tags_i & tags_j:
                within.append(d)
                within_pairs.append((i, j, d, threats))
            else:
                between.append(d)
                between_pairs.append((i, j, d, threats))

        elif mode == "dominant-three":
            eligible_i = bool(tags_i & dominant_tags)
            eligible_j = bool(tags_j & dominant_tags)
            if not eligible_i or not eligible_j:
                continue  # excluded from both buckets
            if tags_i & tags_j:
                within.append(d)
                within_pairs.append((i, j, d, threats))
            else:
                between.append(d)
                between_pairs.append((i, j, d, threats))

    return within, between, within_pairs, between_pairs


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _summarise(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": 0.0, "median": 0.0, "p10": 0.0,
                "p50": 0.0, "p90": 0.0, "min": 0.0, "max": 0.0}
    arr = np.array(values, dtype=np.float64)
    return {
        "count": int(len(values)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
    }


# ---------------------------------------------------------------------------
# Threshold recommendation
# ---------------------------------------------------------------------------

def _auto_recommend(within: list[float], between: list[float]) -> RecommendResult:
    if not within or not between:
        return RecommendResult(
            threshold=None,
            status="no_gap_manual_required",
            clamped=False,
            warning="insufficient data for recommendation",
            within_p90=0.0,
            between_p10=0.0,
        )

    within_p90 = float(np.percentile(within, 90))
    between_p10 = float(np.percentile(between, 10))

    if within_p90 < between_p10:
        candidate = round((within_p90 + between_p10) / 2, 2)
        clamped = False
        warning = None

        if candidate < 0.18:
            candidate = 0.18
            clamped = True
            warning = "clamped to lower bound 0.18"
        elif candidate > 0.32:
            candidate = 0.32
            clamped = True
            warning = "clamped to upper bound 0.32"

        return RecommendResult(
            threshold=candidate,
            status="clamped" if clamped else "clean_gap",
            clamped=clamped,
            warning=warning,
            within_p90=within_p90,
            between_p10=between_p10,
        )

    return RecommendResult(
        threshold=None,
        status="no_gap_manual_required",
        clamped=False,
        warning=(
            f"no clean gap (within.p90={within_p90:.3f} >= between.p10={between_p10:.3f}, "
            f"delta={within_p90 - between_p10:.3f}); manual decision required"
        ),
        within_p90=within_p90,
        between_p10=between_p10,
    )


# ---------------------------------------------------------------------------
# Histogram bar renderer
# ---------------------------------------------------------------------------

def _render_bars(bins: dict, max_bar_width: int = 40) -> list[str]:
    sorted_bins = sorted(bins.keys())
    max_count = max(bins.values()) if bins else 0
    if max_count == 0:
        return []

    lines = []
    first_seen = False
    for (lo, hi) in sorted_bins:
        count = bins[(lo, hi)]
        if not first_seen and count == 0:
            continue
        first_seen = True
        bar_len = int(round(count / max_count * max_bar_width))
        bar = "\u2588" * bar_len
        lines.append(f"  {lo:.2f}-{hi:.2f}: {bar} {count}")
    return lines


# ---------------------------------------------------------------------------
# Dedup simulation
# ---------------------------------------------------------------------------

def _simulate_pair_rerun(
    threats_subset: list[dict],
    threshold: float,
    baseline: float = 0.15,  # Pre-calibration value; kept as comparison point, not current default
) -> dict:
    # Sort by created_at ascending for consistent ordering
    ordered = sorted(threats_subset, key=lambda t: t.get("created_at") or "")

    def _run_greedy(thr: float) -> tuple[list[dict], list[dict]]:
        seen: list[dict] = []
        merges: list[dict] = []
        for threat in ordered:
            emb = threat["embedding"]
            match_dist = None
            match_canonical = None
            for canonical in seen:
                d = 1.0 - memory_repo.cosine_similarity(emb, canonical["embedding"])
                if d < thr:
                    if match_dist is None or d < match_dist:
                        match_dist = d
                        match_canonical = canonical
            if match_canonical is not None:
                merges.append({
                    "canonical_id": match_canonical["id"],
                    "duplicate_id": threat["id"],
                    "distance": match_dist,
                    "canonical_text": match_canonical["text"][:80],
                    "duplicate_text": threat["text"][:80],
                })
            else:
                seen.append(threat)
        return seen, merges

    canonical_seen, new_merges = _run_greedy(threshold)
    baseline_seen, baseline_merges = _run_greedy(baseline)

    # top_new_merges: pairs that merge at threshold but NOT at baseline
    baseline_dup_ids = {m["duplicate_id"] for m in baseline_merges}
    top_new = [
        m for m in new_merges
        if m["duplicate_id"] not in baseline_dup_ids
        and baseline <= m["distance"] < threshold
    ][:10]

    return {
        "total_threats": len(ordered),
        "canonical_count": len(canonical_seen),
        "merged_count": len(new_merges),
        "baseline_merged_count": len(baseline_merges),
        "top_new_merges": top_new,
    }


# ---------------------------------------------------------------------------
# Sample for review
# ---------------------------------------------------------------------------

def _sample_for_review(
    within_pairs: list[tuple],
    between_pairs: list[tuple],
    n: int,
) -> str:
    rng = random.Random(42)
    sample_w = rng.sample(within_pairs, min(n, len(within_pairs)))
    sample_b = rng.sample(between_pairs, min(n, len(between_pairs)))

    lines = []
    for pair_type, samples in [("WITHIN", sample_w), ("BETWEEN", sample_b)]:
        for (i, j, dist, threats) in samples:
            ti = threats[i]
            tj = threats[j]
            lines.append(f"[{pair_type}] distance={dist:.4f}")
            lines.append(f"  A ({ti['id']}): {ti['text'][:100]}")
            lines.append(f"  B ({tj['id']}): {tj['text'][:100]}")
            lines.append(f"  tags_A={ti['tags']}  tags_B={tj['tags']}")
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(
        description="Calibrate the threat dedup cosine-distance threshold."
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--histogram", action="store_true",
                        help="Print distance histograms for within/between pairs.")
    action.add_argument("--pair-rerun", action="store_true",
                        help="Simulate dedup on a report pair at a given threshold.")
    action.add_argument("--recommend", action="store_true",
                        help="Print recommended threshold (exit 2 if no gap).")
    action.add_argument("--verify", action="store_true",
                        help="Check recommended threshold vs current default (exit 1 if drift >0.03).")
    action.add_argument("--sample-for-review", type=int, metavar="N",
                        help="Print N sample pairs from each category for manual review.")

    parser.add_argument("--bin-width", type=float, default=0.02)
    parser.add_argument("--range", nargs=2, type=float, metavar=("LOW", "HIGH"),
                        default=[0.0, 0.6])
    parser.add_argument("--technique-mode", choices=["tag-overlap", "dominant-three"],
                        default="tag-overlap")
    parser.add_argument("--exclude-noise", action="store_true",
                        help="Filter out OCR-noise threats before analysis.")
    parser.add_argument("--threshold", type=float, default=0.28,
                        help="Threshold to simulate in --pair-rerun.")
    parser.add_argument("--report-ids", default="report-verizon-dbir-2025,report-enisa-etl-2025",
                        help="Comma-separated ThreatReport IDs for --pair-rerun.")
    parser.add_argument("--json", action="store_true",
                        help="Also print a JSON summary block.")

    args = parser.parse_args()
    low, high = args.range

    settings = Settings()
    driver = get_driver(settings)

    try:
        with driver.session() as session:

            # --histogram
            if args.histogram:
                threats = _fetch_all_threats(session)
                if args.exclude_noise:
                    before = len(threats)
                    threats = [t for t in threats if not _ocr_noise_heuristic(t["text"])]
                    print(f"[noise filter] removed {before - len(threats)} threats "
                          f"({before} -> {len(threats)})")

                print(f"\nCorpus: {len(threats)} threats  "
                      f"mode={args.technique_mode}  "
                      f"exclude-noise={args.exclude_noise}")

                within, between = classify_pairs(threats, mode=args.technique_mode)
                ws = _summarise(within)
                bs = _summarise(between)
                rec = _auto_recommend(within, between)

                print(f"\nWithin-attack pairs: {ws['count']}")
                print(f"  p10={ws['p10']:.3f}  p50={ws['p50']:.3f}  "
                      f"p90={ws['p90']:.3f}  mean={ws['mean']:.3f}  "
                      f"min={ws['min']:.3f}  max={ws['max']:.3f}")

                print(f"\nBetween-attack pairs: {bs['count']}")
                print(f"  p10={bs['p10']:.3f}  p50={bs['p50']:.3f}  "
                      f"p90={bs['p90']:.3f}  mean={bs['mean']:.3f}  "
                      f"min={bs['min']:.3f}  max={bs['max']:.3f}")

                print("\n--- Within-attack distance histogram ---")
                within_hist = compute_histogram(within, args.bin_width, low, high)
                for line in _render_bars(within_hist):
                    print(line)

                print("\n--- Between-attack distance histogram ---")
                between_hist = compute_histogram(between, args.bin_width, low, high)
                for line in _render_bars(between_hist):
                    print(line)

                print("\n--- Gap analysis ---")
                print(f"  within.p90  = {rec.within_p90:.4f}")
                print(f"  between.p10 = {rec.between_p10:.4f}")
                if rec.status in ("clean_gap", "clamped"):
                    print(f"  status      = {rec.status}")
                    print(f"  recommended = {rec.threshold}")
                    if rec.warning:
                        print(f"  warning     = {rec.warning}")
                else:
                    print(f"  status      = {rec.status}")
                    print(f"  warning     = {rec.warning}")

                if args.json:
                    payload = {
                        "corpus_size": len(threats),
                        "within_count": ws["count"],
                        "between_count": bs["count"],
                        "within": {"p10": ws["p10"], "p50": ws["p50"], "p90": ws["p90"]},
                        "between": {"p10": bs["p10"], "p50": bs["p50"], "p90": bs["p90"]},
                        "status": rec.status,
                        "recommended_threshold": rec.threshold,
                    }
                    print("\n---JSON_START---")
                    print(json.dumps(payload, indent=2))
                    print("---JSON_END---")

                sys.exit(0)

            # --pair-rerun
            elif args.pair_rerun:
                report_ids = [r.strip() for r in args.report_ids.split(",")]
                threats = _fetch_report_threats(session, report_ids)
                if args.exclude_noise:
                    threats = [t for t in threats if not _ocr_noise_heuristic(t["text"])]

                result = _simulate_pair_rerun(threats, args.threshold, baseline=0.15)

                print(f"\nPair-rerun simulation  reports={report_ids}")
                print(f"  total threats   : {result['total_threats']}")
                print(f"  threshold={args.threshold}  -> canonical={result['canonical_count']}  "
                      f"merged={result['merged_count']}")
                print(f"  baseline=0.15   -> merged={result['baseline_merged_count']}")

                if result["top_new_merges"]:
                    print("\nTop new merges (merge at threshold, not at baseline):")
                    for m in result["top_new_merges"]:
                        print(f"  dist={m['distance']:.4f}  "
                              f"canonical={m['canonical_id']!r}  "
                              f"duplicate={m['duplicate_id']!r}")
                        print(f"    canonical text : {m['canonical_text']}")
                        print(f"    duplicate text : {m['duplicate_text']}")

                if args.json:
                    print("\n---JSON_START---")
                    print(json.dumps(result, indent=2))
                    print("---JSON_END---")

                sys.exit(0)

            # --recommend
            elif args.recommend:
                threats = _fetch_all_threats(session)
                if args.exclude_noise:
                    threats = [t for t in threats if not _ocr_noise_heuristic(t["text"])]
                within, between = classify_pairs(threats, mode=args.technique_mode)
                rec = _auto_recommend(within, between)

                if rec.status == "no_gap_manual_required":
                    print(f"WARNING: {rec.warning}")
                    sys.exit(2)

                print(f"Recommended threshold: {rec.threshold}")
                if rec.warning:
                    print(f"Warning: {rec.warning}")
                sys.exit(0)

            # --verify
            elif args.verify:
                current_default = 0.28  # Calibrated default from WP-138

                threats = _fetch_all_threats(session)
                if args.exclude_noise:
                    threats = [t for t in threats if not _ocr_noise_heuristic(t["text"])]
                within, between = classify_pairs(threats, mode=args.technique_mode)
                rec = _auto_recommend(within, between)

                if rec.threshold is None:
                    fresh = current_default
                    drift = 0.0
                    print(f"No recommendation available ({rec.warning}). Skipping drift check.")
                else:
                    fresh = rec.threshold
                    drift = abs(fresh - current_default)

                print(f"\nVerify threshold drift")
                print(f"  current_default      = {current_default}")
                print(f"  fresh_recommendation = {fresh}")
                print(f"  drift                = {drift:.4f}")

                if args.json:
                    print("\n---JSON_START---")
                    print(json.dumps({
                        "current_default": current_default,
                        "fresh_recommendation": fresh,
                        "drift": round(drift, 4),
                        "status": rec.status,
                    }, indent=2))
                    print("---JSON_END---")

                if drift > 0.03:
                    print(f"DRIFT EXCEEDED: {drift:.4f} > 0.03")
                    sys.exit(1)
                sys.exit(0)

            # --sample-for-review
            elif args.sample_for_review is not None:
                n = args.sample_for_review
                threats = _fetch_all_threats(session)
                if args.exclude_noise:
                    threats = [t for t in threats if not _ocr_noise_heuristic(t["text"])]
                within, between, within_pairs, between_pairs = _classify_pairs_with_indices(
                    threats, mode=args.technique_mode
                )
                output = _sample_for_review(within_pairs, between_pairs, n)
                print(output)
                sys.exit(0)

    finally:
        driver.close()


if __name__ == "__main__":
    main()
