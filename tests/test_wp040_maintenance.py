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
