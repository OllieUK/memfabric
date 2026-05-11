"""tests/test_threat_repo.py — Unit tests for WP-108 threat-layer repo functions.

All tests use a MagicMock session — no live stack required.
Pattern follows tests/test_knowledge_bridge.py exactly.
"""
import pytest
from unittest.mock import MagicMock

from cyber_knowledge import repo as knowledge_repo


class FakeRecord(dict):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    return MagicMock()


def _make_req(**kwargs):
    """Return a simple namespace-like object for repo call arguments."""
    class _Req:
        pass
    r = _Req()
    for k, v in kwargs.items():
        setattr(r, k, v)
    return r


NOW = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# upsert_threat_report
# ---------------------------------------------------------------------------


def test_upsert_threat_report_calls_session_run_with_required_params():
    session = _make_session()
    fake_record = FakeRecord(
        id="rpt-001",
        title="Test Report",
        publisher="ACME",
        published_at=None,
        valid_from=None,
        valid_until=None,
        scope=None,
        perspective_notes=None,
        created_at=NOW,
    )
    session.run.return_value.single.return_value = fake_record

    req = _make_req(
        id="rpt-001",
        title="Test Report",
        publisher="ACME",
        published_at=None,
        valid_from=None,
        valid_until=None,
        scope=None,
        perspective_notes=None,
    )
    result = knowledge_repo.upsert_threat_report(session, req, NOW)

    session.run.assert_called_once()
    call_kwargs = session.run.call_args[1]
    assert call_kwargs["id"] == "rpt-001"
    assert call_kwargs["title"] == "Test Report"
    assert call_kwargs["publisher"] == "ACME"
    assert call_kwargs["created_at"] == NOW
    assert result["id"] == "rpt-001"


# ---------------------------------------------------------------------------
# upsert_threat
# ---------------------------------------------------------------------------


def test_upsert_threat_passes_non_empty_embedding_to_session_run():
    session = _make_session()
    fake_record = FakeRecord(
        id="threat-abc12345",
        text="Ransomware encrypted files.",
        tags=["T1486"],
        created_at=NOW,
    )
    session.run.return_value.single.return_value = fake_record

    req = _make_req(id="threat-abc12345", text="Ransomware encrypted files.", tags=["T1486"])
    embedding = [0.1, 0.2, 0.3]

    result = knowledge_repo.upsert_threat(session, req, embedding, NOW)

    session.run.assert_called_once()
    call_kwargs = session.run.call_args[1]
    assert call_kwargs["embedding"] is not None
    assert len(call_kwargs["embedding"]) > 0
    assert call_kwargs["embedding"] == embedding
    assert result["id"] == "threat-abc12345"


# ---------------------------------------------------------------------------
# get_threat_report
# ---------------------------------------------------------------------------


def test_get_threat_report_returns_none_when_single_returns_none():
    session = _make_session()
    session.run.return_value.single.return_value = None

    result = knowledge_repo.get_threat_report(session, "rpt-nonexistent")

    assert result is None


# ---------------------------------------------------------------------------
# get_threat
# ---------------------------------------------------------------------------


def test_get_threat_returns_none_when_single_returns_none():
    session = _make_session()
    session.run.return_value.single.return_value = None

    result = knowledge_repo.get_threat(session, "threat-nonexistent")

    assert result is None


# ---------------------------------------------------------------------------
# list_threats
# ---------------------------------------------------------------------------


def test_list_threats_returns_list_of_dicts():
    session = _make_session()
    rows = [
        FakeRecord(id="t1", text="Phishing email sent.", tags=["T1566"], created_at=NOW),
        FakeRecord(id="t2", text="Ransomware deployed.", tags=["T1486"], created_at=NOW),
    ]
    session.run.return_value.__iter__ = lambda s: iter(rows)

    result = knowledge_repo.list_threats(session)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["id"] == "t1"
    assert result[1]["id"] == "t2"


# ---------------------------------------------------------------------------
# search_threats
# ---------------------------------------------------------------------------


def test_search_threats_returns_list_with_distance_key():
    session = _make_session()
    rows = [
        FakeRecord(id="t1", text="Ransomware deployed.", tags=["T1486"], created_at=NOW, distance=0.05),
    ]
    session.run.return_value.__iter__ = lambda s: iter(rows)

    embedding = [0.1, 0.2, 0.3]
    result = knowledge_repo.search_threats(session, embedding, limit=5)

    assert isinstance(result, list)
    assert len(result) == 1
    assert "distance" in result[0]
    assert result[0]["distance"] == 0.05


# ---------------------------------------------------------------------------
# create_identifies_edge
# ---------------------------------------------------------------------------


def test_create_identifies_edge_returns_none_when_record_is_none():
    session = _make_session()
    session.run.return_value.single.return_value = None

    result = knowledge_repo.create_identifies_edge(
        session,
        threat_report_id="rpt-nonexistent",
        threat_id="threat-nonexistent",
        severity="high",
        confidence="high",
        trend="stable",
        source_terminology=None,
        now=NOW,
    )

    assert result is None


# ---------------------------------------------------------------------------
# create_mapped_to_technique_edge
# ---------------------------------------------------------------------------


def test_create_mapped_to_technique_edge_returns_none_when_record_is_none():
    session = _make_session()
    session.run.return_value.single.return_value = None

    result = knowledge_repo.create_mapped_to_technique_edge(
        session,
        threat_id="threat-nonexistent",
        framework_id="attack-enterprise.T9999",
        now=NOW,
    )

    assert result is None


# ---------------------------------------------------------------------------
# create_targets_edge
# ---------------------------------------------------------------------------


def test_create_targets_edge_returns_none_when_record_is_none():
    session = _make_session()
    session.run.return_value.single.return_value = None

    result = knowledge_repo.create_targets_edge(
        session,
        threat_id="threat-nonexistent",
        asset_id="asset-nonexistent",
        now=NOW,
    )

    assert result is None


# ---------------------------------------------------------------------------
# upsert_asset
# ---------------------------------------------------------------------------


def test_upsert_asset_includes_asset_type_in_session_run_params():
    session = _make_session()
    fake_record = FakeRecord(
        id="asset-it",
        title="IT Systems",
        asset_type="IT",
        exposure=None,
        data_classification=None,
        created_at=NOW,
    )
    session.run.return_value.single.return_value = fake_record

    req = _make_req(
        id="asset-it",
        title="IT Systems",
        asset_type="IT",
        exposure=None,
        data_classification=None,
    )
    result = knowledge_repo.upsert_asset(session, req, NOW)

    session.run.assert_called_once()
    call_kwargs = session.run.call_args[1]
    assert call_kwargs["asset_type"] == "IT"
    assert result["asset_type"] == "IT"
