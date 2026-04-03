import pytest
from unittest.mock import MagicMock, call

from memory_service import knowledge_bridge


class FakeRecord(dict):
    pass


# ---------------------------------------------------------------------------
# validate_controls
# ---------------------------------------------------------------------------


def test_validate_controls_returns_missing_ids():
    mock_session = MagicMock()
    mock_session.run.return_value = [FakeRecord(missing_id="c99")]
    result = knowledge_bridge.validate_controls(mock_session, ["c99"])
    assert result == ["c99"]
    mock_session.run.assert_called_once()


def test_validate_controls_empty_input():
    mock_session = MagicMock()
    result = knowledge_bridge.validate_controls(mock_session, [])
    mock_session.run.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# validate_documents
# ---------------------------------------------------------------------------


def test_validate_documents_returns_missing_ids():
    mock_session = MagicMock()
    mock_session.run.return_value = [FakeRecord(missing_id="d99")]
    result = knowledge_bridge.validate_documents(mock_session, ["d99"])
    assert result == ["d99"]
    mock_session.run.assert_called_once()


def test_validate_documents_empty_input():
    mock_session = MagicMock()
    result = knowledge_bridge.validate_documents(mock_session, [])
    mock_session.run.assert_not_called()
    assert result == []


# ---------------------------------------------------------------------------
# link_controls
# ---------------------------------------------------------------------------


def test_link_controls_calls_merge_for_each_id():
    mock_session = MagicMock()
    knowledge_bridge.link_controls(
        mock_session, "m1", ["c1", "c2"], relationship_type=None, org_id=None
    )
    assert mock_session.run.call_count == 2
    first_cypher = mock_session.run.call_args_list[0][0][0]
    assert "ABOUT_CONTROL" in first_cypher


def test_link_controls_empty_list_no_calls():
    mock_session = MagicMock()
    knowledge_bridge.link_controls(
        mock_session, "m1", [], relationship_type=None, org_id=None
    )
    mock_session.run.assert_not_called()


def test_link_controls_passes_relationship_type_and_org_id():
    mock_session = MagicMock()
    knowledge_bridge.link_controls(
        mock_session, "m1", ["c1"], relationship_type="evidence", org_id="org-1"
    )
    kwargs = mock_session.run.call_args[1]
    assert kwargs["relationship_type"] == "evidence"
    assert kwargs["org_id"] == "org-1"


# ---------------------------------------------------------------------------
# link_documents
# ---------------------------------------------------------------------------


def test_link_documents_calls_merge_for_each_id():
    mock_session = MagicMock()
    knowledge_bridge.link_documents(mock_session, "m1", ["d1"])
    assert mock_session.run.call_count == 1
    first_cypher = mock_session.run.call_args_list[0][0][0]
    assert "CITES_DOC" in first_cypher


def test_link_documents_empty_list_no_calls():
    mock_session = MagicMock()
    knowledge_bridge.link_documents(mock_session, "m1", [])
    mock_session.run.assert_not_called()


# ---------------------------------------------------------------------------
# replace_control_edges
# ---------------------------------------------------------------------------


def test_replace_control_edges_deletes_then_recreates():
    mock_session = MagicMock()
    knowledge_bridge.replace_control_edges(
        mock_session, "m1", ["c1"], relationship_type=None, org_id=None
    )
    assert mock_session.run.call_count == 2
    first_cypher = mock_session.run.call_args_list[0][0][0]
    second_cypher = mock_session.run.call_args_list[1][0][0]
    assert "DELETE" in first_cypher
    assert "MERGE" in second_cypher


# ---------------------------------------------------------------------------
# replace_doc_edges
# ---------------------------------------------------------------------------


def test_replace_doc_edges_deletes_then_recreates():
    mock_session = MagicMock()
    knowledge_bridge.replace_doc_edges(mock_session, "m1", ["d1"])
    assert mock_session.run.call_count == 2
    first_cypher = mock_session.run.call_args_list[0][0][0]
    second_cypher = mock_session.run.call_args_list[1][0][0]
    assert "DELETE" in first_cypher
    assert "MERGE" in second_cypher


# ---------------------------------------------------------------------------
# rewire_cross_layer_edges
# ---------------------------------------------------------------------------


def test_rewire_cross_layer_edges_calls_both_rewires():
    mock_session = MagicMock()
    knowledge_bridge.rewire_cross_layer_edges(mock_session, "src-1", "tgt-1")
    assert mock_session.run.call_count == 2
    all_kwargs = [c[1] for c in mock_session.run.call_args_list]
    assert all(kw.get("src_id") == "src-1" for kw in all_kwargs)
    assert all(kw.get("tgt_id") == "tgt-1" for kw in all_kwargs)


# ---------------------------------------------------------------------------
# hydrate_controls_and_documents
# ---------------------------------------------------------------------------


def test_hydrate_controls_and_documents_filters_null_nodes():
    mock_session = MagicMock()
    record = FakeRecord(
        mid="m1",
        controls=[
            {"id": None, "name": None, "relationship_type": None, "org_id": None},
            {"id": "c1", "name": "Control 1", "relationship_type": "evidence", "org_id": None},
        ],
        documents=[],
    )
    mock_session.run.return_value = [record]
    result = knowledge_bridge.hydrate_controls_and_documents(mock_session, ["m1"])
    assert result["m1"]["controls"] == [
        {"id": "c1", "name": "Control 1", "relationship_type": "evidence", "org_id": None}
    ]
    assert result["m1"]["documents"] == []


def test_hydrate_controls_and_documents_empty_memory_ids():
    mock_session = MagicMock()
    result = knowledge_bridge.hydrate_controls_and_documents(mock_session, [])
    mock_session.run.assert_not_called()
    assert result == {}
