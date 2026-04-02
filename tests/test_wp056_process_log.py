# tests/test_wp056_process_log.py
"""WP-056: Process log for lifecycle and maintenance operations."""
import json
import pytest
from unittest.mock import MagicMock, patch
from memory_service import memory_repo


class TestAppendOperationLog:
    def _make_session(self, existing_log=None):
        """Return a mock session whose run() returns existing_log JSON or None."""
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: (
            json.dumps(existing_log) if existing_log is not None else None
        )
        session.run.return_value.single.return_value = record
        return session

    def test_appends_entry_to_empty_log(self):
        """First call creates a single-entry list."""
        session = self._make_session(existing_log=None)
        entry = {
            "operation": "wake_up",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "agent_id": "claude-code",
        }
        memory_repo.append_operation_log(session, entry)
        # Should call session.run twice: once to read, once to write
        assert session.run.call_count == 2
        write_call = session.run.call_args_list[1]
        written_json = write_call[1]["log_json"]
        parsed = json.loads(written_json)
        assert len(parsed) == 1
        assert parsed[0]["operation"] == "wake_up"
        assert parsed[0]["agent_id"] == "claude-code"

    def test_appends_entry_to_existing_log(self):
        """Subsequent calls append to existing list."""
        existing = [
            {
                "operation": "wake_up",
                "ran_at": "2026-03-01T00:00:00+00:00",
                "agent_id": "claude-code",
            }
        ]
        session = self._make_session(existing_log=existing)
        new_entry = {
            "operation": "close_session",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "agent_id": "claude-code",
        }
        memory_repo.append_operation_log(session, new_entry)
        write_call = session.run.call_args_list[1]
        parsed = json.loads(write_call[1]["log_json"])
        assert len(parsed) == 2
        assert parsed[-1]["operation"] == "close_session"

    def test_caps_log_at_200_entries(self):
        """When log has 200 entries, oldest is dropped on append."""
        existing = [
            {
                "operation": "wake_up",
                "ran_at": f"2025-01-{(i % 28) + 1:02d}T00:00:00+00:00",
                "agent_id": "claude-code",
                "seq": i,
            }
            for i in range(1, 201)  # 200 entries
        ]
        session = self._make_session(existing_log=existing)
        new_entry = {
            "operation": "close_session",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "agent_id": "claude-code",
            "seq": 999,
        }
        memory_repo.append_operation_log(session, new_entry)
        write_call = session.run.call_args_list[1]
        parsed = json.loads(write_call[1]["log_json"])
        assert len(parsed) == 200
        # Oldest entry (seq=1) dropped; newest is close_session
        assert parsed[-1]["seq"] == 999
        assert parsed[0]["seq"] == 2  # entry with seq=2 is now first


class TestGetOperationLog:
    def test_returns_empty_list_when_no_log(self):
        """Returns [] when System node has no operation_log."""
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: None
        session.run.return_value.single.return_value = record
        result = memory_repo.get_operation_log(session)
        assert result == []

    def test_returns_parsed_list(self):
        """Returns the parsed list from System node operation_log."""
        entries = [
            {
                "operation": "wake_up",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "agent_id": "claude-code",
            }
        ]
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: json.dumps(entries)
        session.run.return_value.single.return_value = record
        result = memory_repo.get_operation_log(session)
        assert len(result) == 1
        assert result[0]["operation"] == "wake_up"

    def test_returns_empty_on_corrupt_json(self):
        """Returns [] when operation_log contains malformed JSON."""
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: "not valid json {"
        session.run.return_value.single.return_value = record
        result = memory_repo.get_operation_log(session)
        assert result == []


def _make_mock_driver():
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = lambda s: mock_session
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return mock_driver, mock_session


class TestUpdateHandlerLogsEntry:
    def test_logs_entry_on_success(self, monkeypatch):
        from fastapi.testclient import TestClient
        from memory_service.main import app

        logged = []
        mock_driver, _ = _make_mock_driver()
        app.state.driver = mock_driver

        monkeypatch.setattr(memory_repo, "update_memory", lambda *a, **kw: None)
        monkeypatch.setattr(
            memory_repo,
            "get_memory_for_update",
            lambda session, memory_id: {"fact": "existing fact", "so_what": None},
        )
        monkeypatch.setattr(
            memory_repo,
            "append_operation_log",
            lambda session, entry: logged.append(entry),
        )

        with TestClient(app) as client:
            response = client.patch("/memory/some-id", json={"tags": ["test"]})

        assert response.status_code == 200
        assert len(logged) == 1
        assert logged[0]["operation"] == "update"
        assert logged[0]["memory_id"] == "some-id"
        assert "tags" in logged[0]["fields_updated"]
        assert "ran_at" in logged[0]


