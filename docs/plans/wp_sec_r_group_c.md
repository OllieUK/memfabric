# WP-SEC-R15: Wire STIX SHA-256 Verification into ingest_attack.py

**Date:** 2026-04-11
**Status:** Ready for implementation

---

## Summary

Wire the existing `data/frameworks/attack-stix-pins.json` pin file into
`scripts/ingest_attack.py` so that every code path that resolves a STIX bundle
— cached, freshly downloaded, or user-supplied — is verified against its
SHA-256 pin before `MitreAttackData` ever parses the file.

---

## Context

`scripts/ingest_attack.py` downloads or reads a cached copy of the MITRE
ATT&CK Enterprise STIX bundle, then hands it to `MitreAttackData` for parsing.
The current `_resolve_stix_path()` function has an unfulfilled TODO comment on
the download branch and no check at all on the cached-bundle branch.
`data/frameworks/attack-stix-pins.json` was created in WP-SEC-3 and already
contains the correct pin for `enterprise-attack-17.0.json`. The hash in the pin
file has been confirmed to match the cached bundle on disk (P0.1 verification
passed: `c8966a9a55f1723c0082910f4522af448514343f84ffb9a3e757bdd59642d057`).

No pin update is required before or as part of this WP.

---

## Approach

### Step 1 — Confirm `hashlib` import

Read lines 1–35 of `scripts/ingest_attack.py`. `hashlib` is **not** currently
imported. Add it to the stdlib import block alongside the existing imports
(`argparse`, `sys`, `urllib.request`, `pathlib.Path`, `typing.Optional`).

### Step 2 — Add `_STIX_PINS_FILE` constant

Immediately after the existing `DEFAULT_STIX_PATH` and `STIX_DOWNLOAD_URL`
constants (around line 43), add:

```python
_STIX_PINS_FILE = Path(__file__).resolve().parent.parent / "data" / "frameworks" / "attack-stix-pins.json"
```

Using `.resolve()` makes the path robust when the script is invoked from any
working directory.

### Step 3 — Add `_verify_stix_sha256()` helper

Add a new function in the Helpers section (after `_add_contains`, before the
"Ingestion steps" section heading):

```python
def _verify_stix_sha256(path: Path, skip: bool = False) -> None:
    """Verify path against the SHA-256 pin in attack-stix-pins.json.

    Exits with an error if the hash does not match or no pin entry exists for
    this filename. Pass skip=True to bypass verification (prints a warning to
    stderr and returns immediately — for emergency use only).
    """
    if skip:
        print("WARNING: SHA-256 verification skipped (--skip-sha256-check)", file=sys.stderr)
        return
    try:
        pins = json.loads(_STIX_PINS_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error: cannot read pin file {_STIX_PINS_FILE}: {e}", file=sys.stderr)
        sys.exit(1)
    filename = path.name
    if filename not in pins:
        print(
            f"Error: no SHA-256 pin entry for '{filename}' in {_STIX_PINS_FILE}",
            file=sys.stderr,
        )
        sys.exit(1)
    expected = pins[filename]["sha256"]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        print(
            f"Error: SHA-256 mismatch for {path.name}\n"
            f"  expected: {expected}\n"
            f"  actual:   {actual}\n"
            "The bundle may be corrupted or tampered. Delete the cached file and "
            "re-download, or update the pin if you intentionally updated the bundle.",
            file=sys.stderr,
        )
        sys.exit(1)
```

Note: `json` is already imported at the top of the file.

### Step 4 — Add `--skip-sha256-check` CLI flag

In `_parse_args()`, after the existing `--dry-run` argument, add:

```python
parser.add_argument(
    "--skip-sha256-check",
    action="store_true",
    help="Skip SHA-256 verification of the STIX bundle (emergency use only).",
)
```

### Step 5 — Update `_resolve_stix_path()` signature and body

Change the function signature to:

```python
def _resolve_stix_path(stix_file: Optional[str], skip_sha256: bool = False) -> Path:
```

Then update each branch:

**Branch A — user-supplied `--stix-file`** (currently lines 321–326):

