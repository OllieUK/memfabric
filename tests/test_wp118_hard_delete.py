# tests/test_wp118_hard_delete.py
# WP-118: DELETE /memory/{id} hard-delete endpoint
# Unit tests (U1–U8) + Integration tests (I1–I6, @pytest.mark.integration)

import uuid
import subprocess
import sys
from unittest.mock import MagicMock, patch, call

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    TEST_TAG,
    cleanup_nodes,
    node_exists,
    make_mock_driver,
)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestDeleteMemoryRepo:
    """U1–U2: memory_repo.delete_memory"""

    def test_delete_memory_repo_raises_on_missing(self):
        """U1: raises ValueError when MATCH returns no row."""
        from memory_service import memory_repo

        mock_session = MagicMock()
        # First run = existence check, returns None (not found)
        mock_result = MagicMock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            memory_repo.delete_memory(mock_session, "nonexistent-id")

    def test_delete_memory_repo_calls_detach_delete(self):
        """U2: issues DETACH DELETE as second call when node exists."""
        from memory_service import memory_repo

        mock_session = MagicMock()
        # First run = existence check, returns a row
        check_result = MagicMock()
        check_result.single.return_value = {"id": "abc"}
        # Second run = DETACH DELETE (no return value needed)
        delete_result = MagicMock()
        mock_session.run.side_effect = [check_result, delete_result]

        memory_repo.delete_memory(mock_session, "abc")

        assert mock_session.run.call_count == 2
        # First call: existence check
        first_call_query = mock_session.run.call_args_list[0][0][0]
        assert "MATCH" in first_call_query
        assert "RETURN" in first_call_query
        # Second call: DETACH DELETE — must NOT contain RETURN
        second_call_query = mock_session.run.call_args_list[1][0][0]
        assert "DETACH DELETE" in second_call_query
        assert "RETURN" not in second_call_query


class TestDeleteMemoryClient:
    """U3–U4: MemoryClient.delete_memory"""

    def test_client_delete_memory_sends_delete_request(self):
        """U3: issues DELETE /memory/{id}, returns None on 204."""
        from memory_client.client import MemoryClient

        transport = httpx.MockTransport(
            lambda request: httpx.Response(204) if request.method == "DELETE" else httpx.Response(405)
        )
        client = MemoryClient.__new__(MemoryClient)
        client._http = httpx.Client(transport=transport, base_url="http://test")

        result = client.delete_memory("abc-123")
        assert result is None

    def test_client_delete_memory_raises_on_404(self):
        """U4: raises httpx.HTTPStatusError on 404."""
        from memory_client.client import MemoryClient

        transport = httpx.MockTransport(
            lambda request: httpx.Response(404, json={"detail": "Memory not found"})
        )
        client = MemoryClient.__new__(MemoryClient)
        client._http = httpx.Client(transport=transport, base_url="http://test")

        with pytest.raises(httpx.HTTPStatusError):
            client.delete_memory("missing-id")


