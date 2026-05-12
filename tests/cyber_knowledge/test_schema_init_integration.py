"""WP-174 integration tests — schema-init lands ADR-006 constraints + indexes.

Require a live Memgraph. Marked with @pytest.mark.integration so they only run
under `pytest -m integration` (per CLAUDE.md DoD gate 3).
"""

import pytest
from neo4j.exceptions import ClientError

from cyber_knowledge.ingest.schema_init import KNOWLEDGE_CONSTRAINTS, main as init_main

pytestmark = pytest.mark.integration


NEW_CONSTRAINTS = frozenset(KNOWLEDGE_CONSTRAINTS[-5:])
EXISTING_CONSTRAINTS = frozenset(KNOWLEDGE_CONSTRAINTS[:-5])


@pytest.fixture(scope="module")
def initialised_schema(test_driver):
    assert init_main() == 0, "schema_init returned non-zero exit"
    return test_driver


def _get_constraints(driver) -> set[tuple[str, str]]:
    with driver.session() as session:
        result = session.run("SHOW CONSTRAINT INFO;")
        constraints: set[tuple[str, str]] = set()
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            ctype = str(
                record.get("constraint type")
                or record.get("type")
                or record.get("Type")
                or ""
            )
            props = (
                record.get("properties")
                or record.get("property")
                or record.get("Property")
                or []
            )
            if isinstance(props, str):
                props = [props]
            if "unique" in ctype.lower() and label:
                for prop in props:
                    constraints.add((label, prop))
        return constraints


def _get_vector_indexes(driver) -> dict[str, str]:
    """Return {label: property} for all vector indexes."""
    with driver.session() as session:
        result = session.run("SHOW INDEX INFO;")
        indexes: dict[str, str] = {}
        for record in result:
            label = record.get("label") or record.get("Label") or ""
            prop = record.get("property") or record.get("Property") or ""
            index_type = str(
                record.get("index type")
                or record.get("type")
                or record.get("Type")
                or ""
            )
            if "vector" in index_type.lower() and label:
                indexes[label] = prop
        return indexes


def test_new_constraints_created(initialised_schema):
    constraints = _get_constraints(initialised_schema)
    missing = NEW_CONSTRAINTS - constraints
    assert not missing, f"Missing new constraints: {missing}"


def test_new_vector_indexes_created(initialised_schema):
    indexes = _get_vector_indexes(initialised_schema)
    assert indexes.get("Policy") == "embedding", "policy_embedding_idx missing"
    assert indexes.get("PolicySection") == "embedding", (
        "policy_section_embedding_idx missing"
    )


def test_schema_init_idempotent(initialised_schema):
    # initialised_schema ran init_main() once; rerunning must still exit 0.
    assert init_main() == 0


def test_uniqueness_enforced(initialised_schema):
    for label, prop in NEW_CONSTRAINTS:
        node_id = f"test-wp174-{label.lower()}-uniq"
        try:
            with initialised_schema.session() as session:
                session.run(f"CREATE (n:{label} {{{prop}: $id}})", id=node_id)
                with pytest.raises(ClientError):
                    session.run(
                        f"CREATE (n:{label} {{{prop}: $id}})", id=node_id
                    )
        finally:
            with initialised_schema.session() as session:
                session.run(
                    f"MATCH (n:{label} {{{prop}: $id}}) DETACH DELETE n",
                    id=node_id,
                )


def test_existing_constraints_intact(initialised_schema):
    constraints = _get_constraints(initialised_schema)
    missing = EXISTING_CONSTRAINTS - constraints
    assert not missing, f"Pre-WP-174 constraints missing: {missing}"


def test_no_data_inserted(initialised_schema):
    with initialised_schema.session() as session:
        for label in {label for label, _ in NEW_CONSTRAINTS}:
            result = session.run(f"MATCH (n:{label}) RETURN count(n) AS c")
            count = result.single()["c"]
            assert count == 0, f"Label {label} should have 0 nodes, has {count}"
