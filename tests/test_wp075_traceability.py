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
            "norms": [{"id": "n-1", "title": "GDPR Art 5"}, None],
        }
        session.run.side_effect = [exists_mock, main_mock]
        result = knowledge_repo.trace_up(session, "c-1")
        assert result["norms"] == [{"id": "n-1", "title": "GDPR Art 5"}]

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
                        "chunk_body": "text 1", "confidence": 0.9, "sup_status": "confirmed",
                    },
                    {
                        "doc_id": "doc-1", "doc_title": "Policy A", "chunk_id": "ch-2",
                        "chunk_body": "text 2", "confidence": 0.8, "sup_status": "auto-inferred",
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
                "norms": [{"id": "n-1", "title": "GDPR Art 5"}],
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


# ---------------------------------------------------------------------------
# Integration fixtures and helpers
# ---------------------------------------------------------------------------
# knowledge_client fixture is defined in conftest.py (module-scoped).


@pytest.fixture(scope="module")
def tr_data(knowledge_client, test_driver):
    """Seed full traceability graph; yield node-id dict; teardown on module exit."""
    ids = {
        "fw": "test-wp076-tr-fw",
        "ctrl_parent": "test-wp076-tr-ctrl-parent",
        "ctrl_child": "test-wp076-tr-ctrl-child",
        "precept": "test-wp076-tr-precept",
        "ba": "test-wp076-tr-ba",
        "norm": "test-wp076-tr-norm",
        "doc": "test-wp076-tr-doc",
        "chunk1": "test-wp076-tr-chunk-1",
        "chunk2": "test-wp076-tr-chunk-2",
    }

    # --- Framework ---
    knowledge_client.post("/knowledge/frameworks", json={
        "id": ids["fw"], "name": "Test Framework WP076",
    })

    # --- Controls ---
    knowledge_client.post("/knowledge/controls", json={
        "id": ids["ctrl_parent"],
        "name": "Parent Control WP076",
        "framework_id": ids["fw"],
    })
    knowledge_client.post("/knowledge/controls", json={
        "id": ids["ctrl_child"],
        "name": "Child Control WP076",
        "framework_id": ids["fw"],
        "parent_id": ids["ctrl_parent"],
    })

    # --- Precept + BusinessAttribute via direct Cypher ---
    with test_driver.session() as s:
        s.run(
            "MERGE (:Precept {id: $id, name: 'Security Precept WP076'})",
            id=ids["precept"],
        )
        s.run(
            "MERGE (:BusinessAttribute {id: $id, name: 'Confidentiality'})",
            id=ids["ba"],
        )
        # Parent control ADDRESSES Precept
        s.run(
            """
            MATCH (c:Control {id: $ctrl_id}), (p:Precept {id: $precept_id})
            MERGE (c)-[:ADDRESSES]->(p)
            """,
            ctrl_id=ids["ctrl_parent"],
            precept_id=ids["precept"],
        )
        # Child control ALSO ADDRESSES Precept (needed for attribute_coverage to find it)
        s.run(
            """
            MATCH (c:Control {id: $ctrl_id}), (p:Precept {id: $precept_id})
            MERGE (c)-[:ADDRESSES]->(p)
            """,
            ctrl_id=ids["ctrl_child"],
            precept_id=ids["precept"],
        )
        # Precept FULFILS BusinessAttribute
        s.run(
            """
            MATCH (p:Precept {id: $precept_id}), (ba:BusinessAttribute {id: $ba_id})
            MERGE (p)-[:FULFILS]->(ba)
            """,
            precept_id=ids["precept"],
            ba_id=ids["ba"],
        )

    # --- Norm via HTTP ---
    knowledge_client.post("/knowledge/norms", json={
        "id": ids["norm"],
        "name": "GDPR Art 5 WP076",
        "text": "Data must be processed lawfully.",
        "status": "active",
    })

    # --- Norm REQUIRES Precept via direct Cypher ---
    with test_driver.session() as s:
        s.run(
            """
            MATCH (n:Norm {id: $norm_id}), (p:Precept {id: $precept_id})
            MERGE (n)-[:REQUIRES]->(p)
            """,
            norm_id=ids["norm"],
            precept_id=ids["precept"],
        )

    # --- Document + Chunks via HTTP ---
    knowledge_client.post("/knowledge/documents", json={
        "id": ids["doc"],
        "title": "Test Policy WP076",
        "doc_type": "policy",
    })
    knowledge_client.post("/knowledge/chunks", json={
        "id": ids["chunk1"],
        "text": "Chunk one text for WP076.",
        "sequence": 1,
        "doc_id": ids["doc"],
    })
    knowledge_client.post("/knowledge/chunks", json={
        "id": ids["chunk2"],
        "text": "Chunk two text for WP076.",
        "sequence": 2,
        "doc_id": ids["doc"],
    })

    # --- SUPPORTS edges: both chunks → child control ---
    knowledge_client.post("/knowledge/chunk/supports", json={
        "chunk_id": ids["chunk1"],
        "control_id": ids["ctrl_child"],
        "confidence": 0.85,
        "status": "confirmed",
    })
    knowledge_client.post("/knowledge/chunk/supports", json={
        "chunk_id": ids["chunk2"],
        "control_id": ids["ctrl_child"],
        "confidence": 0.85,
        "status": "confirmed",
    })

    # --- Memory nodes via POST /memory ---
    resp_ev = knowledge_client.post("/memory", json={
        "fact": "evidence memory for test control wp076",
        "type": "observation",
        "agent_id": "test-agent-wp076",
        "control_ids": [ids["ctrl_child"]],
        "control_relationship_type": "evidence",
        "org_id": "test-wp076-tr-org-eu",
        "tags": ["test"],
        "ephemeral": True,
    })
    assert resp_ev.status_code == 200
    memory_evidence_id = resp_ev.json()["memory_id"]

    resp_gap = knowledge_client.post("/memory", json={
        "fact": "gap memory for test control wp076",
        "type": "observation",
        "agent_id": "test-agent-wp076",
        "control_ids": [ids["ctrl_child"]],
        "control_relationship_type": "gap",
        "org_id": "test-wp076-tr-org-eu",
        "tags": ["test"],
        "ephemeral": True,
    })
    assert resp_gap.status_code == 200
    memory_gap_id = resp_gap.json()["memory_id"]

    ids["memory_evidence"] = memory_evidence_id
    ids["memory_gap"] = memory_gap_id

    yield ids

    # --- Teardown ---
    with test_driver.session() as s:
        s.run(
            "MATCH (n) WHERE n.id STARTS WITH 'test-wp076-tr-' DETACH DELETE n"
        )
    with test_driver.session() as s:
        s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_evidence_id)
        s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_gap_id)


