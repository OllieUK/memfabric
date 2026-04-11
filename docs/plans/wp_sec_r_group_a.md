# WP-SEC-R Group A: _filters.py Hardening Sprint

**Date:** 2026-04-11
**Status:** Ready for implementation
**WPs covered:** WP-SEC-R1, WP-SEC-R3R4, WP-SEC-R5

---

## Summary

Three hardening items that all edit the same file (`hooks/_filters.py`) are implemented in one sequenced TDD pass. The changes close bypass paths in `contains_injection()` via NFKC normalisation, extend `_REDACT_PATTERNS` with 12 new token families, and widen `_SENSITIVE_FILENAME_GLOBS` / `_SENSITIVE_PATH_GLOBS` with 6 + 6 new entries respectively. No new modules, no new directories, no changes to any other file except the new test file.

---

## Context

`hooks/_filters.py` (131 lines) is the single shared content-filter module imported by:
- `hooks/session_start.py` — filters wake-up output before injecting into system prompt
- `hooks/post_tool_use.py` — redacts secrets before storing observations
- `memory_service/ingest_guard.py` — filters ingest chunks before storing

The file exposes three public functions: `contains_injection()`, `redact_secrets()`, `is_sensitive_path()`. Existing imports: `re`, `fnmatch`, `PurePath` from pathlib. The `unicodedata` stdlib module is not yet imported and must be added.

---

## Approach — three sequential TDD passes, one commit

Work in strict Pass 1 → Pass 2 → Pass 3 order. Tests must be green at the end of each pass before starting the next. All three passes land as a single commit.

### Pass 1 — WP-SEC-R1: NFKC normalisation + whitespace collapse

**Problem:** `contains_injection()` applies only `text.lower()` before the literal scan. Attackers can bypass detection using:
- Space-inserted tags: `<system - reminder>`
- Soft-hyphen (U+00AD): `<system\u00ADreminder>`
- NBSP (U+00A0): `<system\u00A0reminder>`
- NFKC-collapsible Unicode ligatures

**Fix — change only the body of `contains_injection()`:**

1. Add `import unicodedata` at the top of the file (after the existing imports).
2. Replace the `lower = text.lower()` line with a three-step normalised form computed for detection only. The original `text` is never mutated.

Normalisation sequence (detection copy only):
```python
import unicodedata

def contains_injection(text: str) -> bool:
    """Return True if text contains prompt-injection indicators."""
    # Build a detection-only normalised form — original text is never mutated.
    normalised = unicodedata.normalize("NFKC", text)
    # Strip zero-width and soft-hyphen characters that fragment tokens.
    normalised = re.sub(r'[\u00AD\u200B\u200C\u200D\uFEFF]', '', normalised)
    # Collapse whitespace runs so space-inserted tags collapse to one space.
    normalised = re.sub(r'\s+', ' ', normalised)
    lower = normalised.lower()

    for literal in _INJECTION_LITERALS:
        if literal in lower:
            return True
    for ch in text:          # iterate original — preserves unicode tag / bidi checks
        cp = ord(ch)
        if cp in _INJECTION_UNICODE_RANGES or cp in _BIDI_CHARS:
            return True
    return False
```

Key invariant: the per-character unicode-range/bidi checks iterate `text` (original), not `lower`. This is unchanged from the current implementation and must remain so.

**Do not touch:** `_INJECTION_LITERALS` list, `_INJECTION_UNICODE_RANGES`, `_BIDI_CHARS`.

---

### Pass 2 — WP-SEC-R3R4: Extend `_REDACT_PATTERNS`

Append the following 12 compiled regexes to the `_REDACT_PATTERNS` list. Order within the list does not matter — `redact_secrets()` applies all patterns independently. Preserve all 9 existing patterns unchanged.

