# tests/test_embeddings.py

import json

import pytest

import memory_service.embeddings as emb_module
from memory_service.embeddings import get_embedding, get_embedding_dimension, get_model


class DummyModel:
    def __init__(self, dim=3):
        self.dim = dim

    def encode(self, text):
        base = float(sum(ord(ch) for ch in text))
        return DummyVector([base + float(i) for i in range(self.dim)])

    def get_sentence_embedding_dimension(self):
        return self.dim


class DummyVector:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


@pytest.fixture(autouse=True)
def reset_embedding_model(monkeypatch):
    monkeypatch.setattr(emb_module, "_model", DummyModel())
    monkeypatch.setattr(emb_module, "_cache_dir", None)


def test_get_embedding_returns_list():
    expected_dim = get_embedding_dimension()
    result = get_embedding("hello world")
    assert isinstance(result, list)
    assert len(result) == expected_dim
    assert all(isinstance(v, float) for v in result)


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


def test_get_model_uses_local_files_only_by_default(monkeypatch):
    calls = []

    class RecordingModel(DummyModel):
        def __init__(self, model_name, **kwargs):
            calls.append((model_name, kwargs))
            super().__init__()

    monkeypatch.delenv("EMBEDDING_LOCAL_FILES_ONLY", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    monkeypatch.setattr(emb_module, "_model", None)
    monkeypatch.setattr(emb_module, "SentenceTransformer", RecordingModel)

    model = get_model()

    assert isinstance(model, RecordingModel)
    assert calls == [(emb_module._model_name, {"local_files_only": True})]


def test_get_model_raises_helpful_error_when_local_model_missing(monkeypatch):
    class MissingModel:
        def __init__(self, *args, **kwargs):
            raise OSError("missing model")

    monkeypatch.setenv("EMBEDDING_LOCAL_FILES_ONLY", "true")
    monkeypatch.setattr(emb_module, "_model", None)
    monkeypatch.setattr(emb_module, "SentenceTransformer", MissingModel)

    with pytest.raises(RuntimeError, match="Cache the model locally first"):
        get_model()