# ---------------------------------------------------------------------------
# TestTraceabilityIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTraceabilityIntegration:

    def test_trace_up_returns_business_attributes_and_norms(self, knowledge_client, tr_data):
        """trace-up via child control resolves ancestor ADDRESSES → Precept → BusinessAttribute."""
        resp = knowledge_client.get(
            f"/knowledge/controls/{tr_data['ctrl_child']}/trace-up"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["control_id"] == tr_data["ctrl_child"]
        ba_ids = [ba["id"] for ba in data["business_attributes"]]
        assert tr_data["ba"] in ba_ids
        norm_ids = [n["id"] for n in data["norms"]]
        assert tr_data["norm"] in norm_ids

    def test_trace_up_missing_control_returns_404(self, knowledge_client):
        resp = knowledge_client.get("/knowledge/controls/nonexistent-wp076/trace-up")
        assert resp.status_code == 404

    def test_trace_down_returns_documents_and_chunks(self, knowledge_client, tr_data):
        """trace-down returns documents list with nested chunks via SUPPORTS edges."""
        resp = knowledge_client.get(
            f"/knowledge/controls/{tr_data['ctrl_child']}/trace-down"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["control_id"] == tr_data["ctrl_child"]
        assert len(data["documents"]) == 1
        doc = data["documents"][0]
        assert doc["id"] == tr_data["doc"]
        chunk_ids = [ch["id"] for ch in doc["chunks"]]
        assert tr_data["chunk1"] in chunk_ids
        assert tr_data["chunk2"] in chunk_ids

    def test_trace_down_returns_evidence_and_gap_memories(self, knowledge_client, tr_data):
        """evidence_memories and gap_memories split correctly by relationship_type."""
        resp = knowledge_client.get(
            f"/knowledge/controls/{tr_data['ctrl_child']}/trace-down"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        evidence_ids = [m["id"] for m in data["evidence_memories"]]
        gap_ids = [m["id"] for m in data["gap_memories"]]
        assert tr_data["memory_evidence"] in evidence_ids
        assert tr_data["memory_gap"] in gap_ids
        # evidence memory must not appear in gap list and vice versa
        assert tr_data["memory_evidence"] not in gap_ids
        assert tr_data["memory_gap"] not in evidence_ids

    def test_trace_down_knowledge_only_mode(self, knowledge_client, test_driver):
        """With zero Memory nodes, trace-down returns valid response with empty memory lists."""
        ctrl_id = "test-wp076-tr-ko-ctrl"
        chunk_id = "test-wp076-tr-ko-chunk"
        doc_id = "test-wp076-tr-ko-doc"
        try:
            knowledge_client.post("/knowledge/frameworks", json={
                "id": "test-wp076-tr-ko-fw", "name": "KO FW",
            })
            knowledge_client.post("/knowledge/controls", json={
                "id": ctrl_id,
                "name": "Knowledge-Only Control",
                "framework_id": "test-wp076-tr-ko-fw",
            })
            knowledge_client.post("/knowledge/documents", json={
                "id": doc_id, "title": "KO Doc", "doc_type": "policy",
            })
            knowledge_client.post("/knowledge/chunks", json={
                "id": chunk_id,
                "text": "Knowledge-only chunk text.",
                "sequence": 1,
                "doc_id": doc_id,
            })
            knowledge_client.post("/knowledge/chunk/supports", json={
                "chunk_id": chunk_id,
                "control_id": ctrl_id,
                "confidence": 0.7,
            })
            resp = knowledge_client.get(f"/knowledge/controls/{ctrl_id}/trace-down")
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["evidence_memories"] == []
            assert data["gap_memories"] == []
            assert len(data["documents"]) == 1
        finally:
            with test_driver.session() as s:
                s.run(
                    "MATCH (n) WHERE n.id STARTS WITH 'test-wp076-tr-ko-' DETACH DELETE n"
                )

    def test_trace_down_org_id_filter(self, knowledge_client, tr_data, test_driver):
        """?org_id=org-eu returns only EU-scoped memory edges, not US-scoped."""
        # Add a third Memory with ABOUT_CONTROL edge for org-us
        resp_us = knowledge_client.post("/memory", json={
            "fact": "us-scoped memory for wp076 org filter test",
            "type": "observation",
            "agent_id": "test-agent-wp076",
            "control_ids": [tr_data["ctrl_child"]],
            "control_relationship_type": "evidence",
            "org_id": "test-wp076-tr-org-us",
            "tags": ["test"],
            "ephemeral": True,
        })
        assert resp_us.status_code == 200
        memory_us_id = resp_us.json()["memory_id"]
        try:
            resp = knowledge_client.get(
                f"/knowledge/controls/{tr_data['ctrl_child']}/trace-down"
                f"?org_id=test-wp076-tr-org-eu"
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            all_memory_ids = (
                [m["id"] for m in data["evidence_memories"]]
                + [m["id"] for m in data["gap_memories"]]
            )
            # EU evidence memory must be present
            assert tr_data["memory_evidence"] in all_memory_ids
            # US memory must be absent
            assert memory_us_id not in all_memory_ids
        finally:
            with test_driver.session() as s:
                s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_us_id)

    def test_attribute_coverage_calculation(self, knowledge_client, tr_data):
        """coverage_pct = 50.0 when 1 of 2 controls addressing the attribute has SUPPORTS chunks.

        tr_data seeds: ctrl_parent (no chunks) and ctrl_child (2 chunks) both ADDRESSES precept.
        → total_controls=2, covered_controls=1, coverage_pct=50.0.
        """
        resp = knowledge_client.get(
            f"/knowledge/attributes/{tr_data['ba']}/coverage"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # ctrl_child has chunks (covered), ctrl_parent has no chunks (uncovered) → 50%
        assert data["total_controls"] == 2
        assert data["covered_controls"] == 1
        assert data["coverage_pct"] == 50.0
        assert tr_data["ctrl_parent"] in data["uncovered_control_ids"]

    def test_attribute_coverage_missing_returns_404(self, knowledge_client):
        resp = knowledge_client.get(
            "/knowledge/attributes/nonexistent-ba-wp076/coverage"
        )
        assert resp.status_code == 404

    def test_gap_analysis_classification(self, knowledge_client, tr_data):
        """Three-way classification: child control is covered (chunks + evidence memory)."""
        resp = knowledge_client.post("/knowledge/gap-analysis", json={
            "control_ids": [tr_data["ctrl_child"], tr_data["ctrl_parent"]],
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        covered_ids = [e["control_id"] for e in data["covered"]]
        partial_ids = [e["control_id"] for e in data["partial"]]
        # child has both chunks and evidence memory → covered
        assert tr_data["ctrl_child"] in covered_ids
        # parent has no chunks and no evidence memory → uncovered or partial
        assert tr_data["ctrl_child"] not in partial_ids

    def test_gap_analysis_knowledge_only_mode(self, knowledge_client, test_driver):
        """With zero Memory nodes, controls with chunks appear in partial (not covered)."""
        ctrl_id = "test-wp076-tr-gap-ko-ctrl"
        chunk_id = "test-wp076-tr-gap-ko-chunk"
        doc_id = "test-wp076-tr-gap-ko-doc"
        try:
            knowledge_client.post("/knowledge/frameworks", json={
                "id": "test-wp076-tr-gap-ko-fw", "name": "GAP KO FW",
            })
            knowledge_client.post("/knowledge/controls", json={
                "id": ctrl_id,
                "name": "GAP KO Control",
                "framework_id": "test-wp076-tr-gap-ko-fw",
            })
            knowledge_client.post("/knowledge/documents", json={
                "id": doc_id, "title": "GAP KO Doc", "doc_type": "policy",
            })
            knowledge_client.post("/knowledge/chunks", json={
                "id": chunk_id,
                "text": "GAP knowledge-only chunk.",
                "sequence": 1,
                "doc_id": doc_id,
            })
            knowledge_client.post("/knowledge/chunk/supports", json={
                "chunk_id": chunk_id,
                "control_id": ctrl_id,
                "confidence": 0.6,
            })
            resp = knowledge_client.post("/knowledge/gap-analysis", json={
                "control_ids": [ctrl_id],
            })
            assert resp.status_code == 200, resp.text
            data = resp.json()
            partial_ids = [e["control_id"] for e in data["partial"]]
            covered_ids = [e["control_id"] for e in data["covered"]]
            assert ctrl_id in partial_ids
            assert ctrl_id not in covered_ids
        finally:
            with test_driver.session() as s:
                s.run(
                    "MATCH (n) WHERE n.id STARTS WITH 'test-wp076-tr-gap-ko-' DETACH DELETE n"
                )

    def test_gap_analysis_generic_mode(self, knowledge_client, tr_data):
        """Without org_id, all controls returned regardless of jurisdiction."""
        resp = knowledge_client.post("/knowledge/gap-analysis", json={
            "control_ids": [tr_data["ctrl_child"]],
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        all_ids = (
            [e["control_id"] for e in data["covered"]]
            + [e["control_id"] for e in data["partial"]]
            + [e["control_id"] for e in data["uncovered"]]
        )
        assert tr_data["ctrl_child"] in all_ids
