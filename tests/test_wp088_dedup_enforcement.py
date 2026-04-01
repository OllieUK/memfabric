"""WP-088: Deduplication and agent-ID enforcement. Requires live stack for integration tests."""
import pytest


class TestSettings:
    def test_memory_dedup_threshold_default(self):
        from memory_service.config import Settings
        assert Settings().memory_dedup_threshold == 0.05
