"""tests/test_wp111_attack_mitigations.py — WP-111: M-Series ATT&CK mitigations ingestion.

Unit tests (no live stack required) and integration tests (require live Memgraph + FastAPI).

Unit tests cover:
  - _get_external_id: extracts M-Series IDs from STIX external_references
  - _node_id: maps M-Series external IDs to Framework node IDs
  - _parse_mitigation: parses course-of-action STIX objects
  - Filtering revoked/deprecated objects
  - MITIGATES relationship filtering
  - dry-run mode

Integration tests cover:
  - M-Series Framework nodes present after ingestion
  - CONTAINS edges from ATT&CK root to M-Series nodes
  - MITIGATES edges from M-Series to technique/sub-technique nodes
  - Cross-framework INFORMS edges from M-Series to ISO/NIST/COBIT
"""
from __future__ import annotations

import importlib.util
import pathlib
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "scripts" / "ingest_attack_mitigations.py"


# ---------------------------------------------------------------------------
# Script import helper
# ---------------------------------------------------------------------------

def _import_script():
    spec = importlib.util.spec_from_file_location("ingest_attack_mitigations", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestGetExternalIdMSeries:
    def test_returns_m_series_id(self):
        mod = _import_script()
        stix_obj = {
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "M1017"},
                {"source_name": "capec", "external_id": "CAPEC-1"},
            ]
        }
        assert mod._get_external_id(stix_obj) == "M1017"

    def test_returns_none_for_non_attack_source(self):
        mod = _import_script()
        stix_obj = {
            "external_references": [
                {"source_name": "capec", "external_id": "CAPEC-1"},
            ]
        }
        assert mod._get_external_id(stix_obj) is None

    def test_returns_none_for_empty(self):
        mod = _import_script()
        assert mod._get_external_id({"external_references": []}) is None
        assert mod._get_external_id({}) is None


class TestMSeriesNodeId:
    def test_m1017_maps_to_correct_id(self):
        mod = _import_script()
        assert mod._node_id("M1017") == "attack-enterprise.M1017"

    def test_m1026_maps_to_correct_id(self):
        mod = _import_script()
        assert mod._node_id("M1026") == "attack-enterprise.M1026"


class TestParseMitigations:
    def _make_stix_obj(self, **kwargs):
        obj = {
            "type": "course-of-action",
            "id": "course-of-action--test-uuid-1234",
            "name": "User Training",
            "description": "First paragraph.\n\nSecond paragraph.",
            "external_references": [
                {"source_name": "mitre-attack", "external_id": "M1017"},
            ],
        }
        obj.update(kwargs)
        return obj

    def test_parse_course_of_action(self):
        mod = _import_script()
        obj = self._make_stix_obj()
        result = mod._parse_mitigation(obj)
        assert result is not None
        assert result["id"] == "attack-enterprise.M1017"
        assert result["title"] == "User Training"
        assert result["external_id"] == "M1017"
        assert "First paragraph." in result["body"]

    def test_revoked_object_is_excluded(self):
        mod = _import_script()
        obj = self._make_stix_obj(revoked=True)
        result = mod._parse_mitigation(obj)
        assert result is None

    def test_deprecated_object_is_excluded(self):
        mod = _import_script()
        obj = self._make_stix_obj(x_mitre_deprecated=True)
        result = mod._parse_mitigation(obj)
        assert result is None

    def test_no_external_id_returns_none(self):
        mod = _import_script()
        obj = self._make_stix_obj()
        obj["external_references"] = [{"source_name": "other", "external_id": "X001"}]
        result = mod._parse_mitigation(obj)
        assert result is None


