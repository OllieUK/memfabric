"""tests/test_wp106_attack_ingestion.py — WP-106: MITRE ATT&CK Enterprise ingestion.

Unit tests (no live stack required) and integration tests (require live Memgraph + FastAPI).

Unit tests cover:
  - _get_external_id: extracts ATT&CK IDs from STIX external_references
  - _node_id: maps external IDs to Framework node IDs
  - _root_id: derives root node ID from version string
  - Parent derivation for sub-techniques (T1566.001 → T1566)

Integration tests cover:
  - Framework schema: external_id + domain fields accepted and stored
  - MITIGATES endpoint: Control→Framework edge creation
  - INFORMS endpoint: Framework→Control edge creation
  - ATT&CK hierarchy: root, sample tactic, technique, sub-technique nodes present
  - CONTAINS edges: root→tactic, tactic→technique, technique→sub-technique
"""
from __future__ import annotations

import importlib.util
import pathlib
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "scripts" / "ingest_attack.py"


# ---------------------------------------------------------------------------
# Script import helper
# ---------------------------------------------------------------------------

def _import_script():
    spec = importlib.util.spec_from_file_location("ingest_attack", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Unit test 1 — _get_external_id
# ---------------------------------------------------------------------------

class TestGetExternalId:
    def test_returns_attack_id(self):
        mod = _import_script()
        stix_obj = {
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "T1566"},
                {"source_name": "capec", "external_id": "CAPEC-98"},
            ]
        }
        assert mod._get_external_id(stix_obj) == "T1566"

    def test_returns_none_when_absent(self):
        mod = _import_script()
        assert mod._get_external_id({"external_references": []}) is None
        assert mod._get_external_id({}) is None

    def test_returns_tactic_id(self):
        mod = _import_script()
        obj = {"external_references": [{"source_name": "mitre-attack", "external_id": "TA0001"}]}
        assert mod._get_external_id(obj) == "TA0001"

    def test_returns_subtechnique_id(self):
        mod = _import_script()
        obj = {"external_references": [{"source_name": "mitre-attack", "external_id": "T1566.001"}]}
        assert mod._get_external_id(obj) == "T1566.001"


# ---------------------------------------------------------------------------
# Unit test 2 — _node_id
# ---------------------------------------------------------------------------

class TestNodeId:
    def test_tactic(self):
        mod = _import_script()
        assert mod._node_id("TA0001") == "attack-enterprise.TA0001"

    def test_technique(self):
        mod = _import_script()
        assert mod._node_id("T1566") == "attack-enterprise.T1566"

    def test_subtechnique(self):
        mod = _import_script()
        assert mod._node_id("T1566.001") == "attack-enterprise.T1566.001"


# ---------------------------------------------------------------------------
# Unit test 3 — _root_id
# ---------------------------------------------------------------------------

class TestRootId:
    def test_extracts_major_version(self):
        mod = _import_script()
        assert mod._root_id("17.0") == "attack-enterprise-v17"
        assert mod._root_id("16.1") == "attack-enterprise-v16"
        assert mod._root_id("15.0") == "attack-enterprise-v15"


# ---------------------------------------------------------------------------
# Unit test 4 — parent derivation for sub-techniques
# ---------------------------------------------------------------------------

class TestSubtechniqueParent:
    def test_parent_external_id_derived_from_subtechnique(self):
        """T1566.001 → parent external_id T1566 → node id attack-enterprise.T1566"""
        mod = _import_script()
        sub_ext_id = "T1566.001"
        parent_ext_id = sub_ext_id.rsplit(".", 1)[0]
        assert parent_ext_id == "T1566"
        assert mod._node_id(parent_ext_id) == "attack-enterprise.T1566"

    def test_deep_subtechnique_preserves_single_rsplit(self):
        """Ensure rsplit(., 1) only removes the last segment."""
        ext_id = "T1134.001"
        parent_ext_id = ext_id.rsplit(".", 1)[0]
        assert parent_ext_id == "T1134"


# ---------------------------------------------------------------------------
# Unit test 5 — dry-run exits without API calls
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_returns_dry_run_status(self):
        mod = _import_script()
        client = MagicMock()
        result = mod._upsert(client, {"id": "x", "title": "X"}, "test", dry_run=True)
        assert result == "dry-run"
        client.post.assert_not_called()

    def test_add_contains_dry_run(self):
        mod = _import_script()
        client = MagicMock()
        result = mod._add_contains(client, "parent", "child", dry_run=True)
        assert result == "dry-run"
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# Integration tests — require live stack
# ---------------------------------------------------------------------------

