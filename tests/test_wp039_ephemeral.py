# tests/test_wp039_ephemeral.py
#
# Unit tests for WP-039: ephemeral memory support — repo layer and client layer.
# All tests here are pure unit tests (no live Memgraph required).

from unittest.mock import MagicMock, patch

import httpx
import respx

import memory_service.memory_repo as memory_repo
from memory_client.client import MemoryClient
from memory_service.memory_repo import purge_ephemeral_memories
from memory_service.main import AddMemoryRequest


# ---------------------------------------------------------------------------
# Helper: build a mock session whose .run() returns mock results in sequence.
# ---------------------------------------------------------------------------

def _mock_session_with_side_effects(*run_results):
    """Return a MagicMock session whose .run() calls return run_results in order."""
    session = MagicMock()
    session.run.side_effect = list(run_results)
    return session


def _count_result(n: int):
    """Mock result whose .single() returns {"n": n}."""
    result = MagicMock()
    result.single.return_value = {"n": n}
    return result


# ---------------------------------------------------------------------------
# U1: purge_ephemeral_memories returns 0 when no ephemeral nodes exist
# ---------------------------------------------------------------------------

def test_purge_ephemeral_returns_zero_when_none():
    session = _mock_session_with_side_effects(_count_result(0))

    result = purge_ephemeral_memories(session)

    assert result == 0
    # Only the COUNT query should have been called — not the DELETE query
    assert session.run.call_count == 1


# ---------------------------------------------------------------------------
# U2: purge_ephemeral_memories counts first, deletes second, no RETURN on DELETE
# ---------------------------------------------------------------------------

def test_purge_ephemeral_counts_then_deletes():
    delete_result = MagicMock()
    session = _mock_session_with_side_effects(_count_result(3), delete_result)

    result = purge_ephemeral_memories(session)

    assert result == 3
    assert session.run.call_count == 2

    # Second call must contain DETACH DELETE
    second_call_query = session.run.call_args_list[1][0][0]
    assert "DETACH DELETE" in second_call_query

    # Second call must NOT contain RETURN (Memgraph gotcha)
    assert "RETURN" not in second_call_query


# ---------------------------------------------------------------------------
# U11: _SEARCH_QUERY_TEMPLATE contains ephemeral filter
# ---------------------------------------------------------------------------

def test_search_query_template_has_ephemeral_filter():
    assert "m.ephemeral" in memory_repo._SEARCH_QUERY_TEMPLATE


# ---------------------------------------------------------------------------
# U12: _PERSON_SEARCH_QUERY_TEMPLATE contains ephemeral filter
# ---------------------------------------------------------------------------

def test_person_search_query_template_has_ephemeral_filter():
    assert "m.ephemeral" in memory_repo._PERSON_SEARCH_QUERY_TEMPLATE


# ---------------------------------------------------------------------------
# U3: AddMemoryRequest.ephemeral defaults to False
# ---------------------------------------------------------------------------

def test_add_memory_request_ephemeral_defaults_false():
    req = AddMemoryRequest(fact="x", type="fact", agent_id="test")
    assert req.ephemeral is False


# ---------------------------------------------------------------------------
# U4: AddMemoryRequest.ephemeral accepts True
# ---------------------------------------------------------------------------

def test_add_memory_request_ephemeral_accepts_true():
    req = AddMemoryRequest(fact="x", type="fact", agent_id="test", ephemeral=True)
    assert req.ephemeral is True


# ---------------------------------------------------------------------------
# U5: FastAPI handler passes ephemeral=True into repo
# ---------------------------------------------------------------------------

def test_add_memory_endpoint_passes_ephemeral_to_repo(client):
    with patch("memory_service.memory_repo.add_memory") as mock_add, \
         patch("memory_service.memory_repo.find_duplicate_memory", return_value=None):
        response = client.post(
            "/memory",
            json={
                "fact": "test",
                "type": "fact",
                "agent_id": "test",
                "ephemeral": True,
            }
        )
        assert response.status_code == 200
        assert mock_add.called
        call_req = mock_add.call_args[0][1]
        assert call_req.ephemeral is True


# ---------------------------------------------------------------------------
# U6: POST /memory/maintenance/purge-ephemeral returns {deleted: N}
# ---------------------------------------------------------------------------

def test_purge_ephemeral_endpoint_returns_deleted_count(client):
    with patch("memory_service.memory_repo.purge_ephemeral_memories", return_value=7):
        response = client.post("/memory/maintenance/purge-ephemeral")
        assert response.status_code == 200
        assert response.json() == {"deleted": 7}


# ---------------------------------------------------------------------------
# U7: MemoryClient.purge_ephemeral sends POST and returns dict
# ---------------------------------------------------------------------------

BASE = "http://localhost:8000"


