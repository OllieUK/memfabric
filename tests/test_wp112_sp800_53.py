"""tests/test_wp112_sp800_53.py — WP-112: SP 800-53 Rev 5 ATT&CK bridge ingestion.

Unit tests (no live stack required) and integration tests (require live Memgraph + FastAPI).

Unit tests cover:
  - _node_id: maps control IDs to Framework node IDs
  - _parse_control: parses OSCAL control dicts
  - _extract_base_controls: extracts base controls from OSCAL catalog
  - _upsert dry-run mode
"""
from __future__ import annotations

import importlib.util
import pathlib
from unittest.mock import MagicMock

import pytest

_SP800_53_SCRIPT = pathlib.Path(__file__).parent.parent / "scripts" / "ingest_sp800_53.py"
_CTID_SCRIPT = pathlib.Path(__file__).parent.parent / "scripts" / "ingest_sp800_53_attack_mappings.py"
_CSF_SCRIPT = pathlib.Path(__file__).parent.parent / "scripts" / "ingest_sp800_53_csf_crosswalk.py"


def _import_sp800_53():
    spec = importlib.util.spec_from_file_location("ingest_sp800_53", _SP800_53_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_ctid():
    spec = importlib.util.spec_from_file_location("ingest_sp800_53_attack_mappings", _CTID_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_csf():
    spec = importlib.util.spec_from_file_location("ingest_sp800_53_csf_crosswalk", _CSF_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Unit tests — OSCAL parser
# ---------------------------------------------------------------------------

class TestNodeId:
    def test_uppercase_input(self):
        mod = _import_sp800_53()
        assert mod._node_id("AC-1") == "sp800-53r5.AC-1"

    def test_lowercase_normalised(self):
        mod = _import_sp800_53()
        assert mod._node_id("ac-1") == "sp800-53r5.AC-1"

    def test_si7_maps_correctly(self):
        mod = _import_sp800_53()
        assert mod._node_id("SI-7") == "sp800-53r5.SI-7"


class TestParseControl:
    def _make_control(self, **kwargs):
        ctrl = {
            "id": "ac-1",
            "title": "Policy and Procedures",
            "parts": [
                {"id": "ac-1_smt", "name": "statement", "prose": "Establish policies and procedures."}
            ],
        }
        ctrl.update(kwargs)
        return ctrl

    def test_parse_base_control(self):
        mod = _import_sp800_53()
        result = mod._parse_control(self._make_control())
        assert result is not None
        assert result["id"] == "sp800-53r5.AC-1"
        assert result["external_id"] == "AC-1"
        assert result["title"] == "Policy and Procedures"

    def test_body_extracted_from_statement_part(self):
        mod = _import_sp800_53()
        result = mod._parse_control(self._make_control())
        assert "Establish policies" in result["body"]

    def test_control_with_no_parts_returns_empty_body(self):
        mod = _import_sp800_53()
        ctrl = {"id": "ac-2", "title": "Account Management"}
        result = mod._parse_control(ctrl)
        assert result is not None
        assert result["body"] == ""

    def test_missing_id_returns_none(self):
        mod = _import_sp800_53()
        assert mod._parse_control({"title": "No ID"}) is None

    def test_missing_title_returns_none(self):
        mod = _import_sp800_53()
        assert mod._parse_control({"id": "ac-1"}) is None

    def test_body_extracted_from_sub_parts(self):
        """Statement with no top-level prose but sub-parts should extract sub-part text."""
        mod = _import_sp800_53()
        ctrl = {
            "id": "ac-2",
            "title": "Account Management",
            "parts": [
                {
                    "id": "ac-2_smt",
                    "name": "statement",
                    "parts": [
                        {"id": "ac-2_smt.a", "prose": "Identify and select types of accounts."},
                        {"id": "ac-2_smt.b", "prose": "Assign account managers."},
                    ],
                }
            ],
        }
        result = mod._parse_control(ctrl)
        assert result is not None
        assert "Identify and select types of accounts" in result["body"]
        assert "Assign account managers" in result["body"]

    def test_body_combines_top_prose_and_sub_parts(self):
        """Statement with both top prose and sub-parts should include both."""
        mod = _import_sp800_53()
        ctrl = {
            "id": "ac-3",
            "title": "Access Enforcement",
            "parts": [
                {
                    "id": "ac-3_smt",
                    "name": "statement",
                    "prose": "Enforce approved authorizations.",
                    "parts": [
                        {"id": "ac-3_smt.a", "prose": "For all system access."},
                    ],
                }
            ],
        }
        result = mod._parse_control(ctrl)
        assert result is not None
        assert "Enforce approved authorizations" in result["body"]
        assert "For all system access" in result["body"]


class TestExtractBaseControls:
    def test_basic_extraction(self):
        mod = _import_sp800_53()
        catalog = {
            "catalog": {
                "groups": [
                    {
                        "id": "ac",
                        "controls": [
                            {"id": "ac-1", "title": "Policy"},
                            {"id": "ac-2", "title": "Account Management"},
                        ],
                    }
                ]
            }
        }
        controls = mod._extract_base_controls(catalog)
        ids = [c["id"] for c in controls]
        assert "sp800-53r5.AC-1" in ids
        assert "sp800-53r5.AC-2" in ids
        assert len(controls) == 2

    def test_multiple_families(self):
        mod = _import_sp800_53()
        catalog = {
            "catalog": {
                "groups": [
                    {"id": "ac", "controls": [{"id": "ac-1", "title": "Policy"}]},
                    {"id": "si", "controls": [{"id": "si-1", "title": "Policy"}]},
                ]
            }
        }
        controls = mod._extract_base_controls(catalog)
        ids = {c["id"] for c in controls}
        assert "sp800-53r5.AC-1" in ids
        assert "sp800-53r5.SI-1" in ids

    def test_empty_catalog(self):
        mod = _import_sp800_53()
        assert mod._extract_base_controls({"catalog": {"groups": []}}) == []


class TestDryRunSP80053:
    def test_dry_run_no_api_calls(self):
        mod = _import_sp800_53()
        client = MagicMock()
        result = mod._upsert(client, {"id": "sp800-53r5.AC-1"}, "AC-1", dry_run=True)
        assert result == "dry-run"
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# Integration tests — require live Memgraph + FastAPI
# ---------------------------------------------------------------------------

SP800_53_ROOT_ID = "sp800-53-r5"
AC1_ID = "sp800-53r5.AC-1"


@pytest.mark.integration
class TestSP80053NodesIngested:
    """Verify SP 800-53 Framework nodes are present after ingestion script."""

    def test_root_node_exists(self, knowledge_client):
        resp = knowledge_client.get(f"/knowledge/frameworks/{SP800_53_ROOT_ID}")
        if resp.status_code == 404:
            pytest.skip("SP 800-53 root not yet ingested — run scripts/ingest_sp800_53.py first")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "framework-root"
        assert data["domain"] == "federal"

    def test_ac1_node_exists(self, knowledge_client):
        resp = knowledge_client.get(f"/knowledge/frameworks/{AC1_ID}")
        if resp.status_code == 404:
            pytest.skip("SP 800-53 controls not yet ingested — run scripts/ingest_sp800_53.py first")
        assert resp.status_code == 200
        data = resp.json()
        assert data["level"] == "control"
        assert data["external_id"] == "AC-1"
        assert data["domain"] == "federal"

    def test_control_count_reasonable(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'sp800-53r5.' AND f.level = 'control'
                RETURN count(f) AS cnt
                """
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("SP 800-53 controls not yet ingested — run scripts/ingest_sp800_53.py first")
        assert result["cnt"] >= 300, f"Expected >= 300 SP 800-53 control nodes, got {result['cnt']}"

    def test_controls_with_body_have_embeddings(self, test_driver):
        with test_driver.session() as session:
            with_body_result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'sp800-53r5.' AND f.level = 'control'
                  AND f.body IS NOT NULL
                RETURN count(f) AS cnt
                """
            ).single()
            embedded_result = session.run(
                """
                MATCH (f:Framework)
                WHERE f.id STARTS WITH 'sp800-53r5.' AND f.level = 'control'
                  AND f.body IS NOT NULL AND f.embedding IS NOT NULL
                RETURN count(f) AS cnt
                """
            ).single()
        with_body = with_body_result["cnt"] if with_body_result else 0
        if with_body == 0:
            pytest.skip("SP 800-53 not yet ingested — run scripts/ingest_sp800_53.py first")
        embedded = embedded_result["cnt"] if embedded_result else 0
        assert embedded == with_body, (
            f"Expected all {with_body} controls with body to have embeddings, got {embedded}"
        )


@pytest.mark.integration
class TestSP80053ContainsEdges:
    """Verify CONTAINS edges from SP 800-53 root to control nodes."""

    def test_root_contains_ac1(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (root:Framework {id: $root})-[:CONTAINS]->(c:Framework {id: $cid})
                RETURN count(*) AS cnt
                """,
                root=SP800_53_ROOT_ID,
                cid=AC1_ID,
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("SP 800-53 not yet ingested — run scripts/ingest_sp800_53.py first")
        assert result["cnt"] == 1

    def test_root_contains_all_controls(self, test_driver):
        with test_driver.session() as session:
            result = session.run(
                """
                MATCH (root:Framework {id: $root})-[:CONTAINS]->(c:Framework)
                WHERE c.level = 'control'
                RETURN count(c) AS cnt
                """,
                root=SP800_53_ROOT_ID,
            ).single()
        if result is None or result["cnt"] == 0:
            pytest.skip("SP 800-53 not yet ingested — run scripts/ingest_sp800_53.py first")
        assert result["cnt"] >= 300, f"Expected >= 300 CONTAINS edges from root, got {result['cnt']}"


# ---------------------------------------------------------------------------
# Unit tests — CTID MITIGATES parser
# ---------------------------------------------------------------------------

class TestBuildControlStixMap:
    """Tests for _build_control_stix_map in ingest_sp800_53_attack_mappings.py."""

    def test_base_control_mapped(self):
        mod = _import_ctid()
        objects = [
            {
                "type": "course-of-action",
                "id": "course-of-action--abc",
                "external_references": [{"source_name": "NIST 800-53 Revision 5", "external_id": "AC-3"}],
            }
        ]
        result = mod._build_control_stix_map(objects)
        assert result["course-of-action--abc"] == "sp800-53r5.AC-3"

    def test_enhancement_stripped_to_base(self):
        """AC-2(1) should map to sp800-53r5.AC-2, not create a new node."""
        mod = _import_ctid()
        objects = [
            {
                "type": "course-of-action",
                "id": "course-of-action--xyz",
                "external_references": [{"source_name": "NIST 800-53 Revision 5", "external_id": "AC-2(1)"}],
            }
        ]
        result = mod._build_control_stix_map(objects)
        assert result["course-of-action--xyz"] == "sp800-53r5.AC-2"

    def test_non_control_objects_excluded(self):
        """Non-course-of-action objects are ignored."""
        mod = _import_ctid()
        objects = [
            {"type": "relationship", "id": "relationship--abc", "external_references": []},
            {
                "type": "course-of-action",
                "id": "course-of-action--def",
                "external_references": [{"source_name": "NIST 800-53 Revision 5", "external_id": "AC-1"}],
            },
        ]
        result = mod._build_control_stix_map(objects)
        assert "relationship--abc" not in result
        assert "course-of-action--def" in result

    def test_missing_external_ref_excluded(self):
        """course-of-action without a NIST_SP-800-53_rev5 external reference is skipped."""
        mod = _import_ctid()
        objects = [
            {
                "type": "course-of-action",
                "id": "course-of-action--ghi",
                "external_references": [{"source_name": "other", "external_id": "SOMETHING"}],
            }
        ]
        result = mod._build_control_stix_map(objects)
        assert "course-of-action--ghi" not in result


class TestResolveMitigatesPairs:
    """Tests for _resolve_mitigates_pairs in ingest_sp800_53_attack_mappings.py."""

    def test_mitigates_pair_resolved(self):
        mod = _import_ctid()
        rel_objects = [
            {
                "type": "relationship",
                "relationship_type": "mitigates",
                "source_ref": "course-of-action--abc",
                "target_ref": "attack-pattern--xyz",
            }
        ]
        control_stix_map = {"course-of-action--abc": "sp800-53r5.AC-3"}
        technique_stix_map = {"attack-pattern--xyz": "attack-enterprise.T1548"}
        pairs = mod._resolve_mitigates_pairs(rel_objects, control_stix_map, technique_stix_map)
        assert len(pairs) == 1
        assert pairs[0] == ("sp800-53r5.AC-3", "attack-enterprise.T1548")

    def test_non_mitigates_relationship_excluded(self):
        mod = _import_ctid()
        rel_objects = [
            {
                "type": "relationship",
                "relationship_type": "uses",
                "source_ref": "course-of-action--abc",
                "target_ref": "attack-pattern--xyz",
            }
        ]
        control_stix_map = {"course-of-action--abc": "sp800-53r5.AC-3"}
        technique_stix_map = {"attack-pattern--xyz": "attack-enterprise.T1548"}
        pairs = mod._resolve_mitigates_pairs(rel_objects, control_stix_map, technique_stix_map)
        assert len(pairs) == 0

    def test_unknown_technique_excluded(self):
        mod = _import_ctid()
        rel_objects = [
            {
                "type": "relationship",
                "relationship_type": "mitigates",
                "source_ref": "course-of-action--abc",
                "target_ref": "attack-pattern--unknown",
            }
        ]
        control_stix_map = {"course-of-action--abc": "sp800-53r5.AC-3"}
        technique_stix_map = {}
        pairs = mod._resolve_mitigates_pairs(rel_objects, control_stix_map, technique_stix_map)
        assert len(pairs) == 0

    def test_unknown_control_excluded(self):
        mod = _import_ctid()
        rel_objects = [
            {
                "type": "relationship",
                "relationship_type": "mitigates",
                "source_ref": "course-of-action--unknown",
                "target_ref": "attack-pattern--xyz",
            }
        ]
        control_stix_map = {}
        technique_stix_map = {"attack-pattern--xyz": "attack-enterprise.T1548"}
        pairs = mod._resolve_mitigates_pairs(rel_objects, control_stix_map, technique_stix_map)
        assert len(pairs) == 0
