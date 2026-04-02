# tests/test_wp047_near_duplicates.py
"""Tests for WP-047: near-duplicate detection."""
import math

import pytest

from tests.conftest import cleanup_nodes

_AGENT_ID = "test-agent-wp047"


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


def _add_body(fact: str, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 1,
    }
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Task 2 — Unit: cosine_similarity helper
# ---------------------------------------------------------------------------
class TestCosineSimilarity:
    def test_identical_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_vector_returns_zero(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([], [1.0, 0.0]) == 0.0

    def test_zero_norm_returns_zero(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
