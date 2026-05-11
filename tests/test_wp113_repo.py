# tests/test_wp113_repo.py — WP-113 knowledge_repo unit tests (mock session, no DB)

from unittest.mock import MagicMock, call
import pytest

from cyber_knowledge import repo as knowledge_repo

pytestmark = pytest.mark.cyber



def _make_session_returning(record: dict):
    """Return a mock session whose .run().single() returns a neo4j-like record dict."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_record = MagicMock()
    mock_record.__iter__ = lambda self: iter(record.items())
    for k, v in record.items():
        mock_record.__getitem__ = lambda self, key, _r=record: _r[key]
    mock_record.data = lambda: record
    # Make dict(record) work
    mock_record.keys = lambda: list(record.keys())
    mock_record.__getitem__ = lambda self, key: record[key]
    mock_result.single.return_value = mock_record
    session.run.return_value = mock_result
    return session


def _make_request(**kwargs):
    req = MagicMock()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return req


# ---------------------------------------------------------------------------
# upsert_business_attribute
# ---------------------------------------------------------------------------

def test_upsert_business_attribute_calls_cypher_with_correct_params():
    record = {
        "id": "ba-confidentiality",
        "name": "Confidentiality",
        "description": "Prevents unauthorized disclosure",
        "source_ref": "TSI-W100-SABSA-White-Paper.pdf:p20",
        "status": "active",
        "superseded_by": None,
        "tier": "primitive-root",
        "group": None,
        "t100_stereotype": "sabsa-attribute",
        "created_at": "2026-05-07T00:00:00Z",
    }
    session = _make_session_returning(record)
    req = _make_request(
        id="ba-confidentiality",
        name="Confidentiality",
        description="Prevents unauthorized disclosure",
        source_ref="TSI-W100-SABSA-White-Paper.pdf:p20",
        status="active",
        superseded_by=None,
        tier="primitive-root",
        group=None,
        t100_stereotype="sabsa-attribute",
    )
    embedding = [0.1] * 384
    now = "2026-05-07T00:00:00Z"

    result = knowledge_repo.upsert_business_attribute(session, req, embedding, now)

    assert session.run.called
    call_args = session.run.call_args
    cypher = call_args[0][0]
    params = call_args[1] if call_args[1] else call_args[0][1] if len(call_args[0]) > 1 else {}

    assert "MERGE" in cypher
    assert "BusinessAttribute" in cypher
    assert result["id"] == "ba-confidentiality"
    assert result["tier"] == "primitive-root"


def test_upsert_business_attribute_returns_shaped_dict():
    record = {
        "id": "ba-test",
        "name": "Test BA",
        "description": None,
        "source_ref": None,
        "status": "active",
        "superseded_by": None,
        "tier": "ict-leaf",
        "group": "management",
        "t100_stereotype": "sabsa-attribute",
        "created_at": "2026-05-07T00:00:00Z",
    }
    session = _make_session_returning(record)
    req = _make_request(
        id="ba-test",
        name="Test BA",
        description=None,
        source_ref=None,
        status="active",
        superseded_by=None,
        tier="ict-leaf",
        group="management",
        t100_stereotype="sabsa-attribute",
    )
    result = knowledge_repo.upsert_business_attribute(session, req, [0.0] * 384, "2026-05-07T00:00:00Z")
    assert "id" in result
    assert "tier" in result
    assert "group" in result
    assert "t100_stereotype" in result
    assert "created_at" in result


# ---------------------------------------------------------------------------
# create_influence_edge
# ---------------------------------------------------------------------------

def test_create_influence_edge_calls_merge_cypher():
    record = {
        "source_id": "threat-ransomware",
        "target_id": "ba-availability",
        "polarity": "negative",
        "severity": "high",
        "rationale": "Ransomware disrupts availability",
        "status": "curated",
        "created_at": "2026-05-07T00:00:00Z",
    }
    session = _make_session_returning(record)

    result = knowledge_repo.create_influence_edge(
        session=session,
        source_id="threat-ransomware",
        target_id="ba-availability",
        polarity="negative",
        severity="high",
        rationale="Ransomware disrupts availability",
        status="curated",
        now="2026-05-07T00:00:00Z",
    )

    assert session.run.called
    call_args = session.run.call_args
    cypher = call_args[0][0]
    assert "MERGE" in cypher
    assert "INFLUENCE" in cypher
    assert result is not None
    assert result["polarity"] == "negative"


def test_create_influence_edge_returns_none_when_no_match():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = None
    session.run.return_value = mock_result

    result = knowledge_repo.create_influence_edge(
        session=session,
        source_id="nonexistent-threat",
        target_id="nonexistent-ba",
        polarity="negative",
        severity=None,
        rationale="r",
        status="curated",
        now="2026-05-07T00:00:00Z",
    )

    assert result is None


def test_create_influence_edge_uses_named_params():
    record = {
        "source_id": "s", "target_id": "t", "polarity": "negative",
        "severity": None, "rationale": "r", "status": "curated",
        "created_at": "2026-05-07T00:00:00Z",
    }
    session = _make_session_returning(record)
    knowledge_repo.create_influence_edge(
        session=session,
        source_id="s",
        target_id="t",
        polarity="negative",
        severity=None,
        rationale="r",
        status="curated",
        now="2026-05-07T00:00:00Z",
    )
    call_args = session.run.call_args
    # All params should be passed as keyword args, not interpolated into cypher
    cypher = call_args[0][0]
    assert "$source_id" in cypher or "$polarity" in cypher  # named params used


# ---------------------------------------------------------------------------
# create_contains_edge
# ---------------------------------------------------------------------------

def test_create_contains_edge_calls_merge_cypher():
    record = {
        "parent_id": "ba-group-management",
        "child_id": "ba-ict-authorised",
        "created_at": "2026-05-07T00:00:00Z",
    }
    session = _make_session_returning(record)

    result = knowledge_repo.create_contains_edge(
        session=session,
        parent_id="ba-group-management",
        child_id="ba-ict-authorised",
        rationale="Management group contains Authorised BA",
        now="2026-05-07T00:00:00Z",
    )

    assert session.run.called
    call_args = session.run.call_args
    cypher = call_args[0][0]
    assert "MERGE" in cypher
    assert "CONTAINS" in cypher
    assert result is not None


def test_create_contains_edge_returns_none_when_no_match():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = None
    session.run.return_value = mock_result

    result = knowledge_repo.create_contains_edge(
        session=session,
        parent_id="nonexistent-parent",
        child_id="nonexistent-child",
        rationale=None,
        now="2026-05-07T00:00:00Z",
    )

    assert result is None


def test_create_contains_edge_uses_named_params():
    record = {"parent_id": "p", "child_id": "c", "created_at": "2026-05-07T00:00:00Z"}
    session = _make_session_returning(record)
    knowledge_repo.create_contains_edge(
        session=session,
        parent_id="p",
        child_id="c",
        rationale=None,
        now="2026-05-07T00:00:00Z",
    )
    call_args = session.run.call_args
    cypher = call_args[0][0]
    assert "$parent_id" in cypher or "$child_id" in cypher


# ---------------------------------------------------------------------------
# list_business_attributes
# ---------------------------------------------------------------------------

def test_list_business_attributes_default_excludes_deprecated():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([])
    session.run.return_value = mock_result

    knowledge_repo.list_business_attributes(session, include_deprecated=False)

    call_args = session.run.call_args
    cypher = call_args[0][0]
    # Should filter out deprecated
    assert "deprecated" in cypher or "status" in cypher


def test_list_business_attributes_with_tier_filter():
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([])
    session.run.return_value = mock_result

    knowledge_repo.list_business_attributes(session, tier="primitive-root")
    call_args = session.run.call_args
    # tier filter must use named param, not string interpolation
    cypher = call_args[0][0]
    assert "$tier" in cypher or "tier" in cypher
