"""Unit tests for WP-033 MCP server tools.

All tests patch MemoryClient at the import site inside mcp_server.server
so no live stack is required.
"""
import pytest
from unittest.mock import MagicMock, patch


CORE_MEMORY = {
    "strand_id": "strand-identity",
    "type": "fact",
    "text": "test memory",
    "importance": 4,
}
TOPIC_MEMORY = {
    "strand_id": "strand-projects",
    "type": "observation",
    "text": "topic mem",
    "importance": 3,
}


# ---------------------------------------------------------------------------
# U1: memory_add resolves agent_id and calls client correctly
# ---------------------------------------------------------------------------
def test_u1_memory_add_resolves_agent_id():
    from mcp_server.server import memory_add
    from mcp_server.config import settings

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.add_memory.return_value = "uuid-1234"

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_add(text="hello", type="fact")

    # agent_id is the third positional arg (index 2 after self is excluded)
    call_args = mock_client.add_memory.call_args
    assert call_args.args[2] == settings.agent_id
    assert result == "uuid-1234"


# ---------------------------------------------------------------------------
# U2: memory_search calls client.search_memory and returns a list
# ---------------------------------------------------------------------------
def test_u2_memory_search_calls_client():
    from mcp_server.server import memory_search

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.search_memory.return_value = [{"id": "x", "text": "y"}]

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_search(query="test query")

    mock_client.search_memory.assert_called_once()
    call_kwargs = mock_client.search_memory.call_args
    assert call_kwargs.args[0] == "test query"
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# U3: memory_wake_up returns plain-text briefing with no Rich markup
# ---------------------------------------------------------------------------
def test_u3_memory_wake_up_returns_plain_text():
    from mcp_server.server import memory_wake_up

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.wake_up_split.return_value = ([CORE_MEMORY], [])

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_wake_up()

    assert isinstance(result, str)
    assert "## Memory briefing" in result
    assert "test memory" in result
    # No Rich markup
    assert "[bold]" not in result
    assert "[cyan]" not in result


# ---------------------------------------------------------------------------
# U4: memory_list_strands returns list of dicts with id key
# ---------------------------------------------------------------------------
def test_u4_memory_list_strands_returns_list():
    from mcp_server.server import memory_list_strands

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.list_strands.return_value = [{"id": "strand-x", "name": "X"}]

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_list_strands()

    mock_client.list_strands.assert_called_once()
    assert isinstance(result, list)
    assert result[0]["id"] == "strand-x"


# ---------------------------------------------------------------------------
# U5: memory_close_session returns scaffold text without any client call
# ---------------------------------------------------------------------------
def test_u5_memory_close_session_no_client_call():
    from mcp_server.server import memory_close_session

    mock_client = MagicMock()

    with patch("mcp_server.server.MemoryClient", return_value=mock_client) as MockCls:
        result = memory_close_session()

    MockCls.assert_not_called()
    assert "## Session close-out" in result
    assert "memory_add(" in result


# ---------------------------------------------------------------------------
# U6: memory_wake_up with topic includes "Relevant to today" section
# ---------------------------------------------------------------------------
def test_u6_memory_wake_up_with_topic_includes_relevant_section():
    from mcp_server.server import memory_wake_up

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.wake_up_split.return_value = ([CORE_MEMORY], [TOPIC_MEMORY])

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_wake_up(topic="fabric work")

    assert "### Relevant to today" in result
    assert "topic mem" in result


# ---------------------------------------------------------------------------
# U7: memory_wake_up without topic omits "Relevant to today" section
# ---------------------------------------------------------------------------
def test_u7_memory_wake_up_no_topic_omits_relevant_section():
    from mcp_server.server import memory_wake_up

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.wake_up_split.return_value = ([CORE_MEMORY], [])

    with patch("mcp_server.server.MemoryClient", return_value=mock_client):
        result = memory_wake_up()

    assert "Relevant to today" not in result


# ---------------------------------------------------------------------------
# Integration tests — require live Memgraph + FastAPI service
# ---------------------------------------------------------------------------
@pytest.mark.integration
def test_i1_list_strands_returns_strands():
    from mcp_server.server import memory_list_strands

    result = memory_list_strands()
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "id" in result[0]
    assert "name" in result[0]


@pytest.mark.integration
def test_i2_memory_add_returns_uuid():
    from mcp_server.server import memory_add

    result = memory_add(
        text="WP-033 integration test memory",
        type="fact",
        importance=1,
    )
    assert isinstance(result, str)
    assert len(result) == 36  # UUID format: 8-4-4-4-12


@pytest.mark.integration
def test_i3_memory_search_finds_i2_memory():
    from mcp_server.server import memory_search

    results = memory_search(query="WP-033 integration test", limit=5)
    assert isinstance(results, list)
    assert len(results) >= 1
    texts = [r.get("text", "") for r in results]
    assert any("WP-033 integration test memory" in t for t in texts)


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
