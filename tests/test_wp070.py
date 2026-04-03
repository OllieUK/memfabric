"""Tests for WP-070: knowledge layer write API (knowledge_repo + knowledge_routes).

Unit tests only — no live Memgraph required; all DB calls are mocked.
Integration tests are deferred to WP-076.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, call

# Feature flag must be set before importing main/app
os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory_service import knowledge_repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(return_value=None):
    """Return a mock session whose run().single() returns return_value."""
    session = MagicMock()
    mock_result = MagicMock()
    mock_result.single.return_value = (
        MagicMock(**return_value) if return_value else None
    )
    session.run.return_value = mock_result
    return session


def _make_record(**kwargs):
    """Return a MagicMock that behaves like a neo4j record dict."""
    record = MagicMock()
    record.__iter__ = MagicMock(return_value=iter(kwargs.items()))
    # dict(record) will use __iter__ — but the repo uses dict(result.single())
    # We need to make the mock work with dict() conversion.
    # Use a spec that returns the right items.
    return kwargs  # repos call dict(result.single()); mock .single() to return a plain dict


# ---------------------------------------------------------------------------
# Repository — Framework
# ---------------------------------------------------------------------------


class TestFrameworkRepo:
    def test_upsert_framework_runs_merge_query(self):
        """upsert_framework calls session.run with a MERGE on Framework."""
        req = MagicMock(id="fw-1", name="ISO 27001", version="2022", description="ISMS")
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "fw-1", "name": "ISO 27001", "version": "2022",
            "description": "ISMS", "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_framework(session, req, "2024-01-01T00:00:00+00:00")
        session.run.assert_called_once()
        query = session.run.call_args[0][0]
        assert "MERGE" in query
        assert "Framework" in query

    def test_upsert_framework_returns_dict(self):
        """upsert_framework returns a dict with the expected keys."""
        req = MagicMock(id="fw-1", name="ISO 27001", version=None, description=None)
        session = MagicMock()
        expected = {"id": "fw-1", "name": "ISO 27001", "version": None,
                    "description": None, "created_at": "2024-01-01T00:00:00+00:00"}
        session.run.return_value.single.return_value = expected
        result = knowledge_repo.upsert_framework(session, req, "2024-01-01T00:00:00+00:00")
        assert result["id"] == "fw-1"
        assert result["name"] == "ISO 27001"

    def test_get_framework_returns_none_when_missing(self):
        """get_framework returns None when session.single() returns None."""
        session = MagicMock()
        session.run.return_value.single.return_value = None
        result = knowledge_repo.get_framework(session, "missing-id")
        assert result is None


# ---------------------------------------------------------------------------
# Repository — Control
# ---------------------------------------------------------------------------


class TestControlRepo:
    def test_upsert_control_no_parent_single_query(self):
        """upsert_control with parent_id=None calls session.run exactly once."""
        req = MagicMock(id="c-1", name="A.5", description=None,
                        framework_id="fw-1", parent_id=None)
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "c-1", "name": "A.5", "description": None,
            "framework_id": "fw-1", "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_control(session, req, [0.1, 0.2], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 1

    def test_upsert_control_creates_contains_edge(self):
        """upsert_control with parent_id set calls session.run twice (MERGE + CONTAINS)."""
        req = MagicMock(id="c-2", name="A.5.1", description=None,
                        framework_id="fw-1", parent_id="c-1")
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "c-2", "name": "A.5.1", "description": None,
            "framework_id": "fw-1", "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_control(session, req, [0.1, 0.2], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 2
        contains_query = session.run.call_args_list[1][0][0]
        assert "CONTAINS" in contains_query

    def test_get_control_returns_none_when_missing(self):
        session = MagicMock()
        session.run.return_value.single.return_value = None
        assert knowledge_repo.get_control(session, "x") is None


# ---------------------------------------------------------------------------
# Repository — Norm
# ---------------------------------------------------------------------------


class TestNormRepo:
    def test_upsert_norm_no_optional_edges(self):
        """upsert_norm with no control_id/doc_id calls session.run once."""
        req = MagicMock(id="n-1", name="N1", text="Must encrypt",
                        status="draft", effective_date=None,
                        control_id=None, doc_id=None)
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "n-1", "name": "N1", "text": "Must encrypt",
            "status": "draft", "effective_date": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_norm(session, req, [0.1], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 1

    def test_upsert_norm_creates_implements_edge(self):
        """upsert_norm with control_id set creates IMPLEMENTS edge (run called twice)."""
        req = MagicMock(id="n-1", name="N1", text="Must encrypt",
                        status="draft", effective_date=None,
                        control_id="c-1", doc_id=None)
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "n-1", "name": "N1", "text": "Must encrypt",
            "status": "draft", "effective_date": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_norm(session, req, [0.1], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 2
        assert "IMPLEMENTS" in session.run.call_args_list[1][0][0]

    def test_upsert_norm_creates_sourced_from_edge(self):
        """upsert_norm with doc_id set creates SOURCED_FROM edge."""
        req = MagicMock(id="n-1", name="N1", text="Must encrypt",
                        status="draft", effective_date=None,
                        control_id=None, doc_id="doc-1")
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "n-1", "name": "N1", "text": "Must encrypt",
            "status": "draft", "effective_date": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_norm(session, req, [0.1], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 2
        assert "SOURCED_FROM" in session.run.call_args_list[1][0][0]

    def test_upsert_norm_both_optional_edges(self):
        """upsert_norm with both control_id and doc_id calls session.run three times."""
        req = MagicMock(id="n-1", name="N1", text="Must encrypt",
                        status="draft", effective_date=None,
                        control_id="c-1", doc_id="doc-1")
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "n-1", "name": "N1", "text": "Must encrypt",
            "status": "draft", "effective_date": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_norm(session, req, [0.1], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 3


# ---------------------------------------------------------------------------
# Repository — Chunk
# ---------------------------------------------------------------------------


class TestChunkRepo:
    def test_upsert_chunk_creates_has_chunk_edge(self):
        """upsert_chunk always creates HAS_CHUNK edge (run called at least twice)."""
        req = MagicMock(id="ch-1", text="foo", sequence=0,
                        doc_id="doc-1", prev_chunk_id=None)
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "ch-1", "text": "foo", "sequence": 0,
            "doc_id": "doc-1", "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_chunk(session, req, [0.1], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 2
        has_chunk_query = session.run.call_args_list[1][0][0]
        assert "HAS_CHUNK" in has_chunk_query

    def test_upsert_chunk_creates_has_next_edge(self):
        """upsert_chunk with prev_chunk_id creates HAS_NEXT edge (run called three times)."""
        req = MagicMock(id="ch-2", text="bar", sequence=1,
                        doc_id="doc-1", prev_chunk_id="ch-1")
        session = MagicMock()
        session.run.return_value.single.return_value = {
            "id": "ch-2", "text": "bar", "sequence": 1,
            "doc_id": "doc-1", "created_at": "2024-01-01T00:00:00+00:00"
        }
        knowledge_repo.upsert_chunk(session, req, [0.1], "2024-01-01T00:00:00+00:00")
        assert session.run.call_count == 3
        has_next_query = session.run.call_args_list[2][0][0]
        assert "HAS_NEXT" in has_next_query

    def test_get_chunk_returns_none_when_missing(self):
        session = MagicMock()
        session.run.return_value.single.return_value = None
        assert knowledge_repo.get_chunk(session, "missing") is None


# ---------------------------------------------------------------------------
# Route handlers (FastAPI TestClient)
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """Return (TestClient, mock_session) with feature flag enabled and knowledge routes active.

    Reloads config + main to ensure settings.enable_knowledge_layer=True regardless of
    import order. Patches get_driver so the lifespan uses a mock (no live Memgraph needed).
    """
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


class TestKnowledgeRoutes:
    def test_post_framework_returns_200(self, app_client):
        client, session = app_client
        session.run.return_value.single.return_value = {
            "id": "fw-1", "name": "ISO 27001", "version": "2022",
            "description": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        resp = client.post("/knowledge/frameworks", json={
            "id": "fw-1", "name": "ISO 27001", "version": "2022"
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "fw-1"

    def test_get_framework_not_found_returns_404(self, app_client):
        client, session = app_client
        session.run.return_value.single.return_value = None
        resp = client.get("/knowledge/frameworks/nonexistent")
        assert resp.status_code == 404

    def test_get_framework_returns_200(self, app_client):
        client, session = app_client
        session.run.return_value.single.return_value = {
            "id": "fw-1", "name": "ISO 27001", "version": None,
            "description": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        resp = client.get("/knowledge/frameworks/fw-1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "ISO 27001"

    def test_post_control_calls_get_embedding_with_model_name(self, app_client):
        """POST /knowledge/controls calls get_embedding with knowledge_embedding_model."""
        client, session = app_client
        session.run.return_value.single.return_value = {
            "id": "c-1", "name": "A.5", "description": None,
            "framework_id": "fw-1", "created_at": "2024-01-01T00:00:00+00:00"
        }
        with patch("memory_service.knowledge_routes.get_embedding",
                   return_value=[0.1, 0.2]) as mock_embed:
            resp = client.post("/knowledge/controls", json={
                "id": "c-1", "name": "A.5", "framework_id": "fw-1"
            })
        assert resp.status_code == 200
        mock_embed.assert_called_once()
        _, kwargs = mock_embed.call_args
        assert "model_name" in kwargs

    def test_post_norm_embeds_text_field(self, app_client):
        """POST /knowledge/norms calls get_embedding with req.text."""
        client, session = app_client
        session.run.return_value.single.return_value = {
            "id": "n-1", "name": "N1", "text": "Must encrypt",
            "status": "draft", "effective_date": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        with patch("memory_service.knowledge_routes.get_embedding",
                   return_value=[0.1]) as mock_embed:
            resp = client.post("/knowledge/norms", json={
                "id": "n-1", "name": "N1", "text": "Must encrypt"
            })
        assert resp.status_code == 200
        called_text = mock_embed.call_args[0][0]
        assert called_text == "Must encrypt"

    def test_post_document_does_not_call_get_embedding(self, app_client):
        """POST /knowledge/documents does NOT call get_embedding (no embedding on Document)."""
        client, session = app_client
        session.run.return_value.single.return_value = {
            "id": "doc-1", "title": "Policy", "doc_type": "policy",
            "source_url": None, "created_at": "2024-01-01T00:00:00+00:00"
        }
        with patch("memory_service.knowledge_routes.get_embedding") as mock_embed:
            resp = client.post("/knowledge/documents", json={
                "id": "doc-1", "title": "Policy", "doc_type": "policy"
            })
        assert resp.status_code == 200
        mock_embed.assert_not_called()

    def test_post_chunk_calls_get_embedding(self, app_client):
        """POST /knowledge/chunks calls get_embedding with req.text."""
        client, session = app_client
        session.run.return_value.single.return_value = {
            "id": "ch-1", "text": "Chapter 1", "sequence": 0,
            "doc_id": "doc-1", "created_at": "2024-01-01T00:00:00+00:00"
        }
        with patch("memory_service.knowledge_routes.get_embedding",
                   return_value=[0.1]) as mock_embed:
            resp = client.post("/knowledge/chunks", json={
                "id": "ch-1", "text": "Chapter 1", "sequence": 0, "doc_id": "doc-1"
            })
        assert resp.status_code == 200
        assert mock_embed.call_args[0][0] == "Chapter 1"

    def test_get_norm_not_found_returns_404(self, app_client):
        client, session = app_client
        session.run.return_value.single.return_value = None
        resp = client.get("/knowledge/norms/missing")
        assert resp.status_code == 404

    def test_get_document_not_found_returns_404(self, app_client):
        client, session = app_client
        session.run.return_value.single.return_value = None
        resp = client.get("/knowledge/documents/missing")
        assert resp.status_code == 404

    def test_get_chunk_not_found_returns_404(self, app_client):
        client, session = app_client
        session.run.return_value.single.return_value = None
        resp = client.get("/knowledge/chunks/missing")
        assert resp.status_code == 404

    def test_knowledge_routes_absent_when_flag_off(self):
        """When ENABLE_KNOWLEDGE_LAYER=false, no /knowledge routes are registered."""
        # Temporarily override the env var and reimport
        import importlib
        original = os.environ.get("ENABLE_KNOWLEDGE_LAYER", "")
        try:
            os.environ["ENABLE_KNOWLEDGE_LAYER"] = "false"
            import memory_service.config as cfg_mod
            importlib.reload(cfg_mod)
            import memory_service.main as main_mod
            importlib.reload(main_mod)
            knowledge_paths = [r.path for r in main_mod.app.routes
                               if hasattr(r, "path") and r.path.startswith("/knowledge")]
            assert knowledge_paths == [], f"Expected no /knowledge routes, got: {knowledge_paths}"
        finally:
            os.environ["ENABLE_KNOWLEDGE_LAYER"] = original or "true"
            importlib.reload(cfg_mod)
            importlib.reload(main_mod)
