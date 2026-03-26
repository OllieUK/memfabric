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


def _load_model() -> SentenceTransformer:
    kwargs = {}
    if _local_files_only():
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        kwargs["local_files_only"] = True

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


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = _load_model()
    return _model


def get_embedding_dimension() -> int:
    return int(get_model().get_sentence_embedding_dimension())


def _cache_key(text: str) -> str:
    """Return a SHA-256 hex digest for the given model+text pair."""
    raw = f"{_model_name}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_embedding(text: str) -> list[float]:
    """Return an embedding vector for *text* as a plain list[float].

    Dimension is determined by the loaded model.

    If EMBEDDING_CACHE_DIR is set, results are cached on disk as JSON files
    keyed by SHA-256(model_name + text). Cache misses fall through to the model.
    """
    if _cache_dir:
        cache_path = Path(_cache_dir) / f"{_cache_key(text)}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        embedding: list[float] = get_model().encode(text).tolist()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(embedding), encoding="utf-8")
        return embedding

    return get_model().encode(text).tolist()
