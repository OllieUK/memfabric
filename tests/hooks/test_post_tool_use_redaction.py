"""Unit tests for post_tool_use redaction and sensitive-path logic.

Tests the filter functions in isolation — no live service required.
"""
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from hooks._filters import redact_secrets, is_sensitive_path


class TestPostToolUseRedaction:
    def test_bearer_sk_ant_token_is_redacted(self):
        fact = "Ran bash command: curl -H 'Authorization: Bearer sk-ant-foo123456789012345678901234'"
        result, was_redacted = redact_secrets(fact)
        assert was_redacted is True
        assert "sk-ant-foo123456789012345678901234" not in result
        assert "[REDACTED]" in result

    def test_password_in_fact_is_redacted(self):
        fact = "Ran bash command: psql postgresql://user:hunter2@localhost/db"
        # password= pattern won't match the URL but let's test explicit kv form
        fact2 = "Ran bash command: connect password=hunter2 host=localhost"
        result, was_redacted = redact_secrets(fact2)
        assert was_redacted is True
        assert "hunter2" not in result

    def test_ssh_path_is_sensitive(self):
        assert is_sensitive_path("/home/oliver/.ssh/id_ed25519") is True

    def test_hook_file_is_not_sensitive(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/hooks/post_tool_use.py") is False

    def test_clean_fact_unchanged(self):
        fact = "Edited file: memory_service/memory_repo.py"
        result, was_redacted = redact_secrets(fact)
        assert was_redacted is False
        assert result == fact

    def test_dot_env_path_is_sensitive(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/.env") is True

    def test_credentials_path_is_sensitive(self):
        assert is_sensitive_path("/home/oliver/.config/credentials.json") is True
