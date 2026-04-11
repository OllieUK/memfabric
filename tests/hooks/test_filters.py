"""Unit tests for hooks._filters — injection detection, secret redaction, sensitive path detection."""
import sys
import os

# Ensure project root is on sys.path so hooks._filters is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from hooks._filters import contains_injection, redact_secrets, is_sensitive_path


# ---------------------------------------------------------------------------
# contains_injection
# ---------------------------------------------------------------------------

class TestContainsInjection:
    def test_detects_system_open_tag(self):
        assert contains_injection("<system>") is True

    def test_detects_system_close_tag(self):
        assert contains_injection("</system>") is True

    def test_detects_system_reminder_open(self):
        assert contains_injection("<system-reminder>") is True

    def test_detects_system_reminder_close(self):
        assert contains_injection("</system-reminder>") is True

    def test_detects_ignore_previous_instructions(self):
        assert contains_injection("ignore previous instructions") is True

    def test_detects_ignore_all_previous(self):
        assert contains_injection("ignore all previous") is True

    def test_detects_disregard_previous(self):
        assert contains_injection("disregard previous") is True

    def test_detects_im_start_token(self):
        assert contains_injection("<|im_start|>") is True

    def test_detects_im_end_token(self):
        assert contains_injection("<|im_end|>") is True

    def test_detects_anthropic_api_key_literal(self):
        assert contains_injection("ANTHROPIC_API_KEY=sk-ant-abc123") is True

    def test_detects_openai_api_key_literal(self):
        assert contains_injection("OPENAI_API_KEY=sk-proj-xyz") is True

    def test_detects_sk_ant_prefix(self):
        assert contains_injection("my key is sk-ant-api03-abc") is True

    def test_detects_sk_proj_prefix(self):
        assert contains_injection("using sk-proj-testkey here") is True

    def test_detects_unicode_tag_block(self):
        # U+E0000 is the first character of the Unicode tag block
        assert contains_injection("\U000E0000 hello") is True

    def test_detects_unicode_tag_block_mid_range(self):
        assert contains_injection("a\U000E0041b") is True

    def test_detects_bidi_override_u202e(self):
        assert contains_injection("normal\u202etext") is True

    def test_detects_bidi_override_u202a(self):
        assert contains_injection("\u202ahello") is True

    def test_detects_bidi_override_u2066(self):
        assert contains_injection("test\u2066value") is True

    def test_case_insensitive_system_tag(self):
        assert contains_injection("<SYSTEM>") is True

    def test_case_insensitive_ignore_previous(self):
        assert contains_injection("IGNORE PREVIOUS INSTRUCTIONS now") is True

    def test_returns_false_for_clean_text(self):
        assert contains_injection("The project uses FastAPI and Memgraph for graph storage.") is False

    def test_returns_false_for_empty_string(self):
        assert contains_injection("") is False

    def test_returns_false_for_normal_memory(self):
        assert contains_injection("WP-127 file provenance tracking is complete.") is False


# ---------------------------------------------------------------------------
# redact_secrets
# ---------------------------------------------------------------------------

class TestRedactSecrets:
    def test_redacts_anthropic_style_key(self):
        text = "key=sk-" + "a" * 32
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result
        assert "sk-" + "a" * 32 not in result

    def test_redacts_sk_ant_key(self):
        text = "using sk-ant-api03-supersecretkey123456"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_github_pat(self):
        text = "token: ghp_" + "x" * 36
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_google_api_key(self):
        text = "AIza" + "B" * 35
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_bearer_token(self):
        text = "Authorization: Bearer eyABC.def-ghi.jkl-mno"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_jwt(self):
        # Construct a minimal plausible JWT-shaped string
        part = "A" * 15
        text = f"eyJ{part}.{part}.{part}"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_password_kvpair(self):
        text = "password=hunter2"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_token_kvpair(self):
        text = "token=mysecrettoken"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_api_key_kvpair(self):
        text = "api_key=supersecret"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_redacts_apikey_no_separator(self):
        text = "apikey=topsecret"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert "[REDACTED]" in result

    def test_returns_original_when_no_match(self):
        text = "The graph has 488 nodes and 397 INFORMS edges."
        result, was_redacted = redact_secrets(text)
        assert was_redacted is False
        assert result == text

    def test_multiple_patterns_all_redacted(self):
        sk_key = "sk-" + "z" * 32
        text = f"key={sk_key} and password=secret123"
        result, was_redacted = redact_secrets(text)
        assert was_redacted is True
        assert sk_key not in result
        assert "secret123" not in result


# ---------------------------------------------------------------------------
# is_sensitive_path
# ---------------------------------------------------------------------------

class TestIsSensitivePath:
    def test_ssh_private_key(self):
        assert is_sensitive_path("/home/oliver/.ssh/id_ed25519") is True

    def test_ssh_directory_any_file(self):
        assert is_sensitive_path("/home/oliver/.ssh/known_hosts") is True

    def test_dot_env_file(self):
        assert is_sensitive_path("/home/user/.env") is True

    def test_dot_env_production(self):
        assert is_sensitive_path("/home/user/.env.production") is True

    def test_dot_env_local(self):
        assert is_sensitive_path("/home/user/.env.local") is True

    def test_etc_shadow(self):
        assert is_sensitive_path("/etc/shadow") is True

    def test_credentials_json(self):
        assert is_sensitive_path("/home/user/credentials.json") is True

    def test_pem_file(self):
        assert is_sensitive_path("/home/user/key.pem") is True

    def test_dot_key_file(self):
        assert is_sensitive_path("/home/user/server.key") is True

    def test_id_rsa(self):
        assert is_sensitive_path("/home/user/.ssh/id_rsa") is True

    def test_id_ecdsa(self):
        assert is_sensitive_path("/home/user/.ssh/id_ecdsa") is True

    def test_tax_return(self):
        assert is_sensitive_path("/home/user/documents/tax-return-2025.pdf") is True

    def test_passport_in_name(self):
        assert is_sensitive_path("/home/user/scans/my-passport-scan.jpg") is True

    def test_safe_project_script(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/scripts/ingest_document.py") is False

    def test_safe_tmp_file(self):
        assert is_sensitive_path("/tmp/test_output.txt") is False

    def test_safe_hook_file(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/hooks/post_tool_use.py") is False

    def test_env_example_is_not_sensitive(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/.env.example") is False

    def test_env_template_is_not_sensitive(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/.env.template") is False

    def test_env_sample_is_not_sensitive(self):
        assert is_sensitive_path("/home/oliver/projects/graph-memory-fabric/.env.sample") is False
