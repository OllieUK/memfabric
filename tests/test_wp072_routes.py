"""WP-072 Wave 2: route-level tests for knowledge bridge wiring.

All tests are unit tests using mocked driver/session and patched bridge functions.
No live Memgraph required.
"""
import os

os.environ["ENABLE_KNOWLEDGE_LAYER"] = "true"

from unittest.mock import ANY, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import memory_service.config as _cfg_mod
import memory_service.main as _main_mod


def _current_settings():
    """Return the settings singleton from the live memory_service.config module.

    Needed because test_wp070.py reloads config + main in its app_client fixture,
    creating a new settings object. Using a fresh import here ensures patch.object
    always targets the object that main.py's route handlers are actually using.
    """
    return _cfg_mod.settings


@pytest.fixture
def client():
    import memory_service.main as current_main
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__ = lambda s: mock_session
    mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
    current_main.app.state.driver = mock_driver
    return TestClient(current_main.app), mock_session


# ---------------------------------------------------------------------------
# add_memory route tests
# ---------------------------------------------------------------------------


def test_add_memory_with_control_ids_calls_bridge(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.find_duplicate_memory", return_value=None), \
         patch("memory_service.memory_repo.add_memory"), \
         patch("cyber_knowledge.bridge.validate_controls", return_value=[]) as mock_validate, \
         patch("cyber_knowledge.bridge.link_controls") as mock_link, \
         patch("cyber_knowledge.bridge.validate_documents", return_value=[]), \
         patch("cyber_knowledge.bridge.link_documents"), \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.post("/memory", json={
            "fact": "test fact", "type": "fact", "agent_id": "agent1",
            "control_ids": ["c1"],
        })
    assert resp.status_code == 200
    mock_validate.assert_called_once()
    mock_link.assert_called_once_with(mock_session, ANY, ["c1"], None, None)


def test_add_memory_missing_control_returns_400(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.find_duplicate_memory", return_value=None), \
         patch("memory_service.memory_repo.add_memory"), \
         patch("cyber_knowledge.bridge.validate_controls", return_value=["bad-id"]), \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.post("/memory", json={
            "fact": "test fact", "type": "fact", "agent_id": "agent1",
            "control_ids": ["bad-id"],
        })
    assert resp.status_code == 400
    assert "bad-id" in resp.json()["detail"]


def test_add_memory_missing_doc_returns_400(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.find_duplicate_memory", return_value=None), \
         patch("memory_service.memory_repo.add_memory"), \
         patch("cyber_knowledge.bridge.validate_controls", return_value=[]), \
         patch("cyber_knowledge.bridge.link_controls"), \
         patch("cyber_knowledge.bridge.validate_documents", return_value=["bad-doc"]), \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.post("/memory", json={
            "fact": "test fact", "type": "fact", "agent_id": "agent1",
            "doc_ids": ["bad-doc"],
        })
    assert resp.status_code == 400
    assert "bad-doc" in resp.json()["detail"]


def test_add_memory_flag_off_ignores_control_ids(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.find_duplicate_memory", return_value=None), \
         patch("memory_service.memory_repo.add_memory"), \
         patch("cyber_knowledge.bridge.link_controls") as mock_link, \
         patch.object(_current_settings(), "enable_knowledge_layer", False):
        resp = test_client.post("/memory", json={
            "fact": "test fact", "type": "fact", "agent_id": "agent1",
            "control_ids": ["c1"],
        })
    assert resp.status_code == 200
    mock_link.assert_not_called()


# ---------------------------------------------------------------------------
# update_memory route tests
# ---------------------------------------------------------------------------


def test_update_memory_replaces_control_edges(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.update_memory") as mock_repo_update, \
         patch("memory_service.memory_repo.append_operation_log"), \
         patch("cyber_knowledge.bridge.validate_controls", return_value=[]) as mock_validate, \
         patch("cyber_knowledge.bridge.replace_control_edges") as mock_replace, \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.patch("/memory/mem-123", json={
            "control_ids": ["c2"],
        })
    assert resp.status_code == 200
    mock_validate.assert_called_once()
    mock_replace.assert_called_once_with(mock_session, "mem-123", ["c2"], None, None)


