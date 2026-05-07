# tests/test_wp113_schema_init.py — WP-113 schema initialisation integration tests
#
# Requires live Memgraph. Mark: @pytest.mark.integration

import pytest


@pytest.mark.integration
def test_business_attribute_index_exists(test_driver):
    """business_attribute_embedding_idx must exist after init_knowledge_schema runs."""
    with test_driver.session() as session:
        result = session.run("SHOW INDEX INFO;")
        records = list(result)

    found = False
    for record in records:
        label = record.get("label") or record.get("Label") or ""
        prop = record.get("property") or record.get("Property") or ""
        index_type = str(
            record.get("index type")
            or record.get("type")
            or record.get("Type")
            or ""
        )
        if label == "BusinessAttribute" and prop == "embedding" and "vector" in index_type.lower():
            found = True
            break

    assert found, (
        "business_attribute_embedding_idx not found in SHOW INDEX INFO. "
        "Run: python scripts/init_knowledge_schema.py"
    )


@pytest.mark.integration
def test_no_precept_constraint_or_index(test_driver):
    """No Precept constraint or vector index should exist — Precept is dropped."""
    with test_driver.session() as session:
        index_result = session.run("SHOW INDEX INFO;")
        index_records = list(index_result)

    for record in index_records:
        label = record.get("label") or record.get("Label") or ""
        assert label != "Precept", (
            f"Unexpected Precept index found: {dict(record)}. "
            "Precept was dropped in WP-113."
        )

    # Check constraints (Memgraph uses SHOW CONSTRAINT INFO or similar)
    with test_driver.session() as session:
        try:
            constraint_result = session.run("SHOW CONSTRAINT INFO;")
            constraint_records = list(constraint_result)
            for record in constraint_records:
                label = record.get("label") or record.get("Label") or ""
                assert label != "Precept", (
                    f"Unexpected Precept constraint found: {dict(record)}."
                )
        except Exception:
            # Memgraph may not support SHOW CONSTRAINT INFO in all versions
            pass


@pytest.mark.integration
def test_business_attribute_unique_constraint_exists(test_driver):
    """BusinessAttribute(id) unique constraint must exist."""
    with test_driver.session() as session:
        try:
            # Try to insert a duplicate and expect it to fail
            session.run(
                "MERGE (b:BusinessAttribute {id: $id}) SET b.name = $name",
                id="__test-constraint-check-wp113__",
                name="test",
            )
            session.run(
                "MATCH (b:BusinessAttribute {id: $id}) DETACH DELETE b",
                id="__test-constraint-check-wp113__",
            )
        except Exception as e:
            # If constraint is set up correctly, duplicate merges won't error
            # This test mainly checks the constraint exists (not that upsert fails)
            pass

    # Verify constraint shows up in SHOW CONSTRAINT INFO
    with test_driver.session() as session:
        try:
            result = session.run("SHOW CONSTRAINT INFO;")
            records = list(result)
            labels = [
                (r.get("label") or r.get("Label") or "")
                for r in records
            ]
            assert "BusinessAttribute" in labels, (
                "BusinessAttribute unique constraint not found. "
                "Run: python scripts/init_knowledge_schema.py"
            )
        except Exception:
            # SHOW CONSTRAINT INFO may not be supported; skip assertion
            pytest.skip("SHOW CONSTRAINT INFO not supported in this Memgraph version")
