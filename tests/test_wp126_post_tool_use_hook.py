"""WP-126 / WP-154: Tests for the PostToolUse hook.

WP-154 narrowed the hook's substantive set to two semantic milestones:
  * pytest runs (any Bash command starting with `pytest` or `python -m pytest`)
  * git commits (any Bash command starting with `git commit`)

Write, Edit, WebFetch, and other Bash commands no longer trigger a memory
write; file-level provenance moved to deliberate `memory_add` calls.
"""
import json
from unittest.mock import patch, MagicMock

import httpx


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

PYTEST_PAYLOAD = {
    "tool_name": "Bash",
    "tool_input": {"command": "pytest tests/ -x", "description": "Run tests"},
    "tool_response": {"type": "result", "result": "===== 42 passed in 3.10s ====="},
    "session_id": "test-session",
}

PYTEST_FAIL_PAYLOAD = {
    "tool_name": "Bash",
    "tool_input": {"command": "python3 -m pytest", "description": "Run tests"},
    "tool_response": {
        "type": "result",
        "result": "===== 5 passed, 2 failed in 1.23s =====",
    },
    "session_id": "test-session",
}

GIT_COMMIT_PAYLOAD = {
    "tool_name": "Bash",
    "tool_input": {"command": "git commit -m 'fix: bug'"},
    "tool_response": {
        "type": "result",
        "result": "[master abc1234] fix: bug\n 1 file changed",
    },
    "session_id": "test-session",
}

OTHER_BASH_PAYLOAD = {
    "tool_name": "Bash",
    "tool_input": {"command": "ls -la"},
    "tool_response": {"type": "result", "result": "total 8\n..."},
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
    result = parse_payload(json.dumps(PYTEST_PAYLOAD))
    assert isinstance(result, dict)
    assert result["tool_name"] == "Bash"


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
# Group B — is_substantive (only pytest + git commit count)
# ---------------------------------------------------------------------------

def test_is_substantive_write_false():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(WRITE_PAYLOAD) is False


def test_is_substantive_edit_false():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(EDIT_PAYLOAD) is False


def test_is_substantive_webfetch_false():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(WEBFETCH_PAYLOAD) is False


def test_is_substantive_read_false():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(READ_PAYLOAD) is False


def test_is_substantive_other_bash_false():
    """Plain Bash commands like `ls` no longer trigger the hook."""
    from hooks.post_tool_use import is_substantive
    assert is_substantive(OTHER_BASH_PAYLOAD) is False


def test_is_substantive_pytest_true():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(PYTEST_PAYLOAD) is True


def test_is_substantive_python_dash_m_pytest_true():
    """`python3 -m pytest` is also recognised."""
    from hooks.post_tool_use import is_substantive
    assert is_substantive(PYTEST_FAIL_PAYLOAD) is True


def test_is_substantive_git_commit_true():
    from hooks.post_tool_use import is_substantive
    assert is_substantive(GIT_COMMIT_PAYLOAD) is True


def test_is_substantive_git_status_false():
    """`git status` (and other non-commit git commands) do not trigger."""
    from hooks.post_tool_use import is_substantive
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
        "tool_response": {"type": "result", "result": "On branch master"},
    }
    assert is_substantive(payload) is False


def test_is_substantive_unknown_tool_false():
    from hooks.post_tool_use import is_substantive
    payload = {
        "tool_name": "Glob",
        "tool_input": {"pattern": "**/*.py"},
        "tool_response": {"type": "result", "result": "found 5 files"},
    }
    assert is_substantive(payload) is False


# ---------------------------------------------------------------------------
# Group C — build_memory_params for pytest and git commit
# ---------------------------------------------------------------------------

def test_build_params_pytest_pass_only():
    """`N passed in T s` summary is captured cleanly with importance 2."""
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(PYTEST_PAYLOAD)
    assert params is not None
    assert params["fact"].startswith("pytest:")
    assert "42 passed" in params["fact"]
    assert params["type"] == "observation"
    assert params["importance"] == 2


