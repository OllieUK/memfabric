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

    def test_skipped_when_dry_run(self):
        """append_maintenance_log is not called when dry_run=True."""
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