```python
if stix_file:
    path = Path(stix_file)
    if not path.exists():
        print(f"Error: STIX file not found: {path}", file=sys.stderr)
        sys.exit(1)
    if path.name in json.loads(_STIX_PINS_FILE.read_text()):
        _verify_stix_sha256(path, skip=skip_sha256)
    return path
```

Rationale: user-supplied bundles may be custom or from a different ATT&CK
version. Only verify if the filename is an explicitly pinned file; otherwise
trust the caller.

**Branch B — cached bundle** (currently lines 328–330):

```python
if DEFAULT_STIX_PATH.exists():
    print(f"Using cached STIX bundle: {DEFAULT_STIX_PATH}")
    _verify_stix_sha256(DEFAULT_STIX_PATH, skip=skip_sha256)
    return DEFAULT_STIX_PATH
```

**Branch C — download** (currently lines 332–339, replaces the TODO comment):

```python
print("Downloading ATT&CK Enterprise STIX bundle from MITRE GitHub...")
DEFAULT_STIX_PATH.parent.mkdir(parents=True, exist_ok=True)
urllib.request.urlretrieve(STIX_DOWNLOAD_URL, DEFAULT_STIX_PATH)
_verify_stix_sha256(DEFAULT_STIX_PATH, skip=skip_sha256)
print(f"Saved to: {DEFAULT_STIX_PATH}")
return DEFAULT_STIX_PATH
```

### Step 6 — Propagate `skip_sha256` in `main()`

Change the call to `_resolve_stix_path` in `main()`:

```python
stix_path = _resolve_stix_path(args.stix_file, skip_sha256=args.skip_sha256_check)
```

---

## Affected Files

| File | Change |
|------|--------|
| `scripts/ingest_attack.py` | Add `import hashlib`; add `_STIX_PINS_FILE` constant; add `_verify_stix_sha256()` helper; add `--skip-sha256-check` to `_parse_args()`; update `_resolve_stix_path()` signature and all three branches; update `main()` call site |
| `tests/test_wp_sec_r15_stix_verification.py` | New file — 9 unit tests covering all branches and error paths |

---

## Cypher Patterns

None. This WP makes no database changes.

---

## Scope Boundaries (hard)

Only the following parts of `ingest_attack.py` may be touched:

- The stdlib import block (add `hashlib`)
- The constants block (add `_STIX_PINS_FILE`)
- The Helpers section (add `_verify_stix_sha256`)
- `_parse_args()` (add `--skip-sha256-check` argument)
- `_resolve_stix_path()` (updated signature and body)
- `main()` (updated call to `_resolve_stix_path`)

Do NOT modify: `ETLSettings`, `_upsert`, `_add_contains`, `ingest_root`,
`ingest_tactics`, `ingest_techniques`, `ingest_subtechniques`, `MitreAttackData`
calls, or any other function.

Do NOT modify: `BACKLOG.md`, `data/frameworks/attack-stix-pins.json`.

---

## Test Plan

### Unit Tests

**File:** `tests/test_wp_sec_r15_stix_verification.py`

All tests are pure unit tests. No network access. No live Memgraph. No running
FastAPI service. Tests use `tmp_path` (pytest fixture) and `monkeypatch` to
isolate the script's module-level constants from the real filesystem.

**Import pattern** — match `tests/test_wp_sec3_ingest_guard.py`:

```python
"""Unit tests for _verify_stix_sha256 and _resolve_stix_path in ingest_attack.py.

No live service required — all tests are purely filesystem and hash logic.
"""
import sys
import json
import hashlib
from pathlib import Path

# Ensure project root is on sys.path so scripts/ is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from unittest.mock import patch, MagicMock

import scripts.ingest_attack as _attack_module
from scripts.ingest_attack import _verify_stix_sha256, _resolve_stix_path
```

---

#### Test 1: `test_verify_stix_sha256_clean`

Happy path. Write known bytes to a tmp file, construct a matching pin JSON,
point `_STIX_PINS_FILE` at it, call `_verify_stix_sha256` — expect no
`SystemExit`.

