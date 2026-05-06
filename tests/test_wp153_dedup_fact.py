"""WP-153: Tests for `duplicate_fact` surfacing on dedup + get_memory_fact helper.

When POST /memory hits the dedup path (semantic match within
MEMORY_DEDUP_THRESHOLD), the response now includes the matched memory's fact
text under the `duplicate_fact` field. On the non-dedup path it must remain
absent (or null) so callers can distinguish the two outcomes.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from memory_service.main import app


_AGENT_ID = "test-wp153-dedup-agent"


@pytest.fixture(scope="module")
def client(test_driver):
    """Module-scoped TestClient — see test_wp153_recent_endpoint.py rationale."""
    app.state.driver = test_driver
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable WP-096 API-key auth for this module's tests."""
    import memory_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "api_keys", [])


def _add(client, fact, **extra):
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "tags": ["test"],
        **extra,
    }
    r = client.post("/memory", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _cleanup(test_driver, *ids):
    with test_driver.session() as s:
        for mid in ids:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


@pytest.mark.integration
class TestDuplicateFactSurfacing:
    def test_first_write_has_no_duplicate_fact(self, client, test_driver):
        """A first-time write is not deduplicated and carries no `duplicate_fact`."""
        suffix = uuid.uuid4().hex[:8]
        body = _add(client, f"unique fact for first write {suffix}")
        try:
            assert body["deduplicated"] is False
            assert body.get("duplicate_fact") is None
        finally:
            _cleanup(test_driver, body["memory_id"])

    def test_dedup_path_includes_matched_fact_text(self, client, test_driver):
        """Re-adding the same fact triggers dedup and surfaces the matched fact."""
        suffix = uuid.uuid4().hex[:8]
        original_fact = f"distinctive fact text WP-153 {suffix}"
        first = _add(client, original_fact)
        try:
            second = _add(client, original_fact)
            assert second["deduplicated"] is True
            assert second["memory_id"] == first["memory_id"], (
                "Dedup must return the existing memory id, not a new one"
            )
            assert second.get("duplicate_fact") == original_fact, (
                f"Expected duplicate_fact={original_fact!r}, got {second.get('duplicate_fact')!r}"
            )
        finally:
            _cleanup(test_driver, first["memory_id"])


@pytest.mark.integration
class TestGetMemoryFact:
    def test_returns_fact_for_active_memory(self, client, test_driver):
        from memory_service import memory_repo

        suffix = uuid.uuid4().hex[:8]
        body = _add(client, f"get_memory_fact happy path {suffix}")
        try:
            with test_driver.session() as s:
                fact = memory_repo.get_memory_fact(s, body["memory_id"])
            assert fact is not None
            assert fact == f"get_memory_fact happy path {suffix}"
        finally:
            _cleanup(test_driver, body["memory_id"])

    def test_returns_none_for_unknown_id(self, test_driver):
        from memory_service import memory_repo

        with test_driver.session() as s:
            fact = memory_repo.get_memory_fact(s, "nonexistent-id-wp153")
        assert fact is None

    def test_returns_none_for_archived_memory(self, client, test_driver):
        """get_memory_fact filters by status='active' (or NULL); archived must not return."""
        from memory_service import memory_repo

        suffix = uuid.uuid4().hex[:8]
        body = _add(client, f"archived target {suffix}")
        mid = body["memory_id"]
        try:
            with test_driver.session() as s:
                s.run(
                    "MATCH (m:Memory {id: $id}) SET m.status = 'archived'",
                    id=mid,
                )
                fact = memory_repo.get_memory_fact(s, mid)
            assert fact is None, "Archived memory must not be returned by get_memory_fact"
        finally:
            _cleanup(test_driver, mid)
