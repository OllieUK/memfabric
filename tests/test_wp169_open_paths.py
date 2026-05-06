"""WP-169: Unit tests for verify_api_key _OPEN_PATHS extension.

Tests U-AUTH-6, U-AUTH-7, U-AUTH-8 from the WP-169 test plan.
No live stack required.
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_request(path: str) -> MagicMock:
    """Create a mock FastAPI Request with the given url.path."""
    req = MagicMock()
    req.url.path = path
    return req


def test_u_auth_6_verify_api_key_allows_well_known_oauth_protected_resource():
    """U-AUTH-6: /.well-known/oauth-protected-resource is in _OPEN_PATHS → no raise."""
    import asyncio
    from memory_service.auth import verify_api_key

    req = _make_request("/.well-known/oauth-protected-resource")
    asyncio.run(verify_api_key(req))  # must not raise


def test_u_auth_7_verify_api_key_allows_mcp_well_known_path():
    """U-AUTH-7: /mcp/.well-known/oauth-protected-resource is in _OPEN_PATHS → no raise."""
    import asyncio
    from memory_service.auth import verify_api_key

    req = _make_request("/mcp/.well-known/oauth-protected-resource")
    asyncio.run(verify_api_key(req))  # must not raise


def test_u_auth_8_verify_api_key_blocks_other_paths():
    """U-AUTH-8: /memory/search with api_keys configured → raises 401 (regression guard)."""
    import asyncio
    from fastapi import HTTPException
    from memory_service.auth import verify_api_key

    req = _make_request("/memory/search")
    req.headers.get = MagicMock(return_value=None)

    # settings is imported inside verify_api_key; patch at the config module level
    with patch("memory_service.config.settings") as mock_settings:
        mock_settings.api_keys = frozenset({"some-key"})

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verify_api_key(req))

    assert exc_info.value.status_code == 401


def test_u_auth_open_paths_includes_all_discovery_paths():
    """_OPEN_PATHS contains all three discovery paths required by WP-169."""
    from memory_service.auth import _OPEN_PATHS

    assert "/.well-known/oauth-protected-resource" in _OPEN_PATHS
    assert "/.well-known/oauth-protected-resource/mcp" in _OPEN_PATHS
    assert "/mcp/.well-known/oauth-protected-resource" in _OPEN_PATHS
