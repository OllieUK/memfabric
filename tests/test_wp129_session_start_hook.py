import pytest
import re
import subprocess
import sys
import os
from unittest.mock import patch
import httpx
from memory_client.formatting import format_wake_up


# Minimal result fixture matching wake_up_split() output shape
def _make_result(
    memories=None,
    topic_memories=None,
    companion_anchors=None,
    conversant_anchors=None,
):
    return {
        "memories": memories or [],
        "topic_memories": topic_memories or [],
        "companion_anchors": companion_anchors,
        "conversant_anchors": conversant_anchors,
    }


def _make_mem(text="some fact", importance=3, type="fact", strand_id="strand-core", id="abc"):
    return {
        "id": id,
        "text": text,
        "type": type,
        "importance": importance,
        "strand_id": strand_id,
        "created_at": "2026-04-10T10:00:00+00:00",
        "tags": [],
    }


# --- plain=True removes Rich markup ---

def test_format_wake_up_plain_no_rich_tags():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, plain=True)
    assert not re.search(r'\[[a-zA-Z_ /]+\]', output), f"Rich tags found in: {output!r}"


def test_format_wake_up_rich_has_markup_tags():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, plain=False)
    assert re.search(r'\[[a-zA-Z_ /]+\]', output), "Expected Rich tags in non-plain output"


# --- Structure preservation ---

def test_format_wake_up_contains_heading():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, plain=True)
    assert "Memory briefing" in output


def test_format_wake_up_topic_in_heading():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, topic="graph-memory-fabric", plain=True)
    assert "graph-memory-fabric" in output


def test_format_wake_up_general_session_when_no_topic():
    result = _make_result(memories=[_make_mem()])
    output = format_wake_up(result, topic=None, plain=True)
    assert "general session" in output


def test_format_wake_up_strand_heading_present():
    result = _make_result(memories=[_make_mem(strand_id="strand-core-work")])
    output = format_wake_up(result, plain=True)
    assert "strand-core-work" in output


def test_format_wake_up_memory_text_present():
    result = _make_result(memories=[_make_mem(text="important fact about Memgraph")])
    output = format_wake_up(result, plain=True)
    assert "important fact about Memgraph" in output


# --- Section omission rules ---

def test_format_wake_up_no_topic_section_when_topic_memories_empty():
    result = _make_result(memories=[_make_mem()], topic_memories=[])
    output = format_wake_up(result, topic="some-topic", plain=True)
    assert "Relevant to today" not in output


def test_format_wake_up_topic_section_present_when_topic_and_memories():
    result = _make_result(
        memories=[_make_mem()],
        topic_memories=[_make_mem(text="topic-relevant memory")],
    )
    output = format_wake_up(result, topic="work", plain=True)
    assert "Relevant to today" in output
    assert "topic-relevant memory" in output


def test_format_wake_up_no_companion_section_when_none():
    result = _make_result(memories=[_make_mem()], companion_anchors=None)
    output = format_wake_up(result, plain=True)
    assert "Companion" not in output


def test_format_wake_up_companion_section_when_present():
    result = _make_result(
        memories=[_make_mem()],
        companion_anchors=[_make_mem(text="companion identity fact")],
    )
    output = format_wake_up(result, plain=True)
    assert "Companion" in output
    assert "companion identity fact" in output


def test_format_wake_up_no_conversant_section_when_none():
    result = _make_result(memories=[_make_mem()], conversant_anchors=None)
    output = format_wake_up(result, plain=True)
    assert "Conversant" not in output


def test_format_wake_up_empty_memories_non_empty_output():
    result = _make_result()
    output = format_wake_up(result, plain=True)
    assert len(output) > 0
    assert "Memory briefing" in output


# --- No-strand fallback ---

def test_format_wake_up_no_strand_shows_fallback_label():
    result = _make_result(memories=[_make_mem(strand_id=None)])
    output = format_wake_up(result, plain=True)
    assert "(no strand)" in output


# --- Rich output structure test (for Task 2 regression) ---

def test_format_wake_up_rich_output_matches_cli_structure():
    result = _make_result(
        memories=[_make_mem(text="core fact", strand_id="strand-work")],
        topic_memories=[_make_mem(text="topic fact", strand_id="strand-work")],
        companion_anchors=[_make_mem(text="companion fact", strand_id="strand-companion")],
    )
    output = format_wake_up(result, topic="work", plain=False)
    assert "## Memory briefing — work" in output
    assert "Core context" in output
    assert "Relevant to today" in output
    assert "Companion" in output
    assert "core fact" in output
    assert "topic fact" in output
    assert "companion fact" in output