class TestPurgeEphemeralClient:
    @respx.mock
    def test_purge_ephemeral_returns_dict_with_deleted(self):
        respx.post(f"{BASE}/memory/maintenance/purge-ephemeral").mock(
            return_value=httpx.Response(200, json={"deleted": 4})
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.purge_ephemeral()
        assert result == {"deleted": 4}


# ---------------------------------------------------------------------------
# U8: MemoryClient.add_memory sends ephemeral=True in body
# ---------------------------------------------------------------------------


class TestAddMemoryEphemeralClient:
    @respx.mock
    def test_add_memory_sends_ephemeral_true_in_body(self):
        route = respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(200, json={"memory_id": "test-id", "deduplicated": False, "strand_ids": []})
        )
        with MemoryClient(base_url=BASE) as client:
            client.add_memory(fact="test", type="fact", agent_id="test-agent", ephemeral=True)
        assert route.call_count == 1
        request_body = route.calls[0].request.content
        # Decode the JSON body
        import json
        body = json.loads(request_body)
        assert "ephemeral" in body
        assert body["ephemeral"] is True

    @respx.mock
    def test_add_memory_sends_ephemeral_false_by_default(self):
        route = respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(200, json={"memory_id": "test-id", "deduplicated": False, "strand_ids": []})
        )
        with MemoryClient(base_url=BASE) as client:
            client.add_memory(fact="test", type="fact", agent_id="test-agent")
        assert route.call_count == 1
        request_body = route.calls[0].request.content
        import json
        body = json.loads(request_body)
        assert "ephemeral" in body
        assert body["ephemeral"] is False


# ---------------------------------------------------------------------------
# U9: CLI purge-ephemeral prints count and exits 0
# ---------------------------------------------------------------------------

@respx.mock
def test_cli_purge_ephemeral_prints_deleted_count():
    """CLI purge-ephemeral command prints the deleted count and exits 0."""
    from typer.testing import CliRunner
    from memory_client.cli import app

    respx.post(f"{BASE}/memory/maintenance/purge-ephemeral").mock(
        return_value=httpx.Response(200, json={"deleted": 5})
    )

    runner = CliRunner()
    result = runner.invoke(app, ["purge-ephemeral"])

    assert result.exit_code == 0
    assert "5" in result.output
    assert "ephemeral" in result.output.lower()


# ---------------------------------------------------------------------------
# U10: CLI purge-ephemeral exits 1 on HTTP error
# ---------------------------------------------------------------------------

@respx.mock
def test_cli_purge_ephemeral_exits_nonzero_on_error():
    """CLI purge-ephemeral exits with code 1 when the service returns an error."""
    from typer.testing import CliRunner
    from memory_client.cli import app

    respx.post(f"{BASE}/memory/maintenance/purge-ephemeral").mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )

    runner = CliRunner()
    result = runner.invoke(app, ["purge-ephemeral"])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Integration tests (require live Memgraph + FastAPI)
# ---------------------------------------------------------------------------

import subprocess
import sys
import uuid

import pytest

from tests.conftest import TEST_TAG, cleanup_nodes, node_exists


