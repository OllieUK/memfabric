# WP-032: End-to-End Companion Validation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two spec deviations in the wake-up CLI output (strand grouping + topic section), then run a real companion session (wake-up → work → close-out) to validate all five criteria from the spec.

**Architecture:** The backend `wake_up()` runs two independent searches and returns them as two separate lists in the response — one for importance-ranked ("core"), one for topic-only results. The CLI displays each list in its own section. This matches spec Section 4.2 exactly: each section gets up to `--limit` items independently. The `WakeUpResponse` schema gains a `topic_memories` field (list, only populated when `--topic` provided); existing `memories` field becomes the core list.

**Tech Stack:** Python, FastAPI, neo4j driver (Bolt), Typer/Rich CLI, pytest, respx (unit mocks)

---

## Spec reference

`docs/superpowers/specs/2026-03-21-companion-integration-design.md` — Section 4.2 (wake-up output format) and Section 7 (validation criteria).

**Five validation criteria (Section 7):**
1. `memory wake-up` returns a non-empty briefing with at least one memory grouped by strand
2. At least one memory from the briefing is directly referenced or used during the session
3. At least one new memory is added using a strand ID retrieved from `memory list-strands`
4. `memory close-session` scaffold is used and produces at least one `memory add-memory` call
5. The memory added at close-out appears in the next `memory wake-up` briefing

---

## What is NOT changing

- `close-session` is already correct per spec; no changes needed.
- `MemoryClient.wake_up()` response shape changes (new `topic_memories` key) — `client.py` gains a new `wake_up_split()` method rather than changing the existing `wake_up()` signature, which would break existing tests. The CLI calls `wake_up_split()`; the existing `wake_up()` method is left unchanged.
- `list-strands`, `add-memory`, `search-memory`, `close-session` CLI commands: no changes.

---

## File map

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | `wake_up()`: return `{"core": [...], "topic": [...]}` dict; add `strand_id` to each item via `OPTIONAL MATCH IN_STRAND` |
| `memory_service/main.py` | `WakeUpMemoryItem`: add `strand_id`; `WakeUpResponse`: add `topic_memories` list; endpoint updated |
| `memory_client/client.py` | Add `wake_up_split()` method returning `(core, topic)` tuple |
| `memory_client/cli.py` | `wake_up` command: call `wake_up_split()`, group each list by `strand_id`, render two sections |
| `tests/test_wake_up_close_session.py` | Update fixtures; add new unit tests for split output; update assertions |

---

## Task 1: Backend — return strand_id per memory and two separate lists

**Files:**
- Modify: `memory_service/memory_repo.py` — `wake_up()`
- Modify: `memory_service/main.py` — `WakeUpMemoryItem`, `WakeUpResponse`, `wake_up` endpoint

The current `wake_up()` returns a single merged list. We change it to return a dict with two keys: `core` (importance-ranked, up to `limit`) and `topic` (topic-only results not in core, up to `limit`). Both lists include `strand_id` resolved via `OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)`.

### Why a dict return instead of two separate functions

A single `wake_up()` call that opens one session and runs both queries is cleaner than two separate repo calls at the endpoint level. The endpoint unpacks the dict into two response fields.

- [ ] **Step 1.1: Write the failing integration tests**

Add tests `I5` and `I6` to `tests/test_wake_up_close_session.py`:

```python
@pytest.mark.integration
def test_wake_up_response_has_strand_id(client):
    """I5 — Each memory item includes a strand_id field (may be None for unseeded memories)."""
    resp = client.get("/memory/wake-up", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert "memories" in data
    for mem in data["memories"]:
        assert "strand_id" in mem  # field present; None is acceptable

@pytest.mark.integration
def test_wake_up_with_topic_returns_topic_memories(client):
    """I6 — With --topic, response has both 'memories' (core) and 'topic_memories' fields."""
    resp = client.get("/memory/wake-up", params={"limit": 5, "topic": "graph memory"})
    assert resp.status_code == 200
    data = resp.json()
    assert "memories" in data
    assert "topic_memories" in data
    assert isinstance(data["topic_memories"], list)
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
pytest tests/test_wake_up_close_session.py::test_wake_up_response_has_strand_id tests/test_wake_up_close_session.py::test_wake_up_with_topic_returns_topic_memories -v -m integration
```