def test_format_wake_up_mara_startup_v2_sections_render():
    result = {
        "memories": [],
        "topic_memories": [],
        "global_mara_baseline": [_make_mem(text="global mara fact", strand_id="strand-companion-ai-anchor", id="gm-1")],
        "global_user_baseline": [_make_mem(text="global user fact", strand_id="strand-companion-human-anchor", id="gu-1")],
        "project_mara_persona": [_make_mem(text="project persona fact", strand_id="strand-companion-current-projects", id="pm-1")],
        "project_baseline": [_make_mem(text="project baseline fact", strand_id="strand-core-work-career", id="pb-1")],
    }
    output = format_wake_up(result, topic="mara startup", plain=True)
    assert "Global Mara baseline" in output
    assert "Global user baseline" in output
    assert "Project Mara persona" in output
    assert "Project baseline" in output
    assert "global mara fact" in output
    assert "project baseline fact" in output


def test_format_wake_up_mara_startup_v2_compresses_semantic_duplicates():
    duplicate_a = _make_mem(
        text="Project baseline: backlog maintenance is currently the top priority.",
        strand_id="strand-core-work-career",
    )
    duplicate_b = _make_mem(
        text="Project baseline backlog maintenance is currently the top priority",
        strand_id="strand-companion-current-projects",
    )
    duplicate_b["id"] = "def"
    result = {
        "memories": [],
        "topic_memories": [],
        "global_mara_baseline": [duplicate_a],
        "global_user_baseline": None,
        "project_mara_persona": [duplicate_b],
        "project_baseline": None,
    }
    output = format_wake_up(result, plain=True)
    assert output.count("backlog maintenance is currently the top priority") == 1


# --- Hook script tests ---


def test_hook_main_prints_briefing(capsys):
    """main() prints wake-up briefing to stdout."""
    mock_result = {
        "memories": [_make_mem(text="session start test memory")],
        "topic_memories": [],
        "companion_anchors": None,
        "conversant_anchors": None,
    }
    with patch("hooks.session_start.MemoryClient") as MockClient:
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.wake_up_split.return_value = mock_result
        from hooks.session_start import main
        main()
    captured = capsys.readouterr()
    assert "Memory briefing" in captured.out


def test_hook_main_fallback_on_connect_error(capsys):
    """main() prints fallback message on ConnectError."""
    with patch("hooks.session_start.MemoryClient") as MockClient:
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.wake_up_split.side_effect = httpx.ConnectError("refused")
        from hooks.session_start import main
        main()
    captured = capsys.readouterr()
    assert "unreachable" in captured.out.lower()


def test_hook_main_fallback_on_timeout_error(capsys):
    """main() prints fallback message on TimeoutException."""
    with patch("hooks.session_start.MemoryClient") as MockClient:
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.wake_up_split.side_effect = httpx.TimeoutException("timeout")
        from hooks.session_start import main
        main()
    captured = capsys.readouterr()
    assert "unreachable" in captured.out.lower()


def test_hook_main_fallback_on_http_error(capsys):
    """main() prints fallback message on HTTPStatusError."""
    with patch("hooks.session_start.MemoryClient") as MockClient:
        mock_instance = MockClient.return_value.__enter__.return_value
        response = httpx.Response(500, request=httpx.Request("GET", "http://localhost:8000/memory/wake-up"))
        mock_instance.wake_up_split.side_effect = httpx.HTTPStatusError("error", request=httpx.Request("GET", "http://localhost:8000"), response=response)
        from hooks.session_start import main
        main()
    captured = capsys.readouterr()
    assert "memory service" in captured.out.lower() and "operating without" in captured.out.lower()


def test_hook_main_output_no_rich_markup(capsys):
    """main() output contains no Rich markup tags."""
    mock_result = {
        "memories": [_make_mem(text="plain text check")],
        "topic_memories": [],
        "companion_anchors": None,
        "conversant_anchors": None,
    }
    with patch("hooks.session_start.MemoryClient") as MockClient:
        mock_instance = MockClient.return_value.__enter__.return_value
        mock_instance.wake_up_split.return_value = mock_result
        from hooks.session_start import main
        main()
    captured = capsys.readouterr()
    assert not re.search(r'\[[a-zA-Z_ /]+\]', captured.out), (
        f"Rich tags found in hook output: {captured.out!r}"
    )
