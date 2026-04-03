"""Tests for multi-model embedding support (WP-077).

Unit tests only — mocks SentenceTransformer; no model download required.
"""
import sys
import os
import importlib
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _reload_embeddings():
    """Return a freshly-reloaded embeddings module with clean module-level state."""
    import memory_service.embeddings as emb

    importlib.reload(emb)
    # Reset mutable state that reload may not clear
    emb._model = None
    emb._model_cache.clear()
    return emb


def test_get_embedding_no_model_name_uses_singleton():
    """Calling get_embedding without model_name uses singleton (_load_model called once)."""
    emb = _reload_embeddings()
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2])
    with patch.object(emb, "_load_model", return_value=mock_model) as mock_load:
        emb._model = None
        emb.get_embedding("hello")
        emb.get_embedding("world")
        assert mock_load.call_count == 1


def test_get_embedding_explicit_default_model_uses_singleton():
    """Calling get_embedding with model_name == _model_name uses singleton, not cache."""
    emb = _reload_embeddings()
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2])
    emb._model = mock_model
    with patch.object(emb, "_load_model_by_name") as mock_by_name:
        emb.get_embedding("hello", model_name=emb._model_name)
        mock_by_name.assert_not_called()


def test_get_embedding_different_model_uses_cache():
    """get_embedding with a non-default model uses _model_cache (loaded exactly once)."""
    emb = _reload_embeddings()
    mock_model = MagicMock()
    mock_model.encode.return_value = MagicMock(tolist=lambda: [0.3, 0.4])
    with patch.object(emb, "_load_model_by_name", return_value=mock_model) as mock_load:
        emb.get_embedding("hello", model_name="other-model")
        emb.get_embedding("world", model_name="other-model")
        assert mock_load.call_count == 1


def test_get_embedding_dimension_default():
    """get_embedding_dimension() with no args uses the singleton model."""
    emb = _reload_embeddings()
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 384
    emb._model = mock_model
    result = emb.get_embedding_dimension()
    assert result == 384


def test_get_embedding_dimension_named_model():
    """get_embedding_dimension('other-model') calls _load_model_by_name."""
    emb = _reload_embeddings()
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 768
    with patch.object(emb, "_load_model_by_name", return_value=mock_model):
        result = emb.get_embedding_dimension("other-model")
        assert result == 768


def test_cache_key_is_model_aware():
    """_cache_key produces different hashes for different model names."""
    emb = _reload_embeddings()
    key_a = emb._cache_key("hello", model_name="model-a")
    key_b = emb._cache_key("hello", model_name="model-b")
    assert key_a != key_b


def test_cache_key_none_matches_default():
    """_cache_key with model_name=None produces same hash as model_name=_model_name."""
    emb = _reload_embeddings()
    key_none = emb._cache_key("hello", model_name=None)
    key_default = emb._cache_key("hello", model_name=emb._model_name)
    assert key_none == key_default
