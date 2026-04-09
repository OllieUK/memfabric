"""tests/test_threat_integration.py — Integration tests for WP-108 threat layer.

All tests require a live Memgraph + FastAPI stack. Mark: @pytest.mark.integration.
ID prefix convention: test-wp108-tr- (threat-report), test-wp108-t- (threat), test-wp108-a- (asset).

Run with:
    pytest -m integration tests/test_threat_integration.py
"""
import uuid

import pytest


# ---------------------------------------------------------------------------
# Module-scoped cleanup: remove all test-wp108-* nodes before and after suite
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def wp108_cleanup(test_driver):
    with test_driver.session() as s:
        s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp108-' DETACH DELETE n")
    yield
    with test_driver.session() as s:
        s.run("MATCH (n) WHERE n.id STARTS WITH 'test-wp108-' DETACH DELETE n")


# ---------------------------------------------------------------------------
# TestThreatSchemaIntegration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestThreatSchemaIntegration:
    """Verify that the threat_embedding_idx vector index is present.

    Uses test_driver directly; no HTTP calls; no data written.
    """

    def test_threat_embedding_index_exists(self, test_driver):
        with test_driver.session() as session:
            result = session.run("SHOW INDEX INFO")
            indexes = [dict(r) for r in result]

        found = any(
            (r.get("index name") or r.get("index_name") or r.get("name") or "") == "threat_embedding_idx"
            or (
                (r.get("label") or r.get("Label") or "") == "Threat"
                and (r.get("property") or r.get("Property") or "") == "embedding"
                and "vector" in str(r.get("index type") or r.get("type") or r.get("Type") or "").lower()
            )
            for r in indexes
        )
        assert found, (
            f"Expected vector index threat_embedding_idx on Threat(embedding). Got: {indexes}"
        )


# ---------------------------------------------------------------------------
# TestThreatReportRoundTrip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestThreatReportRoundTrip:
    """ThreatReport create + retrieve via HTTP."""

    def test_threat_report_create_and_get_roundtrip(self, knowledge_client, test_driver):
        report_id = f"test-wp108-tr-{uuid.uuid4().hex[:8]}"
        try:
            create_resp = knowledge_client.post("/knowledge/threat-reports", json={
                "id": report_id,
                "title": "WP-108 Integration Test Report",
                "publisher": "Test Publisher",
            })
            assert create_resp.status_code == 200, create_resp.text
            body = create_resp.json()
            assert body["id"] == report_id
            assert body["title"] == "WP-108 Integration Test Report"
            assert body["publisher"] == "Test Publisher"

            get_resp = knowledge_client.get(f"/knowledge/threat-reports/{report_id}")
            assert get_resp.status_code == 200, get_resp.text
            got = get_resp.json()
            assert got["title"] == "WP-108 Integration Test Report"
            assert got["publisher"] == "Test Publisher"
        finally:
            with test_driver.session() as s:
                s.run("MATCH (n:ThreatReport {id: $id}) DETACH DELETE n", id=report_id)


# ---------------------------------------------------------------------------
# TestThreatRoundTrip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestThreatRoundTrip:
    """Threat create + retrieve via HTTP."""

    def test_threat_create_and_get_roundtrip(self, knowledge_client, test_driver):
        threat_id = f"test-wp108-t-{uuid.uuid4().hex[:8]}"
        try:
            create_resp = knowledge_client.post("/knowledge/threats", json={
                "id": threat_id,
                "text": "Ransomware encrypted critical infrastructure files.",
                "tags": ["T1486"],
            })
            assert create_resp.status_code == 200, create_resp.text
            body = create_resp.json()
            assert body["id"] == threat_id
            assert body["text"] == "Ransomware encrypted critical infrastructure files."

            get_resp = knowledge_client.get(f"/knowledge/threats/{threat_id}")
            assert get_resp.status_code == 200, get_resp.text
            got = get_resp.json()
            assert got["id"] == threat_id
            assert got["text"] == "Ransomware encrypted critical infrastructure files."
        finally:
            with test_driver.session() as s:
                s.run("MATCH (n:Threat {id: $id}) DETACH DELETE n", id=threat_id)


