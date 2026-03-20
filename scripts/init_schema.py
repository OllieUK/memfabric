"""
init_schema.py – Create Memgraph constraints and vector index.

Run once after `docker compose up`, before first use:
    python scripts/init_schema.py

Idempotent: re-running on an already-initialised DB will not error.
"""

import sys

from neo4j.exceptions import ClientError

from memory_service.config import Settings, get_driver


def get_embedding_dimension(model_name: str) -> int:
    """Load the named SentenceTransformer model and return its output dimension."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name).get_sentence_embedding_dimension()


def get_existing_index_dimension(session) -> int | None:
    """Return the dimension of the existing Memory(embedding) vector index, or None if not found."""
    try:
        result = session.run("SHOW INDEX INFO;")
        for record in result:
            # Column names vary by Memgraph version — inspect the row lazily
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(record.get("type") or record.get("Type") or "")
            if label == "Memory" and prop == "embedding" and "vector" in index_type.lower():
                row = dict(record)
                return row.get("dimension") or row.get("Dimension") or row.get("options", {}).get("dimension")
    except Exception as exc:
        print(f"  [WARN] Could not query existing index info: {exc}")
    return None


# Uniqueness constraints: (label, property)
UNIQUENESS_CONSTRAINTS = [
    ("Memory", "id"),
    ("Strand", "id"),
    ("Agent", "id"),
    ("Person", "id"),
    ("Project", "id"),
]


def create_constraint(session, label: str, prop: str) -> None:
    query = (
        f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{prop} IS UNIQUE;"
    )
    try:
        session.run(query)
        print(f"  [OK] Constraint created: {label}.{prop} IS UNIQUE")
    except ClientError as exc:
        if "already exists" in str(exc).lower():
            print(f"  [SKIP] Constraint already exists: {label}.{prop} IS UNIQUE")
        else:
            raise


def create_vector_index(session, dim: int, model_name: str) -> None:
    query = (
        f'CREATE VECTOR INDEX mem_embedding_idx ON :Memory(embedding) '
        f'WITH CONFIG {{"dimension": {dim}, "capacity": 1000, "metric": "cos"}};'
    )
    try:
        session.run(query)
        print(f"  [OK] Vector index created: Memory(embedding) dim={dim} model={model_name} metric=cos")
    except ClientError as exc:
        if "already exists" in str(exc).lower():
            print(f"  [SKIP] Vector index already exists: Memory(embedding)")
        else:
            raise


def main() -> int:
    settings = Settings()
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    print(f"Connecting to Memgraph at {uri} ...")

    try:
        driver = get_driver(settings)
        # Verify connectivity
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Could not connect to Memgraph: {exc}")
        return 1

    print(f"Loading embedding model '{settings.embedding_model}' to determine vector dimension ...")
    try:
        dim = get_embedding_dimension(settings.embedding_model)
        print(f"  Embedding dimension: {dim}")
    except Exception as exc:
        driver.close()
        print(f"[FAIL] Could not load embedding model '{settings.embedding_model}': {exc}")
        return 1

    success = True
    try:
        with driver.session() as session:
            print("\nCreating uniqueness constraints ...")
            for label, prop in UNIQUENESS_CONSTRAINTS:
                try:
                    create_constraint(session, label, prop)
                except Exception as exc:
                    print(f"  [FAIL] Constraint {label}.{prop}: {exc}")
                    success = False

            print("\nCreating vector index ...")
            existing_dim = get_existing_index_dimension(session)
            if existing_dim is not None and existing_dim != dim:
                print(
                    f"  [FAIL] Existing vector index has dimension={existing_dim} but "
                    f"model '{settings.embedding_model}' produces dimension={dim}. "
                    f"Drop the index manually:\n"
                    f"    DROP VECTOR INDEX mem_embedding_idx;\n"
                    f"  Then re-run init_schema.py."
                )
                success = False
            else:
                try:
                    create_vector_index(session, dim=dim, model_name=settings.embedding_model)
                except Exception as exc:
                    print(f"  [FAIL] Vector index: {exc}")
                    success = False
    except Exception as exc:
        print(f"[FAIL] Session error: {exc}")
        return 1
    finally:
        driver.close()

    if success:
        print("\nSchema initialisation complete.")
        return 0
    else:
        print("\nSchema initialisation finished with errors.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
