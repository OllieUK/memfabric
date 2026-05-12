"""WP-174 unit tests — KNOWLEDGE_CONSTRAINTS contains the new ADR-006 labels."""

from cyber_knowledge.ingest.schema_init import KNOWLEDGE_CONSTRAINTS

NEW_LABELS = frozenset({"Precept", "AssetClass", "Policy", "PolicySection", "Param"})


def test_new_labels_present_in_knowledge_constraints():
    labels = {label for label, _ in KNOWLEDGE_CONSTRAINTS}
    missing = NEW_LABELS - labels
    assert not missing, f"Missing constraint labels: {missing}"


def test_no_pre_existing_constraint_lost():
    # Lower bound: at least 11 pre-WP-174 entries plus the 5 new ones.
    assert len(KNOWLEDGE_CONSTRAINTS) >= 16
