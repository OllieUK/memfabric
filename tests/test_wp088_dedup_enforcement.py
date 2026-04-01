"""WP-088: Deduplication and agent-ID enforcement. Requires live stack for integration tests."""
import pytest


class TestSettings:
    def test_memory_dedup_threshold_default(self):
        from memory_service.config import Settings
        assert Settings().memory_dedup_threshold == 0.05


from unittest.mock import MagicMock, call as mock_call


class TestFindDuplicateUnit:
    """Unit tests for find_duplicate_memory — mock session, no live stack."""

    def _mock_session(self, exact_hit, vector_hit):
        """Return a mock session whose run() returns exact_hit on first call,
        vector_hit on second call. None means empty result."""
        def make_result(id_val):
            if id_val is None:
                m = MagicMock()
                m.single.return_value = None
                return m
            else:
                m = MagicMock()
                m.single.return_value = {"id": id_val}
                return m

        session = MagicMock()
        session.run.side_effect = [make_result(exact_hit), make_result(vector_hit)]
        return session

    def test_exact_match_returns_immediately_without_vector_search(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit="existing-uuid", vector_hit=None)
        result = find_duplicate_memory(session, "some fact", [0.1, 0.2], threshold=0.05)
        assert result == "existing-uuid"
        assert session.run.call_count == 1  # vector search never fired

    def test_exact_match_miss_triggers_vector_search(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit=None, vector_hit="vec-match-uuid")
        result = find_duplicate_memory(session, "some fact", [0.1, 0.2], threshold=0.05)
        assert result == "vec-match-uuid"
        assert session.run.call_count == 2

    def test_no_match_returns_none(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = self._mock_session(exact_hit=None, vector_hit=None)
        result = find_duplicate_memory(session, "unique fact", [0.1, 0.2], threshold=0.05)
        assert result is None

    def test_exact_check_excludes_non_active_statuses(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = MagicMock()
        r = MagicMock(); r.single.return_value = None
        session.run.return_value = r
        find_duplicate_memory(session, "fact", [0.1], threshold=0.05)
        first_query = session.run.call_args_list[0][0][0]
        assert "active" in first_query

    def test_vector_check_excludes_non_active_statuses(self):
        from memory_service.memory_repo import find_duplicate_memory
        session = MagicMock()
        r = MagicMock(); r.single.return_value = None
        session.run.return_value = r
        find_duplicate_memory(session, "fact", [0.1], threshold=0.05)
        second_query = session.run.call_args_list[1][0][0]
        assert "active" in second_query