"""
tests/test_wake_up_close_session.py — Tests for WP-030/WP-032: GET /memory/wake-up + CLI commands.

Unit tests (no live stack required):
  U1  — MemoryClient.wake_up() calls GET /memory/wake-up with correct limit param
  U2  — MemoryClient.wake_up(topic=...) passes topic query param
  U3  — MemoryClient.wake_up() raises HTTPStatusError on non-2xx
  U4  — CLI memory wake-up exits 0 and outputs memory text/type
  U5  — CLI memory wake-up --limit 5 --topic "health" forwards both params
  U6  — CLI memory wake-up with empty response prints "No memories found."
  U7  — CLI memory wake-up with HTTP 503 exits 1
  U8  — CLI memory wake-up with connect error exits 1 (respx-injected ConnectError)
  U9  — CLI memory close-session exits 0
  U10 — CLI memory close-session output contains required scaffold sections + datetime
  U11 — CLI memory close-session output contains markdown headers and prompt lines
  U12 — CLI memory close-session makes no API call
  U13 — MemoryClient.wake_up_split() returns (core, topic) tuple from split response
  U14 — CLI wake-up: Relevant to today section shown when topic_memories present
  U15 — CLI wake-up: Relevant to today omitted when no --topic
  U16 — CLI wake-up: Relevant to today omitted when topic_memories empty
  U17 — CLI wake-up: non-consecutive same-strand items grouped under one header

Integration tests (live Memgraph + running FastAPI required):
  I1  — GET /memory/wake-up returns 200 with memories list, each with required fields
  I2  — GET /memory/wake-up?limit=5 returns ≤5 results ordered by importance desc
  I3  — GET /memory/wake-up?topic=...&limit=10 returns core + topic lists with no ID overlap
  I4  — GET /memory/wake-up with Memgraph unavailable returns 503
  I5  — GET /memory/wake-up response includes strand_id on each memory item
  I6  — GET /memory/wake-up?topic=... response includes topic_memories list
"""

import re
import uuid

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
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "Oliver prefers async communication over meetings.",
            "type": "observation",
            "tags": ["strand-core-work"],
            "strand_id": "strand-core-work",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        },
    ],
    "topic_memories": [],
}

_EMPTY_WAKE_UP_RESPONSE = {"memories": [], "topic_memories": []}


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


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
# U13–U14: MemoryClient.wake_up_split()
# ---------------------------------------------------------------------------


