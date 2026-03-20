# tests/test_embeddings.py

import importlib
import json
from pathlib import Path

import pytest

import memory_service.embeddings as emb_module
from memory_service.embeddings import get_embedding


def test_get_embedding_returns_list():
    result = get_embedding("hello world")
    assert isinstance(result, list), "Expected a list, got %s" % type(result)
    assert len(result) == 384, "all-MiniLM-L6-v2 should produce 384-dim vectors"
    assert all(isinstance(v, float) for v in result), "All elements must be float"


def test_get_embedding_consistent():
    first = get_embedding("hello world")
    second = get_embedding("hello world")
    assert first == second, "get_embedding must be deterministic for the same input"


def test_get_embedding_different_texts():
    assert get_embedding("foo") != get_embedding("bar"), (
        "Different texts must produce different embeddings"
    )


def test_get_embedding_cache(monkeypatch, tmp_path):
    """Cache stores result to disk; second call reads from disk, returns same vector."""
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path))

    # Patch the module-level _cache_dir so the already-imported module sees the new dir.
    monkeypatch.setattr(emb_module, "_cache_dir", str(tmp_path))

    text = "cache test sentence"

    first = get_embedding(text)
    cache_key = emb_module._cache_key(text)
    cache_file = tmp_path / f"{cache_key}.json"

    assert cache_file.exists(), "Cache file should have been created after first call"

    stored = json.loads(cache_file.read_text(encoding="utf-8"))
    assert stored == first, "Cache file content must match the returned embedding"

    second = get_embedding(text)
    assert second == first, "Second call (cache hit) must return the same embedding"
