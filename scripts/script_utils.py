"""Deprecation shim — WP-173. Moved to cyber_knowledge.ingest.script_utils.

Re-exports the full module namespace (including underscore-prefixed names)
so existing test imports via importlib.spec_from_file_location keep working.
Remove in WP-180 (see ADR-003).
"""
import warnings as _warnings

_warnings.warn(
    "scripts/script_utils.py path has moved to cyber_knowledge/ingest/script_utils.py (WP-173). "
    "Update imports to `from cyber_knowledge.ingest.script_utils import ...` "
    "and invocations to `python -m cyber_knowledge.ingest.script_utils`.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything (including underscore-prefixed names) by copying the
# target module's globals. `from X import *` would silently skip _-prefixed
# names and break unit tests that target internal helpers.
from cyber_knowledge.ingest import script_utils as _target  # noqa: E402

for _name in dir(_target):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_target, _name)

del _target, _name