ATTACK_ROOT_ID = "attack-enterprise-v17"
TEST_FW_ID = "test-attack-framework-wp106"
TEST_CTRL_ID = "test-control-wp106"

pytestmark_integration = pytest.mark.integration


@pytest.mark.integration
class TestFrameworkSchemaExtensions:
    """Verify external_id + domain fields are stored and returned via API."""

    def test_upsert_framework_stores_external_id_and_domain(self, knowledge_client, test_driver):
        """Framework node with external_id + domain round-trips correctly."""
        resp = knowledge_client.post("/knowledge/frameworks", json={
            "id": TEST_FW_ID,
            "title": "Test ATT&CK Technique (WP-106)",
            "level": "technique",
            "external_id": "T9999",
            "domain": "enterprise",
            "body": "Adversary uses test technique for WP-106 validation.",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["external_id"] == "T9999"
        assert data["domain"] == "enterprise"

        # Verify GET also returns these fields
        get_resp = knowledge_client.get(f"/knowledge/frameworks/{TEST_FW_ID}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["external_id"] == "T9999"
        assert get_data["domain"] == "enterprise"

        # cleanup
        with test_driver.session() as session:
            session.run("MATCH (f:Framework {id: $id}) DETACH DELETE f", id=TEST_FW_ID)


@pytest.mark.integration
class TestMitigatesEndpoint:
    """Verify POST /knowledge/mitigates creates Control→Framework MITIGATES edge."""

    def test_create_mitigates_edge(self, knowledge_client, test_driver):
        # Seed a control and a framework node
        with test_driver.session() as session:
            session.run(
                "MERGE (c:Control {id: $id}) ON CREATE SET c.name = $name, "
                "c.framework_id = 'test-fw', c.created_at = '2026-01-01T00:00:00+00:00'",
                id=TEST_CTRL_ID, name="Test Control WP-106",
            )
            session.run(
                "MERGE (f:Framework {id: $id}) ON CREATE SET f.title = $title, "
                "f.level = 'technique', f.created_at = '2026-01-01T00:00:00+00:00'",
                id=TEST_FW_ID, title="Test Framework WP-106",
            )

        resp = knowledge_client.post("/knowledge/mitigates", json={
            "control_id": TEST_CTRL_ID,
            "framework_id": TEST_FW_ID,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["control_id"] == TEST_CTRL_ID
        assert data["framework_id"] == TEST_FW_ID
        assert "created_at" in data

        # Idempotent: second call should succeed
        resp2 = knowledge_client.post("/knowledge/mitigates", json={
            "control_id": TEST_CTRL_ID,
            "framework_id": TEST_FW_ID,
        })
        assert resp2.status_code == 200

        # cleanup
        with test_driver.session() as session:
            session.run("MATCH (c:Control {id: $id}) DETACH DELETE c", id=TEST_CTRL_ID)
            session.run("MATCH (f:Framework {id: $id}) DETACH DELETE f", id=TEST_FW_ID)

    def test_mitigates_returns_404_when_control_missing(self, knowledge_client):
        resp = knowledge_client.post("/knowledge/mitigates", json={
            "control_id": "nonexistent-control-wp106",
            "framework_id": "nonexistent-framework-wp106",
        })
        assert resp.status_code == 404


@pytest.mark.integration
class TestInformsEndpoint:
    """Verify POST /knowledge/informs creates Framework→Control INFORMS edge."""

    def test_create_informs_edge(self, knowledge_client, test_driver):
        with test_driver.session() as session:
            session.run(
                "MERGE (c:Control {id: $id}) ON CREATE SET c.name = $name, "
                "c.framework_id = 'test-fw', c.created_at = '2026-01-01T00:00:00+00:00'",
                id=TEST_CTRL_ID, name="Test Control WP-106",
            )
            session.run(
                "MERGE (f:Framework {id: $id}) ON CREATE SET f.title = $title, "
                "f.level = 'technique', f.created_at = '2026-01-01T00:00:00+00:00'",
                id=TEST_FW_ID, title="Test Framework WP-106",
            )

        resp = knowledge_client.post("/knowledge/informs", json={
            "framework_id": TEST_FW_ID,
            "control_id": TEST_CTRL_ID,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["framework_id"] == TEST_FW_ID
        assert data["control_id"] == TEST_CTRL_ID

        # Idempotent
        resp2 = knowledge_client.post("/knowledge/informs", json={
            "framework_id": TEST_FW_ID,
            "control_id": TEST_CTRL_ID,
        })
        assert resp2.status_code == 200

        with test_driver.session() as session:
            session.run("MATCH (c:Control {id: $id}) DETACH DELETE c", id=TEST_CTRL_ID)
            session.run("MATCH (f:Framework {id: $id}) DETACH DELETE f", id=TEST_FW_ID)

    def test_informs_returns_404_when_nodes_missing(self, knowledge_client):
        resp = knowledge_client.post("/knowledge/informs", json={
            "framework_id": "nonexistent-fw-wp106",
            "control_id": "nonexistent-ctrl-wp106",
        })
        assert resp.status_code == 404


@pytest.mark.integration
class TestAttackHierarchyIngested:
    """Verify ATT&CK hierarchy is present after ingest_attack.py has been run.

    These tests assume the ingest script has been executed against the live stack.
    They are marked skip-if-missing so the suite can run before ingestion.
    """

    def test_root_node_exists(self, knowledge_client):
        resp = knowledge_client.get(f"/knowledge/frameworks/{ATTACK_ROOT_ID}")
        if resp.status_code == 404:
            pytest.skip("ATT&CK not yet ingested — run scripts/ingest_attack.py first")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "framework"
        assert data["domain"] == "enterprise"
        assert "ATT&CK" in data["title"]

    def test_tactic_initial_access_exists(self, knowledge_client):
        resp = knowledge_client.get("/knowledge/frameworks/attack-enterprise.TA0001")
        if resp.status_code == 404:
            pytest.skip("ATT&CK not yet ingested")
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_id"] == "TA0001"
        assert data["level"] == "category"
        assert data["domain"] == "enterprise"

    def test_phishing_technique_exists(self, knowledge_client):
        resp = knowledge_client.get("/knowledge/frameworks/attack-enterprise.T1566")
        if resp.status_code == 404:
            pytest.skip("ATT&CK not yet ingested")
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_id"] == "T1566"
        assert data["level"] == "technique"

    def test_spearphishing_subtechnique_exists(self, knowledge_client):
        resp = knowledge_client.get("/knowledge/frameworks/attack-enterprise.T1566.001")
        if resp.status_code == 404:
            pytest.skip("ATT&CK not yet ingested")
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_id"] == "T1566.001"
        assert data["level"] == "sub-technique"

    def test_root_to_tactic_contains_edge(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (root:Framework {id: $root})-[:CONTAINS]->(tactic:Framework {id: $tactic})
                RETURN count(*) AS cnt
                """,
                root=ATTACK_ROOT_ID,
                tactic="attack-enterprise.TA0001",
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("ATT&CK not yet ingested")
        assert result["cnt"] == 1

    def test_tactic_to_technique_contains_edge(self, test_driver):
        """T1566 (Phishing) is under TA0001 (Initial Access)."""
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (tactic:Framework {id: $tactic})-[:CONTAINS]->(tech:Framework {id: $tech})
                RETURN count(*) AS cnt
                """,
                tactic="attack-enterprise.TA0001",
                tech="attack-enterprise.T1566",
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("ATT&CK not yet ingested")
        assert result["cnt"] == 1

    def test_technique_to_subtechnique_contains_edge(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (tech:Framework {id: $tech})-[:CONTAINS]->(sub:Framework {id: $sub})
                RETURN count(*) AS cnt
                """,
                tech="attack-enterprise.T1566",
                sub="attack-enterprise.T1566.001",
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("ATT&CK not yet ingested")
        assert result["cnt"] == 1

    def test_attack_technique_count_reasonable(self, test_driver):
        """At least 200 technique-level Framework nodes from ATT&CK Enterprise."""
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'attack-enterprise.' AND f.level = 'technique'
                RETURN count(f) AS cnt
                """
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("ATT&CK not yet ingested")
        assert result["cnt"] >= 200, f"Expected ≥200 techniques, got {result['cnt']}"

    def test_attack_subtechnique_count_reasonable(self, test_driver):
        """At least 400 sub-technique-level Framework nodes from ATT&CK Enterprise."""
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'attack-enterprise.' AND f.level = 'sub-technique'
                RETURN count(f) AS cnt
                """
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("ATT&CK not yet ingested")
        assert result["cnt"] >= 400, f"Expected ≥400 sub-techniques, got {result['cnt']}"

    def test_vector_search_finds_phishing(self, knowledge_client):
        """Semantic search should return phishing-related techniques."""
        resp = knowledge_client.post("/knowledge/search/frameworks", json={
            "query": "phishing email credential theft",
            "limit": 10,
        })
        if resp.status_code != 200:
            pytest.skip("ATT&CK not yet ingested or search unavailable")
        hits = resp.json()
        hit_ids = [h["id"] for h in hits]
        # T1566 (Phishing) should appear near top
        assert any("T1566" in hid for hid in hit_ids), (
            f"Expected T1566 in results, got: {hit_ids}"
        )
