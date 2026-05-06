"""WP-169: Unit tests for BearerTokenMiddleware discovery path allow-list.

Tests U-MW-1 through U-MW-6 from the WP-169 test plan.
No live stack required.
"""
import asyncio
import pytest
from unittest.mock import patch


async def _run_middleware(middleware, path: str, token_header=None, api_keys=frozenset()):
    """Run BearerTokenMiddleware against a synthetic scope, return status code."""
    received_status = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if message["type"] == "http.response.start":
            received_status.append(message["status"])

    headers = []
    if token_header:
        headers.append((b"authorization", token_header.encode()))

    scope = {
        "type": "http",
        "path": path,
        "headers": headers,
    }

    with patch("memory_service.config.settings") as mock_settings:
        mock_settings.api_keys = api_keys

        async def inner_app(s, r, snd):
            await snd({"type": "http.response.start", "status": 200, "headers": []})
            await snd({"type": "http.response.body", "body": b""})

        mw = middleware(inner_app)
        await mw(scope, receive, send)

    return received_status[0] if received_status else None


def test_u_mw_1_passes_through_well_known_path_with_no_token():
    """U-MW-1: /.well-known/oauth-protected-resource with no token → 200."""
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        path="/.well-known/oauth-protected-resource",
        api_keys=frozenset({"some-key"}),
    ))
    assert status == 200


def test_u_mw_2_passes_through_well_known_path_with_invalid_token():
    """U-MW-2: /.well-known/oauth-protected-resource with wrong token → 200 (discovery never checks token)."""
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        path="/.well-known/oauth-protected-resource",
        token_header="Bearer wrong-token",
        api_keys=frozenset({"some-key"}),
    ))
    assert status == 200


def test_u_mw_3_passes_through_mcp_well_known_path():
    """U-MW-3: Starlette rewrites /mcp/.well-known/... to /.well-known/... inside the sub-app.
    Middleware sees /.well-known/oauth-protected-resource — passes through with no token.
    """
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        path="/.well-known/oauth-protected-resource",
        api_keys=frozenset({"some-key"}),
    ))
    assert status == 200


def test_u_mw_4_blocks_non_well_known_path():
    """U-MW-4: /tools/call with no token → 401 (regression guard)."""
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        path="/tools/call",
        api_keys=frozenset({"some-key"}),
    ))
    assert status == 401


def test_u_mw_5_blocks_well_known_path_substring_lookalike():
    """U-MW-5: /foo/.well-known/oauth-protected-resource-evil → 401 (suffix match must be exact)."""
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        path="/foo/.well-known/oauth-protected-resource-evil",
        api_keys=frozenset({"some-key"}),
    ))
    assert status == 401


def test_u_mw_6_blocks_well_known_query_param_smuggle():
    """U-MW-6: path=/tools/call with query smuggling well-known string → 401.
    Middleware reads scope['path'], not query string — this pins that behaviour.
    """
    from memory_service.mcp_auth import BearerTokenMiddleware

    received_status = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if message["type"] == "http.response.start":
            received_status.append(message["status"])

    scope = {
        "type": "http",
        "path": "/tools/call",
        "query_string": b"path=/.well-known/oauth-protected-resource",
        "headers": [],
    }

    async def run():
        with patch("memory_service.config.settings") as mock_settings:
            mock_settings.api_keys = frozenset({"some-key"})

            async def inner_app(s, r, snd):
                await snd({"type": "http.response.start", "status": 200, "headers": []})
                await snd({"type": "http.response.body", "body": b""})

            from memory_service.mcp_auth import BearerTokenMiddleware
            mw = BearerTokenMiddleware(inner_app)
            await mw(scope, receive, send)

    asyncio.run(run())
    assert received_status[0] == 401


def test_u_mw_7_blocks_well_known_path_with_prefix():
    """U-MW-7 (F-4 regression): /foo/.well-known/oauth-protected-resource → 401.
    Pre-fix endswith() would have passed this through; exact-membership blocks it.
    """
    from memory_service.mcp_auth import BearerTokenMiddleware

    status = asyncio.run(_run_middleware(
        BearerTokenMiddleware,
        path="/foo/.well-known/oauth-protected-resource",
        api_keys=frozenset({"some-key"}),
    ))
    assert status == 401


def test_u_mw_discovery_constant_exists():
    """_DISCOVERY_PATHS constant is present in mcp_auth module and uses exact-match semantics."""
    from memory_service import mcp_auth
    assert hasattr(mcp_auth, "_DISCOVERY_PATHS")
    paths = mcp_auth._DISCOVERY_PATHS
    assert isinstance(paths, frozenset)
    assert "/.well-known/oauth-protected-resource" in paths
    assert "/.well-known/oauth-authorization-server" not in paths
