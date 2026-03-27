"""
tests/test_wp038_lifecycle.py — Tests for WP-038: Memory lifecycle operations.

Unit tests verify Pydantic models, Cypher status filters, and HTTP client/CLI wire-up.
Integration tests (require live Memgraph + FastAPI) verify all four lifecycle endpoints
and that archived/merged memories are excluded from search and wake-up.
"""

import pytest
import respx
import httpx
from typer.testing import CliRunner
from unittest.mock import MagicMock

from memory_service.main import UpdateMemoryRequest
from memory_service import memory_repo
from memory_client.client import MemoryClient
from memory_client.cli import app as cli_app
from tests.conftest import cleanup_nodes, edge_exists, get_memory_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENT_ID = "test-wp038-agent"
_BASE_URL = "http://test"
runner = CliRunner()


def _add_memory(client, text: str, *, type: str = "fact") -> str:
    r = client.post("/memory", json={"text": text, "type": type, "agent_id": _AGENT_ID})
    assert r.status_code == 200, r.text
    return r.json()["memory_id"]


def _search(client, query: str) -> list[str]:
    r = client.post("/memory/search", json={"query": query, "max_hops": 0, "limit": 20})
    assert r.status_code == 200, r.text
    return [h["id"] for h in r.json()["memories"]]


def _wake_up_ids(client) -> set[str]:
    r = client.get("/memory/wake-up?limit=50")
    assert r.status_code == 200, r.text
    data = r.json()
    return {m["id"] for m in data["memories"] + data["topic_memories"]}


# ---------------------------------------------------------------------------
# Unit tests — Pydantic model validation
# ---------------------------------------------------------------------------

def test_update_request_rejects_empty_body():
    with pytest.raises(Exception):
        UpdateMemoryRequest()


def test_update_request_accepts_single_field():
    req = UpdateMemoryRequest(fact="new fact")
    assert req.fact == "new fact"


def test_update_request_rejects_importance_out_of_range():
    with pytest.raises(Exception):
        UpdateMemoryRequest(importance=6)
    with pytest.raises(Exception):
        UpdateMemoryRequest(importance=0)


def test_update_request_accepts_all_fields():
    req = UpdateMemoryRequest(
        fact="f", so_what="s", tags=["a"], importance=4,
        person_ids=["p1"], strand_ids=["s1"],
    )
    assert req.importance == 4


# ---------------------------------------------------------------------------
# Unit tests — Cypher status filters (mock session)
# ---------------------------------------------------------------------------

def test_search_cypher_contains_status_filter():
    """_SEARCH_QUERY_TEMPLATE must exclude archived/merged nodes."""
    assert "(m.status IS NULL OR m.status = 'active')" in memory_repo._SEARCH_QUERY_TEMPLATE


def test_wake_up_cypher_contains_status_filter():
    """wake_up core query must exclude archived/merged nodes."""
    session = MagicMock()
    session.run.return_value = []
    memory_repo.wake_up(session, limit=5)
    core_cypher = session.run.call_args_list[0][0][0]
    assert "(m.status IS NULL OR m.status = 'active')" in core_cypher


# ---------------------------------------------------------------------------
# Unit tests — HTTP client methods (respx mock)
# ---------------------------------------------------------------------------

@respx.mock
def test_client_update_memory_sends_patch():
    route = respx.patch(f"{_BASE_URL}/memory/abc123").mock(
        return_value=httpx.Response(200, json={"memory_id": "abc123", "updated_at": "2026-01-01T00:00:00+00:00"})
    )
    with MemoryClient(base_url=_BASE_URL) as client:
        result = client.update_memory("abc123", fact="new fact")
    assert route.called
    assert result["memory_id"] == "abc123"


@respx.mock
def test_client_merge_memory_sends_post():
    route = respx.post(f"{_BASE_URL}/memory/src1/merge").mock(
        return_value=httpx.Response(200, json={"source_id": "src1", "target_id": "tgt1"})
    )
    with MemoryClient(base_url=_BASE_URL) as client:
        result = client.merge_memory("src1", "tgt1")
    assert route.called
    assert result["source_id"] == "src1"


@respx.mock
def test_client_archive_memory_sends_post():
    route = respx.post(f"{_BASE_URL}/memory/abc123/archive").mock(
        return_value=httpx.Response(200, json={"memory_id": "abc123", "archived_at": "2026-01-01T00:00:00+00:00"})
    )
    with MemoryClient(base_url=_BASE_URL) as client:
        result = client.archive_memory("abc123")
    assert route.called
    assert "archived_at" in result


@respx.mock
def test_client_restore_memory_sends_post():
    route = respx.post(f"{_BASE_URL}/memory/abc123/restore").mock(
        return_value=httpx.Response(200, json={"memory_id": "abc123", "status": "active"})
    )
    with MemoryClient(base_url=_BASE_URL) as client:
        result = client.restore_memory("abc123")
    assert route.called
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# Unit tests — CLI commands (CliRunner + respx mock)
# ---------------------------------------------------------------------------