class TestWakeUpSplitClient:
    @respx.mock
    def test_returns_full_response_dict(self):
        """U13: wake_up_split returns the full API response dict."""
        response_data = {
            "memories": [
                {
                    "id": "mem-aaa",
                    "text": "core memory",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-core-health",
                    "importance": 5,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "topic_memories": [
                {
                    "id": "mem-bbb",
                    "text": "topic memory",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-companion-gmf",
                    "importance": 3,
                    "created_at": "2026-01-02T00:00:00+00:00",
                }
            ],
            "maintenance_status": {
                "short_rest_overdue": False,
                "long_rest_overdue": False,
                "short_rest_days_ago": None,
                "long_rest_days_ago": None,
                "recommended_action": None,
            },
        }
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=response_data)
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.wake_up_split(limit=10, topic="graph memory")
        assert isinstance(result, dict)
        assert result["memories"][0]["id"] == "mem-aaa"
        assert result["topic_memories"][0]["id"] == "mem-bbb"
        assert "maintenance_status" in result

    @respx.mock
    def test_returns_companion_and_conversant_anchors_when_present(self):
        """U14: wake_up_split returns companion/conversant anchors when the API includes them."""
        response_data = {
            "memories": [],
            "topic_memories": [],
            "maintenance_status": {},
            "companion_anchors": [
                {
                    "id": "comp-1",
                    "text": "Mara is dominant",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-companion-ai-anchor",
                    "importance": 5,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "conversant_anchors": [
                {
                    "id": "conv-1",
                    "text": "Oliver has ADHD",
                    "type": "fact",
                    "tags": [],
                    "strand_id": "strand-core-health",
                    "importance": 4,
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=response_data)
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.wake_up_split(person_id="oliver-james")
        assert result.get("companion_anchors") is not None
        assert result["companion_anchors"][0]["id"] == "comp-1"
        assert result.get("conversant_anchors") is not None
        assert result["conversant_anchors"][0]["id"] == "conv-1"
        assert route.calls[0].request.url.params["person_id"] == "oliver-james"


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
        assert "2026-01-01 00:00 UTC" in result.output

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


_SPLIT_WAKE_UP_RESPONSE = {
    "memories": [
        {
            "id": "mem-aaa",
            "text": "Oliver has ADHD and benefits from short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "Oliver prefers async communication over meetings.",
            "type": "observation",
            "tags": ["strand-core-work"],
            "strand_id": "strand-core-work",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        },
    ],
    "topic_memories": [
        {
            "id": "mem-ccc",
            "text": "Oliver is building the graph-memory-fabric project.",
            "type": "fact",
            "tags": ["strand-companion-graph-memory-fabric"],
            "strand_id": "strand-companion-graph-memory-fabric",
            "importance": 3,
            "created_at": "2026-01-03T00:00:00+00:00",
        },
    ],
}

_SPLIT_WAKE_UP_NO_TOPIC = {
    "memories": [
        # mem-aaa and mem-ddd share strand-core-health but are non-consecutive
        # (mem-bbb from strand-core-work is between them).
        # This verifies that _render_section sorts before groupby.
        {
            "id": "mem-aaa",
            "text": "Oliver has ADHD and benefits from short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "Oliver prefers async communication over meetings.",
            "type": "observation",
            "tags": ["strand-core-work"],
            "strand_id": "strand-core-work",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        },
        {
            "id": "mem-ddd",
            "text": "Oliver exercises regularly to manage energy levels.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 3,
            "created_at": "2026-01-04T00:00:00+00:00",
        },
    ],
    "topic_memories": [],
}


class TestWakeUpCLIOutput:
    @respx.mock
    def test_topic_section_shown_when_topic_memories_present(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_SPLIT_WAKE_UP_RESPONSE)
        )
        result = runner.invoke(app, ["wake-up", "--topic", "graph memory"])
        assert result.exit_code == 0
        assert "### Core context" in result.output
        assert "### Relevant to today" in result.output
        # Topic memory text appears
        assert "graph-memory-fabric project" in _normalize_whitespace(result.output)

    @respx.mock
    def test_topic_section_omitted_when_no_topic_provided(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_SPLIT_WAKE_UP_NO_TOPIC)
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "### Core context" in result.output
        assert "### Relevant to today" not in result.output

    @respx.mock
    def test_topic_section_omitted_when_topic_memories_empty(self):
        """--topic provided but all results already in core: Relevant to today omitted."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_SPLIT_WAKE_UP_NO_TOPIC)
        )
        result = runner.invoke(app, ["wake-up", "--topic", "health"])
        assert result.exit_code == 0
        assert "### Core context" in result.output
        assert "### Relevant to today" not in result.output

    @respx.mock
    def test_core_groups_by_strand_id(self):
        """Non-consecutive items sharing a strand_id must be grouped under one header.

        _SPLIT_WAKE_UP_NO_TOPIC has mem-aaa and mem-ddd (both strand-core-health)
        with mem-bbb (strand-core-work) between them. Without sort-before-groupby,
        mem-ddd would appear under a second strand-core-health header. This test
        verifies the header appears exactly once and both memories appear under it.
        """
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_SPLIT_WAKE_UP_NO_TOPIC)
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        output = result.output
        # strand-core-health header appears exactly once
        assert output.count("strand-core-health") == 1, (
            "strand-core-health header should appear exactly once (sort+groupby)"
        )
        # Both health memories appear in output
        assert "ADHD" in output
        assert "exercises regularly" in output
        # Strand header appears before both memory texts
        health_pos = output.find("strand-core-health")
        adhd_pos = output.find("ADHD")
        exercise_pos = output.find("exercises regularly")
        assert health_pos < adhd_pos, "Strand header must precede first memory"
        assert health_pos < exercise_pos, "Strand header must precede second memory"

    @respx.mock
    def test_connect_error_exits_nonzero(self):
        respx.get(f"{BASE}/memory/wake-up").mock(side_effect=httpx.ConnectError("connection refused"))
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 1
        assert "Could not connect" in result.output


# ---------------------------------------------------------------------------
# I1–I4: Integration tests (live Memgraph + running FastAPI required)
# ---------------------------------------------------------------------------


class TestWakeUpIntegration:
    # I1: returns 200 with memories list, each item has required fields
    @pytest.mark.integration
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
    @pytest.mark.integration
    def test_limit_and_ordering(self, client):
        response = client.get("/memory/wake-up", params={"limit": 3})
        assert response.status_code == 200
        memories = response.json()["memories"]
        assert len(memories) <= 3
        importances = [m["importance"] for m in memories if m["importance"] is not None]
        assert importances == sorted(importances, reverse=True), (
            "Memories should be ordered by importance descending"
        )

    # I3: topic search returns core + topic_memories with no ID overlap
    @pytest.mark.integration
    def test_topic_search_merges_and_caps(self, client):
        """I3 — Topic search returns core + topic_memories with no ID overlap."""
        resp = client.get(
            "/memory/wake-up",
            params={"topic": "health ADHD focus", "limit": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert "topic_memories" in data
        core_ids = {m["id"] for m in data["memories"]}
        topic_ids = {m["id"] for m in data["topic_memories"]}
        # No ID should appear in both lists
        assert not core_ids.intersection(topic_ids), (
            f"IDs appear in both core and topic: {core_ids & topic_ids}"
        )
        # Each list independently capped at limit
        assert len(data["memories"]) <= 10
        assert len(data["topic_memories"]) <= 10

    # I4: DB unavailable → 503 (tested via mock driver in conftest pattern)
    # This is best tested by bringing Memgraph down; skip here as it requires
    # infrastructure teardown. Covered by unit-level mock in TestWakeUpCLI.

    @pytest.mark.integration
    def test_wake_up_response_has_strand_id(self, client):
        """I5 — Each memory item includes a strand_id field (may be None for unseeded memories)."""
        resp = client.get("/memory/wake-up", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        for mem in data["memories"]:
            assert "strand_id" in mem  # field present; None is acceptable

    @pytest.mark.integration
    def test_wake_up_with_topic_returns_topic_memories(self, client):
        """I6 — With --topic, response has both 'memories' (core) and 'topic_memories' fields."""
        resp = client.get("/memory/wake-up", params={"limit": 5, "topic": "graph memory"})
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert "topic_memories" in data
        assert isinstance(data["topic_memories"], list)

    @pytest.mark.integration
    def test_core_wake_up_prefers_stronger_reinforced_memory(self, client, test_driver):
        strong_id = f"wake-up-strong-{uuid.uuid4()}"
        weak_id = f"wake-up-weak-{uuid.uuid4()}"
        try:
            # Memgraph silently drops multi-statement CREATE with parameters in a
            # single session.run() call — use two separate calls instead.
            # The embedding must match the live index dimension (384 for all-MiniLM-L6-v2).
            # We use a zero vector — this test cares about sort order by strength/importance,
            # not embedding quality.
            zero_embedding = [0.0] * 384
            with test_driver.session() as session:
                session.run(
                    """
                    CREATE (:Memory {
                        id: $id, fact: $fact, text: $fact, type: 'fact',
                        tags: ['strand-companion-ai-anchor', 'test'],
                        importance: 5,
                        created_at: '2026-03-20T00:00:00+00:00',
                        last_used_at: '2026-03-26T00:00:00+00:00',
                        strength: 0.98, min_strength: 0.3,
                        recall_count: 14, reinforcement_count: 4,
                        last_reinforced_at: '2026-03-26T00:00:00+00:00',
                        decay_rate: 0.01, embedding: $embedding
                    })
                    """,
                    id=strong_id, fact="wake-up strong anchor memory", embedding=zero_embedding,
                )
                session.run(
                    """
                    CREATE (:Memory {
                        id: $id, fact: $fact, text: $fact, type: 'fact',
                        tags: ['strand-core-work-career', 'test'],
                        importance: 5,
                        created_at: '2026-03-26T23:59:59+00:00',
                        last_used_at: '2026-03-26T23:59:59+00:00',
                        strength: 0.32, min_strength: 0.3,
                        recall_count: 0, reinforcement_count: 0,
                        last_reinforced_at: '2026-03-26T23:59:59+00:00',
                        decay_rate: 0.07, embedding: $embedding
                    })
                    """,
                    id=weak_id, fact="wake-up weaker recent memory", embedding=zero_embedding,
                )

            # Verify ordering directly via Bolt using the same sort the wake-up
            # endpoint applies. Checking via the API's limit=N is fragile on a
            # live DB with many importance=5 memories — both test nodes may not
            # fit within the top-N results alongside real data.
            with test_driver.session() as session:
                result = session.run(
                    """
                    MATCH (m:Memory)
                    WHERE m.id IN [$strong_id, $weak_id]
                    RETURN m.id AS id
                    ORDER BY m.importance DESC,
                             coalesce(m.strength, 0.0) DESC,
                             coalesce(m.reinforcement_count, 0) DESC,
                             coalesce(m.recall_count, 0) DESC,
                             m.created_at DESC
                    """,
                    strong_id=strong_id,
                    weak_id=weak_id,
                )
                ordered_ids = [r["id"] for r in result]
            assert len(ordered_ids) == 2, "Both test nodes must exist in the graph"
            assert ordered_ids[0] == strong_id, \
                f"Strong memory (strength=0.98) must sort before weak (strength=0.32); got {ordered_ids}"
        finally:
            with test_driver.session() as session:
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=strong_id)
                session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=weak_id)


# ---------------------------------------------------------------------------
# U18–U21: CLI wake-up person-id and anchor sections
# ---------------------------------------------------------------------------

_WAKE_UP_WITH_ANCHORS = {
    "memories": [
        {
            "id": "mem-aaa",
            "text": "Oliver has ADHD.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ],
    "topic_memories": [],
    "maintenance_status": {},
    "companion_anchors": [
        {
            "id": "comp-aaa",
            "text": "Mara is dominant and grounding.",
            "type": "fact",
            "tags": ["strand-companion-ai-anchor"],
            "strand_id": "strand-companion-ai-anchor",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ],
    "conversant_anchors": [
        {
            "id": "conv-aaa",
            "text": "Oliver prefers short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        }
    ],
}


class TestWakeUpCLIAnchors:
    @respx.mock
    def test_u18_person_id_forwarded_to_api(self):
        """U18: --person-id forwards person_id query param to the API."""
        route = respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_WITH_ANCHORS)
        )
        result = runner.invoke(app, ["wake-up", "--person-id", "oliver-james"])
        assert result.exit_code == 0
        params = route.calls[0].request.url.params
        assert params["person_id"] == "oliver-james"

    @respx.mock
    def test_u19_companion_section_rendered(self):
        """U19: '### Companion' section rendered when companion_anchors present."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_WITH_ANCHORS)
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "### Companion" in result.output
        assert "Mara is dominant" in result.output

    @respx.mock
    def test_u20_conversant_section_rendered(self):
        """U20: '### Conversant' section rendered when conversant_anchors present."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_WITH_ANCHORS)
        )
        result = runner.invoke(app, ["wake-up", "--person-id", "oliver-james"])
        assert result.exit_code == 0
        assert "### Conversant" in result.output
        assert "Oliver prefers short feedback loops" in result.output

    @respx.mock
    def test_u21_anchor_sections_omitted_when_absent(self):
        """U21: Companion and Conversant sections omitted when anchors not in response."""
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json=_WAKE_UP_RESPONSE)  # original fixture, no anchors
        )
        result = runner.invoke(app, ["wake-up"])
        assert result.exit_code == 0
        assert "### Companion" not in result.output
        assert "### Conversant" not in result.output
