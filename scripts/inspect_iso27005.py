"""Deprecation shim — WP-173. Moved to cyber_knowledge.ingest.inspect_iso27005.

Re-exports the full module namespace (including underscore-prefixed names)
so existing test imports via importlib.spec_from_file_location keep working.
Remove in WP-180 (see ADR-003).
"""
import warnings as _warnings

_warnings.warn(
    "scripts/inspect_iso27005.py path has moved to cyber_knowledge/ingest/inspect_iso27005.py (WP-173). "
    "Update imports to `from cyber_knowledge.ingest.inspect_iso27005 import ...` "
    "and invocations to `python -m cyber_knowledge.ingest.inspect_iso27005`.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything (including underscore-prefixed names) by copying the
# target module's globals. `from X import *` would silently skip _-prefixed
# names and break unit tests that target internal helpers.
from cyber_knowledge.ingest import inspect_iso27005 as _target  # noqa: E402

for _name in dir(_target):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_target, _name)

del _target, _name

if __name__ == "__main__":
    from cyber_knowledge.ingest.inspect_iso27005 import main as _main  # noqa: E402
    _main()

