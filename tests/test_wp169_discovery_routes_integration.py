"""WP-169: Integration tests for OAuth protected-resource metadata discovery routes.

Tests I-1 through I-8 from the WP-169 test plan.
Require live stack at http://localhost:8000 with API_KEYS configured (non-empty).

Run with: pytest -m integration tests/test_wp169_discovery_routes_integration.py
"""
import pytest

_BASE = "http://localhost:8000"


def _get_api_key() -> str | None:
    try:
        from memory_service.config import settings
        if settings.api_keys:
            return next(iter(settings.api_keys))
    except Exception:
        pass
    return None


@pytest.mark.integration
def test_i1_well_known_protected_resource_no_auth_returns_200():
    """I-1: GET /.well-known/oauth-protected-resource with no auth → 200 + valid JSON."""
    import httpx
    resp = httpx.get(f"{_BASE}/.well-known/oauth-protected-resource", timeout=10)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "resource" in body
    assert body["authorization_servers"] == []


@pytest.mark.integration
def test_i2_well_known_protected_resource_mcp_no_auth_returns_200():
    """I-2: GET /.well-known/oauth-protected-resource/mcp with no auth → 200 + valid JSON."""
    import httpx
    resp = httpx.get(f"{_BASE}/.well-known/oauth-protected-resource/mcp", timeout=10)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "resource" in body
    assert body["authorization_servers"] == []


@pytest.mark.integration
def test_i3_mcp_well_known_protected_resource_no_auth_returns_200_not_401():
    """I-3: GET /mcp/.well-known/oauth-protected-resource with no auth → 200 (NOT 401).
    This is the primary bug-driver test — was 401 before WP-169.
    """
    import httpx
    resp = httpx.get(f"{_BASE}/mcp/.well-known/oauth-protected-resource", timeout=10)
    assert resp.status_code != 401, "Still returning 401 — BearerTokenMiddleware allow-list not applied"
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "resource" in body
    assert body["authorization_servers"] == []


@pytest.mark.integration
def test_i4_mcp_post_with_valid_bearer_still_works():
    """I-4: POST /mcp/ with valid bearer + initialize → 200. Regression guard."""
    import httpx
    token = _get_api_key()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.1"},
        },
    }
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, headers=headers, timeout=30)
    assert resp.status_code in (200, 202), f"Expected 200/202, got {resp.status_code}: {resp.text[:200]}"


@pytest.mark.integration
def test_i5_mcp_post_with_no_bearer_still_returns_401():
    """I-5: POST /mcp/ with no token → 401. Regression guard — carve-out must not leak to JSON-RPC."""
    import httpx
    from memory_service.config import settings
    if not settings.api_keys:
        pytest.skip("No API_KEYS configured — auth not enforced")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0.0.1"},
        },
    }
    resp = httpx.post(f"{_BASE}/mcp/", json=payload, timeout=10)
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


@pytest.mark.integration
def test_i6_memory_search_with_no_bearer_still_returns_401():
    """I-6: POST /memory/search with no token → 401. Regression guard for _OPEN_PATHS extension."""
    import httpx
    from memory_service.config import settings
    if not settings.api_keys:
        pytest.skip("No API_KEYS configured — auth not enforced")
    resp = httpx.post(f"{_BASE}/memory/search", json={"query": "test"}, timeout=10)
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


@pytest.mark.integration
def test_i7_metadata_resource_url_matches_public_base_url():
    """I-7: resource URL in discovery doc starts with settings.public_base_url and ends with /mcp/."""
    import httpx
    from memory_service.config import settings
    resp = httpx.get(f"{_BASE}/.well-known/oauth-protected-resource", timeout=10)
    assert resp.status_code == 200
    body = resp.json()
    expected_base = settings.public_base_url.rstrip("/")
    assert body["resource"].startswith(expected_base), (
        f"resource {body['resource']!r} does not start with {expected_base!r}"
    )
    assert body["resource"].endswith("/mcp/"), (
        f"resource {body['resource']!r} does not end with /mcp/"
    )


@pytest.mark.integration
def test_i8_metadata_well_known_authorization_server_returns_404():
    """I-8: GET /.well-known/oauth-authorization-server → 404.
    Pins the deliberate decision NOT to serve AS metadata (WP-169 out of scope).
    """
    import httpx
    resp = httpx.get(f"{_BASE}/.well-known/oauth-authorization-server", timeout=10)
    assert resp.status_code == 404, (
        f"Expected 404 for oauth-authorization-server, got {resp.status_code}. "
        "If this is intentional, update the test and add a follow-up WP."
    )
