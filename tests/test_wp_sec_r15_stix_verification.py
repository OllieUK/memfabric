"""Unit tests for _verify_stix_sha256 and _resolve_stix_path in ingest_attack.py.

No live service required — all tests are purely filesystem and hash logic.
"""
import sys
import json
import hashlib
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is on sys.path so scripts/ is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Stub mitreattack at the sys.modules level before importing the script,
# so collection succeeds in environments that don't have the package installed.
if "mitreattack" not in sys.modules:
    _mitre_stub = MagicMock()
    sys.modules["mitreattack"] = _mitre_stub
    sys.modules["mitreattack.stix20"] = _mitre_stub
    sys.modules["mitreattack.stix20.MitreAttackData"] = _mitre_stub

import pytest

import cyber_knowledge.ingest.attack as _attack_module
from cyber_knowledge.ingest.attack import _verify_stix_sha256, _resolve_stix_path


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


def test_verify_stix_sha256_skip_prints_warning(tmp_path, capsys):
    bundle = tmp_path / "enterprise-attack-17.0.json"
    bundle.write_bytes(b"content")

    # No pin file needed — skip=True should return before reading it
    _verify_stix_sha256(bundle, skip=True)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err


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
