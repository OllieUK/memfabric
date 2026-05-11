"""tests/test_cti_extractor.py — Unit tests for WP-108 CTI extraction logic.

Tests the pure extraction functions from scripts/extract_cti_threats.py.
No live stack required.
"""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.cyber


# ---------------------------------------------------------------------------
# Dynamic import of scripts/extract_cti_threats.py
# ---------------------------------------------------------------------------

_spec = importlib.util.spec_from_file_location(
    "extract_cti_threats",
    Path(__file__).parent.parent / "cyber_knowledge" / "ingest" / "cti_extract.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

match_techniques = _mod.match_techniques
extract_severity = _mod.extract_severity
extract_trend = _mod.extract_trend
words_to_lines = _mod.words_to_lines
TECHNIQUE_KEYWORDS = _mod.TECHNIQUE_KEYWORDS
SOURCE_TERMINOLOGY_MAX = _mod.SOURCE_TERMINOLOGY_MAX


# ---------------------------------------------------------------------------
# match_techniques
# ---------------------------------------------------------------------------


def test_match_techniques_ransomware_returns_T1486():
    results = match_techniques("ransomware deployed across the network")
    technique_ids = [tid for _, tid in results]
    assert "T1486" in technique_ids


def test_match_techniques_phishing_attachment_returns_T1566_001():
    results = match_techniques("phishing attachment used to deliver malware")
    technique_ids = [tid for _, tid in results]
    assert "T1566.001" in technique_ids


def test_match_techniques_no_keywords_returns_empty_list():
    results = match_techniques("no keywords here at all")
    assert results == []


# ---------------------------------------------------------------------------
# extract_severity
# ---------------------------------------------------------------------------


def test_extract_severity_critical_keyword_returns_critical():
    result = extract_severity("critical vulnerability exploited by threat actor")
    assert result == "critical"


def test_extract_severity_widespread_keyword_returns_high():
    result = extract_severity("widespread campaign targeting financial sector")
    assert result == "high"


def test_extract_severity_moderate_keyword_returns_medium():
    result = extract_severity("moderate impact observed in affected systems")
    assert result == "medium"


def test_extract_severity_no_signals_returns_high_default():
    result = extract_severity("threat actor used tools to enumerate systems")
    assert result == "high"


# ---------------------------------------------------------------------------
# extract_trend
# ---------------------------------------------------------------------------


def test_extract_trend_increasing_keyword_returns_increasing():
    result = extract_trend("ransomware attacks increasing across all sectors")
    assert result == "increasing"


def test_extract_trend_declining_keyword_returns_decreasing():
    result = extract_trend("incidents declining year over year in this category")
    assert result == "decreasing"


def test_extract_trend_no_signals_returns_stable_default():
    result = extract_trend("threat actor deployed tools to gain access")
    assert result == "stable"


# ---------------------------------------------------------------------------
# Threat ID format
# ---------------------------------------------------------------------------


def test_threat_id_sha1_produces_8_char_hex_string():
    sentence = "some sentence"
    hex_id = hashlib.sha1(sentence.encode()).hexdigest()[:8]
    assert len(hex_id) == 8
    assert all(c in "0123456789abcdef" for c in hex_id)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_source_terminology_max_equals_200():
    assert SOURCE_TERMINOLOGY_MAX == 200


# ---------------------------------------------------------------------------
# words_to_lines
# ---------------------------------------------------------------------------


def test_words_to_lines_empty_list_returns_empty():
    result = words_to_lines([])
    assert result == []


# ---------------------------------------------------------------------------
# TECHNIQUE_KEYWORDS coverage
# ---------------------------------------------------------------------------


def test_technique_keywords_covers_required_attack_patterns():
    required_patterns = [
        "phishing",
        "ransomware",
        "credential",
        "lateral movement",
        "exfiltration",
        "ddos",
        "supply chain",
    ]
    for pattern in required_patterns:
        assert pattern in TECHNIQUE_KEYWORDS, (
            f"Expected '{pattern}' to be a key in TECHNIQUE_KEYWORDS"
        )
