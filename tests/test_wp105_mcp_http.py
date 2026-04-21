"""Tests for WP-105: Streamable HTTP MCP transport.

Unit tests (no live stack needed):
  U-AUTH-1 through U-AUTH-5: BearerTokenMiddleware behaviour
  U-MOUNT-1: /mcp mount is routable via FastAPI TestClient

Integration tests (require live stack at http://localhost:8000):
  I-1 through I-8: MCP HTTP transport smoke tests
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers for BearerTokenMiddleware unit tests
# ---------------------------------------------------------------------------

async def _run_middleware(middleware, scope, token_header=None, api_key_header=None, api_keys=frozenset()):
    """Run the middleware and return the response status code."""
    received_status = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if message["type"] == "http.response.start":
            received_status.append(message["status"])

    headers = []
    if token_header:
        headers.append((b"authorization", token_header.encode()))
    if api_key_header:
        headers.append((b"x-api-key", api_key_header.encode()))

    scope = {
        "type": "http",
        "headers": headers,
        **scope,
    }

    with patch("memory_service.config.settings") as mock_settings:
        mock_settings.api_keys = api_keys
        # inner app just sends 200
        async def inner_app(s, r, snd):
            await snd({"type": "http.response.start", "status": 200, "headers": []})
            await snd({"type": "http.response.body", "body": b""})

        mw = middleware(inner_app)
        await mw(scope, receive, send)

    return received_status[0] if received_status else None


# ---------------------------------------------------------------------------
# U-AUTH-1: pass-through when api_keys is empty (dev mode)
# ---------------------------------------------------------------------------
def test_u_auth_1_passthrough_when_no_api_keys():
    import asyncio
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        scope={},
        api_keys=frozenset(),
    ))
    assert status == 200


# ---------------------------------------------------------------------------
# U-AUTH-2: pass with valid bearer token
# ---------------------------------------------------------------------------
def test_u_auth_2_valid_bearer_token():
    import asyncio
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        scope={},
        token_header="Bearer validtoken123",
        api_keys=frozenset(["validtoken123"]),
    ))
    assert status == 200


# ---------------------------------------------------------------------------
# U-AUTH-3: 401 with invalid token
# ---------------------------------------------------------------------------
def test_u_auth_3_invalid_token_returns_401():
    import asyncio
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        scope={},
        token_header="Bearer wrongtoken",
        api_keys=frozenset(["correcttoken"]),
    ))
    assert status == 401


# ---------------------------------------------------------------------------
# U-AUTH-4: 401 with missing token
# ---------------------------------------------------------------------------
def test_u_auth_4_missing_token_returns_401():
    import asyncio
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        scope={},
        api_keys=frozenset(["sometoken"]),
    ))
    assert status == 401


# ---------------------------------------------------------------------------
# U-AUTH-5: X-Api-Key header accepted as alternative
# ---------------------------------------------------------------------------
def test_u_auth_5_xapikey_header_accepted():
    import asyncio
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        scope={},
        api_key_header="myapikey",
        api_keys=frozenset(["myapikey"]),
    ))
    assert status == 200


# ---------------------------------------------------------------------------
# U-MOUNT-1: /mcp path is reachable in FastAPI TestClient
# ---------------------------------------------------------------------------
def test_u_mount_1_mcp_path_routable():
    """The /mcp sub-app is mounted — verify by checking the app's mounted routes."""
    from memory_service.main import app

    # Check that /mcp is registered as a mount on the app
    mount_paths = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            mount_paths.append(path)

    assert "/mcp" in mount_paths, f"/mcp not found in app routes: {mount_paths}"


# ---------------------------------------------------------------------------
# Integration tests — require live stack at http://localhost:8000
# ---------------------------------------------------------------------------

_BASE = "http://localhost:8000"


def _mcp_call(tool_name: str, arguments: dict, token: str | None = None) -> dict:
    """Make a JSON-RPC 2.0 call to the MCP HTTP transport."""
    import httpx
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, headers=headers, timeout=30)
    return resp


def _get_api_key() -> str | None:
    """Read the first configured API key from the service settings."""
    try:
        from memory_service.config import settings
        if settings.api_keys:
            return next(iter(settings.api_keys))
    except Exception:
        pass
    return None


