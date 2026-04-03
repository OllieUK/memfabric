"""WP-072: unit tests for knowledge-layer fields on Pydantic models.

These are pure unit tests — no live stack required.
"""
import os

import pytest

# Ensure knowledge layer is disabled so main.py does not attempt to import
# knowledge_routes (which may not exist yet in this worktree state).
os.environ.setdefault("ENABLE_KNOWLEDGE_LAYER", "false")

from memory_service.main import AddMemoryRequest, MemoryHit, UpdateMemoryRequest


def test_add_memory_request_defaults():
    req = AddMemoryRequest(fact="x", type="fact", agent_id="a")
    assert req.control_ids == []
    assert req.doc_ids == []
    assert req.control_relationship_type is None
    assert req.org_id is None


def test_update_memory_request_control_ids_alone_valid():
    req = UpdateMemoryRequest(control_ids=["c1"])
    assert req.control_ids == ["c1"]


def test_memory_hit_controls_documents_default_empty():
    hit = MemoryHit(
        id="mem-1",
        text="some text",
        type="fact",
        tags=[],
    )
    assert hit.controls == []
    assert hit.documents == []