def test_build_params_pytest_with_failures_importance_3():
    """A summary line with `failed` count bumps importance to 3."""
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(PYTEST_FAIL_PAYLOAD)
    assert params is not None
    assert "5 passed" in params["fact"]
    assert "2 failed" in params["fact"]
    assert params["importance"] == 3


def test_build_params_pytest_no_summary_falls_back():
    """When no summary line is present, fall back to first 120 chars of output."""
    from hooks.post_tool_use import build_memory_params
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "pytest"},
        "tool_response": {"type": "result", "result": "ImportError: No module named 'pytest'"},
    }
    params = build_memory_params(payload)
    assert params is not None
    assert params["fact"].startswith("pytest run:")
    assert "ImportError" in params["fact"]


def test_build_params_git_commit_extracts_sha_branch_message():
    """[branch sha] message form parses into a structured fact."""
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(GIT_COMMIT_PAYLOAD)
    assert params is not None
    assert params["fact"].startswith("git commit ")
    assert "abc1234" in params["fact"]
    assert "master" in params["fact"]
    assert "fix: bug" in params["fact"]
    assert params["type"] == "decision"
    assert params["importance"] == 2


def test_build_params_git_commit_unparseable_falls_back():
    """If the output doesn't match the [branch sha] form, fall back gracefully."""
    from hooks.post_tool_use import build_memory_params
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit --amend"},
        "tool_response": {"type": "result", "result": "no changes to commit"},
    }
    params = build_memory_params(payload)
    assert params is not None
    assert params["fact"].startswith("git commit:")
    assert "no changes" in params["fact"]


def test_build_params_unknown_tool_returns_none():
    from hooks.post_tool_use import build_memory_params
    params = build_memory_params(WRITE_PAYLOAD)
    assert params is None


# ---------------------------------------------------------------------------
# Group D — main() integration with mocked MemoryClient
# ---------------------------------------------------------------------------

def _stdin_mock(payload: dict):
    return patch("sys.stdin", new=MagicMock(read=lambda: json.dumps(payload)))


def test_main_pytest_calls_add_memory():
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_called_once()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["type"] == "observation"
    assert "pytest" in call_kwargs["fact"]


def test_main_git_commit_calls_add_memory_as_decision():
    with _stdin_mock(GIT_COMMIT_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_called_once()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["type"] == "decision"
    assert "git commit" in call_kwargs["fact"]


def test_main_write_does_not_call_add_memory():
    """Write events are no longer captured as observation memories."""
    with _stdin_mock(WRITE_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_edit_does_not_call_add_memory():
    with _stdin_mock(EDIT_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_webfetch_does_not_call_add_memory():
    with _stdin_mock(WEBFETCH_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


def test_main_other_bash_does_not_call_add_memory():
    with _stdin_mock(OTHER_BASH_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    mock_instance.add_memory.assert_not_called()


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


def test_main_strand_is_session_activity():
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["strand_ids"] == ["strand-session-activity"]


def test_main_tags_include_hook():
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            from hooks.post_tool_use import main
            main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert "hook" in call_kwargs["tags"]


def test_main_connect_error_exits_cleanly():
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.ConnectError("refused")
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_timeout_error_exits_cleanly():
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.TimeoutException("timeout")
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_http_status_error_exits_cleanly():
    with _stdin_mock(PYTEST_PAYLOAD):
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
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = Exception("boom")
            from hooks.post_tool_use import main
            main()  # must not raise


def test_main_agent_id_from_constant():
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            with patch("hooks.post_tool_use.AGENT_ID", "my-custom-agent"):
                from hooks.post_tool_use import main
                main()
    call_kwargs = mock_instance.add_memory.call_args[1]
    assert call_kwargs["agent_id"] == "my-custom-agent"


def test_main_error_goes_to_stderr_not_stdout(capsys):
    with _stdin_mock(PYTEST_PAYLOAD):
        with patch("hooks.post_tool_use.MemoryClient") as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            mock_instance.add_memory.side_effect = httpx.ConnectError("refused")
            from hooks.post_tool_use import main
            main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err) > 0
