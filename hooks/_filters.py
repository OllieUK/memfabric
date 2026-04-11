"""
Shared content filters for security-sensitive text processing.

Used by:
  hooks/session_start.py  — filters wake-up output before injecting into system prompt
  hooks/post_tool_use.py  — redacts secrets before storing observations
  memory_service/ingest_guard.py (WP-SEC-3) — filters ingest chunks before storing
"""
import re
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


def contains_injection(text: str) -> bool:
    """Return True if text contains prompt-injection indicators."""
    lower = text.lower()
    for literal in _INJECTION_LITERALS:
        if literal in lower:
            return True
    for ch in text:
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
]

_SENSITIVE_PATH_GLOBS = [
    "*/.ssh/*",
    "*/shadow",
    "*/sudoers",
    "*/sudoers.*",
    "*/data/ingest-quarantine/*",  # quarantine files ARE known injection payloads — never store observations about them
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
