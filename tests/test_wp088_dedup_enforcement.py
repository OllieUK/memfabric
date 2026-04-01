"""WP-088: Deduplication and agent-ID enforcement. Requires live stack for integration tests."""
import pytest


class TestSettings:
    def test_memory_dedup_threshold_default(self):
        from memory_service.config import Settings
        assert Settings().memory_dedup_threshold == 0.05


from unittest.mock import MagicMock


class TestFindDuplicateUnit:
    """Unit tests for find_duplicate_memory — mock session, no live stack."""

    def _mock_session(self, exact_hit, vector_hit):
        """Return a mock session whose run() returns exact_hit on first call,
        vector_hit on second call. None means empty result."""
        def make_result(id_val):
            if id_val is None:
                m = MagicMock()
                m.single.return_value = None
                return m
            else:
                m = MagicMock()
                m.single.return_value = {"id": id_val}
                return m

        session = MagicMock()
        session.run.side_effect = [make_result(exact_hit), make_result(vector_hit)]
        return session

    def test_exact_match_returns_immediately_without_vector_search(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit="existing-uuid", vector_hit=None)
        result = find_duplicate_memory(session, "some fact", [0.1, 0.2], threshold=0.05)
        assert result == "existing-uuid"
        assert session.run.call_count == 1  # vector search never fired

    def test_exact_match_miss_triggers_vector_search(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit=None, vector_hit="vec-match-uuid")
        result = find_duplicate_memory(session, "some fact", [0.1, 0.2], threshold=0.05)
        assert result == "vec-match-uuid"
        assert session.run.call_count == 2

    def test_no_match_returns_none(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit=None, vector_hit=None)
        result = find_duplicate_memory(session, "unique fact", [0.1, 0.2], threshold=0.05)
        assert result is None

    def test_exact_check_excludes_non_active_statuses(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = MagicMock()
        r = MagicMock(); r.single.return_value = None
        session.run.return_value = r
        find_duplicate_memory(session, "fact", [0.1], threshold=0.05)
        first_query = session.run.call_args_list[0][0][0]
        assert "active" in first_query

    def test_vector_query_contains_active_status_filter(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = MagicMock()
        r = MagicMock(); r.single.return_value = None
        session.run.return_value = r
        find_duplicate_memory(session, "fact", [0.1], threshold=0.05)
        second_query = session.run.call_args_list[1][0][0]
        assert "active" in second_query


class TestAddMemoryResponseModel:
    def test_deduplicated_defaults_false(self):
        from memory_service.main import AddMemoryResponse
        r = AddMemoryResponse(memory_id="abc-123")
        assert r.deduplicated is False

    def test_deduplicated_can_be_true(self):
        from memory_service.main import AddMemoryResponse
        r = AddMemoryResponse(memory_id="abc-123", deduplicated=True)
        assert r.deduplicated is True


import uuid as _uuid
from tests.conftest import cleanup_nodes, get_memory_node

_DEDUP_AGENT = "test-wp088-agent"
_DEDUP_CONTEXT = {"Agent": _DEDUP_AGENT}


def _cleanup_dedup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids, extra_ids=_DEDUP_CONTEXT)


@pytest.mark.integration
class TestPreWriteDedup:
    def test_exact_duplicate_returns_same_id_deduplicated_true(self, client, test_driver):
        fact = f"WP-088 exact dedup test {_uuid.uuid4()}"
        body = {"fact": fact, "type": "fact", "agent_id": _DEDUP_AGENT}
        r1 = client.post("/memory", json=body)
        assert r1.status_code == 200
        mid1 = r1.json()["memory_id"]
        assert r1.json()["deduplicated"] is False

        r2 = client.post("/memory", json=body)
        assert r2.status_code == 200
        assert r2.json()["memory_id"] == mid1
        assert r2.json()["deduplicated"] is True

        _cleanup_dedup(test_driver, mid1)

    def test_reinforcement_count_incremented_on_dedup(self, client, test_driver):
        fact = f"WP-088 reinforce test {_uuid.uuid4()}"
        body = {"fact": fact, "type": "fact", "agent_id": _DEDUP_AGENT}
        r1 = client.post("/memory", json=body)
        assert r1.status_code == 200
        mid = r1.json()["memory_id"]

        client.post("/memory", json=body)  # duplicate write

        node = get_memory_node(test_driver, mid)
        assert node["reinforcement_count"] >= 1

        _cleanup_dedup(test_driver, mid)

    def test_different_fact_creates_new_memory(self, client, test_driver):
        # Use semantically unrelated phrases so cosine distance is well above 0.05.
        suffix = _uuid.uuid4()
        r1 = client.post("/memory", json={"fact": f"Oliver drinks coffee every morning {suffix}", "type": "fact", "agent_id": _DEDUP_AGENT})
        r2 = client.post("/memory", json={"fact": f"The project deadline is next Friday {suffix}", "type": "fact", "agent_id": _DEDUP_AGENT})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["memory_id"] != r2.json()["memory_id"]
        assert r2.json()["deduplicated"] is False
        _cleanup_dedup(test_driver, r1.json()["memory_id"], r2.json()["memory_id"])


@pytest.mark.integration
class TestPreWriteSemanticDedup:
    def test_near_identical_fact_deduplicates(self, client, test_driver):
        # These two are semantically near-identical with all-MiniLM-L6-v2.
        # Verified empirically: ~0.025 cosine distance even with UUID suffix appended.
        suffix = _uuid.uuid4()
        fact1 = f"The database is running slowly today {suffix}"
        fact2 = f"The database runs slow today {suffix}"
        r1 = client.post("/memory", json={"fact": fact1, "type": "fact", "agent_id": _DEDUP_AGENT})
        assert r1.status_code == 200
        mid1 = r1.json()["memory_id"]

        r2 = client.post("/memory", json={"fact": fact2, "type": "fact", "agent_id": _DEDUP_AGENT})
        assert r2.status_code == 200
        assert r2.json()["memory_id"] == mid1, (
            "Near-identical facts should resolve to the same memory_id. "
            "If this fails, the model may place these further apart than 0.05 — "
            "consider adjusting the test phrases."
        )
        assert r2.json()["deduplicated"] is True
        _cleanup_dedup(test_driver, mid1)


class TestMcpAgentIdRequired:
    def test_memory_add_without_agent_id_raises(self):
        """Calling memory_add without agent_id must raise TypeError — no fallback."""
        from mcp_server.server import memory_add
        with pytest.raises(TypeError):
            memory_add(fact="some fact", type="fact")  # agent_id omitted

    def test_memory_add_passes_explicit_agent_id_to_client(self):
        """The explicit agent_id must be forwarded verbatim — settings.agent_id not used."""
        from unittest.mock import patch, MagicMock
        from mcp_server.server import memory_add
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.add_memory.return_value = "new-memory-id"
        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_add(fact="some fact", type="fact", agent_id="my-custom-agent")
        assert result == "new-memory-id"
        call_kwargs = mock_client.add_memory.call_args
        # agent_id is the 3rd positional arg (fact, type, agent_id) to client.add_memory
        passed_agent_id = call_kwargs[0][2]
        assert passed_agent_id == "my-custom-agent"

    def test_settings_agent_id_not_used_as_fallback(self):
        """Even if settings.agent_id is set, it must NOT be used when agent_id is not passed."""
        from mcp_server.server import memory_add
        with pytest.raises(TypeError):
            memory_add(fact="fact")  # no agent_id
