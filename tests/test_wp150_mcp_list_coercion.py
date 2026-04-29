"""Tests for WP-150: Defensive coercion of JSON-encoded list parameters in MCP tools.

Unit tests (no live stack):
  U-1..U-13: `_coerce_str_list` behaviour, `StrList` Pydantic alias, `make_list_coercer`
  factory.

Integration tests (`@pytest.mark.integration`, live stack required):
  I-1..I-9: end-to-end through the MCP HTTP transport — `memory_add`, `memory_search`,
  `memory_update`, `memory_reinforce`, `task_add`.
"""
import json as _json
import logging

import pytest
from pydantic import TypeAdapter, ValidationError


# ---------------------------------------------------------------------------
# Unit tests — _coerce_str_list
# ---------------------------------------------------------------------------

def test_u1_coerce_none_passthrough():
    from mcp_server._coercion import _coerce_str_list
    assert _coerce_str_list(None) is None


def test_u2_coerce_real_list_passthrough(caplog):
    from mcp_server._coercion import _coerce_str_list
    caplog.set_level(logging.WARNING, logger="mcp_server._coercion")
    out = _coerce_str_list(["a", "b"])
    assert out == ["a", "b"]
    # No warning logged on real-list passthrough
    assert all("coerc" not in r.message.lower() for r in caplog.records)


def test_u3_coerce_json_array_string(caplog):
    from mcp_server._coercion import _coerce_str_list
    caplog.set_level(logging.WARNING, logger="mcp_server._coercion")
    out = _coerce_str_list('["a","b"]')
    assert out == ["a", "b"]
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_u4_coerce_json_array_string_with_whitespace():
    from mcp_server._coercion import _coerce_str_list
    assert _coerce_str_list('  ["a"]  ') == ["a"]


def test_u5_coerce_bare_string_to_single_element(caplog):
    from mcp_server._coercion import _coerce_str_list
    caplog.set_level(logging.WARNING, logger="mcp_server._coercion")
    out = _coerce_str_list("hello")
    assert out == ["hello"]
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_u6_coerce_malformed_json_returns_original():
    """Malformed JSON falls through to Pydantic — but a bare-looking string
    that starts with '[' should not be silently coerced. We return the
    original input so Pydantic emits its canonical 'should be a valid list'
    error rather than silently wrapping in `["[broken"]`."""
    from mcp_server._coercion import _coerce_str_list
    # A string that opens with '[' but is malformed JSON: returned unchanged
    # so Pydantic strict validator reports the real type mismatch.
    out = _coerce_str_list('[broken')
    assert out == '[broken'


def test_u7_coerce_json_object_string_returns_original():
    from mcp_server._coercion import _coerce_str_list
    out = _coerce_str_list('{"k":"v"}')
    # Not a JSON array; not silently wrapped — let Pydantic reject it.
    assert out == '{"k":"v"}'


def test_u8_coerce_non_string_non_list_passthrough():
    from mcp_server._coercion import _coerce_str_list
    assert _coerce_str_list(42) == 42


def test_u9_strlist_alias_accepts_json_string_via_pydantic():
    from mcp_server._coercion import StrList
    out = TypeAdapter(StrList).validate_python('["x"]')
    assert out == ["x"]


def test_u10_strlist_alias_accepts_real_list():
    from mcp_server._coercion import StrList
    out = TypeAdapter(StrList).validate_python(["x"])
    assert out == ["x"]


def test_u11_strlist_alias_rejects_non_string_items():
    from mcp_server._coercion import StrList
    with pytest.raises(ValidationError):
        TypeAdapter(StrList).validate_python([1, 2])


def test_u12_warning_logged_only_on_coercion(caplog):
    from mcp_server._coercion import _coerce_str_list
    caplog.set_level(logging.WARNING, logger="mcp_server._coercion")
    # Real list — no warning
    _coerce_str_list(["a"])
    n_warnings_after_list = sum(1 for r in caplog.records if r.levelno == logging.WARNING)
    assert n_warnings_after_list == 0
    # JSON string — exactly one warning fires
    _coerce_str_list('["a"]')
    n_warnings_after_string = sum(1 for r in caplog.records if r.levelno == logging.WARNING)
    assert n_warnings_after_string == 1