```python
# AWS access keys
re.compile(r'AKIA[0-9A-Z]{16}'),
re.compile(r'ASIA[0-9A-Z]{16}'),
# Slack tokens
re.compile(r'xox[bpoa]-[0-9]+-[0-9]+-[0-9]+-[A-Za-z0-9]+'),
# Stripe keys
re.compile(r'sk_live_[A-Za-z0-9]{24,}'),
re.compile(r'rk_live_[A-Za-z0-9]{24,}'),
# GitLab PAT
re.compile(r'glpat-[A-Za-z0-9_\-]{20,}'),
# GitHub fine-grained PAT
re.compile(r'github_pat_[A-Za-z0-9_]{22,}_[A-Za-z0-9]{59,}'),
# PEM private key header
re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
# HTTP Basic Auth in URL (min 3-char user and password to avoid port-only false positives)
re.compile(r'https?://[^:/\s]{3,}:[^@/\s]{3,}@'),
# JSON key-value form (≥8 char value to avoid short dev tokens like "token": "dev")
re.compile(r'"(?:password|api_key|token|secret)"\s*:\s*"[A-Za-z0-9+/=!@#$%^&*]{8,}"'),
# YAML key-value form (≥8 char value; negative lookahead avoids matching URLs as values)
re.compile(r'(?i)(?:password|api_key|token|secret)\s*:\s*(?!https?://)[A-Za-z0-9+/=!@#$%^&*_\-]{8,}'),
# CLI flag form (≥8 char value; negative lookahead avoids URLs)
re.compile(r'(?i)--(?:password|token|secret|api-key)\s+(?!https?://)\S{8,}'),
```

Note on overlap with existing patterns: the existing `re.compile(r"sk-[A-Za-z0-9]{32,}")` uses a hyphen and matches Anthropic/OpenAI `sk-` keys. The new `sk_live_` uses an underscore — no overlap, both are required.

**Do not touch:** `redact_secrets()` function body — it already iterates `_REDACT_PATTERNS` correctly.

---

### Pass 3 — WP-SEC-R5: Extend sensitive-path globs

Append to `_SENSITIVE_FILENAME_GLOBS`:
```python
".netrc",
".pgpass",
".my.cnf",
"*.p12",
"*.pfx",
"*.jks",
"*.keystore",
"*.gpg",
"secring.*",
"logins.json",
"cookies.sqlite",
"Login Data",
"*.kdbx",
```

Append to `_SENSITIVE_PATH_GLOBS`:
```python
"*/.aws/*",
"*/.kube/*",
"*/.gnupg/*",
"*/.mozilla/firefox/*/logins.json",
"*/Chrome/*/Login Data",
"*/keyrings/*",
```

Note: `.aws/credentials` is already matched by the existing `credentials*` glob in `_SENSITIVE_FILENAME_GLOBS`. Do not add a redundant entry. The `_ENV_SAFE_NAMES` set and `is_sensitive_path()` function body are unchanged.

Pre-flight check (confirmed before writing this plan): no file in the project tree would be newly flagged by these additions.

---

## Affected Files

| File | Change |
|------|--------|
| `hooks/_filters.py` | Add `import unicodedata`; modify `contains_injection()` body; extend `_REDACT_PATTERNS`; extend `_SENSITIVE_FILENAME_GLOBS` and `_SENSITIVE_PATH_GLOBS` |
| `tests/test_wp_sec_r_filters.py` | Create — 29 synthetic tests + 2 corpus regression tests |

**Do not touch any other file.**

---

## Reusable Utilities

- `unicodedata` — stdlib, add to imports at top of `_filters.py`
- `re`, `fnmatch`, `PurePath` — already imported in `_filters.py`, no change needed
- No conftest fixtures required — all tests are self-contained

---

## Scope Boundaries (hard)

Allowed changes in `_filters.py`:
- `_INJECTION_LITERALS` list (not required, but in scope)
- `contains_injection` function body
- `_REDACT_PATTERNS` list
- `_SENSITIVE_FILENAME_GLOBS` list
- `_SENSITIVE_PATH_GLOBS` list

Do NOT:
- Rewrite docstrings or comments on any function
- Touch `redact_secrets()` or `is_sensitive_path()` function bodies
- Reformat or sort existing regex patterns
- Add helper modules or new directories
- Edit BACKLOG.md, any hook file, or any service file

---

## Testing Strategy

### Test file

`tests/test_wp_sec_r_filters.py`

No live service required. pytest only. Uses stdlib only (`pathlib.Path`) plus the project's own `hooks/_filters.py`. No conftest fixtures, no monkeypatch, flat file layout, plain `assert` statements. Import the three public functions directly:

```python
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from hooks._filters import contains_injection, redact_secrets, is_sensitive_path
```

---

### Unit Tests — Pass 1: contains_injection (R1, tests 1–8)

