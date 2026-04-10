import json
import sys
import unittest.mock
from unittest.mock import patch, MagicMock

import httpx
import pytest

# ---------------------------------------------------------------------------
# Fixture payloads
# ---------------------------------------------------------------------------

WRITE_PAYLOAD = {
    "tool_name": "Write",
    "tool_input": {"file_path": "/tmp/test_file.py", "content": "x = 1"},
    "tool_response": {"type": "result", "result": "File written successfully"},
    "session_id": "test-session",
}

EDIT_PAYLOAD = {
    "tool_name": "Edit",
    "tool_input": {"file_path": "/tmp/test_file.py", "old_string": "x = 1", "new_string": "x = 2"},
    "tool_response": {"type": "result", "result": "Edit applied"},
    "session_id": "test-session",
}

BASH_PAYLOAD_SUBSTANTIVE = {
    "tool_name": "Bash",
    "tool_input": {"command": "pytest tests/ -x", "description": "Run tests"},
    "tool_response": {"type": "result", "result": "=== 42 passed in 3.1s ==="},
    "session_id": "test-session",
}

BASH_PAYLOAD_EMPTY = {
    "tool_name": "Bash",
    "tool_input": {"command": "cd /tmp", "description": ""},
    "tool_response": {"type": "result", "result": ""},
    "session_id": "test-session",
}

WEBFETCH_PAYLOAD = {
    "tool_name": "WebFetch",
    "tool_input": {"url": "https://memgraph.com/docs"},
    "tool_response": {"type": "result", "result": "...page content..."},
    "session_id": "test-session",
}

READ_PAYLOAD = {
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/test_file.py"},
    "tool_response": {"type": "result", "result": "x = 1"},
    "session_id": "test-session",
}

# ---------------------------------------------------------------------------
# Group A — parse_payload
# ---------------------------------------------------------------------------


def test_parse_payload_valid_json():
    from hooks.post_tool_use import parse_payload
    result = parse_payload(json.dumps(WRITE_PAYLOAD))
    assert isinstance(result, dict)
    assert result["tool_name"] == "Write"


def test_parse_payload_empty_string():
    from hooks.post_tool_use import parse_payload
    assert parse_payload("") is None


def test_parse_payload_whitespace_only():
    from hooks.post_tool_use import parse_payload
    assert parse_payload("   \n  ") is None


def test_parse_payload_invalid_json():
    from hooks.post_tool_use import parse_payload
    assert parse_payload("{not valid json}") is None


# ---------------------------------------------------------------------------
# Group B — is_substantive
# ---------------------------------------------------------------------------


def test_is_substantive_write_true():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(WRITE_PAYLOAD) is True


def test_is_substantive_edit_true():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(EDIT_PAYLOAD) is True


def test_is_substantive_bash_long_output_true():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(BASH_PAYLOAD_SUBSTANTIVE) is True


def test_is_substantive_bash_empty_output_false():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(BASH_PAYLOAD_EMPTY) is False


def test_is_substantive_bash_short_output_false():
    from hooks.post_tool_use import is_substantive
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo ok"},
        "tool_response": {"type": "result", "result": "ok"},
    }
    assert is_substantive(payload) is False


def test_is_substantive_bash_whitespace_output_false():
    from hooks.post_tool_use import is_substantive
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "true"},
        "tool_response": {"type": "result", "result": "   "},
    }
    assert is_substantive(payload) is False


def test_is_substantive_webfetch_with_url_true():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(WEBFETCH_PAYLOAD) is True


def test_is_substantive_webfetch_without_url_false():
    from hooks.post_tool_use import is_substantive
    payload = {
        "tool_name": "WebFetch",
        "tool_input": {},
        "tool_response": {"type": "result", "result": "content"},
    }
    assert is_substantive(payload) is False


def test_is_substantive_read_false():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(READ_PAYLOAD) is False


def test_is_substantive_unknown_tool_false():
    from hooks.post_tool_use import is_substantive
    payload = {
        "tool_name": "Glob",
        "tool_input": {"pattern": "**/*.py"},
        "tool_response": {"type": "result", "result": "found 5 files"},
    }
    assert is_substantive(payload) is False


# ---------------------------------------------------------------------------
# Group C — build_memory_params
# ---------------------------------------------------------------------------


