# tests/test_wp113_endpoints.py — WP-113 endpoint integration tests
#
# Requires live Memgraph + FastAPI (knowledge_client fixture).
# Mark: @pytest.mark.integration

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_ba(knowledge_client, ba_id: str):
    """Delete a BusinessAttribute node via the driver-level detach delete."""
    # Use the underlying driver to clean up
    pass  # cleanup done in finally blocks per test


def _cleanup_node(test_driver, label: str, node_id: str):
    with test_driver.session() as session:
        session.run(
            f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n",
            id=node_id,
        )


# ---------------------------------------------------------------------------
# BusinessAttribute CRUD — Tier 1 root
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ba_post_get_tier1_root(knowledge_client, test_driver):
    ba_id = "test-wp113-ba-confidentiality"
    try:
        response = knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Confidentiality (test)",
            "description": "Prevents unauthorized disclosure of information",
            "source_ref": "TSI-W100-SABSA-White-Paper.pdf:p20",
            "tier": "primitive-root",
            "status": "active",
            "t100_stereotype": "sabsa-attribute",
        })
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["id"] == ba_id
        assert data["tier"] == "primitive-root"
        assert data["t100_stereotype"] == "sabsa-attribute"
        assert data["status"] == "active"

        # GET round-trip
        get_resp = knowledge_client.get(f"/knowledge/business-attributes/{ba_id}")
        assert get_resp.status_code == 200, get_resp.text
        got = get_resp.json()
        assert got["id"] == ba_id
        assert got["tier"] == "primitive-root"
        assert got["name"] == "Confidentiality (test)"
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", ba_id)


@pytest.mark.integration
def test_ba_post_get_tier2_group(knowledge_client, test_driver):
    ba_id = "test-wp113-ba-group-management"
    try:
        response = knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Management (test group)",
            "tier": "ict-group",
            "group": "management",
            "status": "active",
        })
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["tier"] == "ict-group"
        assert data["group"] == "management"
        assert data["t100_stereotype"] is None

        get_resp = knowledge_client.get(f"/knowledge/business-attributes/{ba_id}")
        assert get_resp.status_code == 200
        got = get_resp.json()
        assert got["tier"] == "ict-group"
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", ba_id)


@pytest.mark.integration
def test_ba_post_get_tier2_ict_leaf(knowledge_client, test_driver):
    ba_id = "test-wp113-ba-ict-leaf-authorised"
    try:
        response = knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Authorised (test)",
            "description": "Only authorised users can access resources",
            "source_ref": "TSI-W100-SABSA-White-Paper.pdf:p20",
            "tier": "ict-leaf",
            "group": "user",
            "t100_stereotype": "sabsa-attribute",
            "status": "active",
        })
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["tier"] == "ict-leaf"
        assert data["group"] == "user"
        assert data["t100_stereotype"] == "sabsa-attribute"

        get_resp = knowledge_client.get(f"/knowledge/business-attributes/{ba_id}")
        assert get_resp.status_code == 200
        got = get_resp.json()
        assert got["group"] == "user"
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", ba_id)


# ---------------------------------------------------------------------------
# GET list — include_deprecated filter
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ba_list_excludes_deprecated_by_default(knowledge_client, test_driver):
    active_id = "test-wp113-ba-active-list"
    deprecated_id = "test-wp113-ba-deprecated-list"
    superseded_by_id = "test-wp113-ba-superseded-by"
    try:
        knowledge_client.post("/knowledge/business-attributes", json={
            "id": superseded_by_id,
            "name": "Superseded target (test)",
            "tier": "primitive-root",
            "status": "active",
        })
        knowledge_client.post("/knowledge/business-attributes", json={
            "id": active_id,
            "name": "Active BA (test)",
            "tier": "primitive-root",
            "status": "active",
        })
        knowledge_client.post("/knowledge/business-attributes", json={
            "id": deprecated_id,
            "name": "Deprecated BA (test)",
            "tier": "primitive-root",
            "status": "deprecated",
            "superseded_by": superseded_by_id,
        })

        # Default: no deprecated
        resp = knowledge_client.get("/knowledge/business-attributes")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert active_id in ids
        assert deprecated_id not in ids

        # With include_deprecated=true
        resp2 = knowledge_client.get("/knowledge/business-attributes?include_deprecated=true")
        assert resp2.status_code == 200
        ids2 = [item["id"] for item in resp2.json()]
        assert deprecated_id in ids2
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", active_id)
        _cleanup_node(test_driver, "BusinessAttribute", deprecated_id)
        _cleanup_node(test_driver, "BusinessAttribute", superseded_by_id)


# ---------------------------------------------------------------------------
# 404 on missing BA
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ba_get_nonexistent_returns_404(knowledge_client):
    resp = knowledge_client.get("/knowledge/business-attributes/nonexistent-ba-wp113")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Idempotency — double POST returns same result
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ba_double_post_idempotent(knowledge_client, test_driver):
    ba_id = "test-wp113-ba-idempotent"
    try:
        resp1 = knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Idempotent BA (test)",
            "tier": "primitive-root",
            "status": "active",
        })
        resp2 = knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Idempotent BA (test)",
            "tier": "primitive-root",
            "status": "active",
        })
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] == resp2.json()["id"]
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", ba_id)


