"""WP-153: Unit tests for the memory_review_recent MCP tool and dedup fact in memory_add.

Pattern matches tests/test_wp033_mcp_server.py — patch repo functions at the
mcp_server.server import site so no live stack is required.
"""
from unittest.mock import MagicMock, patch


def _make_mock_driver():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session
    return mock_driver, mock_session


def test_memory_review_recent_passes_args_through_to_repo():
    from mcp_server.server import memory_review_recent

    fake_items = [
        {
            "id": "abc-1234",
            "fact": "f1",
            "so_what": None,
            "type": "fact",
            "tags": ["t"],
            "importance": 3,
            "created_at": "2026-05-06T00:00:00+00:00",
            "strand_ids": ["strand-inbox"],
        }
    ]
    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch(
            "mcp_server.server.memory_repo.list_recent_memories",
            return_value=fake_items,
        ) as mock_list:
            result = memory_review_recent(days=14, strand_id="strand-inbox", limit=10)

    mock_list.assert_called_once()
    kwargs = mock_list.call_args.kwargs
    assert kwargs == {"days": 14, "strand_id": "strand-inbox", "limit": 10}
    assert result == fake_items


def test_memory_review_recent_uses_documented_defaults():
    """Calling with no args passes days=7, strand_id=None, limit=50 to the repo."""
    from mcp_server.server import memory_review_recent

    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch(
            "mcp_server.server.memory_repo.list_recent_memories",
            return_value=[],
        ) as mock_list:
            memory_review_recent()

    kwargs = mock_list.call_args.kwargs
    assert kwargs == {"days": 7, "strand_id": None, "limit": 50}


def test_memory_add_dedup_includes_duplicate_fact():
    """When the dedup path fires, the MCP response includes duplicate_fact."""
    from mcp_server.server import memory_add

    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch(
            "mcp_server.server.memory_repo.find_duplicate_memory",
            return_value="existing-id-xyz",
        ):
            with patch(
                "mcp_server.server.memory_repo.get_memory_fact",
                return_value="the original matched fact",
            ):
                with patch("mcp_server.server.memory_repo.reinforce_memory"):
                    with patch("mcp_server.server.get_embedding", return_value=[0.1]):
                        result = memory_add(fact="hello", type="fact", agent_id="test-wp153")

    assert result["memory_id"] == "existing-id-xyz"
    assert result["deduplicated"] is True
    assert result.get("duplicate_fact") == "the original matched fact"


def test_memory_add_non_dedup_omits_duplicate_fact():
    """The non-dedup path must not carry a duplicate_fact key."""
    from mcp_server.server import memory_add

    mock_driver, _ = _make_mock_driver()
    with patch("mcp_server.server._driver", return_value=mock_driver):
        with patch("mcp_server.server.memory_repo.find_duplicate_memory", return_value=None):
            with patch("mcp_server.server.memory_repo.add_memory"):
                with patch("mcp_server.server.get_embedding", return_value=[0.1]):
                    result = memory_add(
                        fact="brand new fact",
                        type="fact",
                        agent_id="test-wp153",
                    )

    assert result["deduplicated"] is False
    assert "duplicate_fact" not in result, (
        f"Non-dedup response leaked duplicate_fact: {result.get('duplicate_fact')!r}"
    )
