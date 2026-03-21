"""
tests/test_cli.py — Unit tests for the memory_client CLI (WP-007).

All HTTP calls are intercepted by respx; no running Memgraph instance or
Memory API service is required.  Tests verify that the CLI:

  - Serialises arguments into the correct HTTP request bodies / query params.
  - Prints expected output (memory_id, table rows, JSON, "not implemented"
    message) to stdout.
  - Exits with code 0 on success and with code 1 on unexpected HTTP errors.
  - Exits non-zero when required CLI arguments are omitted.
"""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from memory_client.cli import app

# ---------------------------------------------------------------------------
# Module-level runner — shared across all test classes
# ---------------------------------------------------------------------------

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

BASE = "http://localhost:8000"

_MEMORY_RESPONSE = {"memory_id": "test-id-123"}

_SEARCH_RESPONSE = {
    "memories": [
        {
            "id": "uuid-1111-aaaa",
            "text": "hello world",
            "type": "fact",
            "tags": ["test"],
            "importance": 3,
            "neighbours": [],
        }
    ]
}

_GRAPH_RESPONSE = {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# TestAddMemory
# ---------------------------------------------------------------------------


class TestAddMemory:
    @respx.mock
    def test_prints_memory_id(self):
        respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(200, json=_MEMORY_RESPONSE)
        )
        result = runner.invoke(app, ["add-memory", "some text", "--type", "fact"])
        assert result.exit_code == 0
        assert "test-id-123" in result.output

    def test_type_is_required(self):
        # --type is mandatory; Typer should reject the invocation before any
        # HTTP call is made, so no respx mock is needed.
        result = runner.invoke(app, ["add-memory", "some text"])
        assert result.exit_code != 0

    @respx.mock
    def test_tags_repeatable(self):
        route = respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(200, json=_MEMORY_RESPONSE)
        )
        result = runner.invoke(
            app,
            ["add-memory", "tagged memory", "--type", "fact", "--tag", "a", "--tag", "b"],
        )
        assert result.exit_code == 0
        sent = json.loads(route.calls.last.request.content)
        assert sent["tags"] == ["a", "b"]

    @respx.mock
    def test_service_error_exits_nonzero(self):
        respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        result = runner.invoke(app, ["add-memory", "some text", "--type", "fact"])
        assert result.exit_code == 1

    @respx.mock
    def test_sends_correct_body_minimal(self):
        route = respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(200, json=_MEMORY_RESPONSE)
        )
        result = runner.invoke(
            app, ["add-memory", "minimal body", "--type", "decision"]
        )
        assert result.exit_code == 0
        sent = json.loads(route.calls.last.request.content)
        assert sent["fact"] == "minimal body"
        assert sent["type"] == "decision"
        assert sent["importance"] == 3  # CLI default

    @respx.mock
    def test_optional_flags_sent_in_body(self):
        route = respx.post(f"{BASE}/memory").mock(
            return_value=httpx.Response(200, json=_MEMORY_RESPONSE)
        )
        result = runner.invoke(
            app,
            [
                "add-memory", "full memory",
                "--type", "insight",
                "--importance", "5",
                "--project-id", "proj-42",
                "--person-id", "person-1",
                "--strand-id", "strand-9",
                "--related-id", "mem-old",
            ],
        )
        assert result.exit_code == 0
        sent = json.loads(route.calls.last.request.content)
        assert sent["importance"] == 5
        assert sent["project_id"] == "proj-42"
        assert sent["person_ids"] == ["person-1"]
        assert sent["strand_ids"] == ["strand-9"]
        assert sent["related_ids"] == ["mem-old"]


# ---------------------------------------------------------------------------
# TestSearchMemory
# ---------------------------------------------------------------------------