Expected: FAIL — `strand_id` absent, `topic_memories` absent.

- [ ] **Step 1.3: Update `wake_up()` in `memory_repo.py`**

Replace the existing `wake_up()` function:

```python
def wake_up(session, limit: int, topic_embedding: list | None = None) -> dict:
    """Return memories for session start as two separate lists.

    Returns:
        dict with keys:
          "core"  — importance-ranked list, up to `limit` items
          "topic" — topic-only items (not in core), up to `limit` items;
                    empty list when topic_embedding is None
        Each item dict: id, text, type, tags, importance, created_at, strand_id
    """
    result = session.run(
        """
        MATCH (m:Memory)
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        ORDER BY m.importance DESC, m.created_at DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    core = [_record_to_memory_dict(r) for r in result]

    if topic_embedding is None:
        return {"core": core, "topic": []}

    core_ids = {item["id"] for item in core}

    topic_result = session.run(
        """
        CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
        YIELD node AS m, distance
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        """,
        limit=limit,
        query_vec=topic_embedding,
    )
    topic = [_record_to_memory_dict(r) for r in topic_result if r["id"] not in core_ids]

    return {"core": core, "topic": topic}
```

Update `_record_to_memory_dict` to handle `strand_id` — but only by reading the key that is now always present in the query result. Do **not** use `.get()` with a default; instead add `strand_id` as an explicit key in the return dict, matched to the query's SELECT list:

```python
def _record_to_memory_dict(record) -> dict:
    """Extract the standard Memory field set from a neo4j Record."""
    return {
        "id": record["id"],
        "text": record["text"],
        "type": record["type"],
        "tags": record["tags"],
        "importance": record["importance"],
        "created_at": record["created_at"],
        "strand_id": record["strand_id"],  # always present: OPTIONAL MATCH returns None if no strand
    }
```

> Note: `_record_to_memory_dict` is only called by `wake_up()`. Any future caller must ensure `strand_id` is in the query's result set. This constraint is documented in the function's docstring.

Update the docstring:

```python
def _record_to_memory_dict(record) -> dict:
    """Extract the standard Memory field set from a neo4j Record.

    Caller MUST select: id, text, type, tags, importance, created_at, strand_id
    in the Cypher query. strand_id may be None (from OPTIONAL MATCH).
    """
```

- [ ] **Step 1.4: Update `main.py` — add `strand_id` to `WakeUpMemoryItem` and `topic_memories` to `WakeUpResponse`**

```python
class WakeUpMemoryItem(BaseModel):
    id: str
    text: str
    type: MemoryType
    tags: List[str]
    importance: Optional[int] = None
    created_at: Optional[str] = None
    strand_id: Optional[str] = None

class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]          # core (importance-ranked)
    topic_memories: List[WakeUpMemoryItem]    # topic-only; empty when no --topic
```

Update the endpoint:

```python
@app.get("/memory/wake-up", response_model=WakeUpResponse)
async def wake_up(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
) -> WakeUpResponse:
    topic_embedding = get_embedding(topic) if topic else None
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.wake_up(session, limit=limit, topic_embedding=topic_embedding)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return WakeUpResponse(
        memories=[WakeUpMemoryItem(**r) for r in result["core"]],
        topic_memories=[WakeUpMemoryItem(**r) for r in result["topic"]],
    )
```

- [ ] **Step 1.5: Run the integration tests**

```bash
pytest tests/test_wake_up_close_session.py::test_wake_up_response_has_strand_id tests/test_wake_up_close_session.py::test_wake_up_with_topic_returns_topic_memories -v -m integration
```

Expected: PASS.

- [ ] **Step 1.6: Run the full wake-up test suite**

```bash
pytest tests/test_wake_up_close_session.py -v
```

Existing unit tests mock `GET /memory/wake-up` to return `_WAKE_UP_RESPONSE` which only has `"memories"` — the new `topic_memories` field is additive and has a default of `[]`, so Pydantic will deserialise it correctly. Existing tests should still pass.

If any test fails because the mock response doesn't include `topic_memories`, update `_WAKE_UP_RESPONSE` fixture:

