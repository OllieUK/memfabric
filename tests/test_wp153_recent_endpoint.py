"""WP-153: Tests for GET /memory/recent endpoint and list_recent_memories repo function.

Integration tests use the live `client` + `test_driver` fixtures. Memory nodes are
created via the public POST /memory route (so test data is realistic) and cleaned
up in finally blocks per project test hygiene rules (every test memory carries
tags=["test"]).
"""
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from memory_service.main import app


_AGENT_ID = "test-wp153-recent-agent"


@pytest.fixture(scope="module")
def client(test_driver):
    """Module-scoped TestClient — the FastMCP lifespan can only run once per
    process, so we cannot use the function-scoped conftest `client` fixture.
    """
    app.state.driver = test_driver
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    """Disable WP-096 API-key auth for this module's tests.

    Mirrors the pattern in tests/test_wp096_auth.py — patch the live settings
    singleton so the auth middleware sees an empty key list (open / dev mode).
    """
    import memory_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "api_keys", [])


def _add(client, fact, *, strand_ids=None, ephemeral=False):
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "tags": ["test"],
    }
    if strand_ids is not None:
        body["strand_ids"] = strand_ids
    if ephemeral:
        body["ephemeral"] = True
    r = client.post("/memory", json=body)
    assert r.status_code == 200, r.text
    return r.json()["memory_id"]


def _cleanup(test_driver, *ids):
    with test_driver.session() as s:
        for mid in ids:
            s.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


@pytest.mark.integration
class TestRecentEndpoint:
    def test_returns_recent_memory_with_default_window(self, client, test_driver):
        """A freshly-added memory appears in the default 7-day window."""
        suffix = uuid.uuid4().hex[:8]
        mid = _add(client, f"recent default-window memory {suffix}")
        try:
            r = client.get("/memory/recent")
            assert r.status_code == 200, r.text
            data = r.json()
            assert "memories" in data
            assert "days" in data and data["days"] == 7
            assert "total" in data and data["total"] == len(data["memories"])
            assert any(m["id"] == mid for m in data["memories"]), (
                f"Just-added memory {mid} not present in /memory/recent default window"
            )
        finally:
            _cleanup(test_driver, mid)

    def test_response_shape_has_required_fields(self, client, test_driver):
        """Each item in `memories` has the documented field set."""
        suffix = uuid.uuid4().hex[:8]
        mid = _add(client, f"recent shape check {suffix}")
        try:
            r = client.get("/memory/recent")
            assert r.status_code == 200
            item = next((m for m in r.json()["memories"] if m["id"] == mid), None)
            assert item is not None
            for field in ("id", "fact", "so_what", "type", "tags", "importance", "created_at", "strand_ids"):
                assert field in item, f"Missing field {field!r} in /memory/recent item"
            assert item["fact"].startswith("recent shape check")
            assert isinstance(item["tags"], list)
            assert isinstance(item["strand_ids"], list)
        finally:
            _cleanup(test_driver, mid)

    def test_strand_filter_narrows_results(self, client, test_driver):
        """`?strand=<id>` returns only memories in that strand.

        Uses strand-test and strand-inbox — both seeded by scripts/seed_strands.py
        and present on every fabric instance, so the test is portable.
        """
        suffix = uuid.uuid4().hex[:8]
        mid_in = _add(
            client,
            f"strand filter narrowing {suffix}",
            strand_ids=["strand-test"],
        )
        mid_out = _add(
            client,
            f"strand filter excluded {suffix}",
            strand_ids=["strand-inbox"],
        )
        try:
            r = client.get("/memory/recent", params={"strand": "strand-test"})
            assert r.status_code == 200
            ids = {m["id"] for m in r.json()["memories"]}
            assert mid_in in ids, (
                f"Expected memory in filtered strand to appear; got ids={ids}"
            )
            assert mid_out not in ids, "Memory in other strand must not appear under filter"
        finally:
            _cleanup(test_driver, mid_in, mid_out)

    def test_results_ordered_newest_first(self, client, test_driver):
        """Two memories added in sequence appear newest-first in the response.

        Facts are made semantically distinct so the second insert does not
        trigger dedup against the first (MEMORY_DEDUP_THRESHOLD=0.28).
        """
        suffix = uuid.uuid4().hex[:8]
        first = _add(client, f"alpha apple banana {suffix}")
        time.sleep(1.1)
        second = _add(client, f"omega zebra umbrella {suffix}")
        try:
            assert first != second, (
                "Test facts must be semantically distinct enough to avoid dedup"
            )
            r = client.get("/memory/recent", params={"limit": 200})
            assert r.status_code == 200
            ids = [m["id"] for m in r.json()["memories"]]
            assert first in ids and second in ids, (
                f"Expected both ids in result; got first={first in ids}, "
                f"second={second in ids}, ids={ids}"
            )
            assert ids.index(second) < ids.index(first), (
                "Newer memory must appear before older in newest-first ordering"
            )
        finally:
            _cleanup(test_driver, first, second)

    def test_limit_param_caps_result_count(self, client, test_driver):
        """`?limit=N` caps the number of memories returned."""
        suffix = uuid.uuid4().hex[:8]
        ids = [_add(client, f"recent limit-cap {i} {suffix}") for i in range(5)]
        try:
            r = client.get("/memory/recent", params={"limit": 2})
            assert r.status_code == 200
            assert len(r.json()["memories"]) <= 2
        finally:
            _cleanup(test_driver, *ids)

    def test_ephemeral_memories_excluded(self, client, test_driver):
        """Ephemeral memories are filtered out of /memory/recent results."""
        suffix = uuid.uuid4().hex[:8]
        mid_durable = _add(client, f"recent durable {suffix}")
        mid_ephemeral = _add(client, f"recent ephemeral {suffix}", ephemeral=True)
        try:
            r = client.get("/memory/recent", params={"limit": 200})
            assert r.status_code == 200
            ids = {m["id"] for m in r.json()["memories"]}
            assert mid_durable in ids
            assert mid_ephemeral not in ids, "Ephemeral memory must not appear in /memory/recent"
        finally:
            _cleanup(test_driver, mid_durable, mid_ephemeral)

    @pytest.mark.parametrize("days,ok", [(0, False), (1, True), (365, True), (366, False)])
    def test_days_param_validation(self, client, days, ok):
        """`days` is bounded 1..365 inclusive."""
        r = client.get("/memory/recent", params={"days": days})
        if ok:
            assert r.status_code == 200, r.text
        else:
            assert r.status_code == 422, f"days={days} should fail validation, got {r.status_code}"

    @pytest.mark.parametrize("limit,ok", [(0, False), (1, True), (200, True), (201, False)])
    def test_limit_param_validation(self, client, limit, ok):
        """`limit` is bounded 1..200 inclusive."""
        r = client.get("/memory/recent", params={"limit": limit})
        if ok:
            assert r.status_code == 200, r.text
        else:
            assert r.status_code == 422