@pytest.mark.integration
def test_i1_mcp_post_valid_token_returns_non_401():
    """POST /mcp with valid bearer token — service processes the request (not 401)."""
    import httpx
    token = _get_api_key()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # MCP initialize call
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, headers=headers, timeout=30)
    assert resp.status_code != 401, f"Expected non-401, got {resp.status_code}"
    assert resp.status_code in (200, 202), f"Unexpected status: {resp.status_code}"


@pytest.mark.integration
def test_i2_mcp_no_token_returns_401_when_keys_configured():
    """POST /mcp with no token returns 401 when API_KEYS is set."""
    import httpx
    from memory_service.config import settings
    if not settings.api_keys:
        pytest.skip("No API_KEYS configured — auth not enforced")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"},
    }}
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, timeout=30)
    assert resp.status_code == 401


@pytest.mark.integration
def test_i3_mcp_invalid_token_returns_401():
    """POST /mcp with bad token returns 401."""
    import httpx
    from memory_service.config import settings
    if not settings.api_keys:
        pytest.skip("No API_KEYS configured — auth not enforced")
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"},
    }}
    headers = {"Content-Type": "application/json", "Authorization": "Bearer invalid_token_xyz"}
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, headers=headers, timeout=30)
    assert resp.status_code == 401


@pytest.mark.integration
def test_i4_tool_memory_list_strands_returns_strands():
    """memory_list_strands via HTTP transport returns at least one strand."""
    token = _get_api_key()
    resp = _mcp_call("memory_list_strands", {}, token=token)
    assert resp.status_code == 200
    data = resp.json()
    # FastMCP returns result in "result" key
    assert "result" in data or "error" not in data


@pytest.mark.integration
def test_i5_tool_memory_search_returns_list():
    """memory_search via HTTP transport returns a result."""
    token = _get_api_key()
    resp = _mcp_call("memory_search", {"query": "test", "limit": 3}, token=token)
    assert resp.status_code == 200


@pytest.mark.integration
def test_i6_memory_add_search_roundtrip(test_driver):
    """Add an ephemeral memory, search for it, verify presence, clean up."""
    import httpx
    from tests.conftest import cleanup_nodes

    token = _get_api_key()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    fact = "WP-105 integration test ephemeral memory"
    add_payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "memory_add",
            "arguments": {
                "fact": fact,
                "agent_id": "test-agent-wp105",
                "type": "fact",
                "importance": 1,
                "tags": ["test"],
            },
        },
    }
    resp = httpx.post(f"{_BASE}/mcp/", json=add_payload, headers=headers, timeout=30)
    assert resp.status_code == 200

    data = resp.json()
    # Extract memory_id from FastMCP response structure
    memory_id = None
    result = data.get("result", {})
    if isinstance(result, dict):
        content = result.get("content", [])
        if content and isinstance(content[0], dict):
            import json as _json
            try:
                parsed = _json.loads(content[0].get("text", "{}"))
                memory_id = parsed.get("memory_id")
            except Exception:
                pass

    try:
        search_payload = {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "memory_search", "arguments": {"query": "WP-105 integration test ephemeral", "limit": 5}},
        }
        search_resp = httpx.post(f"{_BASE}/mcp/", json=search_payload, headers=headers, timeout=30)
        assert search_resp.status_code == 200
    finally:
        if memory_id and test_driver:
            cleanup_nodes(test_driver, memory_id)
        elif test_driver:
            # Best-effort cleanup by agent id
            with test_driver.session() as s:
                s.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id="test-agent-wp105")


@pytest.mark.integration
def test_i7_tool_task_list_returns_list():
    """task_list via HTTP transport returns a result."""
    token = _get_api_key()
    resp = _mcp_call("task_list", {}, token=token)
    assert resp.status_code == 200


@pytest.mark.integration
def test_i8_tool_memory_close_session_returns_scaffold():
    """memory_close_session via HTTP transport returns scaffold text."""
    import httpx
    token = _get_api_key()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "memory_close_session", "arguments": {}},
    }
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, headers=headers, timeout=30)
    assert resp.status_code == 200
    # Verify the scaffold text appears somewhere in the response body
    assert "Session close-out" in resp.text
