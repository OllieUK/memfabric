"""
tests/test_search_memory.py — Integration tests for POST /memory/search (WP-005).

Requires Memgraph running with schema initialised (run scripts/init_schema.py first).
All tests clean up their own nodes.
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

from tests.conftest import cleanup_nodes


# Test-specific node ids — prefixed to avoid colliding with other test modules
_AGENT_ID = "test-search-agent-001"
_AGENT_ID_2 = "test-search-agent-002"
_PROJECT_ID = "test-search-project-001"
_PROJECT_ID_2 = "test-search-project-002"

_CONTEXT_IDS = {
    "Agent": _AGENT_ID,
    "Project": _PROJECT_ID,
}


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids, extra_ids=_CONTEXT_IDS)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID_2)
        session.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=_PROJECT_ID_2)


def _add(client, text, *, type="fact", tags=None, agent_id=_AGENT_ID,
         project_id=None, related_ids=None):
    """Insert a Memory via POST /memory and return its id."""
    body = {"text": text, "type": type, "agent_id": agent_id}
    if tags is not None:
        body["tags"] = tags
    if project_id is not None:
        body["project_id"] = project_id
    if related_ids is not None:
        body["related_ids"] = related_ids
    r = client.post("/memory", json=body)
    assert r.status_code == 200, f"Failed to insert memory: {r.text}"
    return r.json()["memory_id"]


def _search(client, query, **kwargs):
    """POST /memory/search and return the response object."""
    body = {"query": query, **kwargs}
    return client.post("/memory/search", json=body)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchBasic:
    def test_search_response_has_correct_shape(self, client, test_driver):
        """Search returns a valid response with the expected top-level structure."""
        r = _search(client, "zzz_unique_nonexistent_query_xyzzy_9999", limit=1)
        assert r.status_code == 200
        data = r.json()
        assert "memories" in data
        assert isinstance(data["memories"], list)

    def test_basic_search_finds_inserted_memory(self, client, test_driver):
        mid = _add(client, "the capital of France is Paris")
        r = _search(client, "capital city of France")
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid in ids
        _cleanup(test_driver, mid)

    def test_result_has_all_required_fields(self, client, test_driver):
        mid = _add(client, "Python is a programming language")
        r = _search(client, "programming language")
        assert r.status_code == 200
        memories = r.json()["memories"]
        assert len(memories) > 0
        hit = next((m for m in memories if m["id"] == mid), None)
        assert hit is not None, f"Expected {mid} in results"
        assert "id" in hit
        assert "text" in hit
        assert "type" in hit
        assert "tags" in hit
        assert "importance" in hit
        assert "neighbours" in hit
        _cleanup(test_driver, mid)


class TestSearchOrdering:
    def test_closer_result_ranks_first(self, client, test_driver):
        """Insert one near and one far memory; the near one should rank first."""
        near_id = _add(client, "the quick brown fox jumps over the lazy dog")
        far_id = _add(client, "quarterly budget review spreadsheet analysis")
        r = _search(client, "a fox leaping over a dog", limit=10)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        if near_id in ids and far_id in ids:
            assert ids.index(near_id) < ids.index(far_id), \
                "Near memory should rank before far memory"
        _cleanup(test_driver, near_id, far_id)


class TestSearchLimit:
    def test_limit_caps_results(self, client, test_driver):
        ids = [_add(client, f"limit test memory number {i}") for i in range(5)]
        r = _search(client, "limit test memory", limit=2)
        assert r.status_code == 200
        assert len(r.json()["memories"]) <= 2
        _cleanup(test_driver, *ids)

    def test_limit_zero_returns_422(self, client, test_driver):
        r = _search(client, "test", limit=0)
        assert r.status_code == 422

    def test_limit_over_max_returns_422(self, client, test_driver):
        r = _search(client, "test", limit=101)
        assert r.status_code == 422

    def test_max_hops_over_limit_returns_422(self, client, test_driver):
        r = _search(client, "test", max_hops=4)
        assert r.status_code == 422


class TestSearchTagFilter:
    def test_tag_filter_includes_matching(self, client, test_driver):
        mid = _add(client, "Python async programming tips", tags=["python"])
        r = _search(client, "programming tips", tags=["python"])
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid in ids
        _cleanup(test_driver, mid)

    def test_tag_filter_excludes_non_matching(self, client, test_driver):
        mid = _add(client, "Rust systems programming guide", tags=["rust"])
        r = _search(client, "systems programming", tags=["python"], limit=50)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid not in ids
        _cleanup(test_driver, mid)


class TestSearchAgentFilter:
    def test_agent_filter_includes_matching(self, client, test_driver):
        mid = _add(client, "agent filter include test", agent_id=_AGENT_ID)
        r = _search(client, "agent filter include test", agent_ids=[_AGENT_ID])
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid in ids
        _cleanup(test_driver, mid)

    def test_agent_filter_excludes_other_agents(self, client, test_driver):
        mid = _add(client, "agent filter exclude test", agent_id=_AGENT_ID_2)
        r = _search(client, "agent filter exclude test", agent_ids=[_AGENT_ID], limit=50)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid not in ids
        _cleanup(test_driver, mid)


class TestSearchProjectFilter:
    def test_project_filter_includes_matching(self, client, test_driver):
        mid = _add(client, "project filter include test", project_id=_PROJECT_ID)
        r = _search(client, "project filter include test", project_ids=[_PROJECT_ID])
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid in ids
        _cleanup(test_driver, mid)

    def test_project_filter_excludes_non_matching(self, client, test_driver):
        mid = _add(client, "project filter exclude test", project_id=_PROJECT_ID_2)
        r = _search(client, "project filter exclude test", project_ids=[_PROJECT_ID], limit=50)
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["memories"]]
        assert mid not in ids
        _cleanup(test_driver, mid)


class TestSearchGraphExpansion:
    def test_max_hops_0_returns_empty_neighbours(self, client, test_driver):
        seed_id = _add(client, "seed memory for hops test")
        mid = _add(client, "memory with explicit relation", related_ids=[seed_id])
        r = _search(client, "memory with explicit relation", max_hops=0, limit=50)
        assert r.status_code == 200
        hit = next((m for m in r.json()["memories"] if m["id"] == mid), None)
        assert hit is not None, f"Expected memory {mid} in search results"
        assert hit["neighbours"] == []
        _cleanup(test_driver, seed_id, mid)

    def test_max_hops_1_returns_direct_neighbours(self, client, test_driver):
        seed_id = _add(client, "neighbour memory for hops test")
        mid = _add(client, "hub memory pointing to neighbour", related_ids=[seed_id])
        r = _search(client, "hub memory pointing to neighbour", max_hops=1, limit=50)
        assert r.status_code == 200
        hit = next((m for m in r.json()["memories"] if m["id"] == mid), None)
        assert hit is not None, f"Expected memory {mid} in search results"
        assert seed_id in hit["neighbours"]
        _cleanup(test_driver, seed_id, mid)


class TestSearchDbUnavailable:
    def test_returns_503_when_db_down(self, test_driver):
        """Inject a driver that raises ServiceUnavailable; expect 503."""
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_driver.session.side_effect = ServiceUnavailable("connection refused")

        original_driver = getattr(app.state, "driver", None)
        app.state.driver = mock_driver
        try:
            with TestClient(app) as c:
                response = c.post("/memory/search", json={"query": "test"})
            assert response.status_code == 503
        finally:
            app.state.driver = original_driver
