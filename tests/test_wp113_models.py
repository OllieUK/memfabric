# tests/test_wp113_models.py — WP-113 Pydantic model unit tests (no DB required)

import pytest
from pydantic import ValidationError

from cyber_knowledge.schemas import (
    BA_STATUSES,
    BA_TIERS,
    BA_GROUPS,
    T100_STEREOTYPES,
    INFLUENCE_POLARITIES,
    INFLUENCE_STATUSES,
    SABSA_PERSPECTIVES,
    SABSA_MATRICES,
    MATRIX_LAYERS_MAIN,
    MATRIX_LAYERS_SERVICE_MGMT,
    CELL_ROLES,
)
from cyber_knowledge.routes import (
    BusinessAttributeCreate,
    BusinessAttributeResponse,
    InfluenceCreate,
    ContainsCreate,
    FrameworkCreate,
)


# ---------------------------------------------------------------------------
# BA_STATUSES frozenset
# ---------------------------------------------------------------------------

def test_ba_statuses_contains_expected():
    assert "active" in BA_STATUSES
    assert "deprecated" in BA_STATUSES
    assert len(BA_STATUSES) == 2


# ---------------------------------------------------------------------------
# BA_TIERS frozenset
# ---------------------------------------------------------------------------

def test_ba_tiers_contains_expected():
    assert "primitive-root" in BA_TIERS
    assert "ict-group" in BA_TIERS
    assert "ict-leaf" in BA_TIERS
    assert len(BA_TIERS) == 3


# ---------------------------------------------------------------------------
# BA_GROUPS frozenset
# ---------------------------------------------------------------------------

def test_ba_groups_contains_expected():
    expected = {
        "management", "user", "operational", "risk-management",
        "technical-strategy", "business-strategy", "legal-regulatory",
    }
    assert expected == BA_GROUPS


# ---------------------------------------------------------------------------
# T100_STEREOTYPES frozenset
# ---------------------------------------------------------------------------

def test_t100_stereotypes_contains_sabsa_attribute():
    assert "sabsa-attribute" in T100_STEREOTYPES


# ---------------------------------------------------------------------------
# BusinessAttributeCreate — valid cases
# ---------------------------------------------------------------------------

def test_ba_create_tier1_root_valid():
    ba = BusinessAttributeCreate(
        id="test-ba-confidentiality",
        name="Confidentiality",
        tier="primitive-root",
    )
    assert ba.tier == "primitive-root"
    assert ba.status == "active"
    assert ba.group is None
    assert ba.t100_stereotype is None


def test_ba_create_ict_leaf_valid():
    ba = BusinessAttributeCreate(
        id="test-ba-ict-leaf",
        name="Accessible",
        tier="ict-leaf",
        group="user",
        t100_stereotype="sabsa-attribute",
        status="active",
    )
    assert ba.tier == "ict-leaf"
    assert ba.group == "user"
    assert ba.t100_stereotype == "sabsa-attribute"


def test_ba_create_ict_group_valid():
    ba = BusinessAttributeCreate(
        id="test-ba-group-management",
        name="Management",
        tier="ict-group",
        group="management",
    )
    assert ba.tier == "ict-group"


def test_ba_create_deprecated_without_superseded_by_passes_model():
    # FK check is at repo layer; model allows deprecated without superseded_by
    ba = BusinessAttributeCreate(
        id="test-ba-auditability",
        name="Auditability",
        tier="primitive-root",
        status="deprecated",
    )
    assert ba.status == "deprecated"
    assert ba.superseded_by is None


def test_ba_create_deprecated_with_superseded_by_valid():
    ba = BusinessAttributeCreate(
        id="test-ba-auditability",
        name="Auditability",
        tier="primitive-root",
        status="deprecated",
        superseded_by="ba-accountability",
    )
    assert ba.superseded_by == "ba-accountability"


# ---------------------------------------------------------------------------
# BusinessAttributeCreate — invalid cases
# ---------------------------------------------------------------------------

def test_ba_create_invalid_tier_raises():
    with pytest.raises(ValidationError) as exc_info:
        BusinessAttributeCreate(
            id="test-ba-bad",
            name="Bad",
            tier="not-a-real-tier",
        )
    assert "tier" in str(exc_info.value)


def test_ba_create_invalid_status_raises():
    with pytest.raises(ValidationError) as exc_info:
        BusinessAttributeCreate(
            id="test-ba-bad",
            name="Bad",
            tier="primitive-root",
            status="unknown-status",
        )
    assert "status" in str(exc_info.value)


def test_ba_create_invalid_group_raises():
    with pytest.raises(ValidationError) as exc_info:
        BusinessAttributeCreate(
            id="test-ba-bad",
            name="Bad",
            tier="ict-leaf",
            group="not-a-real-group",
        )
    assert "group" in str(exc_info.value)


def test_ba_create_invalid_t100_stereotype_raises():
    with pytest.raises(ValidationError) as exc_info:
        BusinessAttributeCreate(
            id="test-ba-bad",
            name="Bad",
            tier="ict-leaf",
            t100_stereotype="not-a-real-stereotype",
        )
    assert "t100_stereotype" in str(exc_info.value)


# ---------------------------------------------------------------------------
# InfluenceCreate — valid cases
# ---------------------------------------------------------------------------

def test_influence_create_valid_negative():
    inf = InfluenceCreate(
        source_id="threat-ransomware",
        target_id="ba-availability",
        polarity="negative",
        rationale="Ransomware disrupts availability",
        status="curated",
    )
    assert inf.polarity == "negative"
    assert inf.status == "curated"


