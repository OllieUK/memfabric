# tests/test_wp040_maintenance.py
"""WP-040: Memory maintenance orchestration tests."""
import uuid
import pytest
from unittest.mock import MagicMock
from memory_service import memory_repo


class TestNewConfigFields:
    def test_new_config_fields_exist_with_correct_defaults(self):
        from memory_service.config import Settings
        s = Settings()
        assert s.short_rest_recency_days == 7
        assert s.long_rest_recency_days == 1
        assert s.rediscovery_strength_threshold == 0.3
        assert s.edge_hard_prune_floor == 0.01
        assert s.edge_hard_prune_min_days == 90
        assert s.edge_modulation_factor == 0.5
        assert s.edge_modulation_cap == 10.0


class TestSystemNodeHelpers:
    def test_upsert_system_node_sets_fields(self):
        """upsert_system_node calls session.run with last_short_rest_at in the query."""
        session = MagicMock()
        session.run.return_value = None
        memory_repo.upsert_system_node(session, last_short_rest_at="2026-01-01T00:00:00+00:00")
        session.run.assert_called_once()
        call_args = session.run.call_args
        assert "last_short_rest_at" in call_args[0][0]

    def test_get_system_timestamps_returns_dict(self):
        """get_system_timestamps returns dict with last_short_rest_at and last_long_rest_at."""
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: {
            "last_short_rest_at": None,
            "last_long_rest_at": None
        }[key]
        session = MagicMock()
        session.run.return_value.single.return_value = mock_record
        result = memory_repo.get_system_timestamps(session)
        assert "last_short_rest_at" in result
        assert "last_long_rest_at" in result
