"""
smoke_test.py – Insert a test Memory node and verify vector search works.

Requires:
  - Memgraph running with schema initialised (run init_schema.py first)
  - memory_service/embeddings.py present (WP-003)

Run from the project root:
    python scripts/smoke_test.py

Exits 0 on SMOKE TEST PASSED, 1 on SMOKE TEST FAILED.
"""

import sys
from datetime import datetime, timezone

import neo4j
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError
from pydantic_settings import BaseSettings, SettingsConfigDict

TEST_NODE_ID = "smoke-test-001"
TEST_TEXT = "smoke test memory"
DISTANCE_THRESHOLD = 0.01


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


def get_driver(settings: Settings) -> neo4j.Driver:
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    if settings.memgraph_user or settings.memgraph_password:
        auth = (settings.memgraph_user, settings.memgraph_password)
    else:
        auth = None
    return GraphDatabase.driver(uri, auth=auth)


def main() -> int:
    settings = Settings()
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    print(f"Connecting to Memgraph at {uri} ...")

    # Step 1: Verify Memgraph is reachable (fast-fail before slow model load)
    try:
        driver = get_driver(settings)
        driver.verify_connectivity()
    except Exception as exc:
        print(f"SMOKE TEST FAILED: Could not connect to Memgraph — {exc}")
        return 1

    # Step 2: Generate embedding
    print(f"Generating embedding for: '{TEST_TEXT}' ...")
    try:
        from memory_service.embeddings import get_embedding
        embedding = get_embedding(TEST_TEXT)
    except ImportError as exc:
        driver.close()
        print(f"SMOKE TEST FAILED: Could not import get_embedding — {exc}")
        print("  (WP-003 must be completed before the smoke test can run)")
        return 1
    except Exception as exc:
        driver.close()
        print(f"SMOKE TEST FAILED: Error generating embedding — {exc}")
        return 1

    print(f"  Embedding dimension: {len(embedding)}")

    try:
        with driver.session() as session:
            # Cleanup any leftover node from a previous failed run
            session.run(
                "MATCH (m:Memory {id: $id}) DETACH DELETE m",
                id=TEST_NODE_ID,
            )

            # Step 3: Insert test Memory node
            print(f"Inserting test Memory node (id={TEST_NODE_ID}) ...")
            created_at = datetime.now(tz=timezone.utc).isoformat()
            session.run(
                """
                CREATE (m:Memory {
                    id: $id,
                    text: $text,
                    type: $type,
                    tags: $tags,
                    importance: $importance,
                    created_at: $created_at,
                    embedding: $embedding
                })
                """,
                id=TEST_NODE_ID,
                text=TEST_TEXT,
                type="fact",
                tags=[],
                importance=3,
                created_at=created_at,
                embedding=embedding,
            )
            print("  Node inserted.")

            # Step 3: Run vector search
            print("Running vector search ...")
            result = session.run(
                """
                CALL vector_search.search("Memory", "embedding", 1, $query_vec)
                YIELD node, distance
                RETURN node.id AS id, distance
                """,
                query_vec=embedding,
            )
            records = result.data()

            # Step 4: Assert results
            if not records:
                _cleanup(session)
                print("SMOKE TEST FAILED: vector_search returned no results")
                return 1

            returned_id = records[0]["id"]
            distance = records[0]["distance"]
            print(f"  Returned id={returned_id}, distance={distance}")

            if returned_id != TEST_NODE_ID:
                _cleanup(session)
                print(
                    f"SMOKE TEST FAILED: expected id={TEST_NODE_ID}, got id={returned_id}"
                )
                return 1

            if distance >= DISTANCE_THRESHOLD:
                _cleanup(session)
                print(
                    f"SMOKE TEST FAILED: distance={distance} is not < {DISTANCE_THRESHOLD}"
                )
                return 1

            # Step 5: Cleanup
            _cleanup(session)

    except Exception as exc:
        print(f"SMOKE TEST FAILED: Unexpected error — {exc}")
        return 1
    finally:
        driver.close()

    print("SMOKE TEST PASSED")
    return 0


def _cleanup(session) -> None:
    """Remove the test node."""
    try:
        session.run(
            "MATCH (m:Memory {id: $id}) DETACH DELETE m",
            id=TEST_NODE_ID,
        )
        print("  Test node cleaned up.")
    except Exception as exc:
        print(f"  Warning: cleanup failed — {exc}")


if __name__ == "__main__":
    sys.exit(main())
