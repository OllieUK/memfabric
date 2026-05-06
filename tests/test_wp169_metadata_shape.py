"""WP-169: Unit tests for RFC 9728 protected-resource metadata document shape.

Tests U-DOC-1 through U-DOC-4 from the WP-169 test plan.
No live stack required.
"""
import json
import asyncio
import pytest
from unittest.mock import patch


def _get_metadata_handler():
    """Import the metadata handler from main, patching settings to avoid Memgraph connection."""
    from memory_service.main import _oauth_protected_resource_metadata
    return _oauth_protected_resource_metadata


def test_u_doc_1_metadata_document_shape():
    """U-DOC-1: Handler returns dict with required RFC 9728 keys; authorization_servers == []."""
    handler = _get_metadata_handler()

    with patch("memory_service.main.settings") as mock_settings:
        mock_settings.public_base_url = "http://localhost:8000"
        result = asyncio.run(handler())

    assert isinstance(result, dict)
    assert "resource" in result
    assert "authorization_servers" in result
    assert "bearer_methods_supported" in result
    assert "resource_documentation" in result
    assert result["authorization_servers"] == []
    assert result["bearer_methods_supported"] == ["header"]


def test_u_doc_2_metadata_resource_url_uses_public_base_url():
    """U-DOC-2: resource URL uses settings.public_base_url."""
    handler = _get_metadata_handler()

    with patch("memory_service.main.settings") as mock_settings:
        mock_settings.public_base_url = "https://example.com"
        result = asyncio.run(handler())

    assert result["resource"] == "https://example.com/mcp/"


def test_u_doc_3_metadata_resource_url_strips_trailing_slash_on_base():
    """U-DOC-3: Trailing slash on public_base_url doesn't produce double slash."""
    handler = _get_metadata_handler()

    with patch("memory_service.main.settings") as mock_settings:
        mock_settings.public_base_url = "https://example.com/"
        result = asyncio.run(handler())

    assert result["resource"] == "https://example.com/mcp/"
    assert "//mcp/" not in result["resource"]


def test_u_doc_4_metadata_is_json_serialisable():
    """U-DOC-4: Handler result is JSON serialisable and round-trips cleanly."""
    handler = _get_metadata_handler()

    with patch("memory_service.main.settings") as mock_settings:
        mock_settings.public_base_url = "http://localhost:8000"
        result = asyncio.run(handler())

    serialised = json.dumps(result)
    roundtripped = json.loads(serialised)
    assert roundtripped == result
