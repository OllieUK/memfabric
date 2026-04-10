import pytest
from memory_service.main import (
    AddMemoryRequest,
    UpdateMemoryRequest,
    SearchMemoryRequest,
    MemoryHit,
    MemoryType,
)


# --- AddMemoryRequest ---

def test_add_memory_request_files_modified_serialises():
    req = AddMemoryRequest(
        fact="edited memory_repo.py",
        type=MemoryType.fact,
        agent_id="test-agent",
        files_modified=["memory_service/memory_repo.py"],
    )
    data = req.model_dump()
    assert data["files_modified"] == ["memory_service/memory_repo.py"]
    assert data["files_read"] == []


def test_add_memory_request_files_read_serialises():
    req = AddMemoryRequest(
        fact="read config.py",
        type=MemoryType.fact,
        agent_id="test-agent",
        files_read=["memory_service/config.py"],
    )
    data = req.model_dump()
    assert data["files_read"] == ["memory_service/config.py"]
    assert data["files_modified"] == []


def test_add_memory_request_files_default_empty():
    req = AddMemoryRequest(
        fact="no files",
        type=MemoryType.fact,
        agent_id="test-agent",
    )
    data = req.model_dump()
    assert data["files_modified"] == []
    assert data["files_read"] == []


# --- UpdateMemoryRequest ---

def test_update_memory_request_files_modified_passes_validator():
    req = UpdateMemoryRequest(files_modified=["memory_service/main.py"])
    assert req.files_modified == ["memory_service/main.py"]


def test_update_memory_request_files_read_passes_validator():
    req = UpdateMemoryRequest(files_read=["memory_service/config.py"])
    assert req.files_read == ["memory_service/config.py"]


def test_update_memory_request_files_empty_list_passes_validator():
    """Empty list is a valid 'clear this field' value — distinct from None (not provided)."""
    req = UpdateMemoryRequest(files_modified=[])
    assert req.files_modified == []


# --- SearchMemoryRequest ---

def test_search_memory_request_files_modified_field():
    req = SearchMemoryRequest(query="test", files_modified=["memory_service/main.py"])
    assert req.files_modified == ["memory_service/main.py"]
    assert req.files_read is None


def test_search_memory_request_files_default_none():
    req = SearchMemoryRequest(query="test")
    assert req.files_modified is None
    assert req.files_read is None


# --- MemoryHit ---

def test_memory_hit_files_fields_default_empty():
    hit = MemoryHit(
        id="abc",
        text="some text",
        type=MemoryType.fact,
        tags=[],
    )
    assert hit.files_modified == []
    assert hit.files_read == []


def test_memory_hit_files_fields_round_trip():
    hit = MemoryHit(
        id="abc",
        text="some text",
        type=MemoryType.fact,
        tags=[],
        files_modified=["memory_service/main.py"],
        files_read=["memory_service/config.py"],
    )
    data = hit.model_dump()
    assert data["files_modified"] == ["memory_service/main.py"]
    assert data["files_read"] == ["memory_service/config.py"]


def test_update_memory_sets_files_modified():
    """files_modified is included in the scalar SET clause."""
    from unittest.mock import MagicMock
    from memory_service import memory_repo

    session = MagicMock()
    session.run.return_value = MagicMock()

    memory_repo.update_memory(
        session,
        memory_id="test-id",
        patch_fields={"files_modified": ["memory_service/main.py"]},
        new_embedding=None,
        now="2026-01-01T00:00:00+00:00",
    )

    call = session.run.call_args_list[0]
    query = call[0][0]
    assert "files_modified" in query
    assert call[1]["files_modified"] == ["memory_service/main.py"]


# --- Integration with add_memory Cypher ---

def test_add_memory_passes_files_to_cypher():
    """files_modified and files_read are passed as Cypher params."""
    from unittest.mock import MagicMock
    from memory_service import memory_repo

    req = AddMemoryRequest(
        fact="edited main.py",
        type=MemoryType.fact,
        agent_id="test-agent",
        files_modified=["memory_service/main.py"],
        files_read=["memory_service/config.py"],
    )
    req.text = req.fact  # simulate validator

    session = MagicMock()
    session.run.return_value = MagicMock()

    memory_repo.add_memory(
        session, req, "test-id-123", [0.1] * 384, "2026-01-01T00:00:00+00:00", 0.1
    )

    # First session.run call is the main CREATE — inspect kwargs
    call_kwargs = session.run.call_args_list[0]
    call_kw = call_kwargs[1]    # keyword args dict
    assert call_kw.get("files_modified") == ["memory_service/main.py"]
    assert call_kw.get("files_read") == ["memory_service/config.py"]


# --- _build_file_filter_clause ---

def test_build_file_filter_clause_files_modified():
    from memory_service.memory_repo import _build_file_filter_clause
    clause = _build_file_filter_clause(files_modified=["main.py"], files_read=None)
    assert "ANY(f IN m.files_modified WHERE f IN $files_modified)" in clause


def test_build_file_filter_clause_files_read():
    from memory_service.memory_repo import _build_file_filter_clause
    clause = _build_file_filter_clause(files_modified=None, files_read=["config.py"])
    assert "ANY(f IN m.files_read WHERE f IN $files_read)" in clause


