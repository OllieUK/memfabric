"""
tests/test_wp138_threat_dedup_calibration.py

Unit and integration tests for cyber_knowledge/ingest/threat_dedup_calibrate.py (WP-138).

Unit tests: no DB, no subprocess.
Integration tests: require live Memgraph + FastAPI stack.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from cyber_knowledge.ingest.threat_dedup_calibrate import (
    RecommendResult,
    _auto_recommend,
    _ocr_noise_heuristic,
    _simulate_pair_rerun,
    classify_pairs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _t(id_, tags, embedding):
    return {
        "id": id_,
        "text": f"threat {id_}",
        "tags": tags,
        "created_at": "2026-01-01T00:00:00",
        "embedding": embedding,
    }


# ---------------------------------------------------------------------------
# 1. test_classify_pairs — parametrised, 6 cases
# ---------------------------------------------------------------------------

_BASE_THREATS = [
    _t("t1", ["T1486"],          [1.0, 0.0, 0.0, 0.0]),
    _t("t2", ["T1486", "T1566"], [0.9, 0.1, 0.0, 0.0]),
    _t("t3", ["T1110"],          [0.0, 1.0, 0.0, 0.0]),
    _t("t4", [],                 [0.0, 0.0, 1.0, 0.0]),
]

_TAGLESS_3 = [
    _t("a", [], [1.0, 0.0, 0.0, 0.0]),
    _t("b", [], [0.0, 1.0, 0.0, 0.0]),
    _t("c", [], [0.0, 0.0, 1.0, 0.0]),
]

_SAME_TAG_3 = [
    _t("x1", ["T1486"], [1.0, 0.0, 0.0, 0.0]),
    _t("x2", ["T1486"], [0.9, 0.1, 0.0, 0.0]),
    _t("x3", ["T1486"], [0.8, 0.2, 0.0, 0.0]),
]

_DOM3_EXCLUDES = [
    _t("t1", ["T1486"], [1.0, 0.0, 0.0, 0.0]),
    _t("t4", ["T9999"], [0.0, 0.0, 1.0, 0.0]),
]

_UNKNOWN_TAG_2 = [
    _t("u1", ["T9999"], [1.0, 0.0, 0.0, 0.0]),
    _t("u2", ["T9999"], [0.0, 1.0, 0.0, 0.0]),
]

_ZERO_NORM_2 = [
    _t("z1", ["T1486"], [0.0, 0.0, 0.0, 0.0]),
    _t("z2", ["T1486"], [0.0, 0.0, 0.0, 0.0]),
]

@pytest.mark.parametrize("threats,mode,dominant_tags,exp_within,exp_between", [
    pytest.param(
        _BASE_THREATS, "tag-overlap", None, 1, 5,
        id="base",
    ),
    pytest.param(
        [], "tag-overlap", None, 0, 0,
        id="empty",
    ),
    pytest.param(
        _TAGLESS_3, "tag-overlap", None, 0, 3,
        id="all-tagless",
    ),
    pytest.param(
        _SAME_TAG_3, "tag-overlap", None, 3, 0,
        id="all-same-tag",
    ),
    pytest.param(
        _DOM3_EXCLUDES, "dominant-three", frozenset({"T1486", "T1566", "T1110"}), 0, 0,
        id="dominant-three-excludes",
    ),
    pytest.param(
        _BASE_THREATS, "dominant-three", frozenset({"T1486", "T1566", "T1110"}), 1, 2,
        id="dominant-three-base",
    ),
    # Fix 4: no-dominant / tag-overlap — two threats sharing a non-dominant tag still
    # classify as "within" under tag-overlap mode (tag overlap is the only criterion).
    pytest.param(
        _UNKNOWN_TAG_2, "tag-overlap", None, 1, 0,
        id="no-dominant-tag-overlap",
    ),
    # Fix 2: zero-norm embeddings — cosine_similarity_matrix treats zero-norm rows as
    # zero-similarity, so both threats are at distance 1.0 from each other. They share
    # T1486 so they classify as within (1 within pair, 0 between).
    pytest.param(
        _ZERO_NORM_2, "tag-overlap", None, 1, 0,
        id="zero-norm",
    ),
])
def test_classify_pairs(threats, mode, dominant_tags, exp_within, exp_between):
    kwargs = {} if dominant_tags is None else {"dominant_tags": dominant_tags}
    within, between = classify_pairs(threats, mode=mode, **kwargs)
    assert len(within) == exp_within, (
        f"within count mismatch: got {len(within)}, expected {exp_within}"
    )
    assert len(between) == exp_between, (
        f"between count mismatch: got {len(between)}, expected {exp_between}"
    )


# ---------------------------------------------------------------------------
# 2. test_auto_recommend — 3 cases
# ---------------------------------------------------------------------------

def test_auto_recommend():
    # Case 1: clean gap — within p90 ≈ 0.2, between p10 ≈ 0.3 → midpoint 0.25 in range
    r = _auto_recommend([0.1, 0.2], [0.3, 0.4])
    assert r.status == "clean_gap"
    assert r.threshold is not None
    assert 0.18 <= r.threshold <= 0.32
    assert r.clamped is False

    # Case 2: no gap (overlapping distributions)
    r = _auto_recommend([0.1, 0.4], [0.2, 0.5])
    assert r.status == "no_gap_manual_required"
    assert r.threshold is None
    assert r.warning is not None
    assert "manual decision required" in r.warning.lower()

    # Case 3: clamped (gap exists but candidate midpoint < 0.18 lower bound)
    # within p90 ≈ 0.019, between p10 ≈ 0.061 → candidate ≈ 0.040 → clamped to 0.18
    r = _auto_recommend([0.01, 0.02], [0.06, 0.07])
    assert r.status == "clamped"
    assert r.threshold == 0.18
    assert r.clamped is True


# ---------------------------------------------------------------------------
# 3. test_simulate_pair_rerun_order_invariance
# ---------------------------------------------------------------------------

def test_simulate_pair_rerun_order_invariance():
    threats_forward = [
        {
            "id": f"t{i}",
            "text": f"t{i}",
            "tags": [],
            "created_at": f"2026-01-0{i+1}T00:00:00",
            "embedding": list(v),
        }
        for i, v in enumerate([
            [1.0, 0.0, 0.0, 0.0],
            [0.9, 0.1, 0.0, 0.0],   # close to t0
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.5, 0.5, 0.0, 0.0],   # moderately close to t0 and t1
        ])
    ]
    threats_reverse = list(reversed(threats_forward))

    r_fwd = _simulate_pair_rerun(threats_forward, threshold=0.15, baseline=0.05)
    r_rev = _simulate_pair_rerun(threats_reverse, threshold=0.15, baseline=0.05)

    # merge_count must be identical — simulation sorts internally by created_at
    assert r_fwd["merged_count"] == r_rev["merged_count"], (
        f"Order-variant result: fwd={r_fwd['merged_count']}, rev={r_rev['merged_count']}"
    )


# ---------------------------------------------------------------------------
# 4. test_ocr_noise_heuristic — 4 cases
# ---------------------------------------------------------------------------

def test_ocr_noise_heuristic():
    # High digit density in window → True (3+ digits within any 10-char window)
    assert _ocr_noise_heuristic("100 200 300 400 500") is True

    # Normal prose → False
    assert _ocr_noise_heuristic("Ransomware operators target healthcare institutions") is False

    # Empty string → script returns False (early-exit guard: `if not text: return False`)
    assert _ocr_noise_heuristic("") is False

    # High digit density spread across string → True
    assert _ocr_noise_heuristic("abc123def456ghi") is True


# ---------------------------------------------------------------------------
# 5. Integration: histogram runs with semantic assertions
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_histogram_runs_with_semantic_assertions():
    result = subprocess.run(
        [sys.executable, "cyber_knowledge/ingest/threat_dedup_calibrate.py", "--histogram", "--json"],
        capture_output=True, text=True, cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout.lower()
    assert "within" in out
    assert "between" in out
    assert "\u2588" in result.stdout  # histogram bar character

    # Extract JSON block
    start = result.stdout.find("---JSON_START---")
    end = result.stdout.find("---JSON_END---")
    assert start != -1 and end != -1, "JSON block not found in output"
    data = json.loads(result.stdout[start + len("---JSON_START---"):end].strip())

    assert data["corpus_size"] == 364, f"expected 364 threats, got {data['corpus_size']}"
    assert data["within_count"] > 100
    assert data["between_count"] > 1000
    assert 0.0 < data["within"]["p90"] < 1.5
    assert 0.0 < data["between"]["p10"] < 1.5
    assert data["between"]["p10"] > data["within"]["p10"], "between should start higher than within"
    assert data["status"] in {"clean_gap", "no_gap_manual_required", "clamped"}


# ---------------------------------------------------------------------------
# 6. Integration: pair-rerun predicts uplift
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_pair_rerun_predicts_uplift():
    result = subprocess.run(
        [sys.executable, "cyber_knowledge/ingest/threat_dedup_calibrate.py",
         "--pair-rerun", "--threshold", "0.28", "--json"],
        capture_output=True, text=True, cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 0, result.stderr

    start = result.stdout.find("---JSON_START---")
    end = result.stdout.find("---JSON_END---")
    assert start != -1 and end != -1, "JSON block not found in output"
    data = json.loads(result.stdout[start + len("---JSON_START---"):end].strip())

    assert data["merged_count"] > 0
    assert data["canonical_count"] > 0
    assert data["merged_count"] < data["canonical_count"]
    assert data["merged_count"] >= data["baseline_merged_count"]


# ---------------------------------------------------------------------------
# 7. Integration: verify runs cleanly
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_verify_runs_cleanly():
    result = subprocess.run(
        [sys.executable, "cyber_knowledge/ingest/threat_dedup_calibrate.py", "--verify", "--json"],
        capture_output=True, text=True, cwd=_PROJECT_ROOT,
    )
    # Exit 0 if within 0.03 drift, 1 if above
    assert result.returncode in (0, 1)

    start = result.stdout.find("---JSON_START---")
    end = result.stdout.find("---JSON_END---")
    assert start != -1 and end != -1, "JSON block not found in output"
    data = json.loads(result.stdout[start + len("---JSON_START---"):end].strip())

    assert "current_default" in data
    assert "fresh_recommendation" in data
    assert "drift" in data