# ---------------------------------------------------------------------------
# TestThreatVectorSearch
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestThreatVectorSearch:
    """Verify the /knowledge/search/threats endpoint responds correctly."""

    def test_search_threats_endpoint_returns_200_with_list(self, knowledge_client, test_driver):
        threat_id = f"test-wp108-t-srch-{uuid.uuid4().hex[:8]}"
        try:
            # Create a threat so the index has at least one candidate
            create_resp = knowledge_client.post("/knowledge/threats", json={
                "id": threat_id,
                "text": "Ransomware encryption attack on hospital systems.",
                "tags": ["T1486"],
            })
            assert create_resp.status_code == 200, create_resp.text

            search_resp = knowledge_client.post("/knowledge/search/threats", json={
                "query": "ransomware",
                "limit": 5,
            })
            assert search_resp.status_code == 200, search_resp.text
            results = search_resp.json()
            assert isinstance(results, list)
        finally:
            with test_driver.session() as s:
                s.run("MATCH (n:Threat {id: $id}) DETACH DELETE n", id=threat_id)


# ---------------------------------------------------------------------------
# TestIdentifiesEdgeRoundTrip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIdentifiesEdgeRoundTrip:
    """ThreatReport + Threat + IDENTIFIES edge + traversal endpoint."""

    def test_identifies_edge_and_list_threats_for_report(self, knowledge_client, test_driver):
        report_id = f"test-wp108-tr-{uuid.uuid4().hex[:8]}"
        threat_id = f"test-wp108-t-{uuid.uuid4().hex[:8]}"
        try:
            # Create ThreatReport
            r1 = knowledge_client.post("/knowledge/threat-reports", json={
                "id": report_id,
                "title": "IDENTIFIES Edge Test Report",
                "publisher": "Test Publisher",
            })
            assert r1.status_code == 200, r1.text

            # Create Threat
            r2 = knowledge_client.post("/knowledge/threats", json={
                "id": threat_id,
                "text": "Threat actor used phishing to gain initial access.",
                "tags": ["T1566"],
            })
            assert r2.status_code == 200, r2.text

            # Create IDENTIFIES edge
            r3 = knowledge_client.post("/knowledge/identifies", json={
                "threat_report_id": report_id,
                "threat_id": threat_id,
                "severity": "high",
                "confidence": "high",
                "trend": "stable",
            })
            assert r3.status_code == 200, r3.text
            edge_body = r3.json()
            assert edge_body["threat_report_id"] == report_id
            assert edge_body["threat_id"] == threat_id
            assert edge_body["severity"] == "high"

            # Traverse: list threats for report
            r4 = knowledge_client.get(f"/knowledge/threat-reports/{report_id}/threats")
            assert r4.status_code == 200, r4.text
            threats = r4.json()
            assert isinstance(threats, list)
            assert len(threats) > 0, "Expected at least one threat linked to the report"
            threat_ids = [t["id"] for t in threats]
            assert threat_id in threat_ids
        finally:
            with test_driver.session() as s:
                s.run("MATCH (n:ThreatReport {id: $id}) DETACH DELETE n", id=report_id)
            with test_driver.session() as s:
                s.run("MATCH (n:Threat {id: $id}) DETACH DELETE n", id=threat_id)


# ---------------------------------------------------------------------------
# TestAssetRoundTrip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAssetRoundTrip:
    """Asset create + retrieve via HTTP."""

    def test_asset_create_and_get_roundtrip(self, knowledge_client, test_driver):
        asset_id = f"test-wp108-a-{uuid.uuid4().hex[:8]}"
        try:
            create_resp = knowledge_client.post("/knowledge/assets", json={
                "id": asset_id,
                "title": "IT Integration Test Asset",
                "asset_type": "IT",
            })
            assert create_resp.status_code == 200, create_resp.text
            body = create_resp.json()
            assert body["id"] == asset_id
            assert body["title"] == "IT Integration Test Asset"
            assert body["asset_type"] == "IT"

            get_resp = knowledge_client.get(f"/knowledge/assets/{asset_id}")
            assert get_resp.status_code == 200, get_resp.text
            got = get_resp.json()
            assert got["asset_type"] == "IT"
        finally:
            with test_driver.session() as s:
                s.run("MATCH (n:Asset {id: $id}) DETACH DELETE n", id=asset_id)

    def test_asset_create_with_invalid_asset_type_returns_422(self, knowledge_client):
        asset_id = f"test-wp108-a-{uuid.uuid4().hex[:8]}"
        resp = knowledge_client.post("/knowledge/assets", json={
            "id": asset_id,
            "title": "Invalid Asset Type",
            "asset_type": "INVALID_TYPE",
        })
        # Pydantic field_validator fires at body-binding stage → 422 (not 400)
        assert resp.status_code == 422, resp.text
