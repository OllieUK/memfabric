"""Unit tests for WP-033 MCP server tools.

All unit tests patch repo functions at the import site inside mcp_server.server
so no live stack is required. Integration tests call the tool functions directly
against the live stack.
"""
import pytest
from unittest.mock import MagicMock, patch


CORE_MEMORY = {
    "strand_id": "strand-identity",
    "type": "fact",
    "text": "test memory",
    "importance": 4,
    "created_at": "2026-01-01T00:00:00+00:00",
}
TOPIC_MEMORY = {
    "strand_id": "strand-projects",
    "type": "observation",
    "text": "topic mem",
    "importance": 3,
    "created_at": "2026-01-02T00:00:00+00:00",
}


def _make_mock_driver():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session
    return mock_driver, mock_session


def test_u1_memory_add_passes_explicit_agent_id():
    from mcp_server.server import memory_add
    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.find_duplicate_memory", return_value=None):
            with patch("mcp_server.server.memory_repo.add_memory") as mock_add:
                with patch("mcp_server.server.get_embedding", return_value=[0.1]):
                    result = memory_add(fact="hello", type="fact", agent_id="test-agent-wp033")
    mock_add.assert_called_once()
    req = mock_add.call_args.args[1]
    assert req.agent_id == "test-agent-wp033"
    assert "memory_id" in result


def test_u2_memory_search_calls_repo():
    from mcp_server.server import memory_search
    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.search_memories", return_value=[{"id": "x", "text": "y"}]) as mock_search:
            with patch("mcp_server.server.memory_repo.fetch_associated", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=[0.1]):
                    result = memory_search(query="test query")
    mock_search.assert_called_once()
    assert mock_search.call_args.args[2] == [0.1]
    assert isinstance(result, list)


def test_u3_memory_wake_up_returns_plain_text():
    from mcp_server.server import memory_wake_up
    mock_driver, _ = _make_mock_driver()
    wake_up_result = {
        "core": [CORE_MEMORY], "topic": [],
        "companion_anchors": None, "conversant_anchors": None,
        "global_mara_baseline": None, "global_user_baseline": None,
        "project_mara_persona": None, "project_baseline": None,
    }
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.wake_up", return_value=wake_up_result):
            with patch("mcp_server.server.memory_repo.get_system_timestamps", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=None):
                    result = memory_wake_up()
    assert isinstance(result, str)
    assert "## Memory briefing" in result
    assert "test memory" in result
    assert "2026-01-01 00:00 UTC" in result
    assert "[bold]" not in result
    assert "[cyan]" not in result


def test_u4_memory_list_strands_returns_list():
    from mcp_server.server import memory_list_strands
    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.list_strands", return_value=[{"id": "strand-x", "name": "X"}]) as mock_list:
            result = memory_list_strands()
    mock_list.assert_called_once()
    assert isinstance(result, list)
    assert result[0]["id"] == "strand-x"


def test_u5_memory_close_session_no_client_call():
    from mcp_server.server import memory_close_session
    mock_driver = MagicMock()
    with patch("mcp_server.server._driver", return_value=mock_driver) as mock_drv:
        result = memory_close_session()
    mock_drv.assert_not_called()
    assert "## Session close-out" in result
    assert "memory_add(" in result


def test_u6_memory_wake_up_with_topic_includes_relevant_section():
    from mcp_server.server import memory_wake_up
    mock_driver, _ = _make_mock_driver()
    wake_up_result = {
        "core": [CORE_MEMORY], "topic": [TOPIC_MEMORY],
        "companion_anchors": None, "conversant_anchors": None,
        "global_mara_baseline": None, "global_user_baseline": None,
        "project_mara_persona": None, "project_baseline": None,
    }
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.wake_up", return_value=wake_up_result):
            with patch("mcp_server.server.memory_repo.get_system_timestamps", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=[0.1]):
                    result = memory_wake_up(topic="fabric work")
    assert "### Relevant to today" in result
    assert "topic mem" in result