def test_build_params_write():
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(WRITE_PAYLOAD)
    assert params is not None
    assert params["fact"] == "Wrote file: /tmp/test_file.py"
    assert params["files_modified"] == ["/tmp/test_file.py"]
    assert params["files_read"] == []


def test_build_params_edit():
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(EDIT_PAYLOAD)
    assert params is not None
    assert params["fact"] == "Edited file: /tmp/test_file.py"
    assert params["files_modified"] == ["/tmp/test_file.py"]
    assert params["files_read"] == []


def test_build_params_bash_short_command():
    from hooks.post_tool_use import build_memory_params
    cmd = "pytest tests/ -x"
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
        "tool_response": {"type": "result", "result": "=== 42 passed ==="},
    }
    params = build_memory_params(payload)
    assert params is not None
    assert cmd in params["fact"]
    assert "…" not in params["fact"]


def test_build_params_bash_long_command_truncated():
    from hooks.post_tool_use import build_memory_params, BASH_COMMAND_MAX_LEN
    cmd = "x" * 200
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
        "tool_response": {"type": "result", "result": "=== done ==="},
    }
    params = build_memory_params(payload)
    assert params is not None
    assert "…" in params["fact"]
    # The truncated command portion should be exactly BASH_COMMAND_MAX_LEN chars
    truncated_cmd = params["fact"].replace("Ran bash command: ", "")
    assert truncated_cmd == cmd[:BASH_COMMAND_MAX_LEN] + "…"


def test_build_params_webfetch():
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(WEBFETCH_PAYLOAD)
    assert params is not None
    assert "https://memgraph.com/docs" in params["fact"]
    assert params["files_modified"] == []
    assert params["files_read"] == []


def test_build_params_unknown_tool_returns_none():
    from hooks.post_tool_use import build_memory_params
    payload = {
        "tool_name": "Glob",
        "tool_input": {"pattern": "**/*.py"},
        "tool_response": {"type": "result", "result": "found files"},
    }
    assert build_memory_params(payload) is None


# ---------------------------------------------------------------------------
# Group D — main()
# ---------------------------------------------------------------------------


def _stdin_mock(payload: dict):
    return patch("sys.stdin", new=MagicMock(read=lambda: json.dumps(payload)))


def test_main_write_calls_add_memory():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_called_once()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["type"] == "observation"
    assert call_kwargs["files_modified"] == ["/tmp/test_file.py"]


def test_main_edit_calls_add_memory():
    with _stdin_mock(EDIT_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_called_once()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["files_modified"] == ["/tmp/test_file.py"]


def test_main_bash_substantive_calls_add_memory():
    with _stdin_mock(BASH_PAYLOAD_SUBSTANTIVE):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_called_once()


def test_main_bash_empty_skips_add_memory():
    with _stdin_mock(BASH_PAYLOAD_EMPTY):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_webfetch_calls_add_memory():
    with _stdin_mock(WEBFETCH_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_called_once()


def test_main_read_tool_skips():
    with _stdin_mock(READ_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_empty_stdin_skips():
    with patch("sys.stdin", new=MagicMock(read=lambda: "")):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_invalid_json_skips():
    with patch("sys.stdin", new=MagicMock(read=lambda: "{bad json")):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_importance_is_2():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["importance"] == 2


def test_main_strand_is_session_activity():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["strand_ids"] == ["strand-session-activity"]


def test_main_tags_include_hook():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert "hook" in call_kwargs["tags"]


def test_main_connect_error_exits_cleanly():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.ConnectError("refused")
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_timeout_error_exits_cleanly():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.TimeoutException("timeout")
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_http_status_error_exits_cleanly():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "http://localhost:8000"),
                response=httpx.Response(500),
            )
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_unexpected_error_exits_cleanly():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = Exception("boom")
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_agent_id_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_ID", "my-custom-agent")
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            with patch("hooks.post_tool_use.AGENT_ID", "my-custom-agent"):
                from hooks.post_tool_use import main
                main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["agent_id"] == "my-custom-agent"


def test_main_agent_id_default_claude_code():
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            with patch("hooks.post_tool_use.AGENT_ID", "claude-code"):
                from hooks.post_tool_use import main
                main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["agent_id"] == "claude-code"


def test_main_error_goes_to_stderr_not_stdout(capsys):
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.ConnectError("refused")
            from hooks.post_tool_use import main
            main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err) > 0


# ---------------------------------------------------------------------------
# Integration tests (live stack required)
# ---------------------------------------------------------------------------