def test_influence_create_valid_positive():
    inf = InfluenceCreate(
        source_id="ba-resilience",
        target_id="ba-availability",
        polarity="positive",
        rationale="Resilience supports availability",
        status="draft-curated",
    )
    assert inf.polarity == "positive"


def test_influence_create_with_severity_valid():
    inf = InfluenceCreate(
        source_id="threat-apt",
        target_id="ba-confidentiality",
        polarity="negative",
        severity="high",
        rationale="APT steals confidential data",
        status="curated",
    )
    assert inf.severity == "high"


def test_influence_create_auto_inferred_status_valid():
    for status in INFLUENCE_STATUSES:
        inf = InfluenceCreate(
            source_id="s",
            target_id="t",
            polarity="negative",
            rationale="r",
            status=status,
        )
        assert inf.status == status


# ---------------------------------------------------------------------------
# InfluenceCreate — invalid cases
# ---------------------------------------------------------------------------

def test_influence_create_invalid_polarity_raises():
    with pytest.raises(ValidationError) as exc_info:
        InfluenceCreate(
            source_id="s",
            target_id="t",
            polarity="neutral",
            rationale="r",
        )
    assert "polarity" in str(exc_info.value)


def test_influence_create_invalid_status_raises():
    with pytest.raises(ValidationError) as exc_info:
        InfluenceCreate(
            source_id="s",
            target_id="t",
            polarity="negative",
            rationale="r",
            status="made-up-status",
        )
    assert "status" in str(exc_info.value)


def test_influence_create_invalid_severity_raises():
    with pytest.raises(ValidationError) as exc_info:
        InfluenceCreate(
            source_id="s",
            target_id="t",
            polarity="negative",
            severity="catastrophic",
            rationale="r",
        )
    assert "severity" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ContainsCreate — valid cases
# ---------------------------------------------------------------------------

def test_contains_create_valid():
    c = ContainsCreate(
        parent_id="ba-group-management",
        child_id="ba-ict-leaf-authorised",
    )
    assert c.parent_id == "ba-group-management"
    assert c.child_id == "ba-ict-leaf-authorised"
    assert c.rationale is None


def test_contains_create_with_rationale():
    c = ContainsCreate(
        parent_id="parent",
        child_id="child",
        rationale="Child is a sub-concept of parent",
    )
    assert c.rationale == "Child is a sub-concept of parent"


# ---------------------------------------------------------------------------
# Extended FrameworkCreate — cell_role/layer cross-validator
# ---------------------------------------------------------------------------

def test_framework_create_main_matrix_cell_valid_layer():
    for layer in MATRIX_LAYERS_MAIN:
        fw = FrameworkCreate(
            id=f"test-cell-main-{layer}-assets",
            title=f"Main {layer} Assets",
            cell_role="main-matrix-cell",
            layer=layer,
            perspective="assets",
            matrix="main",
        )
        assert fw.cell_role == "main-matrix-cell"
        assert fw.layer == layer


def test_framework_create_service_mgmt_cell_valid_layer():
    for layer in MATRIX_LAYERS_SERVICE_MGMT:
        fw = FrameworkCreate(
            id=f"test-cell-sm-{layer}-assets",
            title=f"SM {layer} Assets",
            cell_role="service-mgmt-cell",
            layer=layer,
            perspective="assets",
            matrix="service-management",
        )
        assert fw.cell_role == "service-mgmt-cell"


def test_framework_create_main_cell_invalid_layer_raises():
    # "operational" is a main-matrix-only layer; not in service-mgmt
    # Conversely: a made-up layer should fail for main-matrix-cell
    with pytest.raises(ValidationError) as exc_info:
        FrameworkCreate(
            id="test-cell-bad",
            title="Bad",
            cell_role="main-matrix-cell",
            layer="not-a-valid-layer",
        )
    assert "layer" in str(exc_info.value)


def test_framework_create_service_mgmt_cell_with_operational_layer_raises():
    # "operational" is ONLY in MATRIX_LAYERS_MAIN, not in MATRIX_LAYERS_SERVICE_MGMT
    with pytest.raises(ValidationError) as exc_info:
        FrameworkCreate(
            id="test-cell-bad",
            title="Bad",
            cell_role="service-mgmt-cell",
            layer="operational",
        )
    assert "layer" in str(exc_info.value)


def test_framework_create_no_cell_role_no_layer_valid():
    fw = FrameworkCreate(
        id="test-plain-framework",
        title="Plain Framework",
    )
    assert fw.cell_role is None
    assert fw.layer is None


def test_framework_create_invalid_cell_role_raises():
    with pytest.raises(ValidationError) as exc_info:
        FrameworkCreate(
            id="test-fw",
            title="Test",
            cell_role="not-a-role",
        )
    assert "cell_role" in str(exc_info.value)


def test_framework_create_invalid_perspective_raises():
    with pytest.raises(ValidationError) as exc_info:
        FrameworkCreate(
            id="test-fw",
            title="Test",
            perspective="not-a-perspective",
        )
    assert "perspective" in str(exc_info.value)


def test_framework_create_invalid_matrix_raises():
    with pytest.raises(ValidationError) as exc_info:
        FrameworkCreate(
            id="test-fw",
            title="Test",
            matrix="not-a-matrix",
        )
    assert "matrix" in str(exc_info.value)


# ---------------------------------------------------------------------------
# INFLUENCE_POLARITIES and INFLUENCE_STATUSES frozensets
# ---------------------------------------------------------------------------

def test_influence_polarities_correct():
    assert INFLUENCE_POLARITIES == frozenset({"positive", "negative"})


def test_influence_statuses_correct():
    expected = frozenset({
        "draft-curated", "curated",
        "auto-inferred-embedding", "auto-inferred-traversal",
    })
    assert INFLUENCE_STATUSES == expected