@respx.mock
def test_cli_update_memory_no_options_exits_1():
    result = runner.invoke(cli_app, ["update-memory", "abc123"])
    assert result.exit_code == 1


@respx.mock
def test_cli_archive_memory_prints_confirmation():
    respx.post(f"http://localhost:8000/memory/abc123/archive").mock(
        return_value=httpx.Response(200, json={"memory_id": "abc123", "archived_at": "2026-01-01T00:00:00+00:00"})
    )
    result = runner.invoke(cli_app, ["archive-memory", "abc123"])
    assert result.exit_code == 0
    assert "Archived" in result.output


@respx.mock
def test_cli_restore_memory_prints_confirmation():
    respx.post(f"http://localhost:8000/memory/abc123/restore").mock(
        return_value=httpx.Response(200, json={"memory_id": "abc123", "status": "active"})
    )
    result = runner.invoke(cli_app, ["restore-memory", "abc123"])
    assert result.exit_code == 0
    assert "Restored" in result.output


@respx.mock
def test_cli_merge_memory_prints_confirmation():
    respx.post(f"http://localhost:8000/memory/src1111/merge").mock(
        return_value=httpx.Response(200, json={"source_id": "src1111", "target_id": "tgt2222"})
    )
    result = runner.invoke(cli_app, ["merge-memory", "src1111", "tgt2222"])
    assert result.exit_code == 0
    assert "src1111"[:8] in result.output