```python
def test_verify_stix_sha256_clean(tmp_path, monkeypatch):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"known bundle content")
    expected_hash = hashlib.sha256(b"known bundle content").hexdigest()

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({
        "enterprise-attack-17.0.json": {
            "sha256": expected_hash,
            "upstream_url": "https://example.com",
            "last_verified": "2026-04-11",
        }
    }))
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    # Should not raise
    _verify_stix_sha256(bundle)
```

---

#### Test 2: `test_verify_stix_sha256_mismatch_exits`

Wrong hash in pin file → `SystemExit`, stderr contains "SHA-256 mismatch".

```python
def test_verify_stix_sha256_mismatch_exits(tmp_path, monkeypatch, capsys):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"real content")

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({
        "enterprise-attack-17.0.json": {
            "sha256": "a" * 64,  # deliberately wrong
            "upstream_url": "https://example.com",
            "last_verified": "2026-04-11",
        }
    }))
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    with pytest.raises(SystemExit):
        _verify_stix_sha256(bundle)

    captured = capsys.readouterr()
    assert "SHA-256 mismatch" in captured.err
```

---

#### Test 3: `test_verify_stix_sha256_missing_pin_entry_exits`

Filename not present in the pin JSON → `SystemExit`, stderr contains
"no SHA-256 pin entry".

```python
def test_verify_stix_sha256_missing_pin_entry_exits(tmp_path, monkeypatch, capsys):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"content")

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({"other-bundle.json": {"sha256": "x" * 64}}))
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    with pytest.raises(SystemExit):
        _verify_stix_sha256(bundle)

    captured = capsys.readouterr()
    assert "no SHA-256 pin entry" in captured.err
```

---

#### Test 4: `test_verify_stix_sha256_malformed_pin_file_exits`

Pin file contains invalid JSON → `SystemExit`, stderr mentions the pin file path
but does not expose a raw Python traceback.

```python
def test_verify_stix_sha256_malformed_pin_file_exits(tmp_path, monkeypatch, capsys):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"content")

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text("{ this is not valid json }")
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    with pytest.raises(SystemExit):
        _verify_stix_sha256(bundle)

    captured = capsys.readouterr()
    assert "Error" in captured.err
    assert "Traceback" not in captured.err
```

---

#### Test 5: `test_verify_stix_sha256_skip_prints_warning`

`skip=True` → function returns without raising `SystemExit`, and stderr contains
"WARNING".

```python
def test_verify_stix_sha256_skip_prints_warning(tmp_path, capsys):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"content")

    # No pin file needed — skip=True should return before reading it
    _verify_stix_sha256(bundle, skip=True)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
```

---

#### Test 6: `test_resolve_stix_path_cached_verifies`

Cached bundle exists and its hash matches the pin → `_resolve_stix_path(None)`
returns the path cleanly without `SystemExit`.

```python
def test_resolve_stix_path_cached_verifies(tmp_path, monkeypatch):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"good cached content")
    expected_hash = hashlib.sha256(b"good cached content").hexdigest()

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({
        "enterprise-attack-17.0.json": {
            "sha256": expected_hash,
            "upstream_url": "https://example.com",
            "last_verified": "2026-04-11",
        }
    }))

    monkeypatch.setattr(_attack_module, "DEFAULT_STIX_PATH", bundle)
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    result = _resolve_stix_path(None)
    assert result == bundle
```

---

#### Test 7: `test_resolve_stix_path_cached_tampered_exits`

Cached bundle exists but its hash does not match the pin → `SystemExit` is
raised before `MitreAttackData` could be called.

```python
def test_resolve_stix_path_cached_tampered_exits(tmp_path, monkeypatch):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"tampered content")

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({
        "enterprise-attack-17.0.json": {
            "sha256": "0" * 64,  # deliberately wrong
            "upstream_url": "https://example.com",
            "last_verified": "2026-04-11",
        }
    }))

    monkeypatch.setattr(_attack_module, "DEFAULT_STIX_PATH", bundle)
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    with pytest.raises(SystemExit):
        _resolve_stix_path(None)
```

---

#### Test 8: `test_resolve_stix_path_download_verifies`

No cached bundle exists. `urlretrieve` is monkeypatched to write a known file.
Pin file matches that file → `_resolve_stix_path(None)` returns cleanly.

