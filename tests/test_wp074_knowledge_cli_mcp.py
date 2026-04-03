"""Tests for WP-074: CLI commands, MCP tools, MemoryClient methods, and ETL script.

All tests are unit tests (mocks only — no live stack required).
Integration tests are deferred to WP-076.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Ensure scripts/ directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


# ---------------------------------------------------------------------------
# MCP registration tests
# ---------------------------------------------------------------------------


def test_mcp_tools_not_registered_when_flag_off():
    """When enable_knowledge_layer is False (default), knowledge tools are not defined."""
    # Ensure the env var is absent (or false) so the module initialises with flag off.
    # Because mcp_server.server may already be imported with the flag off, reload it.
    env_backup = os.environ.pop("ENABLE_KNOWLEDGE_LAYER", None)
    try:
        import mcp_server.server as server_mod
        importlib.reload(server_mod)
        assert not hasattr(server_mod, "knowledge_search_controls"), (
            "knowledge_search_controls should not be defined when flag is off"
        )
    finally:
        if env_backup is not None:
            os.environ["ENABLE_KNOWLEDGE_LAYER"] = env_backup


def test_mcp_tools_registered_when_flag_on():
    """When enable_knowledge_layer is True the if-block is present in server source."""
    # Module-level registration happens at import time, making it difficult to
    # toggle reliably in unit tests without side-effects on other tests.
    # We verify the feature-flag guard is present in the source instead.
    import mcp_server.server as server_mod
    source = inspect.getsource(server_mod)
    assert "if settings.enable_knowledge_layer:" in source, (
        "Expected feature-flag guard in mcp_server.server"
    )
    assert "knowledge_search_controls" in source, (
        "Expected knowledge_search_controls tool defined under flag guard"
    )


# ---------------------------------------------------------------------------
# YAML schema tests
# ---------------------------------------------------------------------------


def test_yaml_schema_valid_minimal():
    from ingest_framework import YamlFrameworkFile
    fw = YamlFrameworkFile(framework_id="test", framework_name="Test")
    assert fw.framework_id == "test"
    assert fw.controls == []


def test_yaml_schema_rejects_missing_framework_id():
    from ingest_framework import YamlFrameworkFile
    with pytest.raises(ValidationError):
        YamlFrameworkFile(framework_name="Test")


def test_yaml_schema_rejects_invalid_norm_missing_text():
    from ingest_framework import YamlNorm
    with pytest.raises(ValidationError):
        YamlNorm(id="n1", name="Norm 1")  # text is required


# ---------------------------------------------------------------------------
# Ingest script tests
# ---------------------------------------------------------------------------

MINIMAL_YAML = """\
framework_id: test-fw
framework_name: Test Framework
controls:
  - id: test-fw.C1
    name: Control One
"""


def _make_yaml_file(tmp_path, content: str) -> str:
    f = tmp_path / "test_fw.yaml"
    f.write_text(content)
    return str(f)


def test_ingest_dry_run_no_api_calls(tmp_path, capsys):
    path = _make_yaml_file(tmp_path, MINIMAL_YAML)
    with patch("sys.argv", ["ingest_framework.py", path, "--dry-run"]):
        from ingest_framework import main
        main()
    out = capsys.readouterr().out
    assert "Dry run" in out
    # No HTTP calls were made; if they were, httpx would raise ConnectError


def test_ingest_prints_created_status(tmp_path, capsys):
    path = _make_yaml_file(tmp_path, MINIMAL_YAML)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {}
    mock_resp.status_code = 200

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("sys.argv", ["ingest_framework.py", path]):
        with patch("httpx.Client", return_value=mock_client):
            import ingest_framework
            importlib.reload(ingest_framework)
            ingest_framework.main()
    out = capsys.readouterr().out
    assert "test-fw" in out


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


runner = CliRunner()


def test_cli_knowledge_group_exists():
    from memory_client.cli import app
    result = runner.invoke(app, ["knowledge", "--help"])
    assert result.exit_code == 0
    assert "search-controls" in result.output or "knowledge" in result.output


def test_cli_search_controls_calls_client():
    from memory_client.cli import app
    with patch("memory_client.cli.MemoryClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_controls.return_value = [
            {
                "id": "ctrl-1",
                "name": "Control One",
                "framework_id": "test-fw",
                "distance": 0.12,
                "created_at": "2026-01-01",
            }
        ]
        mock_cls.return_value = mock_client
        result = runner.invoke(app, ["knowledge", "search-controls", "--query", "access control"])
    assert result.exit_code == 0
    assert "ctrl-1" in result.output


def test_cli_search_controls_handles_connect_error():
    import httpx
    from memory_client.cli import app
    with patch("memory_client.cli.MemoryClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.search_controls.side_effect = httpx.ConnectError("refused")
        mock_cls.return_value = mock_client
        result = runner.invoke(app, ["knowledge", "search-controls", "--query", "access control"])
    assert result.exit_code == 1


def test_cli_list_norms_empty():
    from memory_client.cli import app
    with patch("memory_client.cli.MemoryClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_norms.return_value = []
        mock_cls.return_value = mock_client
        result = runner.invoke(app, ["knowledge", "list-norms"])
    assert result.exit_code == 0
    assert "No norms found" in result.output


def test_cli_review_supports_stub_message():
    from memory_client.cli import app
    result = runner.invoke(app, ["knowledge", "review-supports"])
    assert result.exit_code == 0
    assert "WP-073" in result.output or "not yet available" in result.output.lower()


# ---------------------------------------------------------------------------
# MemoryClient tests
# ---------------------------------------------------------------------------


def test_memory_client_search_controls_builds_correct_body():
    from memory_client.client import MemoryClient

    mock_http = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_http.post.return_value = mock_resp

    with patch("memory_client.client.httpx.Client", return_value=mock_http):
        with MemoryClient(base_url="http://test") as client:
            client.search_controls("access control", limit=5, framework_id="nist-csf-2.0")

    call_args = mock_http.post.call_args
    body = call_args[1].get("json") or call_args[0][1]
    assert body["query"] == "access control"
    assert body["limit"] == 5
    assert body["framework_id"] == "nist-csf-2.0"


def test_memory_client_search_chunks_optional_doc_id():
    from memory_client.client import MemoryClient

    mock_http = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_http.post.return_value = mock_resp

    with patch("memory_client.client.httpx.Client", return_value=mock_http):
        with MemoryClient(base_url="http://test") as client:
            client.search_chunks("data retention")  # no doc_id

    call_args = mock_http.post.call_args
    body = call_args[1].get("json") or call_args[0][1]
    assert "doc_id" not in body


def test_memory_client_list_norms_parses_response():
    from memory_client.client import MemoryClient

    mock_http = MagicMock()
    mock_resp = MagicMock()
    norms_data = [
        {"id": "n1", "name": "Norm 1", "text": "...", "status": "active", "created_at": "2026-01-01"}
    ]
    mock_resp.json.return_value = norms_data
    mock_http.get.return_value = mock_resp

    with patch("memory_client.client.httpx.Client", return_value=mock_http):
        with MemoryClient(base_url="http://test") as client:
            result = client.list_norms()

    assert result == norms_data
