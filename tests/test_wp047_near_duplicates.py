# tests/test_wp047_near_duplicates.py
"""Tests for WP-047: near-duplicate detection."""
import json
import httpx
import pytest
import respx
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from tests.conftest import cleanup_nodes
from memory_client.cli import app as cli_app
from memory_client.client import MemoryClient

_AGENT_ID = "test-agent-wp047"
_BASE_URL = "http://localhost:8000"
_cli_runner = CliRunner()

_SAMPLE_PAIRS = [
    {
        "a": {"id": "id-1", "text": "Memory one"},
        "b": {"id": "id-2", "text": "Memory two"},
        "similarity": 0.95,
    }
]


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


def _add_body(fact: str, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 1,
        "tags": ["test"],
    }
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Task 2 — Unit: cosine_similarity helper
# ---------------------------------------------------------------------------
class TestCosineSimilarity:
    def test_identical_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_vector_returns_zero(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([], [1.0, 0.0]) == 0.0

    def test_zero_norm_returns_zero(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# Task 3 — Integration: GET /memory/duplicates endpoint
# ---------------------------------------------------------------------------
class TestDuplicatesEndpoint:
    @pytest.mark.integration
    def test_near_duplicates_found(self, client, test_driver):
        """Two very similar memories appear as a near-duplicate pair."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("The API server is not responding to requests"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body("The API server has stopped responding to requests"))
            mid_b = r2.json()["memory_id"]

            # Use a low threshold to catch semantically similar memories; high limit to ensure pair is not pushed out
            r3 = client.get("/memory/duplicates", params={"threshold": 0.80, "limit": 100})
            assert r3.status_code == 200
            pairs = r3.json()
            pair_sets = [{p["a"]["id"], p["b"]["id"]} for p in pairs]
            assert {mid_a, mid_b} in pair_sets
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_unrelated_memories_not_paired(self, client, test_driver):
        """Two unrelated memories do not appear as duplicates."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("Oliver likes chocolate ice cream in summer"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body("The Kubernetes deployment pipeline uses Helm charts"))
            mid_b = r2.json()["memory_id"]

            r3 = client.get("/memory/duplicates", params={"threshold": 0.90, "limit": 50})
            assert r3.status_code == 200
            pairs = r3.json()
            pair_sets = [{p["a"]["id"], p["b"]["id"]} for p in pairs]
            assert {mid_a, mid_b} not in pair_sets
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_archived_memories_excluded(self, client, test_driver):
        """Archived memories do not appear in duplicate results."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("WP047 archived dup test alpha"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body("WP047 archived dup test alpha"))  # exact dup would be caught by WP-088, use different route
            mid_b = r2.json()["memory_id"]

            # Archive one
            archive_resp = client.post(f"/memory/{mid_a}/archive")
            assert archive_resp.status_code == 200

            r3 = client.get("/memory/duplicates", params={"threshold": 0.80, "limit": 50})
            assert r3.status_code == 200
            pairs = r3.json()
            all_ids = set()
            for p in pairs:
                all_ids.add(p["a"]["id"])
                all_ids.add(p["b"]["id"])
            assert mid_a not in all_ids
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    def test_default_params(self, client):
        """Endpoint works with default params."""
        r = client.get("/memory/duplicates")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------------------------------------------------------------------
# Task 4 — Unit: client, CLI, MCP
# ---------------------------------------------------------------------------
class TestClientFindDuplicates:
    @respx.mock
    def test_find_duplicates_default(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=_SAMPLE_PAIRS)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.find_duplicates()
        assert len(result) == 1
        assert result[0]["similarity"] == 0.95

    @respx.mock
    def test_find_duplicates_with_params(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=_SAMPLE_PAIRS)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.find_duplicates(threshold=0.90, limit=5)
        req = respx.calls.last.request
        assert "threshold=0.9" in str(req.url)
        assert "limit=5" in str(req.url)


class TestCliFindDuplicates:
    @respx.mock
    def test_find_duplicates_output(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=_SAMPLE_PAIRS)
        )
        result = _cli_runner.invoke(cli_app, ["find-duplicates"], env={"API_BASE_URL": _BASE_URL})
        assert result.exit_code == 0
        assert "0.95" in result.output
        assert "id-1" in result.output

    @respx.mock
    def test_find_duplicates_empty(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = _cli_runner.invoke(cli_app, ["find-duplicates"], env={"API_BASE_URL": _BASE_URL})
        assert result.exit_code == 0
        assert "No near-duplicate" in result.output


class TestMcpFindDuplicates:
    def test_find_duplicates_calls_client(self):
        from mcp_server.server import memory_find_duplicates

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.find_duplicates.return_value = _SAMPLE_PAIRS

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_find_duplicates()

        mock_client.find_duplicates.assert_called_once_with(threshold=None, limit=None)
        assert len(result) == 1