# ---------------------------------------------------------------------------
# Integration tests — PATCH /memory/{id}
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_patch_fact_updates_text_and_embedding(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 original fact patch test")
        r = client.patch(f"/memory/{mid}", json={"fact": "wp038 updated fact patch test"})
        assert r.status_code == 200, r.text
        node = get_memory_node(test_driver, mid)
        assert node["fact"] == "wp038 updated fact patch test"
        assert "updated" in node["text"]
        assert node.get("updated_at") is not None
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_patch_only_so_what_preserves_fact(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 fact preserved in patch test")
        r = client.patch(f"/memory/{mid}", json={"so_what": "the impact is significant"})
        assert r.status_code == 200, r.text
        node = get_memory_node(test_driver, mid)
        assert node["fact"] == "wp038 fact preserved in patch test"
        assert "the impact is significant" in node["text"]
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_patch_tags_replaces_tags(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 tags patch test")
        # First set some tags
        client.patch(f"/memory/{mid}", json={"tags": ["old-tag"]})
        # Now replace
        r = client.patch(f"/memory/{mid}", json={"tags": ["new-tag-a", "new-tag-b"]})
        assert r.status_code == 200, r.text
        node = get_memory_node(test_driver, mid)
        assert set(node["tags"]) == {"new-tag-a", "new-tag-b"}
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_patch_importance_updates_field(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 importance patch test")
        r = client.patch(f"/memory/{mid}", json={"importance": 5})
        assert r.status_code == 200, r.text
        node = get_memory_node(test_driver, mid)
        assert node["importance"] == 5
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_patch_nonexistent_returns_404(client, test_driver):
    r = client.patch("/memory/00000000-0000-0000-0000-000000000000", json={"fact": "x"})
    assert r.status_code == 404


@pytest.mark.integration
def test_patch_archived_memory_returns_404(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 archived patch test")
        client.post(f"/memory/{mid}/archive")
        r = client.patch(f"/memory/{mid}", json={"fact": "should fail"})
        assert r.status_code == 404
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


# ---------------------------------------------------------------------------
# Integration tests — archive / restore
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_archive_sets_status(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 archive status test")
        r = client.post(f"/memory/{mid}/archive")
        assert r.status_code == 200, r.text
        assert r.json()["archived_at"] is not None
        node = get_memory_node(test_driver, mid)
        assert node["status"] == "archived"
        assert node.get("archived_at") is not None
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_archived_memory_excluded_from_search(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 unique archived exclusion search phrase xyzzy")
        client.post(f"/memory/{mid}/archive")
        ids = _search(client, "wp038 unique archived exclusion search phrase xyzzy")
        assert mid not in ids
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_archived_memory_excluded_from_wake_up(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 archived wake up exclusion test", type="insight")
        # Set high importance so it would normally surface
        client.patch(f"/memory/{mid}", json={"importance": 5})
        client.post(f"/memory/{mid}/archive")
        ids = _wake_up_ids(client)
        assert mid not in ids
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_restore_clears_archived_at_and_sets_active(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 restore test")
        client.post(f"/memory/{mid}/archive")
        r = client.post(f"/memory/{mid}/restore")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"
        node = get_memory_node(test_driver, mid)
        assert node["status"] == "active"
        assert node.get("archived_at") is None
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_restored_memory_appears_in_search(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 unique restored search phrase qwerty")
        client.post(f"/memory/{mid}/archive")
        client.post(f"/memory/{mid}/restore")
        ids = _search(client, "wp038 unique restored search phrase qwerty")
        assert mid in ids
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_archive_nonexistent_returns_404(client, test_driver):
    r = client.post("/memory/00000000-0000-0000-0000-000000000000/archive")
    assert r.status_code == 404


@pytest.mark.integration
def test_restore_non_archived_returns_404(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 restore non-archived test")
        r = client.post(f"/memory/{mid}/restore")
        assert r.status_code == 404
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_restore_merged_returns_404(client, test_driver):
    src_id = None
    tgt_id = None
    try:
        src_id = _add_memory(client, "wp038 merge restore source test")
        tgt_id = _add_memory(client, "wp038 merge restore target test")
        client.post(f"/memory/{src_id}/merge", json={"target_id": tgt_id})
        r = client.post(f"/memory/{src_id}/restore")
        assert r.status_code == 404
    finally:
        cleanup_nodes(test_driver, src_id, tgt_id, extra_ids={"Agent": _AGENT_ID})


# ---------------------------------------------------------------------------
# Integration tests — merge
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_merge_sets_source_status_merged(client, test_driver):
    src_id = None
    tgt_id = None
    try:
        src_id = _add_memory(client, "wp038 merge source status test")
        tgt_id = _add_memory(client, "wp038 merge target status test")
        r = client.post(f"/memory/{src_id}/merge", json={"target_id": tgt_id})
        assert r.status_code == 200, r.text
        assert r.json()["source_id"] == src_id
        node = get_memory_node(test_driver, src_id)
        assert node["status"] == "merged"
        assert node["superseded_by"] == tgt_id
    finally:
        cleanup_nodes(test_driver, src_id, tgt_id, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_merge_creates_merged_into_edge(client, test_driver):
    src_id = None
    tgt_id = None
    try:
        src_id = _add_memory(client, "wp038 merge edge source test")
        tgt_id = _add_memory(client, "wp038 merge edge target test")
        client.post(f"/memory/{src_id}/merge", json={"target_id": tgt_id})
        assert edge_exists(test_driver, src_id, "MERGED_INTO", tgt_id)
    finally:
        cleanup_nodes(test_driver, src_id, tgt_id, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_merged_memory_excluded_from_search(client, test_driver):
    src_id = None
    tgt_id = None
    try:
        src_id = _add_memory(client, "wp038 unique merged exclusion phrase zyxwv")
        tgt_id = _add_memory(client, "wp038 merge target for exclusion test")
        client.post(f"/memory/{src_id}/merge", json={"target_id": tgt_id})
        ids = _search(client, "wp038 unique merged exclusion phrase zyxwv")
        assert src_id not in ids
    finally:
        cleanup_nodes(test_driver, src_id, tgt_id, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_merge_rewires_leads_to_edges(client, test_driver):
    src_id = None
    tgt_id = None
    effect_id = None
    try:
        src_id = _add_memory(client, "wp038 merge leads_to source")
        tgt_id = _add_memory(client, "wp038 merge leads_to target")
        effect_id = _add_memory(client, "wp038 merge leads_to effect")
        # Wire source → effect
        with test_driver.session() as s:
            s.run(
                "MATCH (a:Memory {id: $a}), (b:Memory {id: $b}) MERGE (a)-[:LEADS_TO]->(b)",
                a=src_id, b=effect_id,
            )
        client.post(f"/memory/{src_id}/merge", json={"target_id": tgt_id})
        # After merge, target should lead to effect
        assert edge_exists(test_driver, tgt_id, "LEADS_TO", effect_id)
    finally:
        cleanup_nodes(test_driver, src_id, tgt_id, effect_id, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_merge_self_returns_400(client, test_driver):
    mid = None
    try:
        mid = _add_memory(client, "wp038 self merge test")
        r = client.post(f"/memory/{mid}/merge", json={"target_id": mid})
        assert r.status_code == 400
    finally:
        cleanup_nodes(test_driver, mid, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_merge_nonexistent_source_returns_404(client, test_driver):
    tgt_id = None
    try:
        tgt_id = _add_memory(client, "wp038 merge nonexistent source target")
        r = client.post(
            "/memory/00000000-0000-0000-0000-000000000000/merge",
            json={"target_id": tgt_id},
        )
        assert r.status_code == 404
    finally:
        cleanup_nodes(test_driver, tgt_id, extra_ids={"Agent": _AGENT_ID})


@pytest.mark.integration
def test_merge_already_merged_source_returns_404(client, test_driver):
    """Attempting to merge a source that is already merged must return 404."""
    src_id = None
    tgt_id = None
    tgt2_id = None
    try:
        src_id = _add_memory(client, "wp038 double merge source")
        tgt_id = _add_memory(client, "wp038 double merge target 1")
        tgt2_id = _add_memory(client, "wp038 double merge target 2")
        client.post(f"/memory/{src_id}/merge", json={"target_id": tgt_id})
        r = client.post(f"/memory/{src_id}/merge", json={"target_id": tgt2_id})
        assert r.status_code == 404
    finally:
        cleanup_nodes(test_driver, src_id, tgt_id, tgt2_id, extra_ids={"Agent": _AGENT_ID})
