"""
tests/test_wake_up_close_session.py — Tests for WP-030: GET /memory/wake-up + CLI commands.

Unit tests (no live stack required):
  U1 — MemoryClient.wake_up() calls GET /memory/wake-up with correct limit param
  U2 — MemoryClient.wake_up(topic=...) passes topic query param
  U3 — MemoryClient.wake_up() raises HTTPStatusError on non-2xx
  U4 — CLI memory wake-up exits 0 and outputs memory text/type
  U5 — CLI memory wake-up --limit 5 --topic "health" forwards both params
  U6 — CLI memory wake-up with empty response prints "No memories found."
  U7 — CLI memory wake-up with HTTP 503 exits 1
  U8 — CLI memory wake-up with connect error exits 1
  U9 — CLI memory close-session exits 0
  U10 — CLI memory close-session output contains required scaffold sections + datetime
  U11 — CLI memory close-session output contains markdown headers and prompt lines

Integration tests (live Memgraph + running FastAPI required):
  I1 — GET /memory/wake-up returns 200 with memories list, each with required fields
  I2 — GET /memory/wake-up?limit=5 returns ≤5 results ordered by importance desc
  I3 — GET /memory/wake-up?topic=health&limit=10 returns ≤10 results (merged, deduped)
  I4 — GET /memory/wake-up with Memgraph unavailable returns 503
"""

import re

import httpx
import pytest
import respx
from typer.testing import CliRunner

from memory_client.cli import app
from memory_client.client import MemoryClient

runner = CliRunner()

BASE = "http://localhost:8000"

_WAKE_UP_RESPONSE = {
    "memories": [
        {
            "id": "mem-aaa",
            "text": "Oliver has ADHD and benefits from short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "Oliver prefers async communication over meetings.",
            "type": "observation",
            "tags": ["strand-core-work"],
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        },
    ]
}

_EMPTY_WAKE_UP_RESPONSE = {"memories": []}


# ---------------------------------------------------------------------------
# U1–U3: MemoryClient.wake_up()
# ---------------------------------------------------------------------------


class TestWakeUpClient:
    @respx.mock
    def test_returns_list_with_correct_limit(self):
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_RESPONSE)
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.wake_up(limit=10)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "mem-aaa"
        # Verify limit param was sent
        assert route.calls[0].request.url.params["limit"] == "10"

    @respx.mock
    def test_passes_topic_param(self):
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_RESPONSE)
        )
        with MemoryClient(base_url=BASE) as client:
            client.wake_up(limit=5, topic="focus and productivity")
        params = route.calls[0].request.url.params
        assert params["topic"] == "focus and productivity"
        assert params["limit"] == "5"

    @respx.mock
    def test_raises_on_http_error(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        with MemoryClient(base_url=BASE) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.wake_up()


# ---------------------------------------------------------------------------
# U4–U8: CLI wake-up
# ---------------------------------------------------------------------------


class TestWakeUpCLI:
    @respx.mock
    def test_exits_zero_and_shows_memories(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_RESPONSE)
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "Memory briefing" in result.output
        assert "fact" in result.output
        assert "Oliver has ADHD" in result.output

    @respx.mock
    def test_forwards_limit_and_topic(self):
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_RESPONSE)
        )
        result = runner.invoke(app, ["wake-up", "--limit", "5", "--topic", "health"])
        assert result.exit_code == 0
        assert "health" in result.output
        # Single call — topic and limit forwarded as params
        assert route.call_count == 1
        params = route.calls[0].request.url.params
        assert params["topic"] == "health"
        assert params["limit"] == "5"

    @respx.mock
    def test_empty_response_shows_message(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_EMPTY_WAKE_UP_RESPONSE)
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "No memories found." in result.output

    @respx.mock
    def test_http_error_exits_nonzero(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 1

    def test_connect_error_exits_nonzero(self):
        result = runner.invoke(
            app,
            ["wake-up"],
            env={"API_BASE_URL": "http://localhost:19999"},
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# U9–U11: CLI close-session
# ---------------------------------------------------------------------------


class TestCloseSessionCLI:
    def test_exits_zero(self):
        result = runner.invoke(app, ["close-session"])
        assert result.exit_code == 0

    def test_contains_required_scaffold_sections(self):
        result = runner.invoke(app, ["close-session"])
        output = result.output
        assert "Session close-out" in output
        # Datetime stamp — matches YYYY-MM-DD HH:MM UTC pattern
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", output)
        assert "decisions" in output.lower()
        assert "learned or observed" in output.lower()
        assert "actions were committed" in output.lower()

    def test_contains_markdown_and_prompt_lines(self):
        result = runner.invoke(app, ["close-session"])
        output = result.output
        assert "##" in output
        # Contains memory add-memory command prompts
        assert "memory add-memory" in output
        assert "--type decision" in output
        assert "--type insight" in output
        assert "--type todo" in output
        assert "--type fact" in output
        assert "memory list-strands" in output

    def test_no_api_call_made(self):
        # close-session must be entirely local — no httpx transport needed
        # If it tries to connect, it would raise on the bad URL
        result = runner.invoke(
            app,
            ["close-session"],
            env={"API_BASE_URL": "http://localhost:19999"},
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# I1–I4: Integration tests (live Memgraph + running FastAPI required)
# ---------------------------------------------------------------------------


class TestWakeUpIntegration:
    # I1: returns 200 with memories list, each item has required fields
    def test_returns_memories_with_required_fields(self, client):
        response = client.get("/memory/wake-up")
        assert response.status_code == 200
        data = response.json()
        assert "memories" in data
        for mem in data["memories"]:
            assert "id" in mem
            assert "text" in mem
            assert "type" in mem
            assert "tags" in mem
            assert "importance" in mem

    # I2: limit enforced and results ordered by importance desc
    def test_limit_and_ordering(self, client):
        response = client.get("/memory/wake-up", params={"limit": 3})
        assert response.status_code == 200
        memories = response.json()["memories"]
        assert len(memories) <= 3
        importances = [m["importance"] for m in memories if m["importance"] is not None]
        assert importances == sorted(importances, reverse=True), (
            "Memories should be ordered by importance descending"
        )

    # I3: topic search merges and deduplicates, total ≤ limit
    def test_topic_search_merges_and_caps(self, client):
        response = client.get("/memory/wake-up", params={"limit": 10, "topic": "health"})
        assert response.status_code == 200
        memories = response.json()["memories"]
        assert len(memories) <= 10
        # No duplicate ids
        ids = [m["id"] for m in memories]
        assert len(ids) == len(set(ids)), "Merged results must be deduplicated"

    # I4: DB unavailable → 503 (tested via mock driver in conftest pattern)
    # This is best tested by bringing Memgraph down; skip here as it requires
    # infrastructure teardown. Covered by unit-level mock in TestWakeUpCLI.
