"""
init_schema.py – Create Memgraph constraints and vector index.

Run once after `docker compose up`, before first use:
    python scripts/init_schema.py

Idempotent: re-running on an already-initialised DB will not error.
"""

import sys

import neo4j
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    memgraph_user: str = ""
    memgraph_password: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    embedding_model: str = "all-MiniLM-L6-v2"
    agent_id: str = "claude-code"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Uniqueness constraints: (label, property)
UNIQUENESS_CONSTRAINTS = [
    ("Memory", "id"),
    ("Strand", "id"),
    ("Agent", "id"),
    ("Person", "id"),
    ("Project", "id"),
]

# Vector index: dimension=384 for all-MiniLM-L6-v2; metric=cos (cosine)
VECTOR_INDEX_QUERY = (
    'CREATE VECTOR INDEX ON :Memory(embedding) '
    'OPTIONS {dimension: 384, capacity: 1000, metric: "cos"};'
)


def get_driver(settings: Settings) -> neo4j.Driver:
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    if settings.memgraph_user or settings.memgraph_password:
        auth = (settings.memgraph_user, settings.memgraph_password)
    else:
        auth = None
    return GraphDatabase.driver(uri, auth=auth)


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


def create_vector_index(session) -> None:
    try:
        session.run(VECTOR_INDEX_QUERY)
        print("  [OK] Vector index created: Memory(embedding) dim=384 metric=cos")
    except ClientError as exc:
        if "already exists" in str(exc).lower():
            print("  [SKIP] Vector index already exists: Memory(embedding)")
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
            try:
                create_vector_index(session)
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
