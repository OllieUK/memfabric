"""
tests/test_wp071.py — Unit tests for WP-071 knowledge_repo search/list functions (Group A).

All tests are unit tests with mocked sessions — no live stack required.
"""

import pytest
from unittest.mock import MagicMock

from cyber_knowledge import repo as knowledge_repo


# ---------------------------------------------------------------------------
# Helper: FakeRecord for mocking neo4j records
# ---------------------------------------------------------------------------


class FakeRecord(dict):
    """A dict subclass that passes through dict(r) correctly for mocking neo4j records."""
    pass


# ---------------------------------------------------------------------------
# search_controls tests
# ---------------------------------------------------------------------------


class TestSearchControls:
    """Unit tests for search_controls function."""

    def test_search_controls_calls_vector_search(self):
        """Test that search_controls calls vector_search with correct index name."""
        mock_session = MagicMock()
        mock_session.run.return_value = []

        knowledge_repo.search_controls(
            mock_session,
            query_embedding=[0.1, 0.2, 0.3],
            limit=5,
            framework_id=None,
        )

        # Assert session.run was called once
        assert mock_session.run.call_count == 1

        # Assert the Cypher string contains the correct index name
        call_args = mock_session.run.call_args
        cypher_string = call_args[0][0]
        assert "ctrl_embedding_idx" in cypher_string
        assert isinstance(cypher_string, str)

    def test_search_controls_framework_id_filter(self):
        """Test that search_controls passes framework_id parameter correctly."""
        mock_session = MagicMock()
        mock_session.run.return_value = []

        knowledge_repo.search_controls(
            mock_session,
            query_embedding=[0.1, 0.2, 0.3],
            limit=5,
            framework_id="fw-1",
        )

        # Assert framework_id was passed in kwargs
        call_kwargs = mock_session.run.call_args[1]
        assert "framework_id" in call_kwargs
        assert call_kwargs["framework_id"] == "fw-1"

    def test_search_controls_no_framework_id(self):
        """Test that search_controls handles framework_id=None without exception."""
        mock_session = MagicMock()
        mock_session.run.return_value = []

        # Should not raise
        knowledge_repo.search_controls(
            mock_session,
            query_embedding=[0.1, 0.2, 0.3],
            limit=5,
            framework_id=None,
        )

        call_kwargs = mock_session.run.call_args[1]
        assert call_kwargs["framework_id"] is None

    def test_search_controls_returns_dicts(self):
        """Test that search_controls returns a list of dicts."""
        mock_session = MagicMock()

        # Create 2 mock records that can be converted to dicts
        record1 = FakeRecord(
            id="c1",
            name="Control 1",
            description="Desc 1",
            framework_id="fw-1",
            created_at="2026-01-01",
            distance=0.1,
        )
        record2 = FakeRecord(
            id="c2",
            name="Control 2",
            description="Desc 2",
            framework_id="fw-1",
            created_at="2026-01-02",
            distance=0.2,
        )
        mock_session.run.return_value = [record1, record2]

        result = knowledge_repo.search_controls(
            mock_session,
            query_embedding=[0.1, 0.2, 0.3],
            limit=5,
            framework_id=None,
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "c1"
        assert result[0]["name"] == "Control 1"
        assert result[1]["id"] == "c2"


# ---------------------------------------------------------------------------
# search_chunks tests
# ---------------------------------------------------------------------------


class TestSearchChunks:
    """Unit tests for search_chunks function."""

    def test_search_chunks_calls_vector_search(self):
        """Test that search_chunks calls vector_search with correct index name."""
        mock_session = MagicMock()
        mock_session.run.return_value = []

        knowledge_repo.search_chunks(
            mock_session,
            query_embedding=[0.1, 0.2, 0.3],
            limit=5,
            doc_id=None,
        )

        # Assert session.run was called once
        assert mock_session.run.call_count == 1

        # Assert the Cypher string contains the correct index name
        call_args = mock_session.run.call_args
        cypher_string = call_args[0][0]
        assert "chunk_embedding_idx" in cypher_string

    def test_search_chunks_doc_id_filter(self):
        """Test that search_chunks passes doc_id parameter correctly."""
        mock_session = MagicMock()
        mock_session.run.return_value = []

        knowledge_repo.search_chunks(
            mock_session,
            query_embedding=[0.1, 0.2, 0.3],
            limit=5,
            doc_id="doc-1",
        )

        # Assert doc_id was passed in kwargs
        call_kwargs = mock_session.run.call_args[1]
        assert "doc_id" in call_kwargs
        assert call_kwargs["doc_id"] == "doc-1"


# ---------------------------------------------------------------------------
# list_norms tests
# ---------------------------------------------------------------------------


class TestListNorms:
    """Unit tests for list_norms function."""

    def test_list_norms_returns_all(self):
        """Test that list_norms returns all Norm nodes."""
        mock_session = MagicMock()

        # Create 3 mock records
        records = [
            FakeRecord(
                id="n1",
                name="Norm 1",
                text="Text 1",
                status="active",
                effective_date="2026-01-01",
                created_at="2026-01-01",
            ),
            FakeRecord(
                id="n2",
                name="Norm 2",
                text="Text 2",
                status="active",
                effective_date="2026-01-02",
                created_at="2026-01-02",
            ),
            FakeRecord(
                id="n3",
                name="Norm 3",
                text="Text 3",
                status="pending",
                effective_date="2026-01-03",
                created_at="2026-01-03",
            ),
        ]
        mock_session.run.return_value = records

        result = knowledge_repo.list_norms(mock_session)

        assert len(result) == 3
        assert result[0]["id"] == "n1"
        assert result[1]["id"] == "n2"
        assert result[2]["id"] == "n3"

    def test_list_norms_empty(self):
        """Test that list_norms returns empty list when no Norms exist."""
        mock_session = MagicMock()
        mock_session.run.return_value = []

        result = knowledge_repo.list_norms(mock_session)

        assert result == []


# ---------------------------------------------------------------------------
# list_documents tests
# ---------------------------------------------------------------------------


class TestListDocuments:
    """Unit tests for list_documents function."""

    def test_list_documents_returns_all(self):
        """Test that list_documents returns all Document nodes."""
        mock_session = MagicMock()
        mock_session.run.return_value = [
            FakeRecord(id="d1", title="Doc 1", doc_type="policy", source_url=None, created_at="2026-01-01T00:00:00+00:00"),
            FakeRecord(id="d2", title="Doc 2", doc_type="standard", source_url="https://example.com", created_at="2026-01-01T00:00:00+00:00"),
        ]
        result = knowledge_repo.list_documents(mock_session)
        assert len(result) == 2
        assert result[0]["id"] == "d1"
        assert result[1]["id"] == "d2"

    def test_list_documents_empty(self):
        """Test that list_documents returns empty list when no Documents exist."""
        mock_session = MagicMock()
        mock_session.run.return_value = []
        result = knowledge_repo.list_documents(mock_session)
        assert result == []


# ---------------------------------------------------------------------------
# list_incomplete_jurisdictions tests
# ---------------------------------------------------------------------------


class TestListIncompleteJurisdictions:
    """Unit tests for list_incomplete_jurisdictions function."""

    def test_list_incomplete_jurisdictions_structure(self):
        """Test that list_incomplete_jurisdictions returns correct structure."""
        mock_session = MagicMock()

        # First session.run call returns 2 Norm records
        norm_records = [
            FakeRecord(id="n1", name="Norm 1"),
            FakeRecord(id="n2", name="Norm 2"),
        ]

        # Second session.run call returns 1 Control record
        control_records = [
            FakeRecord(id="c1", name="Control 1"),
        ]

        # side_effect makes each call return different values in sequence
        mock_session.run.side_effect = [
            iter(norm_records),
            iter(control_records),
        ]

        result = knowledge_repo.list_incomplete_jurisdictions(mock_session)

        # Check structure
        assert "norms_without_jurisdiction" in result
        assert "controls_without_jurisdiction" in result

        # Check lengths
        assert len(result["norms_without_jurisdiction"]) == 2
        assert len(result["controls_without_jurisdiction"]) == 1

        # Check content
        assert result["norms_without_jurisdiction"][0]["id"] == "n1"
        assert result["norms_without_jurisdiction"][1]["id"] == "n2"
        assert result["controls_without_jurisdiction"][0]["id"] == "c1"


# ---------------------------------------------------------------------------
# GROUP B: Route handlers (FastAPI TestClient) — Search and list endpoints
# ---------------------------------------------------------------------------

import os
os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from unittest.mock import patch
import importlib

from memory_service.config import settings


@pytest.fixture
def app_client_b():
    """Return (TestClient, mock_session) for Group B route tests.

    Reloads config + main to ensure settings.enable_knowledge_layer=True.
    Patches get_driver so the lifespan uses a mock (no live Memgraph needed).
    """
    import memory_service.config as cfg_mod
    import memory_service.main as main_mod

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


class TestSearchControlsRoute:
    """Tests for POST /knowledge/search/controls route."""

    def test_post_search_controls_returns_hits(self, app_client_b):
        """POST /knowledge/search/controls returns 200 with ControlHit list."""
        client, session = app_client_b

        mock_hit = {
            "id": "c1",
            "name": "Test",
            "description": None,
            "framework_id": "fw1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "distance": 0.1,
        }
        with patch("cyber_knowledge.routes.knowledge_repo.search_controls",
                   return_value=[mock_hit]):
            with patch("cyber_knowledge.routes.get_embedding",
                       return_value=[0.1, 0.2, 0.3]):
                resp = client.post("/knowledge/search/controls",
                                   json={"query": "test", "limit": 5})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "c1"
        assert data[0]["distance"] == 0.1

    def test_post_search_controls_calls_get_embedding(self, app_client_b):
        """POST /knowledge/search/controls calls get_embedding with knowledge model."""
        client, session = app_client_b

        with patch("cyber_knowledge.routes.knowledge_repo.search_controls",
                   return_value=[]):
            with patch("cyber_knowledge.routes.get_embedding",
                       return_value=[0.1]) as mock_emb:
                resp = client.post("/knowledge/search/controls",
                                   json={"query": "test query", "limit": 5})

        assert resp.status_code == 200
        mock_emb.assert_called_once()
        # Check that get_embedding was called with model_name kwarg
        call_kwargs = mock_emb.call_args[1]
        assert "model_name" in call_kwargs
        assert call_kwargs["model_name"] == settings.knowledge_embedding_model


class TestSearchChunksRoute:
    """Tests for POST /knowledge/search/chunks route."""

    def test_post_search_chunks_returns_hits(self, app_client_b):
        """POST /knowledge/search/chunks returns 200 with ChunkHit list."""
        client, session = app_client_b

        mock_hit = {
            "id": "ch1",
            "text": "Some text",
            "sequence": 1,
            "doc_id": "d1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "distance": 0.2,
        }
        with patch("cyber_knowledge.routes.knowledge_repo.search_chunks",
                   return_value=[mock_hit]):
            with patch("cyber_knowledge.routes.get_embedding",
                       return_value=[0.1, 0.2, 0.3]):
                resp = client.post("/knowledge/search/chunks",
                                   json={"query": "test", "limit": 5})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "ch1"
        assert data[0]["sequence"] == 1

    def test_post_search_chunks_calls_get_embedding(self, app_client_b):
        """POST /knowledge/search/chunks calls get_embedding with knowledge model."""
        client, session = app_client_b

        with patch("cyber_knowledge.routes.knowledge_repo.search_chunks",
                   return_value=[]):
            with patch("cyber_knowledge.routes.get_embedding",
                       return_value=[0.1]) as mock_emb:
                resp = client.post("/knowledge/search/chunks",
                                   json={"query": "chunk query", "limit": 5})

        assert resp.status_code == 200
        mock_emb.assert_called_once()
        call_kwargs = mock_emb.call_args[1]
        assert "model_name" in call_kwargs
        assert call_kwargs["model_name"] == settings.knowledge_embedding_model


class TestListNormsRoute:
    """Tests for GET /knowledge/norms route."""

    def test_get_norms_returns_list(self, app_client_b):
        """GET /knowledge/norms returns 200 with NormResponse list."""
        client, session = app_client_b

        mock_norms = [
            {
                "id": "n1",
                "name": "Norm 1",
                "text": "Some requirement",
                "status": "active",
                "effective_date": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "n2",
                "name": "Norm 2",
                "text": "Another requirement",
                "status": "draft",
                "effective_date": None,
                "created_at": "2026-01-02T00:00:00+00:00",
            },
        ]
        with patch("cyber_knowledge.routes.knowledge_repo.list_norms",
                   return_value=mock_norms):
            resp = client.get("/knowledge/norms")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "n1"
        assert data[1]["id"] == "n2"

    def test_get_norms_empty_list(self, app_client_b):
        """GET /knowledge/norms returns empty list when no norms exist."""
        client, session = app_client_b

        with patch("cyber_knowledge.routes.knowledge_repo.list_norms",
                   return_value=[]):
            resp = client.get("/knowledge/norms")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestListDocumentsRoute:
    """Tests for GET /knowledge/documents route."""

    def test_get_documents_returns_list(self, app_client_b):
        """GET /knowledge/documents returns 200 with DocumentResponse list."""
        client, session = app_client_b

        mock_docs = [
            {
                "id": "d1",
                "title": "Policy A",
                "doc_type": "policy",
                "source_url": None,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ]
        with patch("cyber_knowledge.routes.knowledge_repo.list_documents",
                   return_value=mock_docs):
            resp = client.get("/knowledge/documents")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "d1"
        assert data[0]["title"] == "Policy A"


class TestListIncompleteJurisdictionsRoute:
    """Tests for GET /knowledge/incomplete-jurisdictions route."""

    def test_get_incomplete_jurisdictions_structure(self, app_client_b):
        """GET /knowledge/incomplete-jurisdictions returns dict with expected keys."""
        client, session = app_client_b

        mock_result = {
            "norms_without_jurisdiction": [],
            "controls_without_jurisdiction": [],
        }
        with patch("cyber_knowledge.routes.knowledge_repo.list_incomplete_jurisdictions",
                   return_value=mock_result):
            resp = client.get("/knowledge/incomplete-jurisdictions")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "norms_without_jurisdiction" in data
        assert "controls_without_jurisdiction" in data