class TestMergeHandlerLogsEntry:
    def test_logs_entry_on_success(self, monkeypatch):
        from fastapi.testclient import TestClient
        from memory_service.main import app

        logged = []
        mock_driver, _ = _make_mock_driver()
        app.state.driver = mock_driver

        monkeypatch.setattr(memory_repo, "merge_memory", lambda *a, **kw: None)
        monkeypatch.setattr(
            memory_repo,
            "append_operation_log",
            lambda session, entry: logged.append(entry),
        )

        with TestClient(app) as client:
            response = client.post(
                "/memory/src-id/merge",
                json={"target_id": "tgt-id", "strategy": "replace"},
            )

        assert response.status_code == 200
        assert len(logged) == 1
        assert logged[0]["operation"] == "merge"
        assert logged[0]["memory_id"] == "src-id"
        assert logged[0]["target_id"] == "tgt-id"
        assert "ran_at" in logged[0]


class TestArchiveHandlerLogsEntry:
    def test_logs_entry_on_success(self, monkeypatch):
        from fastapi.testclient import TestClient
        from memory_service.main import app

        logged = []
        mock_driver, _ = _make_mock_driver()
        app.state.driver = mock_driver

        monkeypatch.setattr(memory_repo, "archive_memory", lambda *a, **kw: None)
        monkeypatch.setattr(
            memory_repo,
            "append_operation_log",
            lambda session, entry: logged.append(entry),
        )

        with TestClient(app) as client:
            response = client.post("/memory/some-id/archive")

        assert response.status_code == 200
        assert len(logged) == 1
        assert logged[0]["operation"] == "archive"
        assert logged[0]["memory_id"] == "some-id"
        assert "ran_at" in logged[0]


class TestRestoreHandlerLogsEntry:
    def test_logs_entry_on_success(self, monkeypatch):
        from fastapi.testclient import TestClient
        from memory_service.main import app

        logged = []
        mock_driver, _ = _make_mock_driver()
        app.state.driver = mock_driver

        monkeypatch.setattr(memory_repo, "restore_memory", lambda *a, **kw: None)
        monkeypatch.setattr(
            memory_repo,
            "append_operation_log",
            lambda session, entry: logged.append(entry),
        )

        with TestClient(app) as client:
            response = client.post("/memory/some-id/restore")

        assert response.status_code == 200
        assert len(logged) == 1
        assert logged[0]["operation"] == "restore"
        assert logged[0]["memory_id"] == "some-id"
        assert "ran_at" in logged[0]


class TestOperationLogEndpoint:
    def test_returns_entries(self, monkeypatch):
        from fastapi.testclient import TestClient
        from memory_service.main import app

        mock_driver, _ = _make_mock_driver()
        app.state.driver = mock_driver

        entries = [
            {
                "operation": "update",
                "memory_id": "abc-123",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "fields_updated": ["tags"],
                "target_id": None,
            }
        ]
        monkeypatch.setattr(memory_repo, "get_operation_log", lambda session: entries)

        with TestClient(app) as client:
            response = client.get("/memory/operation/log")

        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert len(data["entries"]) == 1
        assert data["entries"][0]["operation"] == "update"
        assert data["entries"][0]["memory_id"] == "abc-123"

    def test_returns_empty(self, monkeypatch):
        from fastapi.testclient import TestClient
        from memory_service.main import app

        mock_driver, _ = _make_mock_driver()
        app.state.driver = mock_driver

        monkeypatch.setattr(memory_repo, "get_operation_log", lambda session: [])

        with TestClient(app) as client:
            response = client.get("/memory/operation/log")

        assert response.status_code == 200
        assert response.json() == {"entries": []}


class TestOperationLogClientMethod:
    def test_returns_list_of_entries(self):
        import respx
        import httpx
        from memory_client.client import MemoryClient

        entries = [
            {
                "operation": "archive",
                "memory_id": "m-1",
                "ran_at": "2026-04-02T10:00:00+00:00",
            }
        ]
        with respx.mock:
            respx.get("http://testserver/memory/operation/log").mock(
                return_value=httpx.Response(200, json={"entries": entries})
            )
            client = MemoryClient(base_url="http://testserver")
            result = client.operation_log()

        assert result == entries

    def test_returns_empty_list(self):
        import respx
        import httpx
        from memory_client.client import MemoryClient

        with respx.mock:
            respx.get("http://testserver/memory/operation/log").mock(
                return_value=httpx.Response(200, json={"entries": []})
            )
            client = MemoryClient(base_url="http://testserver")
            result = client.operation_log()

        assert result == []


class TestMcpOperationLogTool:
    def test_returns_formatted_entries(self, monkeypatch):
        from mcp_server.server import memory_operation_log

        entries = [
            {
                "operation": "update",
                "memory_id": "abc-123",
                "ran_at": "2026-04-02T10:00:00+00:00",
                "fields_updated": ["fact", "tags"],
                "target_id": None,
            }
        ]
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.operation_log.return_value = entries

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_operation_log()

        assert "update" in result
        assert "abc-123" in result
        assert "fields_updated" in result

    def test_returns_empty_message(self, monkeypatch):
        from mcp_server.server import memory_operation_log

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.operation_log.return_value = []

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_operation_log()

        assert result == "No operation log entries yet."
