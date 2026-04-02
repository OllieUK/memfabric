# WP-047: Near-Duplicate Detection for Memory Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GET /memory/duplicates` endpoint that surfaces semantically similar memory pairs above a configurable similarity threshold, enabling review-and-merge workflows via the existing WP-038 merge endpoint.

**Architecture:** Iterate Memory node pairs connected by `RELATED_TO` edges (which are auto-created at ingest when vector distance < 0.5). For each pair, compute cosine similarity from stored embeddings. Pairs exceeding the threshold are returned ordered by similarity descending. This avoids a full N² comparison by using the pre-existing graph structure as a filter. Exact-duplicate handling at ingest (WP-088) is already complete — this WP is purely about near-duplicate *review*.

**Tech Stack:** FastAPI, Pydantic, neo4j Python driver, Python `math` stdlib (cosine computation), Typer CLI, FastMCP, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `memory_service/config.py` | Add `near_duplicate_threshold` and `near_duplicate_limit` defaults |
| Modify | `memory_service/main.py` | Add Pydantic models + `GET /memory/duplicates` endpoint |
| Modify | `memory_service/memory_repo.py` | Add `find_near_duplicates()` function |
| Modify | `memory_client/client.py` | Add `find_duplicates()` method |
| Modify | `memory_client/cli.py` | Add `find-duplicates` command |
| Modify | `mcp_server/server.py` | Add `memory_find_duplicates` tool |
| Create | `tests/test_wp047_near_duplicates.py` | Unit + integration tests |

---

### Task 1: Config defaults

**Files:**
- Modify: `memory_service/config.py`

- [ ] **Step 1: Add settings**

In `memory_service/config.py`, add to the `Settings` class:

```python
    near_duplicate_threshold: float = 0.92
    near_duplicate_limit: int = 20
```

- [ ] **Step 2: Commit**

```bash
git add memory_service/config.py
git commit -m "WP-047: add near_duplicate_threshold and near_duplicate_limit settings"
```

---

### Task 2: Repository function — `find_near_duplicates`

**Files:**
- Modify: `memory_service/memory_repo.py`
- Create: `tests/test_wp047_near_duplicates.py`

- [ ] **Step 1: Create test file with unit test for cosine similarity helper**

Create `tests/test_wp047_near_duplicates.py`:

```python
# tests/test_wp047_near_duplicates.py
"""Tests for WP-047: near-duplicate detection."""
import math

import pytest

from tests.conftest import cleanup_nodes

_AGENT_ID = "test-agent-wp047"


def _cleanup(driver, *memory_ids):
    cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


def _add_body(fact: str, **kwargs) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 1,
    }
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Task 2 — Unit: cosine_similarity helper
# ---------------------------------------------------------------------------
class TestCosineSimilarity:
    def test_identical_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_vector_returns_zero(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([], [1.0, 0.0]) == 0.0

    def test_zero_norm_returns_zero(self):
        from memory_service.memory_repo import cosine_similarity
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_wp047_near_duplicates.py::TestCosineSimilarity -v`
Expected: FAIL — `cosine_similarity` doesn't exist.

- [ ] **Step 3: Add `cosine_similarity` helper to memory_repo.py**

In `memory_service/memory_repo.py`, add near the top (after imports):

```python
import math


def cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/test_wp047_near_duplicates.py::TestCosineSimilarity -v`
Expected: PASS

- [ ] **Step 5: Add `find_near_duplicates` function**

In `memory_service/memory_repo.py`, add:

```python
def find_near_duplicates(session, threshold: float, limit: int) -> list[dict]:
    """Find near-duplicate memory pairs via RELATED_TO edges.

    Iterates pairs connected by RELATED_TO, computes cosine similarity
    from stored embeddings, returns pairs above threshold ordered by
    similarity descending.
    """
    result = session.run(
        """
        MATCH (a:Memory)-[r:RELATED_TO]->(b:Memory)
        WHERE (a.status IS NULL OR a.status = 'active')
          AND (b.status IS NULL OR b.status = 'active')
          AND (a.ephemeral IS NULL OR a.ephemeral = false)
          AND (b.ephemeral IS NULL OR b.ephemeral = false)
          AND a.embedding IS NOT NULL AND size(a.embedding) > 0
          AND b.embedding IS NOT NULL AND size(b.embedding) > 0
          AND a.id < b.id
        RETURN a.id AS a_id, a.text AS a_text,
               b.id AS b_id, b.text AS b_text,
               a.embedding AS a_emb, b.embedding AS b_emb
        """
    )

    pairs = []
    for record in result:
        sim = cosine_similarity(record["a_emb"], record["b_emb"])
        if sim >= threshold:
            pairs.append({
                "a": {"id": record["a_id"], "text": record["a_text"]},
                "b": {"id": record["b_id"], "text": record["b_text"]},
                "similarity": round(sim, 4),
            })

    pairs.sort(key=lambda p: p["similarity"], reverse=True)
    return pairs[:limit]
```

Note: `a.id < b.id` ensures each undirected pair is returned only once regardless of edge direction.

- [ ] **Step 6: Commit**

