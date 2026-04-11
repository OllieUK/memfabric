"""
Tests for WP-SEC-R Group A: _filters.py hardening sprint.

Pass 1 (tests 1-8):  contains_injection NFKC normalisation (R1)
Pass 2 (tests 9-21): redact_secrets extended patterns (R3R4)
Pass 3 (tests 22-29 + corpus): is_sensitive_path glob additions (R5)
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hooks._filters import contains_injection, redact_secrets, is_sensitive_path

# ---------------------------------------------------------------------------
# Pass 1 — contains_injection: NFKC normalisation + whitespace collapse (R1)
# ---------------------------------------------------------------------------

def test_contains_injection_baseline_still_fires():
    assert contains_injection("<system-reminder>") is True


def test_contains_injection_space_bypass():
    # space-inserted tag must still be detected
    assert contains_injection("<system - reminder>") is True


def test_contains_injection_soft_hyphen_bypass():
    # soft-hyphen U+00AD fragments the token — must be stripped and detected
    assert contains_injection("<system\u00ADreminder>") is True


def test_contains_injection_nbsp_bypass():
    # non-breaking space U+00A0 must be collapsed and detected
    assert contains_injection("<system\u00A0reminder>") is True


def test_contains_injection_mixed_case_nbsp():
    # mixed-case + soft-hyphen — must still detect system-reminder
    assert contains_injection("<Sys\u00ADtem-Reminder>") is True


def test_contains_injection_clean_text():
    assert contains_injection("the quick brown fox") is False


def test_contains_injection_unicode_tag_block_regression():
    # U+E0041 is in the tag block — per-character check must fire
    assert contains_injection(chr(0xE0041)) is True


def test_contains_injection_bidi_override_regression():
    # U+202E right-to-left override — bidi check must fire
    assert contains_injection(chr(0x202E)) is True


# ---------------------------------------------------------------------------
# Pass 2 — redact_secrets: extended patterns (R3R4, tests 9-21)
# ---------------------------------------------------------------------------

def test_redact_secrets_aws_akia():
    text = "key=AKIAIOSFODNN7EXAMPLE here"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_aws_asia():
    text = "key=ASIAIOSFODNN7EXAMPLE here"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_slack_xoxb():
    text = "token=xoxb-1234-5678-9012-abcdefghijkl"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_stripe_sk_live():
    text = "sk_live_abcdefghijklmnopqrstuvwx"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_gitlab_pat():
    text = "glpat-abcdefghijklmnopqrst"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_github_fine_grained():
    # pattern: github_pat_[A-Za-z0-9_]{22,}_[A-Za-z0-9]{59,}
    suffix_part = "A" * 22 + "_" + "B" * 59
    text = f"github_pat_11AAAAAAA0_{suffix_part}"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_pem_header():
    text = "-----BEGIN RSA PRIVATE KEY-----"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_http_basic_auth():
    text = "https://user:password123@example.com/"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_json_kv():
    text = '{"password": "s3cr3tVal!"}'
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_yaml_kv():
    text = "password: s3cr3tVal!"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_cli_flag():
    text = "--password s3cr3tVal!"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_existing_sk_ant_regression():
    text = "sk-ant-api03-abc" + "d" * 20
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


def test_redact_secrets_existing_bearer_regression():
    text = "Bearer eyJabc.def.ghi"
    result, was_redacted = redact_secrets(text)
    assert was_redacted is True
    assert "[REDACTED]" in result


# ---------------------------------------------------------------------------
# Pass 3 — is_sensitive_path: new filename and path globs (R5, tests 22-29)
# ---------------------------------------------------------------------------

def test_is_sensitive_path_netrc():
    assert is_sensitive_path(".netrc") is True


def test_is_sensitive_path_pgpass():
    assert is_sensitive_path(".pgpass") is True


def test_is_sensitive_path_p12():
    assert is_sensitive_path("foo.p12") is True


def test_is_sensitive_path_aws_config():
    assert is_sensitive_path("/home/x/.aws/config") is True


def test_is_sensitive_path_kube_config():
    assert is_sensitive_path("/home/x/.kube/config") is True


def test_is_sensitive_path_gnupg():
    assert is_sensitive_path("/home/x/.gnupg/private-keys-v1.d/abc.key") is True


def test_is_sensitive_path_env_example_not_flagged():
    assert is_sensitive_path(".env.example") is False


def test_is_sensitive_path_credentials_regression():
    assert is_sensitive_path("credentials.json") is True


# ---------------------------------------------------------------------------
# Pass 3 — Corpus regression tests (F2.1 / F2.2)
# ---------------------------------------------------------------------------

def test_no_injection_flags_on_clean_corpus():
    """New NFKC normalisation must not flag existing framework text."""
    corpus_files = list((_PROJECT_ROOT / "data" / "frameworks").rglob("*.md"))
    corpus_files += list((_PROJECT_ROOT / "data" / "frameworks").rglob("*.yaml"))
    for path in corpus_files:
        text = path.read_text(errors="ignore")[:10_000]
        assert not contains_injection(text), f"False positive injection flag in {path}"


def test_no_redaction_on_framework_corpus():
    """Extended patterns must not redact legitimate control descriptions."""
    corpus_files = list((_PROJECT_ROOT / "data" / "frameworks").rglob("*.md"))
    corpus_files += list((_PROJECT_ROOT / "data" / "frameworks").rglob("*.yaml"))
    for path in corpus_files:
        text = path.read_text(errors="ignore")[:10_000]
        _, was_redacted = redact_secrets(text)
        assert not was_redacted, f"False positive redaction in {path}"
