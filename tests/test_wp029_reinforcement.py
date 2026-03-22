import uuid
import pytest


class TestReinforcementSettings:
    def test_default_values(self):
        from memory_service.config import Settings
        s = Settings()
        assert s.memory_decay_rate == 0.01
        assert s.edge_decay_rate == 0.005
        assert s.recall_strength_increment == 0.05
        assert s.explicit_strength_increment == 0.20
        assert s.edge_recall_increment == 0.02
        assert s.edge_explicit_increment == 0.10
        assert s.edge_prune_threshold == 0.05
        assert s.min_memory_strength == 0.0