```python
def test_resolve_stix_path_download_verifies(tmp_path, monkeypatch):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    # Do NOT pre-create the bundle — force the download branch
    content = b"downloaded bundle content"
    expected_hash = hashlib.sha256(content).hexdigest()

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({
        "enterprise-attack-17.0.json": {
            "sha256": expected_hash,
            "upstream_url": "https://example.com",
            "last_verified": "2026-04-11",
        }
    }))

    def fake_urlretrieve(url, dest):
        Path(dest).write_bytes(content)

    monkeypatch.setattr(_attack_module, "DEFAULT_STIX_PATH", bundle)
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)
    monkeypatch.setattr(_attack_module.urllib.request, "urlretrieve", fake_urlretrieve)

    result = _resolve_stix_path(None)
    assert result == bundle
```

---

#### Test 9: `test_skip_sha256_check_flag_bypasses`

Tampered cached bundle + `skip_sha256=True` → no `SystemExit`, warning printed
to stderr.

```python
def test_skip_sha256_check_flag_bypasses(tmp_path, monkeypatch, capsys):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"tampered content")

    pin_file = tmp_path / "attack-stix-pins.json"
    pin_file.write_text(json.dumps({
        "enterprise-attack-17.0.json": {
            "sha256": "0" * 64,
            "upstream_url": "https://example.com",
            "last_verified": "2026-04-11",
        }
    }))

    monkeypatch.setattr(_attack_module, "DEFAULT_STIX_PATH", bundle)
    monkeypatch.setattr(_attack_module, "_STIX_PINS_FILE", pin_file)

    # Should not raise even though hash is wrong
    result = _resolve_stix_path(None, skip_sha256=True)
    assert result == bundle

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
```

---

### Integration Tests (require live stack)

None required for this WP. The change is confined to a standalone ingestion
script and a new pure-Python helper function. No FastAPI endpoints are modified
and no Memgraph schema changes are made.

The smoke test below (acceptance criterion 2) acts as the integration-adjacent
verification that the script works end-to-end with the real pin file and the
real cached bundle.

---

### Acceptance Criteria

1. All 9 unit tests pass: `pytest tests/test_wp_sec_r15_stix_verification.py -v`
2. Smoke test passes against the existing cached bundle (no live Memgraph
   required — `--dry-run` only parses):
   ```
   python3 scripts/ingest_attack.py --dry-run
   ```
   Expected output includes parse counts (e.g. "Nodes to ingest: NNN total")
   with no SHA-256 error or `SystemExit`.
3. Full pytest suite is green: `pytest` (no regressions).
4. The TODO comment in `_resolve_stix_path` is gone, replaced by the actual
   verification call.
5. The `--skip-sha256-check` flag is documented in `--help` output.

---

## Risks / Open Questions

1. **`scripts/` importability.** The test file uses `sys.path` injection at the
   top (matching `test_wp_sec3_ingest_guard.py`) to import from `scripts/`.
   Verify that `scripts/__init__.py` is absent (the import works as a plain
   module, not a package). If a `scripts/__init__.py` exists, import via
   `importlib.util` instead.

2. **Branch A (user-supplied `--stix-file`) reads the pin file twice.** In the
   proposed implementation, `_STIX_PINS_FILE` is read once to check whether the
   filename is pinned, and then again inside `_verify_stix_sha256` itself. This
   is intentionally simple and the file is small (~200 bytes). No caching is
   needed at this scale.

3. **`MitreAttackData` import at module load.** `from mitreattack.stix20 import
   MitreAttackData` runs on import. Tests that monkeypatch module attributes
   (`DEFAULT_STIX_PATH`, `_STIX_PINS_FILE`) must import `scripts.ingest_attack`
   first and then apply monkeypatches — which is the correct order in the test
   bodies above.

4. **Pin file missing from disk entirely.** If `_STIX_PINS_FILE` does not exist
   (e.g. fresh checkout without `data/` populated), `OSError` is caught by the
   `except (json.JSONDecodeError, OSError)` clause and the script exits with a
   clear error message. No silent pass-through.
