# tests/conftest.py
#
# Shared pytest fixtures and graph helpers for the Graph-Memory Fabric test suite.
#
# Test hygiene rules (enforced by policy, not always by code):
#   1. Every memory node created by a test MUST include tags=["test"] (or TEST_TAG).
#   2. Every test that creates graph nodes MUST clean them up in a finally block or
#      pytest fixture teardown.
#   3. The session-scoped `cleanup_all_test_nodes` autouse fixture acts as a safety
#      net at end-of-suite, deleting any nodes carrying TEST_TAG that slipped through.

# Standard tag injected into every test-created memory.
TEST_TAG = "test"

import importlib
import os

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from memory_service.config import get_driver, settings
from memory_service.main import app


@pytest.fixture(scope="session")
def test_driver():
    driver = get_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception:
        pytest.skip("Memgraph not reachable — skipping integration tests")
    yield driver
    # Safety-net: delete any test-tagged nodes that tests failed to clean up
    _cleanup_by_tag(driver, TEST_TAG)
    driver.close()


def _cleanup_by_tag(driver, tag: str) -> int:
    """Delete all Memory nodes (and orphaned Agent/Project nodes) carrying *tag*.

    Returns the number of Memory nodes deleted.  Called automatically at
    session teardown; can also be called directly in tests that need it.
    """
    with driver.session() as session:
        result = session.run(
            "MATCH (m:Memory) WHERE $tag IN m.tags RETURN m.id AS id",
            tag=tag,
        )
        ids = [r["id"] for r in result]
    with driver.session() as session:
        for mid in ids:
            session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
    # Clean up orphaned test Agent/Project nodes (those with 'test' in their id)
    with driver.session() as session:
        session.run("""
            MATCH (n)
            WHERE (n:Agent OR n:Project)
              AND (toLower(n.id) CONTAINS 'test-' OR toLower(n.id) STARTS WITH 'test')
            DETACH DELETE n
        """)
    return len(ids)


@pytest.fixture
def client(test_driver):
    app.state.driver = test_driver
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def knowledge_client(test_driver):
    """TestClient with ENABLE_KNOWLEDGE_LAYER=true, wired to the live test_driver.

    Reloads config and main so that the feature flag is picked up even if
    conftest imported the app before the flag was set.

    API_KEYS is cleared so integration tests run unauthenticated regardless
    of what the local .env configures — tests are not meant to prove auth.
    """
    prev_keys = os.environ.get("API_KEYS")
    os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"
    os.environ["API_KEYS"] = "[]"
    try:
        import memory_service.config as cfg_mod
        import memory_service.main as main_mod
        importlib.reload(cfg_mod)
        importlib.reload(main_mod)
        main_mod.app.state.driver = test_driver
        with TestClient(main_mod.app, raise_server_exceptions=True) as c:
            yield c
    finally:
        if prev_keys is None:
            os.environ.pop("API_KEYS", None)
        else:
            os.environ["API_KEYS"] = prev_keys


# ---------------------------------------------------------------------------
# Graph inspection helpers (used across multiple test modules)
# ---------------------------------------------------------------------------

def make_mock_driver():
    """Return (driver_mock, session_mock) configured for use as a context manager.

    Used in unit tests that exercise FastAPI handlers without a live Memgraph.
    """
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = lambda s: mock_session
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    return mock_driver, mock_session


def node_exists(driver, label: str, node_id: str) -> bool:
    with driver.session() as session:
        result = session.run(
            f"MATCH (n:{label} {{id: $id}}) RETURN n.id AS id",
            id=node_id,
        )
        return result.single() is not None


def edge_exists(driver, from_id: str, rel_type: str, to_id: str) -> bool:
    with driver.session() as session:
        result = session.run(
            f"MATCH (a {{id: $from_id}})-[r:{rel_type}]->(b {{id: $to_id}}) RETURN r",
            from_id=from_id,
            to_id=to_id,
        )
        return result.single() is not None


def get_memory_node(driver, memory_id: str) -> dict | None:
    with driver.session() as session:
        result = session.run(
            "MATCH (m:Memory {id: $id}) RETURN m",
            id=memory_id,
        )
        record = result.single()
        if record is None:
            return None
        return dict(record["m"])


def cleanup_nodes(driver, *memory_ids, extra_ids: dict[str, str | list[str]] | None = None) -> None:
    """Delete Memory nodes by id and any extra labelled nodes.

    Args:
        driver: neo4j Driver
        *memory_ids: Memory node ids to DETACH DELETE
        extra_ids: mapping of {label: id_or_ids} for additional nodes to delete.
            Value can be a single str id or a list of str ids.
    """
    with driver.session() as session:
        for mid in memory_ids:
            session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
        for label, nid in (extra_ids or {}).items():
            ids = [nid] if isinstance(nid, str) else nid
            for single_id in ids:
                session.run(f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n", id=single_id)


def count_edges(driver, from_id: str, rel_type: str, to_id: str) -> int:
    with driver.session() as session:
        result = session.run(
            f"MATCH (a {{id: $a}})-[r:{rel_type}]->(b {{id: $b}}) RETURN count(r) AS c",
            a=from_id, b=to_id,
        )
        return result.single()["c"]


def get_edge_props(driver, from_id: str, rel_type: str, to_id: str) -> dict:
    with driver.session() as session:
        result = session.run(
            f"MATCH (a {{id: $a}})-[r:{rel_type}]->(b {{id: $b}}) RETURN r",
            a=from_id, b=to_id,
        )
        record = result.single()
        return dict(record["r"]) if record else {}