```bash
git add memory_service/memory_repo.py tests/test_wp047_near_duplicates.py
git commit -m "WP-047: add cosine_similarity helper and find_near_duplicates repo function"
```

---

### Task 3: HTTP endpoint — `GET /memory/duplicates`

**Files:**
- Modify: `memory_service/main.py`
- Test: `tests/test_wp047_near_duplicates.py`

- [ ] **Step 1: Add endpoint integration test**

Append to `tests/test_wp047_near_duplicates.py`:

```python
# ---------------------------------------------------------------------------
# Task 3 — Integration: GET /memory/duplicates endpoint
# ---------------------------------------------------------------------------
class TestDuplicatesEndpoint:
    @pytest.mark.integration
    def test_near_duplicates_found(self, client, test_driver):
        """Two very similar memories appear as a near-duplicate pair."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("The database server is running very slowly today"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body("The database server runs extremely slowly today"))
            mid_b = r2.json()["memory_id"]

            # Use a low threshold to catch semantically similar memories
            r3 = client.get("/memory/duplicates", params={"threshold": 0.80, "limit": 50})
            assert r3.status_code == 200
            pairs = r3.json()
            pair_sets = [{p["a"]["id"], p["b"]["id"]} for p in pairs]
            assert {mid_a, mid_b} in pair_sets
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_unrelated_memories_not_paired(self, client, test_driver):
        """Two unrelated memories do not appear as duplicates."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("Oliver likes chocolate ice cream in summer"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body("The Kubernetes deployment pipeline uses Helm charts"))
            mid_b = r2.json()["memory_id"]

            r3 = client.get("/memory/duplicates", params={"threshold": 0.90, "limit": 50})
            assert r3.status_code == 200
            pairs = r3.json()
            pair_sets = [{p["a"]["id"], p["b"]["id"]} for p in pairs]
            assert {mid_a, mid_b} not in pair_sets
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    @pytest.mark.integration
    def test_archived_memories_excluded(self, client, test_driver):
        """Archived memories do not appear in duplicate results."""
        mid_a = mid_b = None
        try:
            r1 = client.post("/memory", json=_add_body("WP047 archived dup test alpha"))
            mid_a = r1.json()["memory_id"]
            r2 = client.post("/memory", json=_add_body("WP047 archived dup test alpha"))  # exact dup would be caught by WP-088, use different route
            mid_b = r2.json()["memory_id"]

            # Archive one
            client.post(f"/memory/{mid_a}/archive")

            r3 = client.get("/memory/duplicates", params={"threshold": 0.80, "limit": 50})
            pairs = r3.json()
            all_ids = set()
            for p in pairs:
                all_ids.add(p["a"]["id"])
                all_ids.add(p["b"]["id"])
            assert mid_a not in all_ids
        finally:
            if mid_a:
                _cleanup(test_driver, mid_a)
            if mid_b:
                _cleanup(test_driver, mid_b)

    def test_default_params(self, client):
        """Endpoint works with default params."""
        r = client.get("/memory/duplicates")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp047_near_duplicates.py::TestDuplicatesEndpoint -v`
Expected: FAIL — endpoint doesn't exist (404).

- [ ] **Step 3: Add Pydantic models and endpoint**

In `memory_service/main.py`, add models:

```python
class DuplicateMemoryRef(BaseModel):
    id: str
    text: str


class DuplicatePair(BaseModel):
    a: DuplicateMemoryRef
    b: DuplicateMemoryRef
    similarity: float
```

Add endpoint:

```python
@app.get("/memory/duplicates", response_model=List[DuplicatePair])
async def find_duplicates(
    request: Request,
    threshold: float = Query(default=None),
    limit: int = Query(default=None, ge=1, le=100),
) -> List[DuplicatePair]:
    effective_threshold = threshold if threshold is not None else request.app.state.settings.near_duplicate_threshold
    effective_limit = limit if limit is not None else request.app.state.settings.near_duplicate_limit
    try:
        with request.app.state.driver.session() as session:
            pairs = memory_repo.find_near_duplicates(session, effective_threshold, effective_limit)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [DuplicatePair(**p) for p in pairs]
```

Note: Check how `settings` is accessed in the existing endpoints. If `request.app.state.settings` is not the pattern, use the `settings` import from config directly. Looking at `main.py`, `settings` is imported at module level — use that:

```python
@app.get("/memory/duplicates", response_model=List[DuplicatePair])
async def find_duplicates(
    request: Request,
    threshold: float = Query(default=None),
    limit: int = Query(default=None, ge=1, le=100),
) -> List[DuplicatePair]:
    effective_threshold = threshold if threshold is not None else settings.near_duplicate_threshold
    effective_limit = limit if limit is not None else settings.near_duplicate_limit
    try:
        with request.app.state.driver.session() as session:
            pairs = memory_repo.find_near_duplicates(session, effective_threshold, effective_limit)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [DuplicatePair(**p) for p in pairs]
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `pytest tests/test_wp047_near_duplicates.py::TestDuplicatesEndpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add memory_service/main.py tests/test_wp047_near_duplicates.py
git commit -m "WP-047: add GET /memory/duplicates endpoint"
```

---

### Task 4: Client, CLI, and MCP wiring

**Files:**
- Modify: `memory_client/client.py`
- Modify: `memory_client/cli.py`
- Modify: `mcp_server/server.py`
- Test: `tests/test_wp047_near_duplicates.py`

- [ ] **Step 1: Add unit tests**

Append to `tests/test_wp047_near_duplicates.py`:

```python
import json