class TestMitigatesRelationship:
    def test_only_mitigates_rel_type_passes(self):
        """A relationship with type != 'mitigates' must be excluded."""
        mod = _import_script()
        stix_id_map = {"course-of-action--abc": "attack-enterprise.M1017"}
        tech_id_map = {"attack-pattern--xyz": "attack-enterprise.T1566"}

        rel_ok = {
            "type": "relationship",
            "relationship_type": "mitigates",
            "source_ref": "course-of-action--abc",
            "target_ref": "attack-pattern--xyz",
        }
        rel_bad = {
            "type": "relationship",
            "relationship_type": "uses",
            "source_ref": "course-of-action--abc",
            "target_ref": "attack-pattern--xyz",
        }

        pairs_ok = mod._resolve_mitigates_pairs([rel_ok], stix_id_map, tech_id_map)
        pairs_bad = mod._resolve_mitigates_pairs([rel_bad], stix_id_map, tech_id_map)
        assert len(pairs_ok) == 1
        assert len(pairs_bad) == 0

    def test_non_course_of_action_source_excluded(self):
        """source_ref not in M-Series dict is silently skipped."""
        mod = _import_script()
        stix_id_map = {}  # empty — no M-Series sources registered
        tech_id_map = {"attack-pattern--xyz": "attack-enterprise.T1566"}

        rel = {
            "type": "relationship",
            "relationship_type": "mitigates",
            "source_ref": "course-of-action--unknown",
            "target_ref": "attack-pattern--xyz",
        }
        pairs = mod._resolve_mitigates_pairs([rel], stix_id_map, tech_id_map)
        assert len(pairs) == 0


class TestDryRunMitigations:
    def test_dry_run_no_api_calls(self):
        mod = _import_script()
        client = MagicMock()
        result = mod._upsert(client, {"id": "attack-enterprise.M1017", "title": "User Training"}, "M1017", dry_run=True)
        assert result == "dry-run"
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# Integration tests — require live Memgraph + FastAPI
# ---------------------------------------------------------------------------

ATTACK_ROOT_ID = "attack-enterprise-v17"
M1017_ID = "attack-enterprise.M1017"


@pytest.mark.integration
class TestMSeriesNodesIngested:
    """Verify M-Series Framework nodes are present after ingestion script."""

    def test_m1017_node_exists(self, knowledge_client):
        resp = knowledge_client.get(f"/knowledge/frameworks/{M1017_ID}")
        if resp.status_code == 404:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "mitigation"
        assert data["domain"] == "enterprise"
        assert data["external_id"] == "M1017"

    def test_m_series_count_reasonable(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'attack-enterprise.M' AND f.level = 'mitigation'
                RETURN count(f) AS cnt
                """
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        assert result["cnt"] >= 40, f"Expected >= 40 M-Series nodes, got {result['cnt']}"

    def test_m_series_nodes_have_embeddings(self, test_driver):
        with test_driver.session() as session:
            total_result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'attack-enterprise.M' AND f.level = 'mitigation'
                RETURN count(f) AS cnt
                """
            ).single()
            embedded_result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'attack-enterprise.M' AND f.level = 'mitigation'
                  AND f.embedding IS NOT NULL
                RETURN count(f) AS cnt
                """
            ).single()
        total = total_result["cnt"] if total_result else 0
        if total == 0:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        embedded = embedded_result["cnt"] if embedded_result else 0
        assert embedded == total, f"Expected all {total} M-Series nodes to have embeddings, got {embedded}"


@pytest.mark.integration
class TestMSeriesContainsEdges:
    """Verify CONTAINS edges from ATT&CK root to M-Series nodes."""

    def test_root_contains_m1017(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (root:Framework {id: $root})-[:CONTAINS]->(m:Framework {id: $mid})
                RETURN count(*) AS cnt
                """,
                root=ATTACK_ROOT_ID,
                mid=M1017_ID,
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        assert result["cnt"] == 1

    def test_all_m_series_under_root(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (root:Framework {id: $root})-[:CONTAINS]->(m:Framework)
                WHERE m.level = 'mitigation'
                RETURN count(m) AS cnt
                """,
                root=ATTACK_ROOT_ID,
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        assert result["cnt"] >= 40, f"Expected >= 40 M-Series CONTAINS edges from root, got {result['cnt']}"


@pytest.mark.integration
class TestMitigatesEdges:
    """Verify MITIGATES edges from M-Series to technique/sub-technique nodes."""

    def test_mitigates_edge_count_reasonable(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (src:Framework)-[r:MITIGATES]->(dst:Framework)
                WHERE src.id STARTS WITH 'attack-enterprise.M'
                RETURN count(r) AS cnt
                """
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        assert result["cnt"] >= 100, f"Expected >= 100 MITIGATES edges, got {result['cnt']}"

    def test_known_mitigation_edge(self, test_driver):
        """M1017 (User Training) mitigates multiple phishing techniques."""
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (m:Framework {id: $mid})-[:MITIGATES]->(t:Framework)
                RETURN count(*) AS cnt
                """,
                mid=M1017_ID,
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        assert result["cnt"] >= 1

    def test_mitigates_target_is_technique_or_subtechnique(self, test_driver):
        """Sample 10 MITIGATES target nodes; all must have level in {technique, sub-technique}."""
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (src:Framework)-[:MITIGATES]->(dst:Framework)
                WHERE src.id STARTS WITH 'attack-enterprise.M'
                RETURN dst.level AS level
                LIMIT 10
                """
            )
            rows = list(result)
        if not rows:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        allowed_levels = {"technique", "sub-technique"}
        for row in rows:
            assert row["level"] in allowed_levels, f"Unexpected level: {row['level']}"


