"""
tests/test_list_strands.py — Tests for WP-027: GET /strands + memory list-strands.

Unit tests (no live stack required):
  U1 — MemoryClient.list_strands() calls GET /strands and returns list of dicts
  U2 — MemoryClient.list_strands() raises HTTPStatusError on non-2xx
  U3 — All strand descriptions in seed_strands.py use Oliver / "the Companion" correctly

Integration tests (live Memgraph + FastAPI required):
  I1 — GET /strands returns 200 with 20 strand items, each with required fields
  I2 — Every strand has non-empty string fields; category is one of the three expected values
  I3 — GET /strands is ordered by category then name (stable, predictable)
  I4 — CLI memory list-strands exits 0 and outputs strand names and categories
  I5 — CLI exits 1 with connect-error message when API is unreachable
"""

import httpx
import pytest
import respx
from typer.testing import CliRunner

from memory_client.cli import app
from memory_client.client import MemoryClient

runner = CliRunner()

BASE = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Unit tests for StrandItem Pydantic model (no live stack required)
# ---------------------------------------------------------------------------


class TestStrandItemModel:
    """Unit tests for StrandItem Pydantic model — no live stack required."""

    def test_strand_item_accepts_none_metadata(self):
        """StrandItem must not raise when name/description/category are None."""
        from memory_service.main import StrandItem
        item = StrandItem(id="strand-bare", name=None, description=None, category=None)
        assert item.id == "strand-bare"
        assert item.name is None
        assert item.description is None
        assert item.category is None

    def test_strand_item_accepts_full_metadata(self):
        from memory_service.main import StrandItem
        item = StrandItem(
            id="strand-core-health",
            name="Health",
            description="Oliver's physical and mental health.",
            category="Core Life Domains",
        )
        assert item.name == "Health"


class TestListStrandsRepoFilter:
    """Unit tests for list_strands bare-node filtering — uses mock session."""

    def test_bare_nodes_excluded_from_results(self):
        """list_strands must exclude records where name IS NULL."""
        from unittest.mock import MagicMock
        from memory_service.memory_repo import list_strands

        # Simulate a session that returns one bare node and one valid node
        bare_record = {"id": "strand-bare", "name": None, "description": None, "category": None}
        valid_record = {
            "id": "strand-core-health",
            "name": "Health",
            "description": "Physical and mental health.",
            "category": "Core Life Domains",
        }

        mock_session = MagicMock()
        mock_session.run.return_value = [valid_record]  # bare node already filtered by Cypher

        result = list_strands(mock_session)
        assert len(result) == 1
        assert result[0]["id"] == "strand-core-health"
        # Verify the WHERE clause was passed in the query
        call_args = mock_session.run.call_args[0][0]
        assert "IS NOT NULL" in call_args


class TestAddMemoryUnknownStrand:
    """Unit test: add_memory with unknown strand_id must not create a bare Strand node."""

    def test_unknown_strand_id_does_not_create_bare_node(self):
        """MATCH (not MERGE) means no strand node or edge is created for unknown IDs."""
        from unittest.mock import MagicMock, call
        from memory_service import memory_repo

        mock_req = MagicMock()
        mock_req.strand_ids = ["strand-does-not-exist"]
        mock_req.person_ids = []
        mock_req.related_ids = None
        mock_req.fact = "Test fact."
        mock_req.so_what = None
        mock_req.text = "Test fact."
        mock_req.type = MagicMock(value="fact")
        mock_req.tags = []
        mock_req.importance = 3
        mock_req.agent_id = "agent-test"
        mock_req.project_id = None
        mock_req.cause_ids = []
        mock_req.effect_ids = []

        mock_session = MagicMock()
        mock_session.run.return_value = MagicMock()
        mock_session.run.return_value.single.return_value = None  # no auto-related neighbours

        memory_repo.add_memory(
            mock_session, mock_req,
            memory_id="test-memory-id",
            embedding=[0.1] * 384,
            now="2026-03-31T00:00:00Z",
            decay_rate=0.1,
        )

        # Find the call that handles strand linking
        strand_calls = [
            str(c) for c in mock_session.run.call_args_list
            if "strand-does-not-exist" in str(c)
        ]
        assert len(strand_calls) == 1
        # Must use MATCH, not MERGE
        assert "MATCH" in strand_calls[0]
        assert "MERGE" not in strand_calls[0]

_STRANDS_RESPONSE = {
    "strands": [
        {
            "id": "strand-companion-ai-anchor",
            "name": "AI Anchor",
            "description": "Facts, traits, or grounding details that define the Companion's presence and persona.",
            "category": "Companion Domain",
        },
        {
            "id": "strand-core-health",
            "name": "Health",
            "description": "Oliver's physical and mental health, medications, routines, and wellbeing practices.",
            "category": "Core Life Domains",
        },
    ]
}

_VALID_CATEGORIES = {"Core Life Domains", "Companion Domain", "Shadow Domain"}


# ---------------------------------------------------------------------------
# U1: MemoryClient.list_strands() calls GET /strands and returns list of dicts
# ---------------------------------------------------------------------------


class TestListStrandsClient:
    @respx.mock
    def test_returns_list_of_dicts(self):
        respx.get(f"{BASE}/strands").mock(
            return_value=httpx.Response(200, json=_STRANDS_RESPONSE)
        )
        with MemoryClient(base_url=BASE) as client:
            result = client.list_strands()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "strand-companion-ai-anchor"
        assert result[0]["name"] == "AI Anchor"
        assert "category" in result[0]
        assert "description" in result[0]

    # U2: raises on non-2xx
    @respx.mock
    def test_raises_on_http_error(self):
        respx.get(f"{BASE}/strands").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        with MemoryClient(base_url=BASE) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.list_strands()