@pytest.mark.integration
class TestEphemeralIntegration:

    def test_i1_post_memory_ephemeral_stores_flag(self, client, test_driver):
        """I1: POST /memory with ephemeral:true stores node with ephemeral=True in Memgraph."""
        memory_id = None
        try:
            response = client.post("/memory", json={
                "fact": f"WP-039 ephemeral I1 {uuid.uuid4()}",
                "ephemeral": True,
                "tags": [TEST_TAG],
                "type": "fact",
                "agent_id": "test-wp039",
            })
            assert response.status_code == 200
            memory_id = response.json()["memory_id"]

            with test_driver.session() as session:
                result = session.run(
                    "MATCH (m:Memory {id: $id}) RETURN m.ephemeral AS ephemeral",
                    id=memory_id,
                )
                record = result.single()
            assert record is not None
            assert record["ephemeral"] is True
        finally:
            if memory_id:
                cleanup_nodes(test_driver, memory_id)

    def test_i2_ephemeral_excluded_from_search(self, client, test_driver):
        """I2: Ephemeral memory is excluded from POST /memory/search results."""
        unique_term = f"zephyrquark{uuid.uuid4().hex[:8]}"
        ephemeral_id = None
        normal_id = None
        try:
            r_eph = client.post("/memory", json={
                "fact": f"WP-039 I2 ephemeral {unique_term}",
                "ephemeral": True,
                "tags": [TEST_TAG],
                "type": "fact",
                "agent_id": "test-wp039",
            })
            assert r_eph.status_code == 200
            ephemeral_id = r_eph.json()["memory_id"]

            r_norm = client.post("/memory", json={
                "fact": f"WP-039 I2 normal {unique_term}",
                "ephemeral": False,
                "tags": [TEST_TAG],
                "type": "fact",
                "agent_id": "test-wp039",
            })
            assert r_norm.status_code == 200
            normal_id = r_norm.json()["memory_id"]

            search = client.post("/memory/search", json={"query": unique_term, "limit": 20})
            assert search.status_code == 200
            result_ids = [m["id"] for m in search.json()["memories"]]

            assert normal_id in result_ids
            assert ephemeral_id not in result_ids
        finally:
            if ephemeral_id:
                cleanup_nodes(test_driver, ephemeral_id)
            if normal_id:
                cleanup_nodes(test_driver, normal_id)

    def test_i3_ephemeral_excluded_from_wake_up(self, client, test_driver):
        """I3: Ephemeral memory is excluded from GET /memory/wake-up results."""
        memory_id = None
        try:
            response = client.post("/memory", json={
                "fact": f"WP-039 I3 ephemeral wake-up test {uuid.uuid4()}",
                "ephemeral": True,
                "importance": 5,
                "tags": [TEST_TAG],
                "type": "fact",
                "agent_id": "test-wp039",
            })
            assert response.status_code == 200
            memory_id = response.json()["memory_id"]

            wake = client.get("/memory/wake-up?limit=50")
            assert wake.status_code == 200
            returned_ids = [m["id"] for m in wake.json()["memories"]]
            assert memory_id not in returned_ids
        finally:
            if memory_id:
                cleanup_nodes(test_driver, memory_id)

    def test_i4_purge_ephemeral_deletes_ephemeral_keeps_normal(self, client, test_driver):
        """I4: purge-ephemeral deletes ephemeral nodes and returns correct count; normal node survives."""
        ephemeral_ids = []
        normal_id = None
        try:
            for i in range(3):
                r = client.post("/memory", json={
                    "fact": f"WP-039 I4 ephemeral node {i} {uuid.uuid4()}",
                    "ephemeral": True,
                    "tags": [TEST_TAG],
                    "type": "fact",
                    "agent_id": "test-wp039",
                })
                assert r.status_code == 200
                ephemeral_ids.append(r.json()["memory_id"])

            r_norm = client.post("/memory", json={
                "fact": f"WP-039 I4 normal node {uuid.uuid4()}",
                "ephemeral": False,
                "tags": [TEST_TAG],
                "type": "fact",
                "agent_id": "test-wp039",
            })
            assert r_norm.status_code == 200
            normal_id = r_norm.json()["memory_id"]

            purge = client.post("/memory/maintenance/purge-ephemeral")
            assert purge.status_code == 200
            deleted = purge.json()["deleted"]
            assert deleted >= 3

            for eid in ephemeral_ids:
                assert not node_exists(test_driver, "Memory", eid)
            ephemeral_ids = []

            assert node_exists(test_driver, "Memory", normal_id)
        finally:
            for eid in ephemeral_ids:
                cleanup_nodes(test_driver, eid)
            if normal_id:
                cleanup_nodes(test_driver, normal_id)

    def test_i5_purge_ephemeral_with_none_returns_zero(self, client, test_driver):
        """I5: purge-ephemeral returns 0 when no ephemeral nodes exist."""
        # Clear any lingering ephemeral nodes first
        client.post("/memory/maintenance/purge-ephemeral")

        purge = client.post("/memory/maintenance/purge-ephemeral")
        assert purge.status_code == 200
        assert purge.json()["deleted"] == 0

    def test_i6_cli_purge_ephemeral_against_live_service(self, client, test_driver):
        """I6: CLI memory purge-ephemeral deletes ephemeral memories and exits 0.

        Skips if the live service at localhost:8000 does not yet expose the
        purge-ephemeral endpoint (e.g. running a pre-WP-039 build).
        """
        import re
        import httpx as _httpx

        # Probe whether the live service supports the endpoint.
        try:
            probe = _httpx.post("http://localhost:8000/memory/maintenance/purge-ephemeral", timeout=5)
            if probe.status_code == 404:
                pytest.skip("Live service at :8000 does not have purge-ephemeral — skipping CLI smoke test")
        except _httpx.ConnectError:
            pytest.skip("Live service at :8000 not reachable")

        ephemeral_ids = []
        try:
            for i in range(2):
                r = client.post("/memory", json={
                    "fact": f"WP-039 I6 CLI ephemeral {i} {uuid.uuid4()}",
                    "ephemeral": True,
                    "tags": [TEST_TAG],
                    "type": "fact",
                    "agent_id": "test-wp039",
                })
                assert r.status_code == 200
                ephemeral_ids.append(r.json()["memory_id"])

            result = subprocess.run(
                [sys.executable, "-m", "memory_client.cli", "purge-ephemeral"],
                capture_output=True,
                text=True,
                cwd="/home/oliver/projects/graph-memory-fabric/.worktrees/wp-039-ephemeral",
            )
            assert result.returncode == 0
            # Output should contain a non-negative integer (the count)
            numbers = re.findall(r"\d+", result.stdout)
            assert numbers, f"Expected a number in CLI output, got: {result.stdout!r}"
            deleted_count = int(numbers[0])
            assert deleted_count >= 2
            ephemeral_ids = []  # purged
        finally:
            for eid in ephemeral_ids:
                cleanup_nodes(test_driver, eid)
