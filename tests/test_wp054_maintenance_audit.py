# tests/test_wp054_maintenance_audit.py
"""WP-054: Maintenance audit trail and startup escalation loop."""
import json
import pytest
from unittest.mock import MagicMock, call
from memory_service import memory_repo


class TestAppendMaintenanceLog:
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
            "operation": "short_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": False,
            "nodes_affected": 5,
            "edges_affected": 2,
            "edges_discovered": 0,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, entry)
        # Should call session.run twice: once to read, once to write
        assert session.run.call_count == 2
        write_call = session.run.call_args_list[1]
        # The written JSON should contain our entry
        written_json = write_call[1]["log_json"]
        parsed = json.loads(written_json)
        assert len(parsed) == 1
        assert parsed[0]["operation"] == "short_rest"
        assert parsed[0]["nodes_affected"] == 5

    def test_appends_entry_to_existing_log(self):
        """Subsequent calls append to existing list."""
        existing = [
            {
                "operation": "short_rest",
                "ran_at": "2026-03-01T00:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 3,
                "edges_affected": 1,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
        ]
        session = self._make_session(existing_log=existing)
        new_entry = {
            "operation": "long_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": False,
            "nodes_affected": 10,
            "edges_affected": 3,
            "edges_discovered": 2,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, new_entry)
        write_call = session.run.call_args_list[1]
        parsed = json.loads(write_call[1]["log_json"])
        assert len(parsed) == 2
        assert parsed[-1]["operation"] == "long_rest"

    def test_caps_log_at_100_entries(self):
        """When log has 100 entries, oldest is dropped on append."""
        existing = [
            {
                "operation": "short_rest",
                "ran_at": f"2025-01-{i:02d}T00:00:00+00:00",
                "dry_run": False,
                "nodes_affected": i,
                "edges_affected": 0,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
            for i in range(1, 101)  # 100 entries
        ]
        session = self._make_session(existing_log=existing)
        new_entry = {
            "operation": "long_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": False,
            "nodes_affected": 999,
            "edges_affected": 0,
            "edges_discovered": 0,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, new_entry)
        write_call = session.run.call_args_list[1]
        parsed = json.loads(write_call[1]["log_json"])
        assert len(parsed) == 100
        # Oldest entry (nodes_affected=1) dropped; newest is long_rest
        assert parsed[-1]["nodes_affected"] == 999
        assert parsed[0]["nodes_affected"] == 2  # entry with i=2 is now first

    def test_writes_dry_run_entries_when_called(self):
        """append_maintenance_log writes the entry even when dry_run=True in the entry dict; the caller decides whether to invoke it."""
        # This is tested at the short_rest/long_rest level (Task 2)
        # Here just verify append_maintenance_log itself still writes dry_run entries
        # (the caller decides whether to call it)
        session = self._make_session(existing_log=None)
        entry = {
            "operation": "short_rest",
            "ran_at": "2026-04-01T10:00:00+00:00",
            "dry_run": True,
            "nodes_affected": 0,
            "edges_affected": 0,
            "edges_discovered": 0,
            "edges_pruned": 0,
        }
        memory_repo.append_maintenance_log(session, entry)
        assert session.run.call_count == 2  # still reads and writes


class TestGetMaintenanceLog:
    def test_returns_empty_list_when_no_log(self):
        """Returns [] when System node has no maintenance_log."""
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: None
        session.run.return_value.single.return_value = record
        result = memory_repo.get_maintenance_log(session)
        assert result == []

    def test_returns_parsed_list(self):
        """Returns the parsed list from System node maintenance_log."""
        entries = [
            {
                "operation": "short_rest",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 5,
                "edges_affected": 2,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
        ]
        session = MagicMock()
        record = MagicMock()
        record.__getitem__ = lambda self, key: json.dumps(entries)
        session.run.return_value.single.return_value = record
        result = memory_repo.get_maintenance_log(session)
        assert len(result) == 1
        assert result[0]["operation"] == "short_rest"


class TestShortRestLogsAuditEntry:
    def test_audit_log_written_on_real_run(self):
        """short_rest writes an audit entry when dry_run=False."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            session = MagicMock()
            session.run.return_value.__iter__ = lambda s: iter([])
            session.run.return_value.single.return_value = None
            memory_repo.short_rest(
                session,
                now_iso="2026-04-01T10:00:00+00:00",
                recency_days=7,
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                dry_run=False,
            )
        assert len(logged) == 1
        assert logged[0]["operation"] == "short_rest"
        assert logged[0]["dry_run"] is False
        assert "ran_at" in logged[0]
        assert "nodes_affected" in logged[0]
        assert "edges_affected" in logged[0]

    def test_audit_log_not_written_on_dry_run(self):
        """short_rest does NOT write an audit entry when dry_run=True."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            session = MagicMock()
            session.run.return_value.__iter__ = lambda s: iter([])
            session.run.return_value.single.return_value = None
            memory_repo.short_rest(
                session,
                now_iso="2026-04-01T10:00:00+00:00",
                recency_days=7,
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                dry_run=True,
            )
        assert len(logged) == 0


class TestLongRestLogsAuditEntry:
    def test_audit_log_written_on_real_run(self):
        """long_rest writes an audit entry when dry_run=False."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            # Mock decay_pass to return minimal result
            mp.setattr(
                memory_repo,
                "decay_pass",
                lambda *a, **kw: {"nodes_updated": 2, "edges_updated": 1},
            )
            session = MagicMock()
            session.run.return_value.__iter__ = lambda s: iter([])
            session.run.return_value.single.return_value = None
            memory_repo.long_rest(
                session,
                now_iso="2026-04-01T10:00:00+00:00",
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                rediscovery_strength_threshold=0.3,
                edge_hard_prune_floor=0.01,
                edge_hard_prune_min_days=90,
                edge_decay_rate=0.005,
                dry_run=False,
                prune=False,
            )
        assert len(logged) == 1
        assert logged[0]["operation"] == "long_rest"
        assert logged[0]["dry_run"] is False
        assert "edges_discovered" in logged[0]
        assert "edges_pruned" in logged[0]

    def test_audit_log_not_written_on_dry_run(self):
        """long_rest does NOT write an audit entry when dry_run=True."""
        with pytest.MonkeyPatch.context() as mp:
            logged = []
            mp.setattr(
                memory_repo,
                "append_maintenance_log",
                lambda session, entry: logged.append(entry),
            )
            mp.setattr(
                memory_repo,
                "decay_pass",
                lambda *a, **kw: {"nodes_updated": 0, "edges_updated": 0},
            )
            session = MagicMock()
            session.run.return_value.__iter__ = lambda s: iter([])
            session.run.return_value.single.return_value = None
            memory_repo.long_rest(
                session,
                now_iso="2026-04-01T10:00:00+00:00",
                min_strength=0.0,
                edge_modulation_factor=0.5,
                edge_modulation_cap=10.0,
                rediscovery_strength_threshold=0.3,
                edge_hard_prune_floor=0.01,
                edge_hard_prune_min_days=90,
                edge_decay_rate=0.005,
                dry_run=True,
                prune=False,
            )
        assert len(logged) == 0


class TestMaintenanceLogEndpoint:
    def test_maintenance_log_endpoint_returns_entries(self):
        """GET /memory/maintenance/log returns list of audit entries."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from memory_service.main import app

        entries = [
            {
                "operation": "short_rest",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 5,
                "edges_affected": 2,
                "edges_discovered": 0,
                "edges_pruned": 0,
            }
        ]
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        app.state.driver = mock_driver

        with patch("memory_service.main.memory_repo.get_maintenance_log", return_value=entries):
            with TestClient(app) as client:
                response = client.get("/memory/maintenance/log")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert len(data["entries"]) == 1
        assert data["entries"][0]["operation"] == "short_rest"

    def test_maintenance_log_endpoint_empty(self):
        """GET /memory/maintenance/log returns empty list when no log exists."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        app.state.driver = mock_driver

        with patch("memory_service.main.memory_repo.get_maintenance_log", return_value=[]):
            with TestClient(app) as client:
                response = client.get("/memory/maintenance/log")
        assert response.status_code == 200
        assert response.json() == {"entries": []}


class TestMaintenanceStatus:
    def _compute_status(self, last_short=None, last_long=None, now_iso="2026-04-01T10:00:00+00:00", short_recency=1, long_recency=1):
        """Call the helper being tested."""
        from memory_service.main import _compute_maintenance_status
        return _compute_maintenance_status(
            last_short_rest_at=last_short,
            last_long_rest_at=last_long,
            now_iso=now_iso,
            short_rest_recency_days=short_recency,
            long_rest_recency_days=long_recency,
        )

    def test_both_never_run(self):
        status = self._compute_status()
        assert status["long_rest_overdue"] is True
        assert status["short_rest_overdue"] is True
        assert status["long_rest_days_ago"] is None
        assert status["short_rest_days_ago"] is None
        assert "long-rest has never run" in status["recommended_action"]

    def test_short_rest_never_run_long_rest_ok(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        long_ts = (now - timedelta(hours=6)).isoformat()
        status = self._compute_status(last_short=None, last_long=long_ts)
        assert status["short_rest_overdue"] is True
        assert status["long_rest_overdue"] is False
        assert "short-rest has never run" in status["recommended_action"]

    def test_long_rest_overdue_short_rest_ok(self):
        # short ran 0.5 days ago (within 1-day recency), long ran 3 days ago (overdue)
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(hours=12)).isoformat()
        long_ts = (now - timedelta(days=3)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["long_rest_overdue"] is True
        assert status["short_rest_overdue"] is False
        assert "long-rest is overdue" in status["recommended_action"]

    def test_short_rest_overdue_long_rest_ok(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(days=3)).isoformat()
        long_ts = (now - timedelta(hours=6)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["short_rest_overdue"] is True
        assert status["long_rest_overdue"] is False
        assert "short-rest is overdue" in status["recommended_action"]

    def test_both_overdue(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(days=3)).isoformat()
        long_ts = (now - timedelta(days=3)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["short_rest_overdue"] is True
        assert status["long_rest_overdue"] is True
        assert "both short-rest and long-rest are overdue" in status["recommended_action"]

    def test_neither_overdue(self):
        from datetime import datetime, timezone, timedelta
        now = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        short_ts = (now - timedelta(hours=6)).isoformat()
        long_ts = (now - timedelta(hours=6)).isoformat()
        status = self._compute_status(last_short=short_ts, last_long=long_ts)
        assert status["short_rest_overdue"] is False
        assert status["long_rest_overdue"] is False
        assert status["recommended_action"] is None

    def test_wake_up_response_includes_maintenance_status(self):
        """WakeUpResponse has maintenance_status field (not maintenance_warning)."""
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from memory_service.main import app

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = lambda s: mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        app.state.driver = mock_driver

        with patch("memory_service.main.memory_repo.wake_up", return_value={"core": [], "topic": []}):
            with patch("memory_service.main.memory_repo.get_system_timestamps", return_value={"last_short_rest_at": None, "last_long_rest_at": None}):
                with TestClient(app) as client:
                    response = client.get("/memory/wake-up")
        assert response.status_code == 200
        data = response.json()
        assert "maintenance_status" in data
        assert "maintenance_warning" not in data
        ms = data["maintenance_status"]
        assert "short_rest_overdue" in ms
        assert "long_rest_overdue" in ms
        assert "recommended_action" in ms


class TestMemoryClientUpdates:
    def test_wake_up_split_returns_maintenance_status(self):
        """wake_up_split returns (core, topic, maintenance_status) 3-tuple."""
        from unittest.mock import patch, MagicMock
        from memory_client.client import MemoryClient

        response_data = {
            "memories": [{"id": "abc", "fact": "test", "text": "test", "type": "fact", "importance": 3, "strength": 0.8, "tags": [], "created_at": None, "strand_id": None}],
            "topic_memories": [],
            "maintenance_status": {
                "short_rest_overdue": True,
                "long_rest_overdue": False,
                "short_rest_days_ago": 2.5,
                "long_rest_days_ago": 0.5,
                "recommended_action": "short-rest is overdue (2d) — run `memory short-rest`",
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with MemoryClient(base_url="http://localhost:8000") as client:
            with patch.object(client._http, "get", return_value=mock_response):
                result = client.wake_up_split(limit=20)

        assert len(result) == 3
        core, topic, status = result
        assert len(core) == 1
        assert topic == []
        assert status["short_rest_overdue"] is True
        assert status["recommended_action"] is not None

    def test_maintenance_log_client_method(self):
        """maintenance_log() returns list of audit entries."""
        from unittest.mock import patch, MagicMock
        from memory_client.client import MemoryClient

        response_data = {
            "entries": [
                {
                    "operation": "short_rest",
                    "ran_at": "2026-04-01T10:00:00+00:00",
                    "dry_run": False,
                    "nodes_affected": 5,
                    "edges_affected": 2,
                    "edges_discovered": 0,
                    "edges_pruned": 0,
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        with MemoryClient(base_url="http://localhost:8000") as client:
            with patch.object(client._http, "get", return_value=mock_response):
                result = client.maintenance_log()

        assert len(result) == 1
        assert result[0]["operation"] == "short_rest"


class TestMcpUpdates:
    def test_memory_wake_up_shows_maintenance_alert(self):
        """memory_wake_up includes a maintenance alert block when action is recommended."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.wake_up_split.return_value = (
            [],  # core
            [],  # topic
            {
                "short_rest_overdue": True,
                "long_rest_overdue": True,
                "short_rest_days_ago": 3.0,
                "long_rest_days_ago": 3.0,
                "recommended_action": "both short-rest and long-rest are overdue — run `memory long-rest` (covers both)",
            },
        )

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_wake_up
            result = memory_wake_up()

        assert "overdue" in result.lower()
        assert "long-rest" in result

    def test_memory_wake_up_no_alert_when_healthy(self):
        """memory_wake_up omits maintenance block when all is fine."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.wake_up_split.return_value = (
            [],
            [],
            {
                "short_rest_overdue": False,
                "long_rest_overdue": False,
                "short_rest_days_ago": 0.5,
                "long_rest_days_ago": 0.5,
                "recommended_action": None,
            },
        )

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_wake_up
            result = memory_wake_up()

        assert "overdue" not in result.lower()

    def test_memory_maintenance_log_tool(self):
        """memory_maintenance_log returns formatted plain-text summary."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.maintenance_log.return_value = [
            {
                "operation": "short_rest",
                "ran_at": "2026-04-01T10:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 5,
                "edges_affected": 2,
                "edges_discovered": 0,
                "edges_pruned": 0,
            },
            {
                "operation": "long_rest",
                "ran_at": "2026-03-30T08:00:00+00:00",
                "dry_run": False,
                "nodes_affected": 20,
                "edges_affected": 10,
                "edges_discovered": 3,
                "edges_pruned": 1,
            },
        ]

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_maintenance_log
            result = memory_maintenance_log()

        assert "short-rest" in result.lower() or "short_rest" in result
        assert "long-rest" in result.lower() or "long_rest" in result
        assert "5" in result  # nodes_affected for short_rest
        assert "20" in result  # nodes_affected for long_rest

    def test_memory_maintenance_log_empty(self):
        """memory_maintenance_log returns appropriate message when no runs recorded."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.__enter__ = lambda s: mock_client
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.maintenance_log.return_value = []

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            from mcp_server.server import memory_maintenance_log
            result = memory_maintenance_log()

        assert "No maintenance runs recorded yet." in result


@pytest.mark.integration
class TestMaintenanceAuditIntegration:
    """Integration tests — require live Memgraph + FastAPI service (pytest -m integration)."""

    BASE_URL = "http://localhost:8000"

    def test_short_rest_creates_audit_entry(self):
        """Running short-rest adds a correctly-structured entry to the maintenance log.

        We assert on the content of the latest entry rather than the log length,
        because the log is capped at 100 entries — once full, appending replaces
        the oldest entry and the count stays constant.
        """
        import httpx

        r = httpx.post(f"{self.BASE_URL}/memory/maintenance/short-rest", timeout=60.0)
        assert r.status_code == 200

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log", timeout=30.0)
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) > 0
        latest = entries[-1]
        assert latest["operation"] == "short_rest"
        assert latest["dry_run"] is False
        assert "ran_at" in latest

    def test_long_rest_creates_audit_entry(self):
        """Running long-rest adds a correctly-structured entry with edges_discovered field.

        We assert on the content of the latest entry rather than the log length,
        because the log is capped at 100 entries — once full, appending replaces
        the oldest entry and the count stays constant.
        """
        import httpx

        r = httpx.post(f"{self.BASE_URL}/memory/maintenance/long-rest", timeout=60.0)
        assert r.status_code == 200

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log", timeout=30.0)
        entries = r.json()["entries"]
        assert len(entries) > 0
        latest = entries[-1]
        assert latest["operation"] == "long_rest"
        assert "edges_discovered" in latest
        assert "edges_pruned" in latest

    def test_dry_run_does_not_create_audit_entry(self):
        """dry_run=True must not write an audit entry."""
        import httpx

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        before = len(r.json()["entries"])

        r = httpx.post(f"{self.BASE_URL}/memory/maintenance/short-rest?dry_run=true", timeout=60.0)
        assert r.status_code == 200
        assert r.json()["dry_run"] is True

        r = httpx.get(f"{self.BASE_URL}/memory/maintenance/log")
        assert len(r.json()["entries"]) == before  # unchanged

    def test_wake_up_maintenance_status_structured(self):
        """GET /memory/wake-up returns maintenance_status (not maintenance_warning)."""
        import httpx

        r = httpx.get(f"{self.BASE_URL}/memory/wake-up")
        assert r.status_code == 200
        data = r.json()
        assert "maintenance_status" in data
        assert "maintenance_warning" not in data
        ms = data["maintenance_status"]
        assert "short_rest_overdue" in ms
        assert "long_rest_overdue" in ms
        assert "recommended_action" in ms
