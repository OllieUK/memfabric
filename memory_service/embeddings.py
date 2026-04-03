# memory_service/embeddings.py
#
# Local embedding module — no FastAPI, no neo4j imports.
# Importable standalone: python -c "from memory_service.embeddings import get_embedding; print(get_embedding('test')[:3])"

import hashlib
import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer

_model_name: str = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
_model: SentenceTransformer | None = None
_model_cache: dict[str, SentenceTransformer] = {}

_cache_dir: str | None = os.environ.get("EMBEDDING_CACHE_DIR") or None


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _local_files_only() -> bool:
    if _env_flag("EMBEDDING_LOCAL_FILES_ONLY", True):
        return True
    return _env_flag("HF_HUB_OFFLINE", False) or _env_flag("TRANSFORMERS_OFFLINE", False)


def _make_st_kwargs() -> dict:
    """Return kwargs for SentenceTransformer construction, setting offline env vars as a side-effect."""
    if not _local_files_only():
        return {}
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    return {"local_files_only": True}


def _load_model() -> SentenceTransformer:
    kwargs = _make_st_kwargs()
    try:
        return SentenceTransformer(_model_name, **kwargs)
    except Exception as exc:
        if kwargs.get("local_files_only"):
            raise RuntimeError(
                "Could not load the embedding model "
                f"'{_model_name}' from local files. Cache the model locally first or "
                "set EMBEDDING_LOCAL_FILES_ONLY=false for a one-time download."
            ) from exc
        raise RuntimeError(
            f"Could not load the embedding model '{_model_name}'."
        ) from exc


def _load_model_by_name(model_name: str) -> SentenceTransformer:
    """Load a SentenceTransformer by explicit name, reusing shared offline config."""
    kwargs = _make_st_kwargs()
    try:
        return SentenceTransformer(model_name, **kwargs)
    except Exception as exc:
        if kwargs.get("local_files_only"):
            raise RuntimeError(
                f"Could not load the embedding model '{model_name}' from local files. "
                "Cache the model locally first or set EMBEDDING_LOCAL_FILES_ONLY=false."
            ) from exc
        raise RuntimeError(f"Could not load the embedding model '{model_name}'.") from exc


def get_model(model_name: str | None = None) -> SentenceTransformer:
    """Return the SentenceTransformer for the given model name.

    model_name=None or model_name==_model_name → singleton path (backward-compat).
    model_name=<other> → load/return from _model_cache.
    """
    global _model
    if model_name is None or model_name == _model_name:
        if _model is None:
            _model = _load_model()
        return _model
    if model_name not in _model_cache:
        _model_cache[model_name] = _load_model_by_name(model_name)
    return _model_cache[model_name]


def get_embedding_dimension(model_name: str | None = None) -> int:
    """Return the embedding dimension for the given model (default: EMBEDDING_MODEL)."""
    return int(get_model(model_name).get_sentence_embedding_dimension())


def _cache_key(text: str, model_name: str | None = None) -> str:
    """Return a SHA-256 hex digest for the given model+text pair."""
    raw = f"{model_name or _model_name}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_embedding(text: str, model_name: str | None = None) -> list[float]:
    """Return an embedding vector for *text* as a plain list[float].

    model_name=None → uses EMBEDDING_MODEL (default, backward-compatible).
    model_name=<name> → uses that model (loaded/cached on first call).

    If EMBEDDING_CACHE_DIR is set, results are cached on disk as JSON files
    keyed by SHA-256(model_name + text). Different models produce separate cache entries.
    """
    if _cache_dir:
        cache_path = Path(_cache_dir) / f"{_cache_key(text, model_name)}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        embedding: list[float] = get_model(model_name).encode(text).tolist()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(embedding), encoding="utf-8")
        return embedding

    return get_model(model_name).encode(text).tolist()
