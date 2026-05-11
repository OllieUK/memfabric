"""
tests/test_wp138b_threat_merge.py

Unit and integration tests for WP-138b: merge_threat (knowledge_repo) and
POST /knowledge/threats/{threat_id}/merge (knowledge_routes).

Unit tests:  no DB, no HTTP — fast. Use MagicMock session.
Integration: require live Memgraph + FastAPI. Mark @pytest.mark.integration.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pytest

from cyber_knowledge import repo as knowledge_repo

pytestmark = pytest.mark.cyber


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return f"test-threat-{uuid.uuid4().hex[:8]}"


def _rid() -> str:
    return f"test-report-{uuid.uuid4().hex[:8]}"


def _fid() -> str:
    return f"test-framework-{uuid.uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Unit tests — knowledge_repo.merge_threat
# ---------------------------------------------------------------------------


def _make_session_with_results(*results):
    """Build a MagicMock session where each successive session.run() call
    returns the next mock result in *results.
    """
    session = MagicMock()
    run_results = []
    for r in results:
        mock_result = MagicMock()
        mock_result.single.return_value = r
        run_results.append(mock_result)
    session.run.side_effect = run_results
    return session


class TestMergeThreatUnit:

    def test_merge_threat_validates_same_id(self):
        session = MagicMock()
        with pytest.raises(ValueError, match="Source and target must differ"):
            knowledge_repo.merge_threat(session, "x", "x")
        session.run.assert_not_called()

    def test_merge_threat_raises_if_source_not_found(self):
        # Validation query returns None → nodes not found / archived
        session = _make_session_with_results(None)
        with pytest.raises(ValueError, match="not found or already archived"):
            knowledge_repo.merge_threat(session, "src-1", "tgt-1")

    def test_merge_threat_raises_if_source_archived(self):
        # The validation Cypher filters archived=true, so it returns None
        session = _make_session_with_results(None)
        with pytest.raises(ValueError):
            knowledge_repo.merge_threat(session, "archived-src", "live-tgt")

    def test_merge_threat_raises_if_target_archived(self):
        session = _make_session_with_results(None)
        with pytest.raises(ValueError):
            knowledge_repo.merge_threat(session, "live-src", "archived-tgt")

    def test_merge_threat_returns_correct_counts(self):
        # Validation succeeds, identifies rewire returns 3, techniques returns 2, archive OK
        validation_record = {"src_id": "src-1"}
        identifies_count_record = {"identifies_count": 3}
        identifies_rewire_record = None  # DELETE step returns nothing
        techniques_count_record = {"techniques_count": 2}
        techniques_rewire_record = None  # DELETE step returns nothing
        archive_record = None  # SET step returns nothing

        session = _make_session_with_results(
            validation_record,      # validate
            identifies_count_record,  # pre-count identifies
            identifies_rewire_record, # rewire+delete identifies
            techniques_count_record,  # pre-count techniques
            techniques_rewire_record, # rewire+delete techniques
            archive_record,           # archive step
        )

        result = knowledge_repo.merge_threat(session, "src-1", "tgt-1")
        assert result["source_id"] == "src-1"
        assert result["target_id"] == "tgt-1"
        assert result["identifies_rewired"] == 3
        assert result["techniques_rewired"] == 2

    def test_merge_threat_calls_archive_step(self):
        validation_record = {"src_id": "src-1"}
        identifies_count_record = {"identifies_count": 1}
        techniques_count_record = {"techniques_count": 0}

        session = _make_session_with_results(
            validation_record,
            identifies_count_record,
            None,   # rewire identifies
            techniques_count_record,
            None,   # rewire techniques
            None,   # archive
        )

        knowledge_repo.merge_threat(session, "src-1", "tgt-1")

        # The last run call should contain "SET src.archived" or "archived"
        last_call_args = session.run.call_args_list[-1]
        cypher_str = last_call_args[0][0]
        assert "archived" in cypher_str.lower()


# ---------------------------------------------------------------------------
# Script unit tests — apply_threat_dedup_wp138b helpers
# ---------------------------------------------------------------------------


class TestScriptHelpers:
    """Unit tests for helper logic in apply_threat_dedup_wp138b.

    The script module is imported lazily to avoid subprocess-level side effects
    at collection time.
    """

    @pytest.fixture(autouse=True)
    def _import_script(self):
        import importlib
        import sys
        from pathlib import Path
        proj_root = Path(__file__).resolve().parent.parent
        if str(proj_root) not in sys.path:
            sys.path.insert(0, str(proj_root))
        # Import will succeed once the file is written; if not written yet this
        # will ImportError (expected during TDD red phase)
        import cyber_knowledge.ingest.threat_dedup_apply as m
        self.mod = m

    def test_pick_canonical_higher_identifies_wins(self):
        # Node A has 5 IDENTIFIES edges, node B has 2 — A wins regardless of age
        node_a = {"id": "a", "created_at": "2026-04-01T00:00:00", "identifies_count": 5}
        node_b = {"id": "b", "created_at": "2026-01-01T00:00:00", "identifies_count": 2}
        canonical = self.mod._pick_canonical(node_a, node_b)
        assert canonical["id"] == "a"

    def test_pick_canonical_tiebreak_older_created_at(self):
        # Equal identifies count → older created_at wins
        node_a = {"id": "a", "created_at": "2026-04-01T00:00:00", "identifies_count": 3}
        node_b = {"id": "b", "created_at": "2026-01-01T00:00:00", "identifies_count": 3}
        canonical = self.mod._pick_canonical(node_a, node_b)
        assert canonical["id"] == "b"

    def test_safety_gate_triggers_at_31(self):
        pairs = [("a", "b", 0.10, 0.90)] * 31
        with pytest.raises(self.mod.SafetyGateError):
            self.mod._check_safety_gate(pairs, force=False)

    def test_safety_gate_bypassed_with_force(self):
        pairs = [("a", "b", 0.10, 0.90)] * 31
        # Should not raise
        self.mod._check_safety_gate(pairs, force=True)

    def test_cross_report_filter_excludes_same_report_pairs(self):
        # Two threats from the same ThreatReport must not be included as candidates
        report_membership = {
            "threat-a": {"report-1"},
            "threat-b": {"report-1"},
        }
        pairs = [("threat-a", "threat-b", 0.05, 0.95)]
        filtered = self.mod._filter_cross_report(pairs, report_membership)
        assert len(filtered) == 0

    def test_cross_report_filter_includes_different_report_pairs(self):
        report_membership = {
            "threat-a": {"report-1"},
            "threat-b": {"report-2"},
        }
        pairs = [("threat-a", "threat-b", 0.05, 0.95)]
        filtered = self.mod._filter_cross_report(pairs, report_membership)
        assert len(filtered) == 1

    def test_dry_run_makes_no_http_calls(self):
        # _execute_merges with dry_run=True must not call requests
        with patch("requests.post") as mock_post:
            self.mod._execute_merges(
                merges=[("src-1", "tgt-1", 0.10, 0.90)],
                base_url="http://localhost:8000",
                bearer_token="test-token",
                dry_run=True,
            )
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Integration tests — POST /knowledge/threats/{threat_id}/merge
# ---------------------------------------------------------------------------


def _create_threat(client, threat_id: str, text: str) -> None:
    resp = client.post("/knowledge/threats", json={"id": threat_id, "text": text, "tags": ["test"]})
    assert resp.status_code == 200, resp.text


def _create_threat_report(client, report_id: str, title: str) -> None:
    resp = client.post("/knowledge/threat-reports", json={
        "id": report_id,
        "title": title,
        "publisher": "test-publisher",
    })
    assert resp.status_code == 200, resp.text


def _create_framework(client, fw_id: str, title: str) -> None:
    resp = client.post("/knowledge/frameworks", json={
        "id": fw_id,
        "title": title,
        "level": "technique",
    })
    assert resp.status_code == 200, resp.text


def _create_identifies(client, report_id: str, threat_id: str, severity: str = "high") -> None:
    resp = client.post("/knowledge/identifies", json={
        "threat_report_id": report_id,
        "threat_id": threat_id,
        "severity": severity,
        "confidence": "high",
        "trend": "increasing",
    })
    assert resp.status_code == 200, resp.text


def _create_mapped_to_technique(client, threat_id: str, fw_id: str) -> None:
    resp = client.post("/knowledge/mapped-to-technique", json={
        "threat_id": threat_id,
        "framework_id": fw_id,
    })
    assert resp.status_code == 200, resp.text


def _detach_delete(driver, node_id: str) -> None:
    with driver.session() as s:
        s.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)


def _count_identifies_edges(driver, report_id: str, threat_id: str) -> int:
    with driver.session() as s:
        result = s.run(
            "MATCH (tr:ThreatReport {id: $rid})-[r:IDENTIFIES]->(t:Threat {id: $tid}) "
            "RETURN count(r) AS c",
            rid=report_id, tid=threat_id,
        )
        return result.single()["c"]


def _get_threat_node(driver, threat_id: str) -> dict | None:
    with driver.session() as s:
        result = s.run(
            "MATCH (t:Threat {id: $id}) RETURN t",
            id=threat_id,
        )
        record = result.single()
        return dict(record["t"]) if record else None


def _edge_exists_between(driver, from_id: str, rel: str, to_id: str) -> bool:
    with driver.session() as s:
        result = s.run(
            f"MATCH (a {{id: $a}})-[r:{rel}]->(b {{id: $b}}) RETURN count(r) AS c",
            a=from_id, b=to_id,
        )
        return result.single()["c"] > 0


@pytest.mark.integration
class TestMergeThreatIntegration:

    def test_merge_threat_rewires_identifies_from_different_reports(
        self, knowledge_client, test_driver
    ):
        """ThreatReport B's IDENTIFIES edge must be rewired to ThreatA after merge."""
        src = _uid()
        tgt = _uid()
        rep_a = _rid()
        rep_b = _rid()
        nodes = [src, tgt, rep_a, rep_b]
        try:
            _create_threat(knowledge_client, tgt, "canonical threat text about phishing attacks")
            _create_threat(knowledge_client, src, "duplicate threat text about phishing emails")
            _create_threat_report(knowledge_client, rep_a, "Report A")
            _create_threat_report(knowledge_client, rep_b, "Report B")
            _create_identifies(knowledge_client, rep_a, tgt, severity="high")
            _create_identifies(knowledge_client, rep_b, src, severity="medium")

            resp = knowledge_client.post(
                f"/knowledge/threats/{src}/merge",
                json={"target_id": tgt},
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["source_id"] == src
            assert data["target_id"] == tgt
            assert data["identifies_rewired"] == 1

            # rep_b must now point to tgt with severity=medium
            edge_props = None
            with test_driver.session() as s:
                result = s.run(
                    "MATCH (tr:ThreatReport {id: $rid})-[r:IDENTIFIES]->(t:Threat {id: $tid}) "
                    "RETURN r.severity AS severity",
                    rid=rep_b, tid=tgt,
                )
                rec = result.single()
                assert rec is not None, "rep_b should now IDENTIFY tgt"
                assert rec["severity"] == "medium"

            # rep_a's edge to tgt must still be severity=high
            with test_driver.session() as s:
                result = s.run(
                    "MATCH (tr:ThreatReport {id: $rid})-[r:IDENTIFIES]->(t:Threat {id: $tid}) "
                    "RETURN r.severity AS severity",
                    rid=rep_a, tid=tgt,
                )
                rec = result.single()
                assert rec is not None
                assert rec["severity"] == "high"

            # src must be archived
            node = _get_threat_node(test_driver, src)
            assert node is not None
            assert node.get("archived") is True
            assert node.get("merged_into") == tgt
        finally:
            for nid in nodes:
                _detach_delete(test_driver, nid)

    def test_merge_threat_deduplicates_identifies_from_same_report(
        self, knowledge_client, test_driver
    ):
        """When both src and tgt already have IDENTIFIES from the same ThreatReport,
        after merge ThreatReport must have exactly ONE IDENTIFIES edge to tgt,
        with the ORIGINAL severity (not overwritten by src's severity).
        """
        src = _uid()
        tgt = _uid()
        rep_a = _rid()
        nodes = [src, tgt, rep_a]
        try:
            _create_threat(knowledge_client, tgt, "canonical threat about ransomware")
            _create_threat(knowledge_client, src, "duplicate threat about ransomware encryption")
            _create_threat_report(knowledge_client, rep_a, "Single Report")
            _create_identifies(knowledge_client, rep_a, tgt, severity="high")
            _create_identifies(knowledge_client, rep_a, src, severity="low")

            resp = knowledge_client.post(
                f"/knowledge/threats/{src}/merge",
                json={"target_id": tgt},
            )
            assert resp.status_code == 200, resp.text

            # Exactly one IDENTIFIES edge from rep_a to tgt
            count = _count_identifies_edges(test_driver, rep_a, tgt)
            assert count == 1, f"Expected 1 edge, got {count}"

            # The edge must retain severity=high (original tgt edge, not overwritten by src's low)
            with test_driver.session() as s:
                result = s.run(
                    "MATCH (tr:ThreatReport {id: $rid})-[r:IDENTIFIES]->(t:Threat {id: $tid}) "
                    "RETURN r.severity AS severity",
                    rid=rep_a, tid=tgt,
                )
                rec = result.single()
                assert rec["severity"] == "high", "Original severity must be preserved"

            node = _get_threat_node(test_driver, src)
            assert node.get("archived") is True
        finally:
            for nid in nodes:
                _detach_delete(test_driver, nid)

    def test_merge_threat_rewires_mapped_to_technique(
        self, knowledge_client, test_driver
    ):
        """After merge: tgt has MAPPED_TO_TECHNIQUE edges for both fw_x and fw_y;
        no duplicate for fw_x; src has no outgoing edges.
        """
        src = _uid()
        tgt = _uid()
        fw_x = _fid()
        fw_y = _fid()
        rep_a = _rid()
        rep_b = _rid()
        nodes = [src, tgt, fw_x, fw_y, rep_a, rep_b]
        try:
            _create_threat(knowledge_client, tgt, "canonical technique threat A")
            _create_threat(knowledge_client, src, "duplicate technique threat B")
            _create_framework(knowledge_client, fw_x, "Framework X")
            _create_framework(knowledge_client, fw_y, "Framework Y")
            # Give each threat an IDENTIFIES edge so merge doesn't complain
            _create_threat_report(knowledge_client, rep_a, "Report for tgt")
            _create_threat_report(knowledge_client, rep_b, "Report for src")
            _create_identifies(knowledge_client, rep_a, tgt)
            _create_identifies(knowledge_client, rep_b, src)
            # tgt and src both map to fw_x; only src maps to fw_y
            _create_mapped_to_technique(knowledge_client, tgt, fw_x)
            _create_mapped_to_technique(knowledge_client, src, fw_x)
            _create_mapped_to_technique(knowledge_client, src, fw_y)

            resp = knowledge_client.post(
                f"/knowledge/threats/{src}/merge",
                json={"target_id": tgt},
            )
            assert resp.status_code == 200, resp.text

            # tgt should have exactly one edge to fw_x
            assert _edge_exists_between(test_driver, tgt, "MAPPED_TO_TECHNIQUE", fw_x)
            with test_driver.session() as s:
                result = s.run(
                    "MATCH (t:Threat {id: $tid})-[r:MAPPED_TO_TECHNIQUE]->(:Framework {id: $fid}) "
                    "RETURN count(r) AS c",
                    tid=tgt, fid=fw_x,
                )
                assert result.single()["c"] == 1, "Must be exactly one edge to fw_x"

            # tgt should also have edge to fw_y
            assert _edge_exists_between(test_driver, tgt, "MAPPED_TO_TECHNIQUE", fw_y)

            # src should have no outgoing MAPPED_TO_TECHNIQUE
            with test_driver.session() as s:
                result = s.run(
                    "MATCH (t:Threat {id: $tid})-[r:MAPPED_TO_TECHNIQUE]->() RETURN count(r) AS c",
                    tid=src,
                )
                assert result.single()["c"] == 0
        finally:
            for nid in nodes:
                _detach_delete(test_driver, nid)

    def test_merge_threat_returns_correct_response(
        self, knowledge_client, test_driver
    ):
        """HTTP 200 with identifies_rewired=1, techniques_rewired=1."""
        src = _uid()
        tgt = _uid()
        rep_a = _rid()
        rep_b = _rid()
        fw_a = _fid()
        nodes = [src, tgt, rep_a, rep_b, fw_a]
        try:
            _create_threat(knowledge_client, tgt, "canonical threat for response check")
            _create_threat(knowledge_client, src, "source threat for response check")
            _create_threat_report(knowledge_client, rep_a, "Rep A for response")
            _create_threat_report(knowledge_client, rep_b, "Rep B for response")
            _create_identifies(knowledge_client, rep_a, tgt)
            _create_identifies(knowledge_client, rep_b, src)
            _create_framework(knowledge_client, fw_a, "Framework for response test")
            _create_mapped_to_technique(knowledge_client, src, fw_a)

            resp = knowledge_client.post(
                f"/knowledge/threats/{src}/merge",
                json={"target_id": tgt},
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["source_id"] == src
            assert data["target_id"] == tgt
            assert data["identifies_rewired"] == 1
            assert data["techniques_rewired"] == 1
        finally:
            for nid in nodes:
                _detach_delete(test_driver, nid)

    def test_merge_threat_400_same_id(self, knowledge_client, test_driver):
        """POST with source == target must return HTTP 400."""
        fake_id = _uid()
        resp = knowledge_client.post(
            f"/knowledge/threats/{fake_id}/merge",
            json={"target_id": fake_id},
        )
        assert resp.status_code == 400

    def test_merge_threat_404_missing_source(self, knowledge_client, test_driver):
        """Non-existent source threat must return HTTP 404."""
        resp = knowledge_client.post(
            "/knowledge/threats/nonexistent-src-99999/merge",
            json={"target_id": "nonexistent-tgt-99999"},
        )
        assert resp.status_code == 404

    def test_merge_threat_404_archived_source(self, knowledge_client, test_driver):
        """Archived source threat must return HTTP 404."""
        src = _uid()
        tgt = _uid()
        rep_a = _rid()
        rep_b = _rid()
        nodes = [src, tgt, rep_a, rep_b]
        try:
            _create_threat(knowledge_client, tgt, "live target for archived source test")
            _create_threat(knowledge_client, src, "source that will be archived")
            _create_threat_report(knowledge_client, rep_a, "Rep for tgt")
            _create_threat_report(knowledge_client, rep_b, "Rep for src")
            _create_identifies(knowledge_client, rep_a, tgt)
            _create_identifies(knowledge_client, rep_b, src)
            # Archive the source directly via Bolt
            with test_driver.session() as s:
                s.run(
                    "MATCH (t:Threat {id: $id}) SET t.archived = true",
                    id=src,
                )
            resp = knowledge_client.post(
                f"/knowledge/threats/{src}/merge",
                json={"target_id": tgt},
            )
            assert resp.status_code == 404
        finally:
            for nid in nodes:
                _detach_delete(test_driver, nid)

    def test_operation_log_entry_written(self, knowledge_client, test_driver):
        """After merge, GET /memory/operation/log must contain merge_threat entry."""
        src = _uid()
        tgt = _uid()
        rep_a = _rid()
        rep_b = _rid()
        nodes = [src, tgt, rep_a, rep_b]
        try:
            _create_threat(knowledge_client, tgt, "canonical threat for op-log test")
            _create_threat(knowledge_client, src, "source threat for op-log test")
            _create_threat_report(knowledge_client, rep_a, "Rep A op-log")
            _create_threat_report(knowledge_client, rep_b, "Rep B op-log")
            _create_identifies(knowledge_client, rep_a, tgt)
            _create_identifies(knowledge_client, rep_b, src)

            resp = knowledge_client.post(
                f"/knowledge/threats/{src}/merge",
                json={"target_id": tgt},
            )
            assert resp.status_code == 200, resp.text

            # Fetch operation log — raw from DB to avoid OperationLogEntry schema constraints
            with test_driver.session() as s:
                from memory_service import memory_repo

                raw_entries = memory_repo.get_operation_log(s)
            merge_entries = [
                e for e in raw_entries
                if e.get("operation") == "merge_threat"
                and e.get("source_id") == src
                and e.get("target_id") == tgt
            ]
            assert len(merge_entries) >= 1, (
                f"Expected merge_threat entry in op log, got: {raw_entries[-5:]}"
            )
            entry = merge_entries[-1]
            assert "identifies_rewired" in entry
            assert "techniques_rewired" in entry
        finally:
            for nid in nodes:
                _detach_delete(test_driver, nid)