def test_u7_memory_wake_up_no_topic_omits_relevant_section():
    from mcp_server.server import memory_wake_up
    mock_driver, _ = _make_mock_driver()
    wake_up_result = {
        "core": [CORE_MEMORY], "topic": [],
        "companion_anchors": None, "conversant_anchors": None,
        "global_mara_baseline": None, "global_user_baseline": None,
        "project_mara_persona": None, "project_baseline": None,
    }
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.wake_up", return_value=wake_up_result):
            with patch("mcp_server.server.memory_repo.get_system_timestamps", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=None):
                    result = memory_wake_up()
    assert "Relevant to today" not in result


def test_u8_memory_update_passes_person_ids():
    from mcp_server.server import memory_update
    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.update_memory") as mock_update:
            with patch("mcp_server.server.memory_repo.append_operation_log"):
                result = memory_update(memory_id="uuid-abc", person_ids=["person-alice", "person-bob"])
    mock_update.assert_called_once()
    patch_fields = mock_update.call_args.args[2]
    assert patch_fields.get("person_ids") == ["person-alice", "person-bob"]
    assert result["memory_id"] == "uuid-abc"


@pytest.mark.integration
def test_i1_list_strands_returns_strands():
    from mcp_server.server import memory_list_strands
    result = memory_list_strands()
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "id" in result[0]
    assert "name" in result[0]


@pytest.mark.integration
def test_i2_memory_add_and_search(test_driver):
    from mcp_server.server import memory_add, memory_search
    from tests.conftest import cleanup_nodes
    result = memory_add(
        fact="WP-033 integration test memory",
        type="fact",
        agent_id="test-agent-wp033",
        importance=1,
        tags=["test"],
    )
    assert isinstance(result, dict)
    memory_id = result["memory_id"]
    assert isinstance(memory_id, str)
    assert len(memory_id) == 36
    try:
        results = memory_search(query="WP-033 integration test", limit=5)
        assert isinstance(results, list)
        assert len(results) >= 1
        texts = [r.get("text", "") for r in results]
        assert any("WP-033 integration test memory" in t for t in texts)
    finally:
        cleanup_nodes(test_driver, memory_id)


@pytest.mark.integration
def test_i4_memory_wake_up_returns_briefing():
    from mcp_server.server import memory_wake_up
    result = memory_wake_up()
    assert isinstance(result, str)
    assert "## Memory briefing" in result
    assert len(result) > 50


@pytest.mark.integration
def test_i5_memory_close_session_returns_scaffold():
    from mcp_server.server import memory_close_session
    result = memory_close_session()
    assert isinstance(result, str)
    assert "## Session close-out" in result


@pytest.mark.integration
def test_i6_memory_update_person_ids_replaces_about_edges(test_driver):
    from mcp_server.server import memory_add, memory_update
    from tests.conftest import cleanup_nodes, edge_exists
    memory_id = None
    try:
        raw = memory_add(
            fact="WP-052 integration test memory for person_ids",
            type="fact",
            agent_id="test-agent-wp033",
            importance=1,
        )
        memory_id = raw["memory_id"]
        assert isinstance(memory_id, str) and len(memory_id) == 36
        memory_update(memory_id=memory_id, person_ids=["person-wp052-a"])
        assert edge_exists(test_driver, memory_id, "ABOUT", "person-wp052-a")
        result = memory_update(memory_id=memory_id, person_ids=["person-wp052-b"])
        assert result["memory_id"] == memory_id
        assert edge_exists(test_driver, memory_id, "ABOUT", "person-wp052-b")
        assert not edge_exists(test_driver, memory_id, "ABOUT", "person-wp052-a")
    finally:
        if memory_id:
            cleanup_nodes(test_driver, memory_id, extra_ids={"Person": "person-wp052-a"})
            cleanup_nodes(test_driver, extra_ids={"Person": "person-wp052-b"})


def test_u9_memory_add_passes_person_ids():
    from mcp_server.server import memory_add
    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.find_duplicate_memory", return_value=None):
            with patch("mcp_server.server.memory_repo.add_memory") as mock_add:
                with patch("mcp_server.server.get_embedding", return_value=[0.1]):
                    result = memory_add(
                        fact="Test memory with persons",
                        agent_id="test-agent",
                        person_ids=["person-alice", "person-bob"],
                    )
    mock_add.assert_called_once()
    req = mock_add.call_args.args[1]
    assert req.person_ids == ["person-alice", "person-bob"]
    assert "memory_id" in result