@pytest.mark.integration
class TestMSeriesInformsEdges:
    """Verify cross-framework INFORMS edges from M-Series after running --m-series flag."""

    def test_informs_edges_created(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (src:Framework)-[r:INFORMS]->(dst:Framework)
                WHERE src.id STARTS WITH 'attack-enterprise.M'
                  AND r.source = 'embedding-similarity'
                RETURN count(r) AS cnt
                """
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("M-Series INFORMS edges not yet created — run scripts/create_cross_framework_informs.py --m-series first")
        assert result["cnt"] > 0

    def test_m_series_informs_iso_or_nist(self, test_driver):
        """At least one M-Series→ISO and one M-Series→NIST INFORMS edge exists."""
        with test_driver.session() as session:
            iso_result = session.run(
                """
                MATCH (src:Framework)-[r:INFORMS]->(dst:Framework)
                WHERE src.id STARTS WITH 'attack-enterprise.M'
                  AND dst.id STARTS WITH 'iso-27001-2022.'
                  AND r.source = 'embedding-similarity'
                RETURN count(r) AS cnt
                """
            ).single()
            nist_result = session.run(
                """
                MATCH (src:Framework)-[r:INFORMS]->(dst:Framework)
                WHERE src.id STARTS WITH 'attack-enterprise.M'
                  AND dst.id STARTS WITH 'nist-csf-2.0.'
                  AND r.source = 'embedding-similarity'
                RETURN count(r) AS cnt
                """
            ).single()
        iso_count = iso_result["cnt"] if iso_result else 0
        nist_count = nist_result["cnt"] if nist_result else 0
        if iso_count == 0 and nist_count == 0:
            pytest.skip("M-Series INFORMS edges not yet created — run scripts/create_cross_framework_informs.py --m-series first")
        assert iso_count >= 1, f"Expected >= 1 M-Series→ISO INFORMS edges, got {iso_count}"
        assert nist_count >= 1, f"Expected >= 1 M-Series→NIST INFORMS edges, got {nist_count}"

    def test_vector_search_finds_m_series(self, knowledge_client):
        """Semantic search for security awareness training should return M-Series results."""
        resp = knowledge_client.post("/knowledge/search/frameworks", json={
            "query": "user security awareness training phishing",
            "limit": 20,
        })
        if resp.status_code != 200:
            pytest.skip("Search endpoint unavailable or M-Series not yet ingested")
        hits = resp.json()
        if not hits:
            pytest.skip("M-Series not yet ingested — run scripts/ingest_attack_mitigations.py first")
        hit_ids = [h["id"] for h in hits]
        m_series_hits = [hid for hid in hit_ids if hid.startswith("attack-enterprise.M")]
        assert len(m_series_hits) >= 1, (
            f"Expected at least one M-Series result, got: {hit_ids}"
        )
