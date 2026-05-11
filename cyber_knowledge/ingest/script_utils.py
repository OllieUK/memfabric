"""
scripts/script_utils.py — Shared utilities for seed and migration scripts.

Provides ApiSettings (pydantic-settings BaseSettings) so every script reads
API_BASE_URL from the environment / .env rather than hard-coding it.
"""

import sys
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_base_url: str = "http://localhost:8000"
    memfabric_mcp_bearer_token: str = ""


def get_api_client(settings: ApiSettings) -> httpx.Client:
    headers = {}
    if settings.memfabric_mcp_bearer_token:
        headers["Authorization"] = f"Bearer {settings.memfabric_mcp_bearer_token}"
    return httpx.Client(base_url=settings.api_base_url, timeout=30, headers=headers)


def make_settings(api_url: str | None) -> ApiSettings:
    """Return ApiSettings, overriding api_base_url when api_url is provided."""
    if api_url:
        return ApiSettings(api_base_url=api_url)
    return ApiSettings()


def fetch_ict_leaves(client: httpx.Client) -> list[dict]:
    """Fetch all active ICT-leaf BusinessAttribute nodes."""
    resp = client.get("/knowledge/business-attributes?limit=500")
    resp.raise_for_status()
    return [b for b in resp.json() if b.get("tier") == "ict-leaf" and b.get("status") == "active"]


def search_threats(client: httpx.Client, query: str, top_k: int) -> list[dict]:
    """Semantic search for Threat nodes matching query."""
    resp = client.post("/knowledge/search/threats", json={"query": query, "limit": top_k})
    resp.raise_for_status()
    return resp.json()