def test_update_memory_flag_off_ignores_control_ids(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.update_memory"), \
         patch("memory_service.memory_repo.append_operation_log"), \
         patch("cyber_knowledge.bridge.replace_control_edges") as mock_replace, \
         patch.object(_current_settings(), "enable_knowledge_layer", False):
        resp = test_client.patch("/memory/mem-123", json={
            "control_ids": ["c2"],
        })
    assert resp.status_code == 200
    mock_replace.assert_not_called()


def test_update_memory_bridge_fields_not_in_repo_call(client):
    """Bridge fields must not reach memory_repo.update_memory."""
    test_client, mock_session = client
    with patch("memory_service.memory_repo.update_memory") as mock_repo_update, \
         patch("memory_service.memory_repo.append_operation_log"), \
         patch("cyber_knowledge.bridge.validate_controls", return_value=[]), \
         patch("cyber_knowledge.bridge.replace_control_edges"), \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.patch("/memory/mem-123", json={
            "control_ids": ["c2"],
            "org_id": "org-1",
        })
    assert resp.status_code == 200
    repo_patch = mock_repo_update.call_args[0][2]
    assert "control_ids" not in repo_patch
    assert "org_id" not in repo_patch


def test_update_memory_bridge_only_404_on_missing_memory(client):
    """Bridge-only PATCH on a non-existent memory must return 404."""
    test_client, mock_session = client
    with patch("memory_service.memory_repo.update_memory"), \
         patch("memory_service.memory_repo.append_operation_log"), \
         patch("memory_service.memory_repo.get_memory_for_update", return_value=None) as mock_get, \
         patch("cyber_knowledge.bridge.validate_controls", return_value=[]), \
         patch("cyber_knowledge.bridge.replace_control_edges") as mock_replace, \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.patch("/memory/ghost-id", json={
            "control_ids": ["c1"],
        })
    assert resp.status_code == 404
    mock_get.assert_called_once()
    mock_replace.assert_not_called()


# ---------------------------------------------------------------------------
# merge_memory route tests
# ---------------------------------------------------------------------------


def test_merge_memory_rewires_cross_layer_edges(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.merge_memory"), \
         patch("memory_service.memory_repo.append_operation_log"), \
         patch("cyber_knowledge.bridge.rewire_cross_layer_edges") as mock_rewire, \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.post("/memory/source-id/merge", json={
            "target_id": "target-id",
        })
    assert resp.status_code == 200
    mock_rewire.assert_called_once_with(mock_session, "source-id", "target-id")


def test_merge_memory_flag_off_no_rewire(client):
    test_client, mock_session = client
    with patch("memory_service.memory_repo.merge_memory"), \
         patch("memory_service.memory_repo.append_operation_log"), \
         patch("cyber_knowledge.bridge.rewire_cross_layer_edges") as mock_rewire, \
         patch.object(_current_settings(), "enable_knowledge_layer", False):
        resp = test_client.post("/memory/source-id/merge", json={
            "target_id": "target-id",
        })
    assert resp.status_code == 200
    mock_rewire.assert_not_called()


# ---------------------------------------------------------------------------
# search_memory route tests
# ---------------------------------------------------------------------------


def test_search_memory_hydrates_controls_when_flag_on(client):
    test_client, mock_session = client
    mock_results = [{
        "id": "m1", "text": "t", "type": "fact", "tags": [],
        "importance": 3, "strand_ids": [], "neighbours": [],
    }]
    with patch("memory_service.memory_repo.search_memories", return_value=mock_results), \
         patch("memory_service.memory_repo.fetch_associated", return_value={}), \
         patch("cyber_knowledge.bridge.hydrate_controls_and_documents",
               return_value={"m1": {"controls": [{"id": "c1", "name": "Ctrl"}], "documents": []}}) as mock_hydrate, \
         patch.object(_current_settings(), "enable_knowledge_layer", True):
        resp = test_client.post("/memory/search", json={"query": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["memories"][0]["controls"] == [{"id": "c1", "name": "Ctrl"}]
    mock_hydrate.assert_called_once()


def test_search_memory_controls_empty_when_flag_off(client):
    test_client, mock_session = client
    mock_results = [{
        "id": "m1", "text": "t", "type": "fact", "tags": [],
        "importance": 3, "strand_ids": [], "neighbours": [],
    }]
    with patch("memory_service.memory_repo.search_memories", return_value=mock_results), \
         patch("memory_service.memory_repo.fetch_associated", return_value={}), \
         patch("cyber_knowledge.bridge.hydrate_controls_and_documents") as mock_hydrate, \
         patch.object(_current_settings(), "enable_knowledge_layer", False):
        resp = test_client.post("/memory/search", json={"query": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["memories"][0]["controls"] == []
    mock_hydrate.assert_not_called()