class TestDeleteCLI:
    """U5–U6: CLI memory delete command"""

    def test_cli_delete_prints_confirmation(self):
        """U5: CLI prints 'Deleted' and exits 0 on 204."""
        from typer.testing import CliRunner
        from memory_client.cli import app as cli_app

        runner = CliRunner()
        with patch("memory_client.cli._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.delete_memory.return_value = None
            mock_make.return_value = mock_client

            result = runner.invoke(cli_app, ["delete", "abcd1234-0000-0000-0000-000000000000"])

        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_cli_delete_prints_error_on_404(self):
        """U6: CLI exits 1 on 404."""
        from typer.testing import CliRunner
        from memory_client.cli import app as cli_app

        runner = CliRunner()
        with patch("memory_client.cli._make_client") as mock_make:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.delete_memory.side_effect = httpx.HTTPStatusError(
                "404",
                request=httpx.Request("DELETE", "http://test/memory/x"),
                response=httpx.Response(404, text="Not Found"),
            )
            mock_make.return_value = mock_client

            result = runner.invoke(cli_app, ["delete", "missing-id"])

        assert result.exit_code == 1


class TestDeleteRoute:
    """U7–U8: FastAPI route DELETE /memory/{memory_id}"""

    def test_route_delete_returns_204_on_success(self):
        """U7: FastAPI handler returns 204 when repo succeeds."""
        from memory_service.main import app
        from memory_service import memory_repo

        mock_driver, mock_session = make_mock_driver()
        app.state.driver = mock_driver

        with patch.object(memory_repo, "delete_memory", return_value=None) as mock_del, \
             patch.object(memory_repo, "append_operation_log", return_value=None):
            with TestClient(app) as c:
                response = c.delete("/memory/some-uuid")

        assert response.status_code == 204

    def test_route_delete_returns_404_on_missing(self):
        """U8: FastAPI handler returns 404 when repo raises ValueError."""
        from memory_service.main import app
        from memory_service import memory_repo

        mock_driver, mock_session = make_mock_driver()
        app.state.driver = mock_driver

        with patch.object(memory_repo, "delete_memory", side_effect=ValueError("Memory 'missing-uuid' not found")), \
             patch.object(memory_repo, "append_operation_log", return_value=None):
            with TestClient(app) as c:
                response = c.delete("/memory/missing-uuid")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Integration tests (require live Memgraph + FastAPI at http://localhost:8000)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDeleteIntegration:

    def test_delete_returns_204_and_node_is_gone(self, client, test_driver):
        """I1: POST /memory, DELETE /memory/{id} → 204, verify node absent."""
        memory_id = None
        try:
            create = client.post("/memory", json={
                "fact": "WP-118 integration test node",
                "type": "fact",
                "agent_id": "test-agent",
                "tags": [TEST_TAG],
            })
            assert create.status_code == 200
            memory_id = create.json()["memory_id"]

            response = client.delete(f"/memory/{memory_id}")
            assert response.status_code == 204

            assert not node_exists(test_driver, "Memory", memory_id)
            memory_id = None  # already deleted
        finally:
            if memory_id:
                cleanup_nodes(test_driver, memory_id)

    def test_delete_removes_all_edges(self, client, test_driver):
        """I2: Create two memories with RELATED_TO edge, DELETE one, verify no orphan edges."""
        id_a = None
        id_b = None
        try:
            r_a = client.post("/memory", json={
                "fact": "WP-118 edge test A",
                "type": "fact",
                "agent_id": "test-agent",
                "tags": [TEST_TAG],
            })
            r_b = client.post("/memory", json={
                "fact": "WP-118 edge test B",
                "type": "fact",
                "agent_id": "test-agent",
                "tags": [TEST_TAG],
                "related_ids": [],
            })
            assert r_a.status_code == 200
            assert r_b.status_code == 200
            id_a = r_a.json()["memory_id"]
            id_b = r_b.json()["memory_id"]

            # Manually create a RELATED_TO edge
            with test_driver.session() as session:
                session.run(
                    "MATCH (a:Memory {id: $a}), (b:Memory {id: $b}) "
                    "MERGE (a)-[:RELATED_TO {weight: 0.9}]->(b)",
                    a=id_a, b=id_b,
                )

            response = client.delete(f"/memory/{id_a}")
            assert response.status_code == 204
            id_a = None

            # Verify no RELATED_TO edges involving the deleted node remain
            with test_driver.session() as session:
                result = session.run(
                    "MATCH ()-[r:RELATED_TO]->(m:Memory {id: $b}) RETURN count(r) AS c",
                    b=id_b,
                )
                count = result.single()["c"]
            assert count == 0
        finally:
            if id_a:
                cleanup_nodes(test_driver, id_a)
            if id_b:
                cleanup_nodes(test_driver, id_b)

    def test_delete_nonexistent_returns_404(self, client, test_driver):
        """I3: DELETE /memory/{random-uuid} → 404."""
        random_id = str(uuid.uuid4())
        response = client.delete(f"/memory/{random_id}")
        assert response.status_code == 404

    def test_delete_appends_operation_log(self, client, test_driver):
        """I4: Create, DELETE, GET /memory/operation/log → entry with operation=delete."""
        memory_id = None
        try:
            create = client.post("/memory", json={
                "fact": "WP-118 operation log test",
                "type": "fact",
                "agent_id": "test-agent",
                "tags": [TEST_TAG],
            })
            assert create.status_code == 200
            memory_id = create.json()["memory_id"]

            response = client.delete(f"/memory/{memory_id}")
            assert response.status_code == 204
            memory_id = None

            log_response = client.get("/memory/operation/log")
            assert log_response.status_code == 200
            entries = log_response.json()["entries"]
            delete_entries = [e for e in entries if e.get("operation") == "delete"]
            assert len(delete_entries) > 0
        finally:
            if memory_id:
                cleanup_nodes(test_driver, memory_id)

    def test_delete_archived_memory_succeeds(self, client, test_driver):
        """I5: Create, archive, DELETE → 204 and gone (status-agnostic)."""
        memory_id = None
        try:
            create = client.post("/memory", json={
                "fact": "WP-118 archived delete test",
                "type": "fact",
                "agent_id": "test-agent",
                "tags": [TEST_TAG],
            })
            assert create.status_code == 200
            memory_id = create.json()["memory_id"]

            archive = client.post(f"/memory/{memory_id}/archive")
            assert archive.status_code == 200

            response = client.delete(f"/memory/{memory_id}")
            assert response.status_code == 204

            assert not node_exists(test_driver, "Memory", memory_id)
            memory_id = None
        finally:
            if memory_id:
                cleanup_nodes(test_driver, memory_id)

    def test_cli_delete_integration(self, client, test_driver):
        """I6: Run CLI `memory delete <id>` against live service → exit 0, 'Deleted' in output."""
        memory_id = None
        try:
            create = client.post("/memory", json={
                "fact": "WP-118 CLI integration test",
                "type": "fact",
                "agent_id": "test-agent",
                "tags": [TEST_TAG],
            })
            assert create.status_code == 200
            memory_id = create.json()["memory_id"]

            result = subprocess.run(
                [sys.executable, "-m", "memory_client.cli", "delete", memory_id],
                capture_output=True,
                text=True,
                cwd="/home/oliver/projects/graph-memory-fabric",
            )
            assert result.returncode == 0
            assert "Deleted" in result.stdout
            memory_id = None
        finally:
            if memory_id:
                cleanup_nodes(test_driver, memory_id)