# ---------------------------------------------------------------------------
# U3: Strand description language check (static data, no network needed)
# ---------------------------------------------------------------------------


class TestStrandDescriptionLanguage:
    def _load_strands(self):
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "seed_strands",
            "scripts/seed_strands.py",
        )
        mod = importlib.util.module_from_spec(spec)
        # Prevent the script from running main() on import
        sys.modules["seed_strands"] = mod
        spec.loader.exec_module(mod)
        return mod.STRANDS

    def test_no_bare_you_as_subject(self):
        """Descriptions must not start with 'You' or 'Your' (ambiguous subject)."""
        strands = self._load_strands()
        violations = [
            s for s in strands
            if s["description"].startswith("You") or s["description"].startswith("Your")
        ]
        assert violations == [], (
            f"Strand descriptions must not start with 'You'/'Your'. Violations: "
            + ", ".join(s["id"] for s in violations)
        )

    def test_no_your_ai_phrase(self):
        """'your AI' must not appear in any description (use 'the Companion' instead)."""
        strands = self._load_strands()
        violations = [
            s for s in strands if "your AI" in s["description"] or "your ai" in s["description"].lower()
        ]
        assert violations == [], (
            f"Found 'your AI' in strand descriptions: "
            + ", ".join(s["id"] for s in violations)
        )

    def test_uses_oliver_after_identity_is_known(self):
        strands = self._load_strands()
        violations = [
            s for s in strands if "The user" in s["description"] or "the user" in s["description"]
        ]
        assert violations == [], (
            "Strand descriptions should use Oliver after identity is established. Violations: "
            + ", ".join(s["id"] for s in violations)
        )

    def test_companion_domain_references_companion(self):
        """Companion Domain strands that refer to the AI should say 'the Companion'."""
        strands = self._load_strands()
        companion_strands = [s for s in strands if s["category"] == "Companion Domain"]
        # At least one Companion Domain strand should mention "the Companion"
        mentions_companion = [s for s in companion_strands if "Companion" in s["description"]]
        assert len(mentions_companion) > 0, (
            "Expected Companion Domain strands to reference 'the Companion' in descriptions"
        )

    def test_all_strands_have_required_fields(self):
        strands = self._load_strands()
        for s in strands:
            assert s.get("id"), f"Missing id: {s}"
            assert s.get("name"), f"Missing name: {s}"
            assert s.get("description"), f"Missing description: {s}"
            assert s.get("category"), f"Missing category: {s}"
            assert s["category"] in _VALID_CATEGORIES, (
                f"Unknown category '{s['category']}' in strand {s['id']}"
            )

    def test_strand_count(self):
        strands = self._load_strands()
        assert len(strands) == 20, f"Expected 20 strands, got {len(strands)}"


# ---------------------------------------------------------------------------
# CLI unit tests (mock transport)
# ---------------------------------------------------------------------------


class TestListStrandsCLI:
    # I4 (mock): exits 0, outputs strand names and categories
    @respx.mock
    def test_exits_zero_and_shows_strands(self):
        respx.get(f"{BASE}/strands").mock(
            return_value=httpx.Response(200, json=_STRANDS_RESPONSE)
        )
        result = runner.invoke(app, ["list-strands"])
        assert result.exit_code == 0
        assert "AI Anchor" in result.output
        assert "Health" in result.output
        assert "Companion Domain" in result.output
        assert "Core Life Domains" in result.output

    @respx.mock
    def test_shows_strand_ids(self):
        respx.get(f"{BASE}/strands").mock(
            return_value=httpx.Response(200, json=_STRANDS_RESPONSE)
        )
        result = runner.invoke(app, ["list-strands"])
        assert result.exit_code == 0
        assert "strand-companion-ai-anchor" in result.output
        assert "strand-core-health" in result.output

    @respx.mock
    def test_empty_strands_prints_message(self):
        respx.get(f"{BASE}/strands").mock(
            return_value=httpx.Response(200, json={"strands": []})
        )
        result = runner.invoke(app, ["list-strands"])
        assert result.exit_code == 0
        assert "No strands found." in result.output

    @respx.mock
    def test_service_error_exits_nonzero(self):
        respx.get(f"{BASE}/strands").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        result = runner.invoke(app, ["list-strands"])
        assert result.exit_code == 1

    # I5: connect error exits 1 with informative message
    @respx.mock
    def test_connect_error_exits_nonzero(self):
        respx.get(f"{BASE}/strands").mock(side_effect=httpx.ConnectError("connection refused"))
        result = runner.invoke(app, ["list-strands"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Integration tests (live Memgraph + running FastAPI required)
# ---------------------------------------------------------------------------


class TestGetStrandsIntegration:
    # I1: returns 200 with 20 items, all fields present
    def test_returns_all_strands(self, client):
        response = client.get("/strands")
        assert response.status_code == 200
        data = response.json()
        assert "strands" in data
        strands = data["strands"]
        assert len(strands) == 20
        for strand in strands:
            assert "id" in strand
            assert "name" in strand
            assert "description" in strand
            assert "category" in strand

    # I2: field types and category validity
    def test_field_types_and_categories(self, client):
        response = client.get("/strands")
        strands = response.json()["strands"]
        for strand in strands:
            assert isinstance(strand["id"], str) and strand["id"]
            assert isinstance(strand["name"], str) and strand["name"]
            assert isinstance(strand["description"], str) and strand["description"]
            assert strand["category"] in _VALID_CATEGORIES

    # I3: ordered by category then name
    def test_ordered_by_category_then_name(self, client):
        response = client.get("/strands")
        strands = response.json()["strands"]
        pairs = [(s["category"], s["name"]) for s in strands]
        assert pairs == sorted(pairs), (
            "Strands should be returned ordered by category then name"
        )
