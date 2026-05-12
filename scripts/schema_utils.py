"""Deprecation shim — schema utilities moved to cyber_knowledge.ingest.schema_utils.

Kept so scripts/init_schema.py and tests/test_wp077_schema_utils.py keep working
during the WP-173/174 package-boundary transition.
"""
import warnings

from cyber_knowledge.ingest.schema_utils import (
    SentenceTransformer,
    create_constraint,
    get_embedding_dimension,
)

warnings.warn(
    "scripts.schema_utils is deprecated; import from cyber_knowledge.ingest.schema_utils.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["SentenceTransformer", "create_constraint", "get_embedding_dimension"]