class TestSearchMemory:
    @respx.mock
    def test_prints_table_with_results(self):
        respx.post(f"{BASE}/memory/search").mock(
            return_value=httpx.Response(200, json=_SEARCH_RESPONSE)
        )
        result = runner.invoke(app, ["search-memory", "hello"])
        assert result.exit_code == 0
        # Rich may word-wrap the text column, so check that both words are
        # present in the output rather than requiring them on the same line.
        assert "hello" in result.output
        assert "world" in result.output

    @respx.mock
    def test_no_results_prints_message(self):
        respx.post(f"{BASE}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        result = runner.invoke(app, ["search-memory", "nothing here"])
        assert result.exit_code == 0
        assert "No memories found." in result.output

    @respx.mock
    def test_filters_passed_to_api(self):
        route = respx.post(f"{BASE}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        result = runner.invoke(
            app,
            [
                "search-memory", "query text",
                "--tag", "alpha",
                "--tag", "beta",
                "--agent-id", "agent-007",
                "--project-id", "proj-99",
                "--limit", "5",
                "--max-hops", "2",
            ],
        )
        assert result.exit_code == 0
        sent = json.loads(route.calls.last.request.content)
        assert sent["query"] == "query text"
        assert sent["tags"] == ["alpha", "beta"]
        assert sent["agent_ids"] == ["agent-007"]
        assert sent["project_ids"] == ["proj-99"]
        assert sent["limit"] == 5
        assert sent["max_hops"] == 2

    @respx.mock
    def test_service_error_exits_nonzero(self):
        respx.post(f"{BASE}/memory/search").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        result = runner.invoke(app, ["search-memory", "query"])
        assert result.exit_code == 1

    @respx.mock
    def test_short_id_shown_in_table(self):
        """Table should display only the first 8 characters of the memory ID."""
        respx.post(f"{BASE}/memory/search").mock(
            return_value=httpx.Response(200, json=_SEARCH_RESPONSE)
        )
        result = runner.invoke(app, ["search-memory", "hello"])
        assert result.exit_code == 0
        # First 8 chars of "uuid-1111-aaaa"
        assert "uuid-111" in result.output

    @respx.mock
    def test_default_limit_and_max_hops(self):
        """When no --limit or --max-hops are given the defaults (10, 1) must be sent."""
        route = respx.post(f"{BASE}/memory/search").mock(
            return_value=httpx.Response(200, json={"memories": []})
        )
        runner.invoke(app, ["search-memory", "defaults test"])
        sent = json.loads(route.calls.last.request.content)
        assert sent["limit"] == 10
        assert sent["max_hops"] == 1


# ---------------------------------------------------------------------------
# TestDumpGraph
# ---------------------------------------------------------------------------


class TestDumpGraph:
    @respx.mock
    def test_not_implemented_prints_message(self):
        """A 500 from GET /memory/graph should print a friendly message and exit 1."""
        respx.get(f"{BASE}/memory/graph").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        result = runner.invoke(app, ["dump-graph"])
        assert result.exit_code == 1
        assert "not yet implemented" in result.output.lower() or "WP-006" in result.output

    @respx.mock
    def test_success_prints_json(self):
        """A 200 response should have its JSON body pretty-printed to stdout."""
        respx.get(f"{BASE}/memory/graph").mock(
            return_value=httpx.Response(200, json=_GRAPH_RESPONSE)
        )
        result = runner.invoke(app, ["dump-graph"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed == _GRAPH_RESPONSE

    @respx.mock
    def test_query_params_forwarded(self):
        """Filters supplied to dump-graph must be sent as query parameters."""
        route = respx.get(f"{BASE}/memory/graph").mock(
            return_value=httpx.Response(200, json=_GRAPH_RESPONSE)
        )
        result = runner.invoke(
            app,
            ["dump-graph", "--project-id", "proj-1", "--agent-id", "agt-2", "--tag", "important"],
        )
        assert result.exit_code == 0
        params = dict(route.calls.last.request.url.params)
        assert params["project_id"] == "proj-1"
        assert params["agent_id"] == "agt-2"
        assert params["tag"] == "important"

    @respx.mock
    def test_unexpected_error_exits_nonzero(self):
        """A non-500/501 HTTP error (e.g. 403) should exit with code 1."""
        respx.get(f"{BASE}/memory/graph").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        result = runner.invoke(app, ["dump-graph"])
        assert result.exit_code == 1

    @respx.mock
    def test_no_filters_sends_no_params(self):
        """When no optional flags are given, no query params should be sent."""
        route = respx.get(f"{BASE}/memory/graph").mock(
            return_value=httpx.Response(200, json=_GRAPH_RESPONSE)
        )
        runner.invoke(app, ["dump-graph"])
        params = dict(route.calls.last.request.url.params)
        assert params == {}