| # | Test name | Assertion |
|---|-----------|-----------|
| 1 | `test_contains_injection_baseline_still_fires` | `contains_injection("<system-reminder>")` is `True` |
| 2 | `test_contains_injection_space_bypass` | `contains_injection("<system - reminder>")` is `True` |
| 3 | `test_contains_injection_soft_hyphen_bypass` | `contains_injection("<system\u00ADreminder>")` is `True` |
| 4 | `test_contains_injection_nbsp_bypass` | `contains_injection("<system\u00A0reminder>")` is `True` |
| 5 | `test_contains_injection_mixed_case_nbsp` | `contains_injection("<Sys\u00ADtem-Reminder>")` is `True` |
| 6 | `test_contains_injection_clean_text` | `contains_injection("the quick brown fox")` is `False` |
| 7 | `test_contains_injection_unicode_tag_block_regression` | `contains_injection(chr(0xE0041))` is `True` |
| 8 | `test_contains_injection_bidi_override_regression` | `contains_injection(chr(0x202E))` is `True` |

---

### Unit Tests — Pass 2: redact_secrets (R3R4, tests 9–21)

| # | Test name | Input / Assertion |
|---|-----------|-------------------|
| 9 | `test_redact_secrets_aws_akia` | `"AKIAIOSFODNN7EXAMPLE"` → `was_redacted` is `True` |
| 10 | `test_redact_secrets_aws_asia` | `"ASIAIOSFODNN7EXAMPLE"` → `was_redacted` is `True` |
| 11 | `test_redact_secrets_slack_xoxb` | `"xoxb-1234-5678-9012-abcdefghijkl"` → `was_redacted` is `True` |
| 12 | `test_redact_secrets_stripe_sk_live` | `"sk_live_abcdefghijklmnopqrstuvwx"` → `was_redacted` is `True` |
| 13 | `test_redact_secrets_gitlab_pat` | `"glpat-abcdefghijklmnopqrst"` → `was_redacted` is `True` |
| 14 | `test_redact_secrets_github_fine_grained` | `"github_pat_11AAAAAAA0" + "_" + "A" * 22 + "_" + "B" * 59` → `was_redacted` is `True` |
| 15 | `test_redact_secrets_pem_header` | `"-----BEGIN RSA PRIVATE KEY-----"` → `was_redacted` is `True` |
| 16 | `test_redact_secrets_http_basic_auth` | `"https://user:password123@example.com/"` → `was_redacted` is `True` |
| 17 | `test_redact_secrets_json_kv` | `'{"password": "s3cr3tVal!"}'` → `was_redacted` is `True` |
| 18 | `test_redact_secrets_yaml_kv` | `"password: s3cr3tVal!"` → `was_redacted` is `True` |
| 19 | `test_redact_secrets_cli_flag` | `"--password s3cr3tVal!"` → `was_redacted` is `True` |
| 20 | `test_redact_secrets_existing_sk_ant_regression` | `"sk-ant-api03-abc"` → `was_redacted` is `True` |
| 21 | `test_redact_secrets_existing_bearer_regression` | `"Bearer eyJabc.def.ghi"` → `was_redacted` is `True` |

For tests 9–21, assert both that `was_redacted is True` and that `"[REDACTED]"` appears in the returned text.

---

### Unit Tests — Pass 3: is_sensitive_path (R5, tests 22–29)

| # | Test name | Input / Assertion |
|---|-----------|-------------------|
| 22 | `test_is_sensitive_path_netrc` | `is_sensitive_path(".netrc")` is `True` |
| 23 | `test_is_sensitive_path_pgpass` | `is_sensitive_path(".pgpass")` is `True` |
| 24 | `test_is_sensitive_path_p12` | `is_sensitive_path("foo.p12")` is `True` |
| 25 | `test_is_sensitive_path_aws_config` | `is_sensitive_path("/home/x/.aws/config")` is `True` |
| 26 | `test_is_sensitive_path_kube_config` | `is_sensitive_path("/home/x/.kube/config")` is `True` |
| 27 | `test_is_sensitive_path_gnupg` | `is_sensitive_path("/home/x/.gnupg/private-keys-v1.d/abc.key")` is `True` |
| 28 | `test_is_sensitive_path_env_example_not_flagged` | `is_sensitive_path(".env.example")` is `False` |
| 29 | `test_is_sensitive_path_credentials_regression` | `is_sensitive_path("credentials.json")` is `True` |

---

