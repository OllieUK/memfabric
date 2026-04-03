"""schema_utils.py — Shared utilities for Memgraph schema initialisation scripts."""
from neo4j.exceptions import ClientError
from sentence_transformers import SentenceTransformer


def get_embedding_dimension(model_name: str) -> int:
    """Load the named SentenceTransformer model and return its output dimension."""
    return SentenceTransformer(model_name).get_sentence_embedding_dimension()


def create_constraint(session, label: str, prop: str) -> None:
    """Create a uniqueness constraint; skip gracefully if it already exists."""
    query = f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{prop} IS UNIQUE;"
    try:
        session.run(query)
        print(f"  [OK] Constraint created: {label}.{prop} IS UNIQUE")
    except ClientError as exc:
        if "already exists" in str(exc).lower():
            print(f"  [SKIP] Constraint already exists: {label}.{prop} IS UNIQUE")
        else:
            raise
