"""
Shared content filters for security-sensitive text processing.

Used by:
  hooks/session_start.py  — filters wake-up output before injecting into system prompt
  hooks/post_tool_use.py  — redacts secrets before storing observations
  memory_service/ingest_guard.py (WP-SEC-3) — filters ingest chunks before storing
"""
import re
import unicodedata
from fnmatch import fnmatch
from pathlib import PurePath

# ---------------------------------------------------------------------------
# Injection detection
# ---------------------------------------------------------------------------

_INJECTION_LITERALS = [
    "<system>",
    "</system>",
    "<system-reminder>",
    "</system-reminder>",
    "ignore previous instructions",
    "ignore all previous",
    "disregard previous",
    "<|im_start|>",
    "<|im_end|>",
    "anthropic_api_key=",
    "openai_api_key=",
    "sk-ant-",
    "sk-proj-",
]

# Unicode tag block U+E0000–U+E007F and bidi override characters
_INJECTION_UNICODE_RANGES = range(0xE0000, 0xE0080)
_BIDI_CHARS = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}

# Pre-computed dense forms of each literal (whitespace, NBSP, hyphens stripped).
# Built once at module load — avoids recomputing on every contains_injection() call.
_INJECTION_LITERALS_DENSE = [re.sub(r'[\s\u00A0-]+', '', lit) for lit in _INJECTION_LITERALS]


def contains_injection(text: str) -> bool:
    """Return True if text contains prompt-injection indicators."""
    # Build a detection-only normalised form — original text is never mutated.
    normalised = unicodedata.normalize("NFKC", text)
    # Strip zero-width and soft-hyphen characters that fragment tokens.
    normalised = re.sub(r'[\u00AD\u200B\u200C\u200D\uFEFF]', '', normalised)
    # Collapse whitespace runs so space-inserted tags collapse to one space.
    normalised = re.sub(r'[\s\u00A0]+', ' ', normalised)
    lower = normalised.lower()

    # Dense form: strip all whitespace, NBSP, and hyphens so that
    # space-inserted or hyphen-fragmented tags collapse to token sequences.
    dense = re.sub(r'[\s\u00A0-]+', '', lower)

    for literal, dense_literal in zip(_INJECTION_LITERALS, _INJECTION_LITERALS_DENSE):
        if literal in lower:
            return True
        if dense_literal in dense:
            return True
    for ch in text:          # iterate original — preserves unicode tag / bidi checks
        cp = ord(ch)
        if cp in _INJECTION_UNICODE_RANGES or cp in _BIDI_CHARS:
            return True
    return False


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------

_REDACT_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{35}"),
    re.compile(r"Bearer [A-Za-z0-9._\-]+"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)password\s*=\s*\S+"),
    re.compile(r"(?i)token\s*=\s*\S+"),
    re.compile(r"(?i)api[_\-]?key\s*=\s*\S+"),
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
    # JSON key-value form (>=8 char value to avoid short dev tokens like "token": "dev")
    re.compile(r'"(?:password|api_key|token|secret)"\s*:\s*"[A-Za-z0-9+/=!@#$%^&*]{8,}"'),
    # YAML key-value form (>=8 char value; negative lookahead avoids matching URLs as values)
    re.compile(r'(?i)(?:password|api_key|token|secret)\s*:\s*(?!https?://)[A-Za-z0-9+/=!@#$%^&*_\-]{8,}'),
    # CLI flag form (>=8 char value; negative lookahead avoids URLs)
    re.compile(r'(?i)--(?:password|token|secret|api-key)\s+(?!https?://)\S{8,}'),
]


def redact_secrets(text: str) -> tuple[str, bool]:
    """Replace secret patterns with [REDACTED]. Returns (redacted_text, was_redacted)."""
    was_redacted = False
    for pattern in _REDACT_PATTERNS:
        new_text, count = pattern.subn("[REDACTED]", text)
        if count:
            text = new_text
            was_redacted = True
    return text, was_redacted


# ---------------------------------------------------------------------------
# Sensitive path detection
# ---------------------------------------------------------------------------

# Filenames that are never sensitive (template/example .env files safe to store observations about)
_ENV_SAFE_NAMES = {".env.example", ".env.template", ".env.sample"}

_SENSITIVE_FILENAME_GLOBS = [
    ".env",
    ".env.*",
    "credentials*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "tax-return*",
    "*passport*",
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
    "login data",
    "*.kdbx",
]

_SENSITIVE_PATH_GLOBS = [
    "*/.ssh/*",
    "*/shadow",
    "*/sudoers",
    "*/sudoers.*",
    "*/data/ingest-quarantine/*",  # quarantine files ARE known injection payloads — never store observations about them
    "*/.aws/*",
    "*/.kube/*",
    "*/.gnupg/*",
    "*/.mozilla/firefox/*/logins.json",
    "*/Chrome/*/Login Data",
    "*/keyrings/*",
]


def is_sensitive_path(path: str) -> bool:
    """Return True if path refers to a sensitive file (credentials, keys, etc.)."""
    p = PurePath(path)
    name_lower = p.name.lower()

    # Template/example env files are safe — they contain no real secrets
    if name_lower in _ENV_SAFE_NAMES:
        return False

    for glob in _SENSITIVE_FILENAME_GLOBS:
        if fnmatch(name_lower, glob):
            return True

    path_str = str(p)
    for glob in _SENSITIVE_PATH_GLOBS:
        if fnmatch(path_str, glob):
            return True

    if path_str in ("/etc/shadow", "/etc/sudoers"):
        return True
    if path_str.startswith("/etc/sudoers"):
        return True

    return False
