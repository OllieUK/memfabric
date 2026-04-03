"""
init_knowledge_schema.py — Create Memgraph constraints and vector indexes for the information security knowledge layer.

Run after init_schema.py, once the knowledge layer is needed:
    python scripts/init_knowledge_schema.py

Idempotent: re-running on an already-initialised DB will not error.
"""

import sys

from neo4j.exceptions import ClientError

from memory_service.config import Settings, get_driver
from scripts.schema_utils import create_constraint, get_embedding_dimension


# New uniqueness constraints: (label, property)
KNOWLEDGE_CONSTRAINTS = [
    ("Norm", "id"),
    ("Control", "id"),
    ("Document", "id"),
    ("Chunk", "id"),
    ("BusinessAttribute", "id"),
    ("Organisation", "id"),
    ("Jurisdiction", "code"),   # primary key is 'code', not 'id'
]


def validate_vector_index(
    session,
    index_name: str,
    expected_label: str,
    expected_property: str,
) -> bool:
    """Read back SHOW INDEX INFO and assert label+property match expectations.

    Returns True if the index is found and valid, False if not found or mismatched.
    Prints [OK] on success, [FAIL] with detail on mismatch or absence.
    Column names vary by Memgraph version — .get() with fallbacks is used throughout.
    """
    try:
        result = session.run("SHOW INDEX INFO;")
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(
                record.get("index type")
                or record.get("type")
                or record.get("Type")
                or ""
            )
            if label == expected_label and prop == expected_property and "vector" in index_type.lower():
                print(
                    f"  [OK] Vector index validated: {index_name} on "
                    f"{expected_label}({expected_property})"
                )
                return True

        print(
            f"  [FAIL] Vector index '{index_name}' not found in SHOW INDEX INFO "
            f"(expected {expected_label}({expected_property}) type=vector)"
        )
        return False

    except Exception as exc:
        print(f"  [FAIL] Could not validate index '{index_name}': {exc}")
        return False


def create_vector_index(
    session,
    index_name: str,
    label: str,
    prop: str,
    dim: int,
    capacity: int,
) -> None:
    """Create a named vector index on :{label}({prop}).

    Silently skips if the index already exists.
    """
    query = (
        f'CREATE VECTOR INDEX {index_name} ON :{label}({prop}) '
        f'WITH CONFIG {{"dimension": {dim}, "capacity": {capacity}, "metric": "cos"}};'
    )
    try:
        session.run(query)
        print(
            f"  [OK] Vector index created: {index_name} on {label}({prop}) "
            f"dim={dim} capacity={capacity} metric=cos"
        )
    except ClientError as exc:
        if "already exists" in str(exc).lower():
            print(f"  [SKIP] Vector index already exists: {index_name} on {label}({prop})")
        else:
            raise


_LEGACY_MEM_CAPACITY = 1000


def _check_mem_embedding_idx_capacity(session) -> None:
    """Warn if mem_embedding_idx still has the legacy capacity=1000."""
    try:
        result = session.run("SHOW INDEX INFO;")
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(
                record.get("index type")
                or record.get("type")
                or record.get("Type")
                or ""
            )
            if label == "Memory" and prop == "embedding" and "vector" in index_type.lower():
                row = dict(record)
                capacity = (
                    row.get("capacity")
                    or row.get("Capacity")
                    or (row.get("options") or {}).get("capacity")
                )
                if capacity is not None and int(capacity) == _LEGACY_MEM_CAPACITY:
                    print(
                        f"\n  [WARN] mem_embedding_idx still has capacity={_LEGACY_MEM_CAPACITY}. "
                        f"Vector indexes cannot be altered in-place.\n"
                        f"  To increase capacity:\n"
                        f"    1. Update MEMORY_INDEX_CAPACITY in .env\n"
                        f"    2. DROP VECTOR INDEX mem_embedding_idx;\n"
                        f"    3. Re-run: python scripts/init_schema.py"
                    )
                else:
                    print(
                        f"  [OK] mem_embedding_idx capacity={capacity} "
                        f"(no action required)"
                    )
                return
        print("  [INFO] mem_embedding_idx not found in SHOW INDEX INFO — skipping capacity check.")
    except Exception as exc:
        print(f"  [WARN] Could not check mem_embedding_idx capacity: {exc}")


def main() -> int:
    settings = Settings()
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    print(f"Connecting to Memgraph at {uri} ...")

    try:
        driver = get_driver(settings)
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Could not connect to Memgraph: {exc}")
        return 1

    print(f"Loading knowledge embedding model '{settings.knowledge_embedding_model}' to determine vector dimension ...")
    try:
        dim = get_embedding_dimension(settings.knowledge_embedding_model)
        print(f"  Embedding dimension: {dim}")
    except Exception as exc:
        driver.close()
        print(f"[FAIL] Could not load knowledge embedding model '{settings.knowledge_embedding_model}': {exc}")
        return 1

    success = True
    try:
        with driver.session() as session:
            # --- Uniqueness constraints ---
            print("\nCreating uniqueness constraints ...")
            for label, prop in KNOWLEDGE_CONSTRAINTS:
                try:
                    create_constraint(session, label, prop)
                except Exception as exc:
                    print(f"  [FAIL] Constraint {label}.{prop}: {exc}")
                    success = False

            # --- ctrl_embedding_idx ---
            print("\nCreating vector index: ctrl_embedding_idx ...")
            try:
                create_vector_index(
                    session,
                    index_name="ctrl_embedding_idx",
                    label="Control",
                    prop="embedding",
                    dim=dim,
                    capacity=settings.ctrl_index_capacity,
                )
            except Exception as exc:
                print(f"  [FAIL] ctrl_embedding_idx: {exc}")
                success = False

            print("Validating vector index: ctrl_embedding_idx ...")
            if not validate_vector_index(session, "ctrl_embedding_idx", "Control", "embedding"):
                success = False

            # --- chunk_embedding_idx ---
            print("\nCreating vector index: chunk_embedding_idx ...")
            try:
                create_vector_index(
                    session,
                    index_name="chunk_embedding_idx",
                    label="Chunk",
                    prop="embedding",
                    dim=dim,
                    capacity=settings.chunk_index_capacity,
                )
            except Exception as exc:
                print(f"  [FAIL] chunk_embedding_idx: {exc}")
                success = False

            print("Validating vector index: chunk_embedding_idx ...")
            if not validate_vector_index(session, "chunk_embedding_idx", "Chunk", "embedding"):
                success = False

            # --- Existing mem_embedding_idx capacity advisory ---
            print("\nChecking mem_embedding_idx capacity ...")
            _check_mem_embedding_idx_capacity(session)

    except Exception as exc:
        print(f"[FAIL] Session error: {exc}")
        return 1
    finally:
        driver.close()

    if success:
        print("\nKnowledge layer schema initialisation complete.")
        return 0
    else:
        print("\nKnowledge layer schema initialisation finished with errors.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