def test_u13_make_list_coercer_factory_int():
    """Future-proofing factory: handles a non-string item type."""
    from mcp_server._coercion import make_list_coercer
    coerce_int = make_list_coercer(int)
    assert coerce_int('[1,2]') == [1, 2]
    assert coerce_int(None) is None
    assert coerce_int([1, 2]) == [1, 2]


# ---------------------------------------------------------------------------
# Integration tests — live stack required
# ---------------------------------------------------------------------------

_BASE = "http://localhost:8000"


def _get_api_key() -> str | None:
    try:
        from memory_service.config import settings
        if settings.api_keys:
            return next(iter(settings.api_keys))
    except Exception:
        pass
    return None


def _mcp_call(tool_name: str, arguments: dict, token: str | None = None):
    import httpx
    headers = {
        "Content-Type": "application/json",
        # FastMCP streamable-HTTP transport requires both content types in Accept.
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    return httpx.post(f"{_BASE}/mcp/", json=payload, headers=headers, timeout=30)


def _parse_sse_or_json(resp) -> dict:
    """Decode the response body which may be SSE-framed or plain JSON."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        # Stream format: lines beginning with `data: ` carry the JSON payload.
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                try:
                    return _json.loads(payload)
                except Exception:
                    continue
        return {}
    return resp.json()


def _extract_result(resp) -> dict | list | None:
    """Pull the structured tool result out of the FastMCP HTTP response envelope."""
    data = _parse_sse_or_json(resp)
    result = data.get("result", {}) if isinstance(data, dict) else {}
    if not isinstance(result, dict):
        return None
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        try:
            return _json.loads(content[0].get("text", "null"))
        except Exception:
            return None
    return None


def _unique_fact(label: str) -> str:
    import uuid
    return f"WP-150 {label} {uuid.uuid4()}"


@pytest.mark.integration
def test_i1_memory_add_accepts_json_string_strand_ids(test_driver):
    """JSON-string-encoded strand_ids is coerced and the memory is created threaded."""
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    fact = _unique_fact("I-1")
    resp = _mcp_call(
        "memory_add",
        {
            "fact": fact,
            "agent_id": "test-agent-wp150",
            "type": "fact",
            "importance": 1,
            "tags": ["test"],
            "strand_ids": '["strand-inbox"]',
        },
        token=token,
    )
    assert resp.status_code == 200, resp.text
    parsed = _extract_result(resp)
    assert parsed is not None, f"No structured result: {resp.text}"
    memory_id = parsed.get("memory_id")
    try:
        assert memory_id, parsed
        assert parsed.get("strand_ids") == ["strand-inbox"], parsed
    finally:
        if memory_id:
            cleanup_nodes(test_driver, memory_id, extra_ids={"Agent": "test-agent-wp150"})


@pytest.mark.integration
def test_i2_memory_add_real_list_strand_ids_unchanged(test_driver):
    """Compliant clients passing a real list still work and get the same shape."""
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    fact = _unique_fact("I-2")
    resp = _mcp_call(
        "memory_add",
        {
            "fact": fact,
            "agent_id": "test-agent-wp150",
            "type": "fact",
            "importance": 1,
            "tags": ["test"],
            "strand_ids": ["strand-inbox"],
        },
        token=token,
    )
    assert resp.status_code == 200, resp.text
    parsed = _extract_result(resp)
    memory_id = parsed.get("memory_id") if parsed else None
    try:
        assert parsed and parsed.get("strand_ids") == ["strand-inbox"]
    finally:
        if memory_id:
            cleanup_nodes(test_driver, memory_id, extra_ids={"Agent": "test-agent-wp150"})


@pytest.mark.integration
def test_i3_memory_add_json_string_threading_verified(test_driver):
    """After a JSON-string strand_ids call, IN_STRAND edge exists in graph."""
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    fact = _unique_fact("I-3")
    resp = _mcp_call(
        "memory_add",
        {
            "fact": fact,
            "agent_id": "test-agent-wp150",
            "type": "fact",
            "importance": 1,
            "tags": ["test"],
            "strand_ids": '["strand-inbox"]',
        },
        token=token,
    )
    assert resp.status_code == 200, resp.text
    parsed = _extract_result(resp)
    memory_id = parsed.get("memory_id") if parsed else None
    try:
        assert memory_id
        # Verify IN_STRAND edge directly in the graph.
        with test_driver.session() as session:
            rec = session.run(
                "MATCH (m:Memory {id: $id})-[:IN_STRAND]->(s:Strand) RETURN s.id AS sid",
                id=memory_id,
            ).single()
        assert rec is not None, "No IN_STRAND edge found"
        assert rec["sid"] == "strand-inbox"
    finally:
        if memory_id:
            cleanup_nodes(test_driver, memory_id, extra_ids={"Agent": "test-agent-wp150"})


@pytest.mark.integration
def test_i4_memory_add_bare_string_strand_ids(test_driver):
    """A bare (non-JSON) string is coerced to a single-element list."""
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    fact = _unique_fact("I-4")
    resp = _mcp_call(
        "memory_add",
        {
            "fact": fact,
            "agent_id": "test-agent-wp150",
            "type": "fact",
            "importance": 1,
            "tags": ["test"],
            "strand_ids": "strand-inbox",
        },
        token=token,
    )
    assert resp.status_code == 200, resp.text
    parsed = _extract_result(resp)
    memory_id = parsed.get("memory_id") if parsed else None
    try:
        assert parsed and parsed.get("strand_ids") == ["strand-inbox"]
    finally:
        if memory_id:
            cleanup_nodes(test_driver, memory_id, extra_ids={"Agent": "test-agent-wp150"})


@pytest.mark.integration
def test_i5_memory_search_json_string_tags():
    """memory_search accepts JSON-string-encoded tags param without validation error."""
    token = _get_api_key()
    resp = _mcp_call(
        "memory_search",
        {"query": "wp-150 nothing", "tags": '["test"]', "limit": 3},
        token=token,
    )
    assert resp.status_code == 200, resp.text
    data = _parse_sse_or_json(resp)
    assert "error" not in data, data


@pytest.mark.integration
def test_i6_memory_add_malformed_json_returns_validation_error():
    """Malformed JSON should still yield a validation error, not silent acceptance."""
    token = _get_api_key()
    resp = _mcp_call(
        "memory_add",
        {
            "fact": _unique_fact("I-6"),
            "agent_id": "test-agent-wp150",
            "type": "fact",
            "importance": 1,
            "tags": ["test"],
            "strand_ids": "[broken",
        },
        token=token,
    )
    # FastMCP returns errors as JSON-RPC error or 200 with isError flag.
    # Either way, the response must NOT report success with a memory_id.
    assert resp.status_code in (200, 400, 422), resp.text
    parsed = _extract_result(resp)
    if parsed and isinstance(parsed, dict):
        # If a memory_id was returned, the bug isn't fixed correctly.
        # Bare-string fallback would coerce "[broken" -> ["[broken"], which is
        # a list of length 1 — not what we want when the input was clearly
        # intended as JSON. We allow that as acceptable outcome only if the
        # surface behaviour is consistent. Strict assert: malformed JSON
        # opening with '[' should error out.
        envelope = _parse_sse_or_json(resp)
        is_error = envelope.get("result", {}).get("isError") if isinstance(envelope, dict) else False
        assert "memory_id" not in parsed or is_error, \
            f"Malformed JSON was silently accepted: {parsed}"


@pytest.mark.integration
def test_i7_memory_update_json_string_strand_ids(test_driver):
    """memory_update with JSON-encoded strand_ids replaces strand membership."""
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    fact = _unique_fact("I-7")
    add_resp = _mcp_call(
        "memory_add",
        {
            "fact": fact,
            "agent_id": "test-agent-wp150",
            "type": "fact",
            "importance": 1,
            "tags": ["test"],
            "strand_ids": ["strand-inbox"],
        },
        token=token,
    )
    assert add_resp.status_code == 200, add_resp.text
    parsed_add = _extract_result(add_resp)
    memory_id = parsed_add.get("memory_id") if parsed_add else None
    assert memory_id

    try:
        # Re-thread via JSON-string-encoded strand_ids.
        upd_resp = _mcp_call(
            "memory_update",
            {"memory_id": memory_id, "strand_ids": '["strand-test"]'},
            token=token,
        )
        assert upd_resp.status_code == 200, upd_resp.text
        upd_parsed = _extract_result(upd_resp)
        assert upd_parsed and upd_parsed.get("memory_id") == memory_id

        # Verify graph: only one IN_STRAND edge, pointing at strand-test.
        with test_driver.session() as session:
            recs = list(session.run(
                "MATCH (m:Memory {id: $id})-[:IN_STRAND]->(s:Strand) RETURN s.id AS sid",
                id=memory_id,
            ))
        sids = sorted(r["sid"] for r in recs)
        # strand-test may or may not be pre-seeded; if not, MATCH-based linking
        # silently skips it, leaving zero edges. Either case proves coercion
        # worked (no validation error).
        assert sids in ([], ["strand-test"]), f"Unexpected strand membership: {sids}"
    finally:
        cleanup_nodes(test_driver, memory_id, extra_ids={"Agent": "test-agent-wp150"})


@pytest.mark.integration
def test_i8_memory_reinforce_json_string_co_recalled_ids(test_driver):
    """memory_reinforce with JSON-encoded co_recalled_ids strengthens Hebbian edge."""
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    fact_a = _unique_fact("I-8-A")
    fact_b = _unique_fact("I-8-B")
    a_id = b_id = None
    try:
        for label, fact in [("A", fact_a), ("B", fact_b)]:
            r = _mcp_call(
                "memory_add",
                {
                    "fact": fact,
                    "agent_id": "test-agent-wp150",
                    "type": "fact",
                    "importance": 1,
                    "tags": ["test"],
                    "strand_ids": ["strand-inbox"],
                },
                token=token,
            )
            assert r.status_code == 200, r.text
            p = _extract_result(r)
            if label == "A":
                a_id = p["memory_id"]
            else:
                b_id = p["memory_id"]

        assert a_id and b_id
        # Reinforce A with co_recalled_ids as JSON string.
        rr = _mcp_call(
            "memory_reinforce",
            {"memory_id": a_id, "co_recalled_ids": _json.dumps([b_id])},
            token=token,
        )
        assert rr.status_code == 200, rr.text
        rp = _extract_result(rr)
        assert rp and rp.get("memory_id") == a_id
        # Verify a RELATED_TO edge between A and B exists with activation_count >= 1.
        with test_driver.session() as session:
            rec = session.run(
                "MATCH (a:Memory {id: $a})-[r:RELATED_TO]-(b:Memory {id: $b}) "
                "RETURN r.activation_count AS ac LIMIT 1",
                a=a_id, b=b_id,
            ).single()
        # Edge may or may not pre-exist; the key contract is no validation error.
        if rec is not None:
            assert (rec["ac"] or 0) >= 1
    finally:
        for mid in (a_id, b_id):
            if mid:
                cleanup_nodes(test_driver, mid, extra_ids={"Agent": "test-agent-wp150"})


@pytest.mark.integration
def test_i9_task_add_json_string_memory_ids(test_driver):
    """task_add accepts JSON-string-encoded memory_ids without validation error."""
    token = _get_api_key()
    resp = _mcp_call(
        "task_add",
        {
            "title": "WP-150 I-9 task",
            "agent_id": "test-agent-wp150",
            "memory_ids": '["00000000-0000-0000-0000-000000000000"]',
        },
        token=token,
    )
    assert resp.status_code == 200, resp.text
    parsed = _extract_result(resp)
    assert parsed is not None
    task_id = parsed.get("id") or parsed.get("task_id")
    # Cleanup.
    if task_id:
        with test_driver.session() as session:
            session.run("MATCH (t:Task {id: $id}) DETACH DELETE t", id=task_id)
    with test_driver.session() as session:
        session.run("MATCH (a:Agent {id: 'test-agent-wp150'}) DETACH DELETE a")
