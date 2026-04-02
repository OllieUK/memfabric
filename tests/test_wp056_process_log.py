# tests/test_wp056_process_log.py
"""WP-056: Process log for lifecycle and maintenance operations."""
import json
import pytest
from unittest.mock import MagicMock
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
