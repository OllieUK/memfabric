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
