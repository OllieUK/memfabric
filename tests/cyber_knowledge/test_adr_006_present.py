"""WP-174 unit tests — ADR-006 file presence and content invariants."""

import re
from pathlib import Path

import pytest

from tests.cyber_knowledge.test_schema_init_constants import NEW_LABELS


ADR_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "architecture"
    / "ADR-006-asset-policy-oscal-parameter-model.md"
)


@pytest.fixture(scope="module")
def adr_text() -> str:
    assert ADR_PATH.exists(), f"ADR-006 not found at {ADR_PATH}"
    return ADR_PATH.read_text(encoding="utf-8")


def test_adr_006_file_present():
    assert ADR_PATH.exists(), f"ADR-006 not found at {ADR_PATH}"


def test_adr_006_references_prior_adrs(adr_text: str):
    for prior in ("ADR-001", "ADR-002", "ADR-005"):
        assert prior in adr_text, f"ADR-006 must reference {prior}"


def test_adr_006_decision_has_numbered_list(adr_text: str):
    # Find the Decision section and count numbered list items inside it.
    match = re.search(
        r"##\s*1\.\s*Decision\b(.*?)(?:\n##\s|\Z)",
        adr_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    assert match is not None, "Could not locate '## 1. Decision' section"
    section = match.group(1)
    numbered = re.findall(r"^\s*\d+\.\s+\S", section, flags=re.MULTILINE)
    assert len(numbered) >= 5, (
        f"Decision section must contain >=5 numbered items, found {len(numbered)}"
    )


def test_adr_006_names_every_new_label(adr_text: str):
    for label in NEW_LABELS:
        assert label in adr_text, f"ADR-006 must mention label '{label}'"
