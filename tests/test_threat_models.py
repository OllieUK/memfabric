"""tests/test_threat_models.py — Unit tests for WP-108 threat-layer Pydantic models and enums.

No live stack required. All assertions are pure model/schema validation.
"""
from pathlib import Path

import pytest
import pydantic
import yaml

from cyber_knowledge.routes import (
    ThreatReportCreate,
    ThreatCreate,
    AssetCreate,
    IdentifiesCreate,
)
from cyber_knowledge.schemas import (
    THREAT_REPORT_SCOPES,
    IDENTIFIES_SEVERITIES,
    IDENTIFIES_CONFIDENCES,
    IDENTIFIES_TRENDS,
    ASSET_TYPES,
    ASSET_EXPOSURES,
    ASSET_DATA_CLASSIFICATIONS,
)

PROJECT_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# ThreatReportCreate
# ---------------------------------------------------------------------------


def test_threat_report_create_accepts_valid_fields():
    m = ThreatReportCreate(id="rpt-001", title="Annual Threat Report", publisher="ACME CERT")
    assert m.id == "rpt-001"
    assert m.title == "Annual Threat Report"
    assert m.publisher == "ACME CERT"


def test_threat_report_create_rejects_missing_title():
    with pytest.raises(pydantic.ValidationError):
        ThreatReportCreate(id="rpt-001", publisher="ACME CERT")


def test_threat_report_create_rejects_missing_publisher():
    with pytest.raises(pydantic.ValidationError):
        ThreatReportCreate(id="rpt-001", title="Annual Threat Report")


# ---------------------------------------------------------------------------
# ThreatCreate
# ---------------------------------------------------------------------------


def test_threat_create_accepts_valid_id_and_text():
    m = ThreatCreate(id="threat-abc12345", text="Ransomware encrypted critical files.")
    assert m.id == "threat-abc12345"
    assert m.text == "Ransomware encrypted critical files."


def test_threat_create_rejects_missing_text():
    with pytest.raises(pydantic.ValidationError):
        ThreatCreate(id="threat-abc12345")


# ---------------------------------------------------------------------------
# AssetCreate
# ---------------------------------------------------------------------------


def test_asset_create_accepts_valid_fields():
    m = AssetCreate(id="asset-it", title="Information Technology Systems", asset_type="IT")
    assert m.id == "asset-it"
    assert m.asset_type == "IT"


def test_asset_create_rejects_missing_title():
    with pytest.raises(pydantic.ValidationError):
        AssetCreate(id="asset-it", asset_type="IT")


def test_asset_create_rejects_invalid_asset_type():
    with pytest.raises(pydantic.ValidationError):
        AssetCreate(id="asset-x", title="Bad Asset", asset_type="INVALID_TYPE")


# ---------------------------------------------------------------------------
# IdentifiesCreate
# ---------------------------------------------------------------------------


def test_identifies_create_accepts_all_required_fields():
    m = IdentifiesCreate(
        threat_report_id="rpt-001",
        threat_id="threat-abc12345",
        severity="high",
        confidence="high",
        trend="stable",
    )
    assert m.severity == "high"
    assert m.confidence == "high"
    assert m.trend == "stable"


def test_identifies_create_rejects_missing_severity():
    with pytest.raises(pydantic.ValidationError):
        IdentifiesCreate(
            threat_report_id="rpt-001",
            threat_id="threat-abc12345",
            confidence="high",
            trend="stable",
        )


# ---------------------------------------------------------------------------
# Enum sets — all 7 new knowledge_schemas sets are non-empty
# ---------------------------------------------------------------------------


def test_all_7_threat_enum_sets_are_non_empty():
    sets = [
        THREAT_REPORT_SCOPES,
        IDENTIFIES_SEVERITIES,
        IDENTIFIES_CONFIDENCES,
        IDENTIFIES_TRENDS,
        ASSET_TYPES,
        ASSET_EXPOSURES,
        ASSET_DATA_CLASSIFICATIONS,
    ]
    for s in sets:
        assert len(s) > 0, f"Enum set is unexpectedly empty: {s}"


def test_asset_types_contains_exactly_expected_values():
    expected = {"IT", "OT", "IoT", "IT-OT-integration"}
    assert ASSET_TYPES == expected


def test_identifies_severities_contains_exactly_expected_values():
    expected = {"critical", "high", "medium", "low"}
    assert IDENTIFIES_SEVERITIES == expected


# ---------------------------------------------------------------------------
# assets.yaml — loads and validates
# ---------------------------------------------------------------------------


def test_assets_yaml_loads_and_validates():
    yaml_path = PROJECT_ROOT / "data" / "threats" / "assets.yaml"
    assert yaml_path.exists(), f"assets.yaml not found at {yaml_path}"

    data = yaml.safe_load(yaml_path.read_text())
    assets = data["assets"]

    assert len(assets) == 4, f"Expected exactly 4 assets, got {len(assets)}"

    for asset in assets:
        assert "id" in asset, f"Missing 'id' in asset: {asset}"
        assert "title" in asset, f"Missing 'title' in asset: {asset}"
        assert "asset_type" in asset, f"Missing 'asset_type' in asset: {asset}"
        assert asset["asset_type"] in ASSET_TYPES, (
            f"Invalid asset_type '{asset['asset_type']}' in asset {asset['id']}"
        )