```python
_WAKE_UP_RESPONSE = {
    "memories": [
        {
            "id": "mem-aaa",
            "text": "The user has ADHD and benefits from short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "The user prefers async communication over meetings.",
            "type": "observation",
            "tags": ["strand-core-work"],
            "strand_id": "strand-core-work",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        },
    ],
    "topic_memories": [],
}
```

Also update the test assertion in `test_exits_zero_and_shows_memories` that checks `"Oliver has ADHD"`:
```python
assert "The user has ADHD" in result.output
```

- [ ] **Step 1.7: Commit**

```bash
git add memory_service/memory_repo.py memory_service/main.py tests/test_wake_up_close_session.py
git commit -m "fix: wake-up returns strand_id per memory and separate topic_memories list"
```

---

## Task 2: Client — add `wake_up_split()` method

**Files:**
- Modify: `memory_client/client.py`

Adding a new method rather than changing `wake_up()` avoids breaking existing callers and tests.

- [ ] **Step 2.1: Write failing unit test**

Add to `tests/test_wake_up_close_session.py`:

```python
class TestWakeUpSplitClient:
    @respx.mock
    def test_returns_core_and_topic_lists(self):
        respx.get(f"{BASE}/memory/wake-up").mock(
            return_value=httpx.Response(200, json={
                "memories": [{"id": "mem-aaa", "text": "core memory", "type": "fact",
                               "tags": [], "strand_id": "strand-core-health",
                               "importance": 5, "created_at": "2026-01-01T00:00:00+00:00"}],
                "topic_memories": [{"id": "mem-bbb", "text": "topic memory", "type": "fact",
                                    "tags": [], "strand_id": "strand-companion-gmf",
                                    "importance": 3, "created_at": "2026-01-02T00:00:00+00:00"}],
            })
        )
        with MemoryClient(base_url=BASE) as client:
            core, topic = client.wake_up_split(limit=10, topic="graph memory")
        assert len(core) == 1
        assert core[0]["id"] == "mem-aaa"
        assert len(topic) == 1
        assert topic[0]["id"] == "mem-bbb"
```

- [ ] **Step 2.2: Run test to confirm it fails**

```bash
pytest tests/test_wake_up_close_session.py::TestWakeUpSplitClient -v
```

Expected: FAIL — `wake_up_split` not defined.

- [ ] **Step 2.3: Add `wake_up_split()` to `client.py`**

```python
def wake_up_split(
    self, *, limit: int = 20, topic: str | None = None
) -> tuple[list[dict], list[dict]]:
    """GET /memory/wake-up. Returns (core_memories, topic_memories) tuple.

    core_memories: importance-ranked list (always populated if DB has memories)
    topic_memories: topic-only results (empty when no topic provided)
    """
    params: dict = {"limit": limit}
    if topic is not None:
        params["topic"] = topic
    response = self._http.get("/memory/wake-up", params=params)
    response.raise_for_status()
    data = response.json()
    return data["memories"], data.get("topic_memories", [])
```

- [ ] **Step 2.4: Run the test**