def test_build_file_filter_clause_none_returns_empty():
    from memory_service.memory_repo import _build_file_filter_clause
    clause = _build_file_filter_clause(files_modified=None, files_read=None)
    assert clause == ""


# --- search_memories ---

def test_search_memories_passes_files_to_session_run():
    """files_modified and files_read are passed as Cypher params to search_memories."""
    from unittest.mock import MagicMock
    from memory_service import memory_repo

    req = SearchMemoryRequest(
        query="test search",
        files_modified=["memory_service/main.py"],
        files_read=["memory_service/config.py"],
    )

    session = MagicMock()
    session.run.return_value = MagicMock()
    session.run.return_value.__iter__ = lambda self: iter([])

    memory_repo.search_memories(
        session, req, [0.1] * 384, neighbour_cap=5
    )

    # Inspect the session.run call kwargs
    call_kwargs = session.run.call_args_list[0]
    call_kw = call_kwargs[1]    # keyword args dict
    assert call_kw.get("files_modified") == ["memory_service/main.py"]
    assert call_kw.get("files_read") == ["memory_service/config.py"]


# --- get_memories_by_file ---

def test_get_memories_by_file_role_modified_queries_files_modified():
    from unittest.mock import MagicMock
    from memory_service import memory_repo

    session = MagicMock()
    session.run.return_value = iter([])

    memory_repo.get_memories_by_file(session, path="memory_service/main.py", role="modified", limit=10)

    call = session.run.call_args_list[0]
    query = call[0][0]
    # WHERE clause should filter on files_modified only
    assert "ANY(f IN m.files_modified WHERE f = $path)" in query
    assert "ANY(f IN m.files_read WHERE f = $path)" not in query
    assert call[1]["path"] == "memory_service/main.py"


def test_get_memories_by_file_role_read_queries_files_read():
    from unittest.mock import MagicMock
    from memory_service import memory_repo

    session = MagicMock()
    session.run.return_value = iter([])

    memory_repo.get_memories_by_file(session, path="memory_service/config.py", role="read", limit=10)

    call = session.run.call_args_list[0]
    query = call[0][0]
    # WHERE clause should filter on files_read only
    assert "ANY(f IN m.files_read WHERE f = $path)" in query
    assert "ANY(f IN m.files_modified WHERE f = $path)" not in query


def test_get_memories_by_file_role_any_queries_both():
    from unittest.mock import MagicMock
    from memory_service import memory_repo

    session = MagicMock()
    session.run.return_value = iter([])

    memory_repo.get_memories_by_file(session, path="memory_service/main.py", role="any", limit=10)

    call = session.run.call_args_list[0]
    query = call[0][0]
    assert "m.files_modified" in query
    assert "m.files_read" in query


# --- MemoryClient unit tests ---

def test_client_add_memory_passes_files():
    """files_modified and files_read are sent in the POST /memory request body."""
    from unittest.mock import MagicMock, patch
    import httpx
    from memory_client.client import MemoryClient

    mock_response = MagicMock()
    mock_response.json.return_value = {"memory_id": "abc", "deduplicated": False, "strand_ids": []}
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx.Client, "post", return_value=mock_response) as mock_post:
        client = MemoryClient(base_url="http://localhost:8000")
        client.add_memory(
            fact="edited main.py",
            type="fact",
            agent_id="test-agent",
            files_modified=["memory_service/main.py"],
            files_read=["memory_service/config.py"],
        )

    _, kwargs = mock_post.call_args
    body = kwargs["json"]
    assert body["files_modified"] == ["memory_service/main.py"]
    assert body["files_read"] == ["memory_service/config.py"]


def test_client_update_memory_passes_files():
    """files_modified and files_read are sent in the PATCH /memory/{id} request body."""
    from unittest.mock import MagicMock, patch
    import httpx
    from memory_client.client import MemoryClient

    mock_response = MagicMock()
    mock_response.json.return_value = {"memory_id": "abc", "updated_at": "2026-01-01T00:00:00+00:00"}
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx.Client, "patch", return_value=mock_response) as mock_patch:
        client = MemoryClient(base_url="http://localhost:8000")
        client.update_memory(
            "abc",
            files_modified=["memory_service/main.py"],
            files_read=["memory_service/config.py"],
        )

    _, kwargs = mock_patch.call_args
    body = kwargs["json"]
    assert body["files_modified"] == ["memory_service/main.py"]
    assert body["files_read"] == ["memory_service/config.py"]


def test_client_get_memories_by_file():
    """GET /memory/by-file is called with correct params; returns the memories list."""
    from unittest.mock import MagicMock, patch
    import httpx
    from memory_client.client import MemoryClient

    fake_memory = {"id": "abc", "text": "edited main.py", "type": "fact", "importance": 3,
                   "files_modified": ["memory_service/main.py"], "files_read": []}
    mock_response = MagicMock()
    mock_response.json.return_value = {"memories": [fake_memory]}
    mock_response.raise_for_status = MagicMock()

    with patch.object(httpx.Client, "get", return_value=mock_response) as mock_get:
        client = MemoryClient(base_url="http://localhost:8000")
        result = client.get_memories_by_file(
            path="memory_service/main.py",
            role="modified",
            limit=5,
        )

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["path"] == "memory_service/main.py"
    assert kwargs["params"]["role"] == "modified"
    assert kwargs["params"]["limit"] == 5
    assert result == [fake_memory]