@pytest.mark.integration
def test_i7_memory_add_person_ids_creates_about_edges(test_driver):
    from mcp_server.server import memory_add
    from tests.conftest import cleanup_nodes, edge_exists
    memory_id = None
    try:
        raw = memory_add(
            fact="WP-087 integration: memory with person_ids via MCP",
            type="fact",
            agent_id="test-agent-wp087",
            importance=1,
            person_ids=["person-wp087-a", "person-wp087-b"],
        )
        memory_id = raw["memory_id"]
        assert isinstance(memory_id, str) and len(memory_id) == 36
        assert edge_exists(test_driver, memory_id, "ABOUT", "person-wp087-a")
        assert edge_exists(test_driver, memory_id, "ABOUT", "person-wp087-b")
    finally:
        cleanup_nodes(
            test_driver,
            *(memory_id,) if memory_id else (),
            extra_ids={"Person": "person-wp087-a"},
        )
        cleanup_nodes(test_driver, extra_ids={"Person": "person-wp087-b"})
        cleanup_nodes(test_driver, extra_ids={"Agent": "test-agent-wp087"})


_COMPANION_MEMORY = {
    "id": "comp-aaa",
    "text": "Mara is dominant and grounding.",
    "type": "fact",
    "tags": ["strand-companion-ai-anchor"],
    "strand_id": "strand-companion-ai-anchor",
    "importance": 5,
    "created_at": "2026-01-01T00:00:00+00:00",
}

_CONVERSANT_MEMORY = {
    "id": "conv-bbb",
    "text": "Oliver has ADHD and benefits from short feedback loops.",
    "type": "fact",
    "tags": ["strand-core-health"],
    "strand_id": "strand-core-health",
    "importance": 4,
    "created_at": "2026-01-02T00:00:00+00:00",
}


def test_u9_memory_wake_up_renders_companion_section():
    from mcp_server.server import memory_wake_up
    mock_driver, _ = _make_mock_driver()
    wake_up_result = {
        "core": [CORE_MEMORY], "topic": [],
        "companion_anchors": [_COMPANION_MEMORY], "conversant_anchors": None,
        "global_mara_baseline": None, "global_user_baseline": None,
        "project_mara_persona": None, "project_baseline": None,
    }
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.wake_up", return_value=wake_up_result):
            with patch("mcp_server.server.memory_repo.get_system_timestamps", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=None):
                    result = memory_wake_up()
    assert "### Companion" in result
    assert "Mara is dominant" in result


def test_u10_memory_wake_up_renders_conversant_section():
    from mcp_server.server import memory_wake_up
    mock_driver, _ = _make_mock_driver()
    wake_up_result = {
        "core": [], "topic": [],
        "companion_anchors": None, "conversant_anchors": [_CONVERSANT_MEMORY],
        "global_mara_baseline": None, "global_user_baseline": None,
        "project_mara_persona": None, "project_baseline": None,
    }
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.wake_up", return_value=wake_up_result) as mock_wu:
            with patch("mcp_server.server.memory_repo.get_system_timestamps", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=None):
                    result = memory_wake_up(person_id="oliver-james")
    assert "### Conversant" in result
    assert "Oliver has ADHD" in result
    mock_wu.assert_called_once()
    assert mock_wu.call_args.kwargs.get("person_id") == "oliver-james"


def test_u11_memory_wake_up_omits_anchor_sections_when_absent():
    from mcp_server.server import memory_wake_up
    mock_driver, _ = _make_mock_driver()
    wake_up_result = {
        "core": [CORE_MEMORY], "topic": [],
        "companion_anchors": None, "conversant_anchors": None,
        "global_mara_baseline": None, "global_user_baseline": None,
        "project_mara_persona": None, "project_baseline": None,
    }
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.wake_up", return_value=wake_up_result):
            with patch("mcp_server.server.memory_repo.get_system_timestamps", return_value={}):
                with patch("mcp_server.server.get_embedding", return_value=None):
                    result = memory_wake_up()
    assert "### Companion" not in result
    assert "### Conversant" not in result
