# tests/test_wp096_auth.py
"""
WP-096 — API authentication (bearer tokens / API keys)

Unit tests: no live stack required, all FastAPI routes tested via TestClient
            with API_KEYS patched on the settings object.

Integration tests: require a live stack (Memgraph + FastAPI service running
                   with API_KEYS set in .env). Run with:
                   pytest -m integration tests/test_wp096_auth.py
"""
import pytest
from fastapi.testclient import TestClient

from memory_service.main import app
from memory_client.config import settings as client_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_keys(monkeypatch, keys: list[str]) -> None:
    """Patch api_keys on the *current* settings singleton in memory_service.config.

    We import the module (not the object) so that if another test has reloaded
    memory_service.config (e.g. test_wp070.py's app_client fixture), we still
    patch the live singleton that auth.py will read, not a stale pre-reload copy.
    """
    import memory_service.config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "api_keys", keys)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestAuthUnit:
    """Fast unit tests against the TestClient (no live Memgraph)."""

    def test_health_always_open(self, monkeypatch):
        """GET /health must succeed without any token, even when keys are configured."""
        _set_keys(monkeypatch, ["secret"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_protected_endpoint_401_when_keys_set_no_token(self, monkeypatch):
        """A protected endpoint returns 401 when API_KEYS is set and no token is sent."""
        _set_keys(monkeypatch, ["secret"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/strands")
        assert resp.status_code == 401
        assert resp.headers.get("WWW-Authenticate") == "Bearer"

    def test_protected_endpoint_401_wrong_token(self, monkeypatch):
        """A wrong bearer token returns 401."""
        _set_keys(monkeypatch, ["correct"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/strands", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_bearer_token_accepted(self, monkeypatch):
        """Authorization: Bearer <token> is accepted when the token is in API_KEYS."""
        _set_keys(monkeypatch, ["my-secret"])
        with TestClient(app, raise_server_exceptions=False) as client:
            # /strands will either 200 or 503 (no Memgraph) — both mean auth passed
            resp = client.get("/strands", headers={"Authorization": "Bearer my-secret"})
        assert resp.status_code != 401

    def test_x_api_key_header_accepted(self, monkeypatch):
        """X-Api-Key header is accepted as an alternative to Authorization: Bearer."""
        _set_keys(monkeypatch, ["my-secret"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/strands", headers={"X-Api-Key": "my-secret"})
        assert resp.status_code != 401

    def test_multiple_keys_any_valid(self, monkeypatch):
        """All keys listed in API_KEYS are independently accepted."""
        _set_keys(monkeypatch, ["key-alpha", "key-beta"])
        with TestClient(app, raise_server_exceptions=False) as client:
            for key in ("key-alpha", "key-beta"):
                resp = client.get("/strands", headers={"Authorization": f"Bearer {key}"})
                assert resp.status_code != 401, f"Key {key!r} was rejected"

    def test_no_keys_configured_open_access(self, monkeypatch):
        """When API_KEYS is empty the service is open (dev mode)."""
        _set_keys(monkeypatch, [])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/strands")
        assert resp.status_code != 401

    def test_x_api_key_uppercase_variant(self, monkeypatch):
        """X-API-Key (all caps) is also accepted."""
        _set_keys(monkeypatch, ["tok"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/strands", headers={"X-API-Key": "tok"})
        assert resp.status_code != 401

    def test_bearer_case_insensitive_scheme(self, monkeypatch):
        """'bearer' (lowercase) prefix is accepted."""
        _set_keys(monkeypatch, ["tok"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/strands", headers={"Authorization": "bearer tok"})
        assert resp.status_code != 401

    def test_post_memory_protected(self, monkeypatch):
        """POST /memory is protected (not just read endpoints)."""
        _set_keys(monkeypatch, ["s"])
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/memory",
                json={"fact": "test", "type": "fact", "agent_id": "test"},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests (require live stack)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAuthIntegration:
    """
    Run against a live FastAPI service with API_KEYS set in .env.

    Prerequisites:
      1. Memgraph running
      2. FastAPI service running with API_KEYS=<some-token> in .env
      3. Pass --api-key=<some-token> or set API_KEY env var for the client

    These tests use httpx directly against the running service.
    """

    @pytest.fixture
    def live_url(self):
        return client_settings.api_base_url if client_settings.api_base_url else "http://localhost:8000"

    @pytest.fixture
    def valid_key(self):
        """Requires API_KEY env var to be set to a key in the service's API_KEYS."""
        import os
        key = os.environ.get("API_KEY")
        if not key:
            pytest.skip("API_KEY env var not set — skipping live auth integration tests")
        return key

    def test_live_health_no_auth(self, live_url):
        import httpx
        resp = httpx.get(f"{live_url}/health", verify=False)
        assert resp.status_code == 200

    def test_live_strands_401_no_token(self, live_url):
        import httpx
        resp = httpx.get(f"{live_url}/strands", verify=False)
        assert resp.status_code == 401

    def test_live_strands_200_with_bearer(self, live_url, valid_key):
        import httpx
        resp = httpx.get(
            f"{live_url}/strands",
            headers={"Authorization": f"Bearer {valid_key}"},
            verify=False,
        )
        assert resp.status_code == 200

    def test_live_strands_200_with_x_api_key(self, live_url, valid_key):
        import httpx
        resp = httpx.get(
            f"{live_url}/strands",
            headers={"X-Api-Key": valid_key},
            verify=False,
        )
        assert resp.status_code == 200

    def test_live_401_wrong_token(self, live_url):
        import httpx
        resp = httpx.get(
            f"{live_url}/strands",
            headers={"Authorization": "Bearer definitely-wrong"},
            verify=False,
        )
        assert resp.status_code == 401
