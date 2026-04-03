"""Tests for WP-075: traceability repo functions and route handlers.

Unit tests only — no live Memgraph required; all DB calls are mocked.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory_service import knowledge_repo


# ---------------------------------------------------------------------------
# Fixture — FastAPI TestClient with mock driver
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """Return (TestClient, mock_session) with feature flag enabled and knowledge routes active."""
    import importlib
    import memory_service.config as cfg_mod
    import memory_service.main as main_mod
    from fastapi.testclient import TestClient

    os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"
    importlib.reload(cfg_mod)
    importlib.reload(main_mod)

    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

    with patch("memory_service.main.get_driver", return_value=mock_driver):
        with patch("memory_service.main.get_embedding_dimension"):
            with TestClient(main_mod.app) as client:
                yield client, mock_session


# ---------------------------------------------------------------------------
# TestTraceUpRepo
# ---------------------------------------------------------------------------


class TestTraceUpRepo:
    def _make_session(self):
        return MagicMock()

    def test_trace_up_returns_none_when_control_missing(self):
        session = self._make_session()
        session.run.return_value.single.return_value = None
        result = knowledge_repo.trace_up(session, "c-missing")
        assert result is None

    def test_trace_up_runs_query_with_control_id(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "c-1"}
        main_mock = MagicMock()
        main_mock.single.return_value = {
            "control_id": "c-1",
            "business_attributes": [],
            "norms": [],
        }
        session.run.side_effect = [exists_mock, main_mock]
        knowledge_repo.trace_up(session, "c-1")
        assert session.run.call_count == 2

    def test_trace_up_returns_business_attributes(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "c-1"}
        main_mock = MagicMock()
        main_mock.single.return_value = {
            "control_id": "c-1",
            "business_attributes": [{"id": "ba-1", "name": "Confidentiality"}, None],
            "norms": [],
        }
        session.run.side_effect = [exists_mock, main_mock]
        result = knowledge_repo.trace_up(session, "c-1")
        assert result["business_attributes"] == [{"id": "ba-1", "name": "Confidentiality"}]

    def test_trace_up_returns_norms(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "c-1"}
        main_mock = MagicMock()
        main_mock.single.return_value = {
            "control_id": "c-1",
            "business_attributes": [],
            "norms": [{"id": "n-1", "name": "GDPR Art 5", "status": "active"}, None],
        }
        session.run.side_effect = [exists_mock, main_mock]
        result = knowledge_repo.trace_up(session, "c-1")
        assert result["norms"] == [{"id": "n-1", "name": "GDPR Art 5", "status": "active"}]

    def test_trace_up_returns_empty_lists_when_no_precepts(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "c-1"}
        main_mock = MagicMock()
        main_mock.single.return_value = {
            "control_id": "c-1",
            "business_attributes": [],
            "norms": [],
        }
        session.run.side_effect = [exists_mock, main_mock]
        result = knowledge_repo.trace_up(session, "c-1")
        assert result["business_attributes"] == []
        assert result["norms"] == []


# ---------------------------------------------------------------------------
# TestTraceDownRepo
# ---------------------------------------------------------------------------


class TestTraceDownRepo:
    def _make_session(self):
        return MagicMock()

    def test_trace_down_returns_none_when_control_missing(self):
        # trace_down detects not-found from the main query returning None
        # (MATCH (c:Control {id: $id}) with no match → single() returns None)
        session = self._make_session()
        session.run.return_value.single.return_value = None
        result = knowledge_repo.trace_down(session, "c-missing", None)
        assert result is None

    def test_trace_down_groups_chunks_under_documents(self):
        session = self._make_session()
        with patch("memory_service.knowledge_repo.get_control", return_value={"id": "c-1"}):
            session.run.return_value.single.return_value = {
                "control_id": "c-1",
                "doc_chunks": [
                    {
                        "doc_id": "doc-1", "doc_title": "Policy A", "chunk_id": "ch-1",
                        "chunk_text": "text 1", "confidence": 0.9, "sup_status": "confirmed",
                    },
                    {
                        "doc_id": "doc-1", "doc_title": "Policy A", "chunk_id": "ch-2",
                        "chunk_text": "text 2", "confidence": 0.8, "sup_status": "auto-inferred",
                    },
                ],
                "memory_refs": [],
            }
            result = knowledge_repo.trace_down(session, "c-1", None)
        assert len(result["documents"]) == 1
        assert result["documents"][0]["id"] == "doc-1"
        assert len(result["documents"][0]["chunks"]) == 2

    def test_trace_down_splits_evidence_and_gap_memories(self):
        session = self._make_session()
        with patch("memory_service.knowledge_repo.get_control", return_value={"id": "c-1"}):
            session.run.return_value.single.return_value = {
                "control_id": "c-1",
                "doc_chunks": [],
                "memory_refs": [
                    {"id": "m-1", "text": "evidence text", "relationship_type": "evidence"},
                    {"id": "m-2", "text": "gap text", "relationship_type": "gap"},
                ],
            }
            result = knowledge_repo.trace_down(session, "c-1", None)
        assert len(result["evidence_memories"]) == 1
        assert result["evidence_memories"][0]["id"] == "m-1"
        assert len(result["gap_memories"]) == 1
        assert result["gap_memories"][0]["id"] == "m-2"

    def test_trace_down_returns_empty_lists_with_no_memory_nodes(self):
        session = self._make_session()
        with patch("memory_service.knowledge_repo.get_control", return_value={"id": "c-1"}):
            session.run.return_value.single.return_value = {
                "control_id": "c-1",
                "doc_chunks": [],
                "memory_refs": [],
            }
            result = knowledge_repo.trace_down(session, "c-1", None)
        assert result["evidence_memories"] == []
        assert result["gap_memories"] == []
        assert result["documents"] == []

    def test_trace_down_org_id_passed_as_param(self):
        session = self._make_session()
        with patch("memory_service.knowledge_repo.get_control", return_value={"id": "c-1"}):
            session.run.return_value.single.return_value = {
                "control_id": "c-1", "doc_chunks": [], "memory_refs": []
            }
            knowledge_repo.trace_down(session, "c-1", "org-acme")
        call_kwargs = session.run.call_args[1]
        assert call_kwargs.get("org_id") == "org-acme"

    def test_trace_down_org_id_none_passes_none(self):
        session = self._make_session()
        with patch("memory_service.knowledge_repo.get_control", return_value={"id": "c-1"}):
            session.run.return_value.single.return_value = {
                "control_id": "c-1", "doc_chunks": [], "memory_refs": []
            }
            knowledge_repo.trace_down(session, "c-1", None)
        call_kwargs = session.run.call_args[1]
        assert call_kwargs.get("org_id") is None


# ---------------------------------------------------------------------------
# TestAttributeCoverageRepo
# ---------------------------------------------------------------------------


class TestAttributeCoverageRepo:
    def _make_session(self):
        return MagicMock()

    def test_attribute_coverage_returns_none_when_not_found(self):
        session = self._make_session()
        session.run.return_value.single.return_value = None
        result = knowledge_repo.attribute_coverage(session, "ba-missing")
        assert result is None

    def test_attribute_coverage_calculates_pct_correctly(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "ba-1"}
        controls_mock = MagicMock()
        controls_mock.__iter__ = MagicMock(return_value=iter([
            {"control_id": "c-1"},
            {"control_id": "c-2"},
            {"control_id": "c-3"},
            {"control_id": "c-4"},
        ]))
        coverage_mock = MagicMock()
        coverage_mock.__iter__ = MagicMock(return_value=iter([
            {"control_id": "c-1", "chunk_count": 3},
            {"control_id": "c-2", "chunk_count": 1},
            {"control_id": "c-3", "chunk_count": 0},
            {"control_id": "c-4", "chunk_count": 0},
        ]))
        session.run.side_effect = [exists_mock, controls_mock, coverage_mock]
        result = knowledge_repo.attribute_coverage(session, "ba-1")
        assert result["total_controls"] == 4
        assert result["covered_controls"] == 2
        assert result["coverage_pct"] == 50.0

    def test_attribute_coverage_zero_total_returns_zero_pct(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "ba-1"}
        controls_mock = MagicMock()
        controls_mock.__iter__ = MagicMock(return_value=iter([]))
        session.run.side_effect = [exists_mock, controls_mock]
        result = knowledge_repo.attribute_coverage(session, "ba-1")
        assert result["coverage_pct"] == 0.0
        assert result["total_controls"] == 0

    def test_attribute_coverage_filters_none_from_uncovered_ids(self):
        session = self._make_session()
        exists_mock = MagicMock()
        exists_mock.single.return_value = {"id": "ba-1"}
        controls_mock = MagicMock()
        controls_mock.__iter__ = MagicMock(return_value=iter([
            {"control_id": "c-1"},
            {"control_id": "c-2"},
        ]))
        coverage_mock = MagicMock()
        coverage_mock.__iter__ = MagicMock(return_value=iter([
            {"control_id": "c-1", "chunk_count": 0},
            {"control_id": "c-2", "chunk_count": 2},
        ]))
        session.run.side_effect = [exists_mock, controls_mock, coverage_mock]
        result = knowledge_repo.attribute_coverage(session, "ba-1")
        assert result["uncovered_control_ids"] == ["c-1"]


# ---------------------------------------------------------------------------
# TestGapAnalysisRepo
# ---------------------------------------------------------------------------


class TestGapAnalysisRepo:
    def _make_session(self):
        return MagicMock()

    def test_gap_analysis_fetches_all_controls_when_ids_empty(self):
        session = self._make_session()
        all_controls_mock = MagicMock()
        all_controls_mock.__iter__ = MagicMock(return_value=iter([
            {"id": "c-1", "name": "Control 1"},
        ]))
        classify_mock = MagicMock()
        classify_mock.__iter__ = MagicMock(return_value=iter([
            {
                "control_id": "c-1", "control_name": "Control 1",
                "chunk_count": 0, "memory_count": 0,
            },
        ]))
        session.run.side_effect = [all_controls_mock, classify_mock]
        result = knowledge_repo.gap_analysis(session, [], None)
        assert session.run.call_count == 2
        assert len(result["uncovered"]) == 1

    def test_gap_analysis_classifies_covered_correctly(self):
        session = self._make_session()
        classify_mock = MagicMock()
        classify_mock.__iter__ = MagicMock(return_value=iter([
            {
                "control_id": "c-1", "control_name": "Control 1",
                "chunk_count": 2, "memory_count": 1,
            },
        ]))
        session.run.return_value = classify_mock
        result = knowledge_repo.gap_analysis(session, ["c-1"], None)
        assert len(result["covered"]) == 1
        assert result["covered"][0]["control_id"] == "c-1"

    def test_gap_analysis_classifies_partial_chunks_only(self):
        session = self._make_session()
        classify_mock = MagicMock()
        classify_mock.__iter__ = MagicMock(return_value=iter([
            {
                "control_id": "c-1", "control_name": "Control 1",
                "chunk_count": 2, "memory_count": 0,
            },
        ]))
        session.run.return_value = classify_mock
        result = knowledge_repo.gap_analysis(session, ["c-1"], None)
        assert len(result["partial"]) == 1

    def test_gap_analysis_classifies_partial_memory_only(self):
        session = self._make_session()
        classify_mock = MagicMock()
        classify_mock.__iter__ = MagicMock(return_value=iter([
            {
                "control_id": "c-1", "control_name": "Control 1",
                "chunk_count": 0, "memory_count": 3,
            },
        ]))
        session.run.return_value = classify_mock
        result = knowledge_repo.gap_analysis(session, ["c-1"], None)
        assert len(result["partial"]) == 1

    def test_gap_analysis_classifies_uncovered_correctly(self):
        session = self._make_session()
        classify_mock = MagicMock()
        classify_mock.__iter__ = MagicMock(return_value=iter([
            {
                "control_id": "c-1", "control_name": "Control 1",
                "chunk_count": 0, "memory_count": 0,
            },
        ]))
        session.run.return_value = classify_mock
        result = knowledge_repo.gap_analysis(session, ["c-1"], None)
        assert len(result["uncovered"]) == 1

    def test_gap_analysis_org_id_passed_to_query(self):
        session = self._make_session()
        classify_mock = MagicMock()
        classify_mock.__iter__ = MagicMock(return_value=iter([]))
        session.run.return_value = classify_mock
        knowledge_repo.gap_analysis(session, ["c-1"], "org-acme")
        call_kwargs = session.run.call_args[1]
        assert call_kwargs.get("org_id") == "org-acme"

    def test_gap_analysis_returns_empty_lists_when_no_controls(self):
        session = self._make_session()
        all_controls_mock = MagicMock()
        all_controls_mock.__iter__ = MagicMock(return_value=iter([]))
        session.run.return_value = all_controls_mock
        result = knowledge_repo.gap_analysis(session, [], None)
        assert result == {"covered": [], "partial": [], "uncovered": []}


# ---------------------------------------------------------------------------
# TestTraceabilityRoutes
# ---------------------------------------------------------------------------


class TestTraceabilityRoutes:
    def test_get_trace_up_returns_200(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.trace_up") as mock_fn:
            mock_fn.return_value = {
                "control_id": "c-1",
                "business_attributes": [{"id": "ba-1", "name": "Confidentiality"}],
                "norms": [{"id": "n-1", "name": "GDPR Art 5", "status": "active"}],
            }
            resp = client.get("/knowledge/controls/c-1/trace-up")
        assert resp.status_code == 200
        data = resp.json()
        assert data["control_id"] == "c-1"
        assert len(data["business_attributes"]) == 1
        assert len(data["norms"]) == 1

    def test_get_trace_up_returns_404_when_missing(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.trace_up", return_value=None):
            resp = client.get("/knowledge/controls/nonexistent/trace-up")
        assert resp.status_code == 404

    def test_get_trace_down_returns_200(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.trace_down") as mock_fn:
            mock_fn.return_value = {
                "control_id": "c-1",
                "documents": [],
                "evidence_memories": [],
                "gap_memories": [],
            }
            resp = client.get("/knowledge/controls/c-1/trace-down")
        assert resp.status_code == 200
        data = resp.json()
        assert data["control_id"] == "c-1"
        assert data["documents"] == []

    def test_get_trace_down_accepts_org_id_param(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.trace_down") as mock_fn:
            mock_fn.return_value = {
                "control_id": "c-1",
                "documents": [],
                "evidence_memories": [],
                "gap_memories": [],
            }
            resp = client.get("/knowledge/controls/c-1/trace-down?org_id=org-acme")
        assert resp.status_code == 200
        mock_fn.assert_called_once()
        call_args = mock_fn.call_args
        assert "org-acme" in call_args[0] or call_args[1].get("org_id") == "org-acme"

    def test_get_trace_down_returns_404_when_missing(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.trace_down", return_value=None):
            resp = client.get("/knowledge/controls/nonexistent/trace-down")
        assert resp.status_code == 404

    def test_get_attribute_coverage_returns_200(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.attribute_coverage") as mock_fn:
            mock_fn.return_value = {
                "attribute_id": "ba-1",
                "total_controls": 4,
                "covered_controls": 2,
                "coverage_pct": 50.0,
                "uncovered_control_ids": ["c-3", "c-4"],
            }
            resp = client.get("/knowledge/attributes/ba-1/coverage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage_pct"] == 50.0
        assert data["total_controls"] == 4

    def test_get_attribute_coverage_returns_404_when_missing(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.attribute_coverage", return_value=None):
            resp = client.get("/knowledge/attributes/nonexistent/coverage")
        assert resp.status_code == 404

    def test_post_gap_analysis_returns_200_empty_body(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.gap_analysis") as mock_fn:
            mock_fn.return_value = {"covered": [], "partial": [], "uncovered": []}
            resp = client.post("/knowledge/gap-analysis", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "covered" in data
        assert "partial" in data
        assert "uncovered" in data

    def test_post_gap_analysis_with_control_ids(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.gap_analysis") as mock_fn:
            mock_fn.return_value = {"covered": [], "partial": [], "uncovered": []}
            resp = client.post("/knowledge/gap-analysis", json={"control_ids": ["c-1", "c-2"]})
        assert resp.status_code == 200
        call_args = mock_fn.call_args[0]
        assert "c-1" in call_args[1]

    def test_post_gap_analysis_with_org_id(self, app_client):
        client, session = app_client
        with patch("memory_service.knowledge_repo.gap_analysis") as mock_fn:
            mock_fn.return_value = {"covered": [], "partial": [], "uncovered": []}
            resp = client.post("/knowledge/gap-analysis", json={"org_id": "org-acme"})
        assert resp.status_code == 200
        call_args = mock_fn.call_args[0]
        assert call_args[2] == "org-acme"