from memory_client.client import MemoryClient as _MemoryClient


@pytest.fixture
def mem_client():
    with _MemoryClient(base_url="http://localhost:8000") as c:
        yield c


@pytest.fixture
def cleanup_memories(mem_client):
    """Archive all hook-tagged memories created during the test."""
    yield
    try:
        hits = mem_client.search_memory(
            "hook post-tool-use observation",
            tags=["hook", "post-tool-use"],
            limit=50,
        )
        for hit in hits:
            try:
                mem_client.archive_memory(hit["id"])
            except Exception:
                pass
    except Exception:
        pass


def _run_hook_with_payload(payload: dict) -> None:
    from hooks.post_tool_use import main
    with unittest.mock.patch("sys.stdin", new=unittest.mock.MagicMock(read=lambda: json.dumps(payload))):
        main()


@pytest.mark.integration
class TestWP126Integration:

    def test_integration_write_observation_stored(self, mem_client, cleanup_memories):
        """Running main() with Write payload stores an observation retrievable by file path."""
        file_path = "/tmp/wp126_integration_write_test.py"
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": "x = 1"},
            "tool_response": {"type": "result", "result": "File written successfully"},
            "session_id": "test-session",
        }
        _run_hook_with_payload(payload)

        hits = mem_client.get_memories_by_file(file_path, role="modified")
        facts = [h.get("text", "") or h.get("fact", "") for h in hits]
        assert any(file_path in f for f in facts), f"Expected memory for {file_path}, got: {facts}"

    def test_integration_bash_observation_stored(self, mem_client, cleanup_memories):
        """Substantive Bash payload stores an observation memory."""
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_wp126_post_tool_use_hook.py -v", "description": "Run WP-126 tests"},
            "tool_response": {"type": "result", "result": "=== 38 passed in 2.1s ==="},
            "session_id": "test-session",
        }
        hits_before = mem_client.search_memory(
            "pytest tests/test_wp126_post_tool_use_hook.py",
            tags=["hook", "post-tool-use"],
            limit=50,
        )
        count_before = len(hits_before)

        _run_hook_with_payload(payload)

        hits_after = mem_client.search_memory(
            "pytest tests/test_wp126_post_tool_use_hook.py",
            tags=["hook", "post-tool-use"],
            limit=50,
        )
        assert len(hits_after) > count_before

    def test_integration_empty_bash_not_stored(self, mem_client, cleanup_memories):
        """Empty-output Bash payload stores nothing."""
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "cd /tmp", "description": ""},
            "tool_response": {"type": "result", "result": ""},
            "session_id": "test-session",
        }
        hits_before = mem_client.search_memory(
            "hook post-tool-use observation",
            tags=["hook", "post-tool-use"],
            limit=100,
        )
        count_before = len(hits_before)

        _run_hook_with_payload(payload)

        hits_after = mem_client.search_memory(
            "hook post-tool-use observation",
            tags=["hook", "post-tool-use"],
            limit=100,
        )
        assert len(hits_after) == count_before

    def test_integration_service_unreachable_exits_cleanly(self):
        """Hook exits cleanly when service is unreachable."""
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/unreachable_test.py", "content": "x = 1"},
            "tool_response": {"type": "result", "result": "File written successfully"},
            "session_id": "test-session",
        }
        with unittest.mock.patch("hooks.post_tool_use.API_BASE_URL", "http://localhost:19999"):
            from hooks.post_tool_use import main
            with unittest.mock.patch("sys.stdin", new=unittest.mock.MagicMock(read=lambda: json.dumps(payload))):
                main()  # must not raise

    def test_integration_observation_has_correct_type(self, mem_client, cleanup_memories):
        """Stored observation has type=observation and importance=2."""
        file_path = "/tmp/wp126_integration_type_check.py"
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": "y = 2"},
            "tool_response": {"type": "result", "result": "File written successfully"},
            "session_id": "test-session",
        }
        _run_hook_with_payload(payload)

        hits = mem_client.get_memories_by_file(file_path, role="modified")
        matching = [h for h in hits if file_path in (h.get("text", "") or "")]
        assert matching, f"No memory found for {file_path}"
        hit = matching[0]
        assert hit.get("type") == "observation", f"Expected type=observation, got {hit.get('type')}"
        assert hit.get("importance") == 2, f"Expected importance=2, got {hit.get('importance')}"