### Corpus Regression Tests (critical — prevent false positives F2.1 / F2.2)

These two tests must be written in Pass 3 and must pass before the commit is made. If either fails, narrow the pattern (longer length anchors, stricter character sets) rather than skipping the test.

```python
def test_no_injection_flags_on_clean_corpus():
    """New NFKC normalisation must not flag existing framework text."""
    from pathlib import Path
    corpus_files = list(Path("data/frameworks").rglob("*.md"))
    corpus_files += list(Path("data/frameworks").rglob("*.yaml"))
    for path in corpus_files:
        text = path.read_text(errors="ignore")[:10_000]
        assert not contains_injection(text), f"False positive injection flag in {path}"


def test_no_redaction_on_framework_corpus():
    """Extended patterns must not redact legitimate control descriptions."""
    from pathlib import Path
    corpus_files = list(Path("data/frameworks").rglob("*.md"))
    corpus_files += list(Path("data/frameworks").rglob("*.yaml"))
    for path in corpus_files:
        text = path.read_text(errors="ignore")[:10_000]
        _, was_redacted = redact_secrets(text)
        assert not was_redacted, f"False positive redaction in {path}"
```

Note: `data/frameworks/` contains no `.md` files (confirmed). The glob is retained as specified and also extended to `.yaml` to give the corpus tests real coverage against the 6 YAML framework files present. If a YAML corpus test fails due to a pattern match in legitimate control text, narrow the offending pattern before proceeding.

---

### Integration Tests

None required. All three functions are pure text transforms with no database, network, or filesystem side-effects. The corpus regression tests read local files but need no live service.

---

### Acceptance Criteria

1. All 29 synthetic tests pass under `pytest tests/test_wp_sec_r_filters.py`.
2. Both corpus regression tests pass (no false positives across all `data/frameworks/**/*.{md,yaml}` files).
3. Full `pytest` suite green — no regressions in `tests/test_wp126_post_tool_use_hook.py`, `tests/test_wp127_file_provenance.py`, or `tests/test_wp_sec3_ingest_guard.py`.
4. Manual smoke: inject `<system - reminder>` into a test call to `contains_injection()` and confirm `True`.
5. Manual smoke: inject `AKIAIOSFODNN7EXAMPLE` into a test call to `redact_secrets()` and confirm `[REDACTED]` in output.
6. Manual smoke: `is_sensitive_path("/home/oliver/.kube/config")` returns `True`.

---

## Risks / Open Questions

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | YAML KV pattern (`password\s*:\s*...`) may match legitimate YAML keys in framework files (e.g. a control named "token") | The ≥8 char length anchor mitigates short values; corpus test F2.2 catches any remaining hits. If a hit occurs, raise the anchor to 12 or add a negative-lookahead for common non-secret values. |
| 2 | HTTP Basic Auth pattern may match port-only URLs like `http://host:8080/path` | The `[^:/\s]{3,}` and `[^@/\s]{3,}` quantifiers require ≥3 chars in both user and password fields; `:8080/` has only 4 digits for the "password" but the `@` is absent so the pattern does not match. Confirmed safe. |
| 3 | `is_sensitive_path` uses `fnmatch` on `name_lower` (lowercase) but `Login Data` is mixed-case | `Login Data` is added as a literal — `name_lower` will be `login data` and the glob `Login Data` will not match. Fix: add `login data` (lowercase) to the list instead of `Login Data`, or lowercase the glob at match time. **Resolution: add `"login data"` (all lowercase) to `_SENSITIVE_FILENAME_GLOBS` and update test 22–29 paths accordingly.** |
| 4 | `data/frameworks/*.md` glob currently matches zero files | Corpus tests are extended to also cover `.yaml` files (see corpus test note above). The `.md` glob is kept for forward compatibility. |
| 5 | `github_pat_` regex requires long suffix — test 14 string construction must be exact | Implementer must verify the test string satisfies `[A-Za-z0-9_]{22,}_[A-Za-z0-9]{59,}` — the `_PROJECT_ROOT` sys.path block must be included or the import will fail. |

---

## Sub-commit Structure

All three passes land as **one commit** with message:

```
WP-SEC-R1/R3R4/R5: NFKC injection bypass, extended redaction patterns, sensitive-path globs
```

The implementer must not commit between passes. Running `pytest tests/test_wp_sec_r_filters.py` green at the end of each pass is a local gate only.
