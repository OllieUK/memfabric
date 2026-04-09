# tests/test_wp039_ephemeral.py
#
# Unit tests for WP-039: ephemeral memory support — repo layer.
# All tests here are pure unit tests (no live Memgraph required).

from unittest.mock import MagicMock, call

import memory_service.memory_repo as memory_repo
from memory_service.memory_repo import purge_ephemeral_memories


# ---------------------------------------------------------------------------
# Helper: build a mock session whose .run() returns mock results in sequence.
# ---------------------------------------------------------------------------

def _mock_session_with_side_effects(*run_results):
    """Return a MagicMock session whose .run() calls return run_results in order."""
    session = MagicMock()
    session.run.side_effect = list(run_results)
    return session


def _count_result(n: int):
    """Mock result whose .single() returns {"n": n}."""
    result = MagicMock()
    result.single.return_value = {"n": n}
    return result


# ---------------------------------------------------------------------------
# U1: purge_ephemeral_memories returns 0 when no ephemeral nodes exist
# ---------------------------------------------------------------------------

def test_purge_ephemeral_returns_zero_when_none():
    session = _mock_session_with_side_effects(_count_result(0))

    result = purge_ephemeral_memories(session)

    assert result == 0
    # Only the COUNT query should have been called — not the DELETE query
    assert session.run.call_count == 1


# ---------------------------------------------------------------------------
# U2: purge_ephemeral_memories counts first, deletes second, no RETURN on DELETE
# ---------------------------------------------------------------------------

def test_purge_ephemeral_counts_then_deletes():
    delete_result = MagicMock()
    session = _mock_session_with_side_effects(_count_result(3), delete_result)

    result = purge_ephemeral_memories(session)

    assert result == 3
    assert session.run.call_count == 2

    # Second call must contain DETACH DELETE
    second_call_query = session.run.call_args_list[1][0][0]
    assert "DETACH DELETE" in second_call_query

    # Second call must NOT contain RETURN (Memgraph gotcha)
    assert "RETURN" not in second_call_query


# ---------------------------------------------------------------------------
# U11: _SEARCH_QUERY_TEMPLATE contains ephemeral filter
# ---------------------------------------------------------------------------

def test_search_query_template_has_ephemeral_filter():
    assert "m.ephemeral" in memory_repo._SEARCH_QUERY_TEMPLATE


# ---------------------------------------------------------------------------
# U12: _PERSON_SEARCH_QUERY_TEMPLATE contains ephemeral filter
# ---------------------------------------------------------------------------

def test_person_search_query_template_has_ephemeral_filter():
    assert "m.ephemeral" in memory_repo._PERSON_SEARCH_QUERY_TEMPLATE
