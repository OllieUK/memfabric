"""
Ingest guard — filters chunk/norm/threat text before persistence.

Reuses hooks/_filters.py to detect prompt-injection patterns in text
coming from PDFs, YAML, or STIX bundles before it reaches Memgraph.

Flagged chunks are quarantined to data/ingest-quarantine/<sha256>.txt
so they can be reviewed rather than silently lost.

Usage::

    from memory_service.ingest_guard import check_text, QuarantineError

    safe_text = check_text(text, source="ingest_document.py:chunk-7")
    # Raises QuarantineError if the text is flagged.
    # Returns text unchanged if clean.

Or call guard_chunk() which handles quarantine I/O internally and
returns a bool indicating whether the caller should skip the write.
"""
import hashlib
import sys
from pathlib import Path

# Resolve project root so this module is importable from any working directory
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent

# Lazily populated on first use
_filters_module = None


def _filters():
    """Lazy import of hooks._filters to avoid circular import issues."""
    global _filters_module
    if _filters_module is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hooks._filters",
            _PROJECT_ROOT / "hooks" / "_filters.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _filters_module = mod
    return _filters_module


QUARANTINE_DIR = _PROJECT_ROOT / "data" / "ingest-quarantine"


class QuarantineError(ValueError):
    """Raised when a chunk is flagged by the ingest guard."""

    def __init__(self, message: str, quarantine_path: Path | None = None) -> None:
        super().__init__(message)
        self.quarantine_path = quarantine_path


def _quarantine_chunk(text: str, source: str) -> Path:
    """Write flagged text to the quarantine directory.

    Returns the path of the quarantine file.
    """
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    path = QUARANTINE_DIR / f"{sha}.txt"
    content = f"# Quarantined by ingest_guard\n# Source: {source}\n\n{text}\n"
    path.write_text(content, encoding="utf-8")
    return path


def guard_chunk(text: str, source: str = "unknown") -> bool:
    """Check text for injection patterns before persistence.

    If the text is flagged:
    - Writes it to data/ingest-quarantine/<sha256>.txt
    - Prints a warning to stderr
    - Returns True (caller should skip this chunk)

    If the text is clean:
    - Returns False (caller should proceed normally)

    Never raises — any unexpected error is logged to stderr and
    returns False (fail-open) to avoid blocking ingest.
    """
    try:
        f = _filters()
        if f.contains_injection(text):
            path = _quarantine_chunk(text, source)
            print(
                f"[ingest_guard] QUARANTINED chunk from {source} "
                f"— injection pattern detected. "
                f"File: {path}",
                file=sys.stderr,
            )
            return True
        return False
    except Exception as exc:  # noqa: BLE001
        print(
            f"[ingest_guard] ERROR checking chunk from {source}: {exc!r} "
            f"— proceeding (fail-open)",
            file=sys.stderr,
        )
        return False
