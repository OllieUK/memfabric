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