```bash
pytest tests/test_wake_up_close_session.py::TestWakeUpSplitClient -v
```

Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add memory_client/client.py tests/test_wake_up_close_session.py
git commit -m "feat: MemoryClient.wake_up_split() returns (core, topic) tuple"
```

---

## Task 3: CLI — group by strand_id and render two sections

**Files:**
- Modify: `memory_client/cli.py` — `wake_up` command

- [ ] **Step 3.1: Write failing unit tests**

Add to `tests/test_wake_up_close_session.py`:

```python
_SPLIT_WAKE_UP_RESPONSE = {
    "memories": [
        {
            "id": "mem-aaa",
            "text": "The user has ADHD and benefits from short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "The user prefers async communication over meetings.",
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
            "text": "The user is building the graph-memory-fabric project.",
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
            "text": "The user has ADHD and benefits from short feedback loops.",
            "type": "fact",
            "tags": ["strand-core-health"],
            "strand_id": "strand-core-health",
            "importance": 5,
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "mem-bbb",
            "text": "The user prefers async communication over meetings.",
            "type": "observation",
            "tags": ["strand-core-work"],
            "strand_id": "strand-core-work",
            "importance": 4,
            "created_at": "2026-01-02T00:00:00+00:00",
        },
        {
            "id": "mem-ddd",
            "text": "The user exercises regularly to manage energy levels.",
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
        assert "graph-memory-fabric project" in result.output

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
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
pytest tests/test_wake_up_close_session.py::TestWakeUpCLIOutput -v
```

Expected: FAIL.

- [ ] **Step 3.3: Update `wake_up` command in `cli.py`**

Replace the existing `wake_up` command body:

```python
@app.command("wake-up")
def wake_up(
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Topic to focus the session on"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="Max memories to return"),
) -> None:
    """Print a memory briefing for session start."""
    try:
        with _make_client() as client:
            core, topic_memories = client.wake_up_split(limit=limit, topic=topic)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    heading = f"[bold]## Memory briefing — {topic if topic else 'general session'}[/bold]"
    console.print(heading)

    def _render_section(items: list) -> None:
        if not items:
            console.print("  No memories found.")
            return
        # Sort before groupby: itertools.groupby only groups consecutive equal-key items
        sorted_items = sorted(items, key=lambda m: m.get("strand_id") or "(no strand)")
        for strand_id, group in groupby(sorted_items, key=lambda m: m.get("strand_id") or "(no strand)"):
            console.print(f"\n[dim]{strand_id}[/dim]")
            for mem in group:
                imp = str(mem.get("importance") or "")
                console.print(f"  [{imp}] [bold]{mem['type']}[/bold] — {mem['text']}")

    console.print("\n[bold cyan]### Core context[/bold cyan]")
    _render_section(core)

    # Render topic section only when topic was provided AND there are topic-only results
    if topic and topic_memories:
        console.print("\n[bold cyan]### Relevant to today[/bold cyan]")
        _render_section(topic_memories)
```

- [ ] **Step 3.4: Run the new CLI tests**

```bash
pytest tests/test_wake_up_close_session.py::TestWakeUpCLIOutput -v
```

Expected: all 4 tests PASS.

- [ ] **Step 3.5: Run the full test suite**

```bash
pytest tests/test_wake_up_close_session.py -v
```

Existing tests `U4` and `U5` mock `GET /memory/wake-up` to return `_WAKE_UP_RESPONSE` (no `topic_memories` key). The new `wake_up_split()` client method uses `.get("topic_memories", [])` so this is handled gracefully. `U4` and `U5` still call `runner.invoke(app, ["wake-up"])` — the CLI now calls `client.wake_up_split()`, not `client.wake_up()`. The mock URL is the same, so respx intercepts correctly.

- [ ] **Step 3.6: Commit**

```bash
git add memory_client/cli.py tests/test_wake_up_close_session.py
git commit -m "fix: wake-up CLI groups by strand_id, renders Relevant to today section"
```

---

## Task 4: Validation session — run end-to-end against the live stack

**No code produced.** This task is a live companion session. Run it and record evidence for each criterion.

**Pre-flight: verify the stack is up**

- [ ] **Step 4.1: Check services are running**

```bash
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}
```

If not running:
```bash
docker compose up -d
uvicorn memory_service.main:app --reload &
```

- [ ] **Step 4.2: Verify memories exist in the DB**

```bash
python -m memory_client.cli wake-up --limit 5
```

Expected: non-empty briefing. If empty, re-seed (the 12 Notion Vault entries were seeded in WP-030 — if DB was reset, add at least one seed memory):

```bash
python scripts/seed_strands.py
python -m memory_client.cli add-memory \
  "The user is building the graph-memory-fabric project as a local-first memory system for AI companions." \
  --type fact \
  --strand-id strand-companion-graph-memory-fabric \
  --importance 5
```

---

**Criterion 1: wake-up returns a non-empty briefing with at least one memory grouped by strand**

- [ ] **Step 4.3: Run wake-up and record output**

```bash
python -m memory_client.cli wake-up --topic "graph memory fabric"
```

Evidence to record:
- Non-empty briefing returned? (Y/N)
- At least one memory appears under a strand ID header? (Y/N)
- `### Core context` section present? (Y/N)
- `### Relevant to today` section present (given `--topic` was provided and topic hits exist)? (Y/N)

---

**Criterion 2: at least one memory from the briefing is referenced during the session**

- [ ] **Step 4.4: Reference a memory from the briefing**

Read the briefing. Pick one memory. Add a new memory that acknowledges it:

```bash
python -m memory_client.cli add-memory \
  "The user confirmed during WP-032 validation that [paste text of referenced memory] remains accurate." \
  --type observation \
  --strand-id <strand-id-of-referenced-memory> \
  --importance 2
```

Evidence to record: memory ID returned.

---

**Criterion 3: at least one new memory added using a strand ID from `memory list-strands`**

- [ ] **Step 4.5: List strands and pick one**

```bash
python -m memory_client.cli list-strands
```

Pick any strand ID from the output.

- [ ] **Step 4.6: Add a memory using that strand ID**

```bash
python -m memory_client.cli add-memory \
  "The user validated the companion session loop (WP-032) end-to-end against the live stack." \
  --type event \
  --strand-id <strand-id-from-list-strands> \
  --importance 4
```

Evidence to record: strand ID used, memory ID returned.

---

**Criterion 4: `memory close-session` scaffold produces at least one `memory add-memory` call**

- [ ] **Step 4.7: Run close-session and follow the scaffold**

```bash
python -m memory_client.cli close-session
```

Read the scaffold. Answer at least one question. Execute the corresponding `memory add-memory` command.

Evidence to record: which scaffold question was answered, the `memory add-memory` command run, the memory ID returned.

---

**Criterion 5: the memory added at close-out appears in the next wake-up**

- [ ] **Step 4.8: Run wake-up and verify close-out memory is present**

```bash
python -m memory_client.cli wake-up --limit 30
```

Scan the output for the text of the memory added in Step 4.7. If not visible in the briefing (may be ranked below the limit), search directly:

```bash
python -m memory_client.cli search-memory "WP-032 companion session"
```

Evidence to record: close-out memory present in next wake-up? (Y/N)

---

**Step 4.9: Record findings**

Create `docs/wp-032-validation-evidence.md`:

```markdown
# WP-032 Validation Evidence
Date: YYYY-MM-DD

## Criteria checklist

| # | Criterion | Result | Notes |
|---|-----------|--------|-------|
| 1 | wake-up returns non-empty briefing grouped by strand | PASS/FAIL | |
| 2 | briefing memory referenced during session | PASS/FAIL | memory ID: |
| 3 | memory added using strand ID from list-strands | PASS/FAIL | strand: , memory ID: |
| 4 | close-session scaffold produced add-memory call | PASS/FAIL | memory ID: |
| 5 | close-out memory appears in next wake-up | PASS/FAIL | |

## Gaps and findings

[List any friction, missing features, or awkward interactions discovered during the session]

## Backlog items to add

[Any new WP candidates discovered]
```

- [ ] **Step 4.10: Commit evidence + update BACKLOG.md**

Move WP-032 to Currently In Progress (if not already done at start), then to Completed. Add retrospective note. Add any new backlog items found.

```bash
git add docs/wp-032-validation-evidence.md BACKLOG.md
git commit -m "WP-032: end-to-end companion validation — evidence and gap list"
```

---

## Acceptance criteria checklist

- [ ] `GET /memory/wake-up` response includes `strand_id` on each memory item and `topic_memories` list
- [ ] `memory wake-up` CLI groups memories by `strand_id` (not tag)
- [ ] `memory wake-up --topic "..."` displays `### Relevant to today` section when topic-only memories exist
- [ ] `memory wake-up --topic "..."` omits `### Relevant to today` when all topic results already in core
- [ ] `memory wake-up` (no `--topic`) shows only `### Core context`
- [ ] All existing unit tests in `test_wake_up_close_session.py` still pass
- [ ] New unit/integration tests (`I5`, `I6`, `TestWakeUpSplitClient`, `TestWakeUpCLIOutput`) pass
- [ ] All five spec validation criteria confirmed with evidence in `docs/wp-032-validation-evidence.md`
- [ ] BACKLOG.md updated: WP-032 in Completed, retrospective note added

---

## Test run commands (reference)

```bash
# Unit tests only (no live stack needed)
pytest tests/test_wake_up_close_session.py -v -m "not integration"

# Integration tests (live stack required)
pytest tests/test_wake_up_close_session.py -v -m integration

# All WP-032 tests
pytest tests/test_wake_up_close_session.py -v

# Full suite
pytest -v
```