import httpx
import respx
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner

from memory_client.cli import app as cli_app
from memory_client.client import MemoryClient

_BASE_URL = "http://localhost:8000"
_cli_runner = CliRunner()

_SAMPLE_PAIRS = [
    {
        "a": {"id": "id-1", "text": "Memory one"},
        "b": {"id": "id-2", "text": "Memory two"},
        "similarity": 0.95,
    }
]


# ---------------------------------------------------------------------------
# Task 4 — Unit: client, CLI, MCP
# ---------------------------------------------------------------------------
class TestClientFindDuplicates:
    @respx.mock
    def test_find_duplicates_default(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=_SAMPLE_PAIRS)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.find_duplicates()
        assert len(result) == 1
        assert result[0]["similarity"] == 0.95

    @respx.mock
    def test_find_duplicates_with_params(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=_SAMPLE_PAIRS)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.find_duplicates(threshold=0.90, limit=5)
        req = respx.calls.last.request
        assert "threshold=0.9" in str(req.url)
        assert "limit=5" in str(req.url)


class TestCliFindDuplicates:
    @respx.mock
    def test_find_duplicates_output(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=_SAMPLE_PAIRS)
        )
        result = _cli_runner.invoke(cli_app, ["find-duplicates"])
        assert result.exit_code == 0
        assert "0.95" in result.output
        assert "id-1" in result.output

    @respx.mock
    def test_find_duplicates_empty(self):
        respx.get(f"{_BASE_URL}/memory/duplicates").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = _cli_runner.invoke(cli_app, ["find-duplicates"])
        assert result.exit_code == 0
        assert "No near-duplicate" in result.output


class TestMcpFindDuplicates:
    def test_find_duplicates_calls_client(self):
        from mcp_server.server import memory_find_duplicates

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.find_duplicates.return_value = _SAMPLE_PAIRS

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_find_duplicates()

        mock_client.find_duplicates.assert_called_once_with(threshold=None, limit=None)
        assert len(result) == 1
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_wp047_near_duplicates.py -k "TestClient or TestCli or TestMcp" -v`
Expected: FAIL — methods/commands/tools don't exist.

- [ ] **Step 3: Add `find_duplicates` to MemoryClient**

In `memory_client/client.py`, add:

```python
    def find_duplicates(
        self, *, threshold: float | None = None, limit: int | None = None
    ) -> list[dict]:
        """GET /memory/duplicates. Returns near-duplicate pairs."""
        params: dict = {}
        if threshold is not None:
            params["threshold"] = threshold
        if limit is not None:
            params["limit"] = limit
        response = self._http.get("/memory/duplicates", params=params)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Add `find-duplicates` CLI command**

In `memory_client/cli.py`, add:

```python
@app.command("find-duplicates")
def find_duplicates(
    threshold: Optional[float] = typer.Option(None, "--threshold", "-t", help="Similarity threshold (0-1)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max pairs to return"),
) -> None:
    """Find near-duplicate memory pairs for review."""
    try:
        with _make_client() as client:
            pairs = client.find_duplicates(threshold=threshold, limit=limit)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not pairs:
        console.print("No near-duplicate pairs found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Similarity", style="bold")
    table.add_column("Memory A ID", style="dim")
    table.add_column("Memory A Text")
    table.add_column("Memory B ID", style="dim")
    table.add_column("Memory B Text")
    for p in pairs:
        table.add_row(
            f"{p['similarity']:.4f}",
            p["a"]["id"][:12],
            p["a"]["text"][:60],
            p["b"]["id"][:12],
            p["b"]["text"][:60],
        )
    console.print(table)
```

- [ ] **Step 5: Add `memory_find_duplicates` MCP tool**

In `mcp_server/server.py`, add:

```python
@mcp.tool
def memory_find_duplicates(
    threshold: float | None = None, limit: int | None = None
) -> list[dict]:
    """Find near-duplicate memory pairs above a similarity threshold for review and merge."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.find_duplicates(threshold=threshold, limit=limit)
```

Update the module docstring to include `memory_find_duplicates`.

- [ ] **Step 6: Run tests — expect PASS**

Run: `pytest tests/test_wp047_near_duplicates.py -k "TestClient or TestCli or TestMcp" -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add memory_client/client.py memory_client/cli.py mcp_server/server.py tests/test_wp047_near_duplicates.py
git commit -m "WP-047: wire find-duplicates through client, CLI, and MCP"
```

---

### Task 5: Finalise — BACKLOG update and /simplify

- [ ] **Step 1: Move WP-047 to Completed in BACKLOG.md**
- [ ] **Step 2: Run `/simplify`**
- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-047: update BACKLOG — mark complete"
```
