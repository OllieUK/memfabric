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
_model: SentenceTransformer = SentenceTransformer(_model_name)

_cache_dir: str | None = os.environ.get("EMBEDDING_CACHE_DIR") or None


def _cache_key(text: str) -> str:
    """Return a SHA-256 hex digest for the given model+text pair."""
    raw = f"{_model_name}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_embedding(text: str) -> list[float]:
    """Return a 384-dim (all-MiniLM-L6-v2) embedding for *text* as a plain list[float].

    If EMBEDDING_CACHE_DIR is set, results are cached on disk as JSON files
    keyed by SHA-256(model_name + text). Cache misses fall through to the model.
    """
    if _cache_dir:
        cache_path = Path(_cache_dir) / f"{_cache_key(text)}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        embedding: list[float] = _model.encode(text).tolist()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(embedding), encoding="utf-8")
        return embedding

    return _model.encode(text).tolist()