# ---------------------------------------------------------------------------
# POST deprecated BA with nonexistent superseded_by → 422 or 400
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ba_deprecated_with_nonexistent_superseded_by_rejected(knowledge_client, test_driver):
    ba_id = "test-wp113-ba-deprecated-bad-fk"
    try:
        resp = knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Bad deprecated BA",
            "tier": "primitive-root",
            "status": "deprecated",
            "superseded_by": "absolutely-nonexistent-ba-id-wp113",
        })
        assert resp.status_code in (400, 422), (
            f"Expected 400 or 422 for dangling superseded_by FK, got {resp.status_code}"
        )
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", ba_id)


# ---------------------------------------------------------------------------
# INFLUENCE edge round-trip (negative polarity)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_influence_edge_roundtrip(knowledge_client, test_driver):
    threat_id = "test-wp113-threat-influence-src"
    ba_id = "test-wp113-ba-influence-target"
    try:
        # Seed a Threat node
        knowledge_client.post("/knowledge/threat-reports", json={
            "id": "test-wp113-tr-influence",
            "title": "Test TR",
            "publisher": "test",
        })
        knowledge_client.post("/knowledge/threats", json={
            "id": threat_id,
            "text": "Test threat for influence wiring",
            "tags": ["test"],
        })
        knowledge_client.post("/knowledge/threat-reports/test-wp113-tr-influence/threats", json={
            "threat_id": threat_id,
        })

        # Seed target BA
        knowledge_client.post("/knowledge/business-attributes", json={
            "id": ba_id,
            "name": "Availability (test influence target)",
            "tier": "primitive-root",
            "status": "active",
        })

        # Create INFLUENCE edge
        resp = knowledge_client.post("/knowledge/influence", json={
            "source_id": threat_id,
            "target_id": ba_id,
            "polarity": "negative",
            "severity": "high",
            "rationale": "Threat disrupts availability",
            "status": "curated",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["polarity"] == "negative"
        assert data["source_id"] == threat_id
        assert data["target_id"] == ba_id
    finally:
        _cleanup_node(test_driver, "Threat", threat_id)
        _cleanup_node(test_driver, "ThreatReport", "test-wp113-tr-influence")
        _cleanup_node(test_driver, "BusinessAttribute", ba_id)


# ---------------------------------------------------------------------------
# CONTAINS edge round-trip
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_contains_edge_roundtrip(knowledge_client, test_driver):
    parent_id = "test-wp113-ba-contains-parent"
    child_id = "test-wp113-ba-contains-child"
    try:
        knowledge_client.post("/knowledge/business-attributes", json={
            "id": parent_id,
            "name": "Parent BA (test)",
            "tier": "ict-group",
            "group": "management",
            "status": "active",
        })
        knowledge_client.post("/knowledge/business-attributes", json={
            "id": child_id,
            "name": "Child BA (test)",
            "tier": "ict-leaf",
            "group": "management",
            "t100_stereotype": "sabsa-attribute",
            "status": "active",
        })

        resp = knowledge_client.post("/knowledge/contains", json={
            "parent_id": parent_id,
            "child_id": child_id,
            "rationale": "Child is a leaf of parent group",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["parent_id"] == parent_id
        assert data["child_id"] == child_id
    finally:
        _cleanup_node(test_driver, "BusinessAttribute", parent_id)
        _cleanup_node(test_driver, "BusinessAttribute", child_id)


# ---------------------------------------------------------------------------
# Extended FrameworkCreate — cell_role with valid layer → 201
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_framework_main_matrix_cell_valid_layer_201(knowledge_client, test_driver):
    fw_id = "test-wp113-cell-main-contextual-assets"
    try:
        resp = knowledge_client.post("/knowledge/frameworks", json={
            "id": fw_id,
            "title": "Contextual/Assets (test)",
            "cell_role": "main-matrix-cell",
            "layer": "contextual",
            "perspective": "assets",
            "matrix": "main",
        })
        assert resp.status_code in (200, 201), resp.text
    finally:
        _cleanup_node(test_driver, "Framework", fw_id)


@pytest.mark.integration
def test_framework_main_matrix_cell_service_mgmt_layer_422(knowledge_client):
    # "operational" is ONLY in MATRIX_LAYERS_MAIN; NOT valid for service-mgmt-cell
    resp = knowledge_client.post("/knowledge/frameworks", json={
        "id": "test-wp113-cell-bad-layer",
        "title": "Bad cell (test)",
        "cell_role": "service-mgmt-cell",
        "layer": "operational",
        "perspective": "assets",
        "matrix": "service-management",
    })
    assert resp.status_code == 422, (
        f"Expected 422 for service-mgmt-cell with operational layer, got {resp.status_code}"
    )
