# WP-037 Implementation Plan — Person nodes + `ABOUT` edges

**Date:** 2026-03-21
**Spec:** `docs/superpowers/specs/2026-03-21-wp-037-person-nodes-design.md`
**Test plan:** Embedded below (from `engineering:testing-strategy`)

---

## Test plan summary

| Layer | Class | Tests | Stack |
|-------|-------|-------|-------|
| Unit | `TestCreatePersonRequestModel` | 4 | None |
| Unit | `TestMemoryClientListPersons` | 4 | respx mock |
| Unit | `TestMemoryClientCreatePerson` | 6 | respx mock |
| Unit | `TestListPersonsCLI` | 6 | respx + CliRunner |
| Unit | `TestCreatePersonCLI` | 5 | respx + CliRunner |
| Unit | `TestMcpListPersons` | 3 | patch MemoryClient |
| Unit | `TestMcpCreatePerson` | 4 | patch MemoryClient |
| Integration | `TestGetPersonEndpoint` | 5 | live Memgraph + TestClient |
| Integration | `TestPostPersonEndpoint` | 10 | live Memgraph + TestClient |
| Integration | `TestAboutEdgeViaPostMemory` | 4 | live Memgraph + TestClient |
| Integration | `TestAboutEdgeViaPostPerson` | 2 | live Memgraph + TestClient |
| Integration | `TestMigratePersonNodesScript` | 6 | live Memgraph |
| **Total** | | **59** | |

All integration tests use the `client` and `test_driver` fixtures from `conftest.py`. No mocking of Memgraph. Test file: `tests/test_wp037_person_nodes.py`.

---

## Tasks

### Task 1 — Unit tests for `CreatePersonRequest` model (4 tests)
**File:** `tests/test_wp037_person_nodes.py` (new)
**Stack:** No live services

#### Steps

1. Create `tests/test_wp037_person_nodes.py` with module imports:
   ```python
   import pytest
   from pydantic import ValidationError
   from memory_service.main import CreatePersonRequest
   ```

2. Write class `TestCreatePersonRequestModel` with 4 tests:
   - `test_id_and_name_required_fields` — `CreatePersonRequest()` with no args raises `ValidationError`
   - `test_name_required_field` — `CreatePersonRequest(id="x")` with no `name` raises `ValidationError`
   - `test_description_defaults_to_none` — `CreatePersonRequest(id="x", name="X")` has `.description is None`
   - `test_description_accepted_as_string` — `CreatePersonRequest(id="x", name="X", description="bio")` stores description correctly

3. Run `pytest tests/test_wp037_person_nodes.py::TestCreatePersonRequestModel -v` — all 4 should fail (model not yet defined). Mark "red".

---

### Task 2 — API models + endpoints in `memory_service/main.py`
**File:** `memory_service/main.py`

#### Steps

4. Add `PersonItem`, `PersonsResponse`, `CreatePersonRequest` Pydantic models after the `StrandsResponse` block (around line 186):
   ```python
   class PersonItem(BaseModel):
       id: str
       name: str
       description: Optional[str] = None

   class PersonsResponse(BaseModel):
       persons: List[PersonItem]

   class CreatePersonRequest(BaseModel):
       id: str
       name: str
       description: Optional[str] = None
   ```

5. Add `GET /person` endpoint after `list_strands`:
   ```python
   @app.get("/person", response_model=PersonsResponse)
   async def list_persons(request: Request) -> PersonsResponse:
       try:
           with request.app.state.driver.session() as session:
               persons = memory_repo.list_persons(session)
       except ServiceUnavailable as exc:
           raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
       return PersonsResponse(persons=[PersonItem(**p) for p in persons])
   ```

6. Add `POST /person` endpoint immediately after:
   ```python
   @app.post("/person", response_model=PersonItem)
   async def create_person(req: CreatePersonRequest, request: Request) -> PersonItem:
       try:
           with request.app.state.driver.session() as session:
               person = memory_repo.upsert_person(session, req)
       except ServiceUnavailable as exc:
           raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
       return PersonItem(**person)
   ```

7. Run `TestCreatePersonRequestModel` again — all 4 should now pass.

---

### Task 3 — Repository functions in `memory_service/memory_repo.py`
**File:** `memory_service/memory_repo.py`

#### Steps

8. Add `list_persons(session)` after the `list_strands` function (end of file):
   ```python
   def list_persons(session) -> list[dict]:
       """Return all Person nodes ordered by id."""
       result = session.run(
           "MATCH (p:Person) RETURN p.id AS id, p.name AS name, "
           "p.description AS description ORDER BY p.id"
       )
       return [
           {"id": r["id"], "name": r["name"], "description": r["description"]}
           for r in result
       ]
   ```

9. Add `upsert_person(session, req)` immediately after:
   ```python
   def upsert_person(session, req) -> dict:
       """Create or update a Person node by id. Returns the stored values."""
       result = session.run(
           """
           MERGE (p:Person {id: $id})
           SET p.name = $name, p.description = $description
           RETURN p.id AS id, p.name AS name, p.description AS description
           """,
           id=req.id,
           name=req.name,
           description=req.description,
       )
       record = result.single()
       return {"id": record["id"], "name": record["name"], "description": record["description"]}
   ```

---

### Task 4 — Integration tests for `GET /person` and `POST /person`
**File:** `tests/test_wp037_person_nodes.py`
**Stack:** live Memgraph + `TestClient`

Shared test constants (add at module top after imports):
```python
_PERSON_ID_A = "test-person-wp037-a"
_PERSON_ID_B = "test-person-wp037-b"
_AGENT_ID = "test-agent-wp037"
```

Cleanup helper (add as module-level function):
```python
def _cleanup_persons(driver, *person_ids, memory_ids=()):
    from tests.conftest import cleanup_nodes
    cleanup_nodes(driver, *memory_ids, extra_ids={"Agent": _AGENT_ID})
    with driver.session() as session:
        for pid in person_ids:
            session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=pid)
```

#### Steps

10. Write `TestGetPersonEndpoint` (5 tests) using `client` and `test_driver` fixtures:
    - `test_returns_200_with_persons_key` — GET /person returns 200 with `"persons"` key
    - `test_returns_list_type` — `persons` is a JSON array
    - `test_newly_created_person_appears_in_list` — POST /person then GET /person; item with matching id is present
    - `test_list_ordered_by_id` — insert `"zzz-test"` then `"aaa-test"`; GET /person returns them sorted ascending
    - `test_person_item_has_required_fields` — each item has `"id"` (str), `"name"` (str), `"description"` (present, may be null)

11. Write `TestPostPersonEndpoint` (10 tests):
    - `test_returns_200_with_person_fields` — POST returns 200 body with id/name/description
    - `test_person_node_exists_in_graph_after_create` — `node_exists(test_driver, "Person", id)` True
    - `test_create_without_description_stores_null` — description field is null in response
    - `test_create_with_description_stores_value` — description field matches provided string
    - `test_upsert_updates_name_on_second_call` — POST same id twice, different name; second response has new name
    - `test_upsert_updates_description_on_second_call` — POST same id twice, different description; second response has new description
    - `test_upsert_does_not_create_duplicate_node` — POST same id twice; `MATCH (p:Person {id: $id}) RETURN count(p)` = 1
    - `test_missing_id_returns_422` — body without `id` → 422
    - `test_missing_name_returns_422` — body without `name` → 422
    - `test_503_when_db_unavailable` — inject mock driver raising `ServiceUnavailable`; POST /person → 503

12. Run `pytest tests/test_wp037_person_nodes.py -k "TestGetPerson or TestPostPerson" -v` — should all pass.

---

### Task 5 — Integration tests for `ABOUT` edges (regression + combined flow)
**File:** `tests/test_wp037_person_nodes.py`

#### Steps

13. Write `TestAboutEdgeViaPostMemory` (4 tests) — guard existing behaviour:
    - `test_about_edge_created_when_person_id_provided` — POST /memory with `person_ids=["test-person-wp037-a"]`; `edge_exists(driver, memory_id, "ABOUT", _PERSON_ID_A)` True
    - `test_person_node_created_implicitly_by_add_memory` — POST /memory with unknown person id; `node_exists(driver, "Person", id)` True
    - `test_no_about_edge_when_person_ids_empty` — POST /memory with `person_ids=[]`; no ABOUT edge to any Person from that memory
    - `test_multiple_person_ids_create_multiple_about_edges` — two person ids in one request; both ABOUT edges exist

14. Write `TestAboutEdgeViaPostPerson` (2 tests):
    - `test_post_person_then_post_memory_creates_about_edge` — explicit POST /person, then POST /memory with that person_id; edge_exists True
    - `test_about_edge_is_idempotent` — POST /memory twice to same person_id; exactly 1 ABOUT edge from each memory

15. Run full integration tests so far: `pytest tests/test_wp037_person_nodes.py -v -k "not Migrate and not CLI and not Mcp and not Client"` — all should pass.

---

### Task 6 — Unit tests for `MemoryClient.list_persons` and `MemoryClient.create_person`
**File:** `tests/test_wp037_person_nodes.py`

Uses `respx` for HTTP mocking (same pattern as `test_list_strands.py`).

#### Steps

16. Write `TestMemoryClientListPersons` (4 tests) with `respx.mock`:
    - `test_calls_get_person_endpoint` — `list_persons()` sends GET to `/person`
    - `test_returns_list_of_person_dicts` — `{"persons": [{...}]}` response; return value is the list
    - `test_returns_empty_list_when_no_persons` — `{"persons": []}` response; empty list returned (not error)
    - `test_raises_on_503` — 503 response raises `httpx.HTTPStatusError`

17. Write `TestMemoryClientCreatePerson` (6 tests):
    - `test_calls_post_person_endpoint` — POST to `/person`
    - `test_body_contains_id_and_name` — request body has `"id"` and `"name"`
    - `test_description_omitted_when_none` — `description=None` means key absent from body
    - `test_description_sent_when_provided` — `description="bio"` → `"description": "bio"` in body
    - `test_returns_person_dict_from_response` — response parsed as dict and returned
    - `test_raises_on_422` — 422 response raises `httpx.HTTPStatusError`

---

### Task 7 — `MemoryClient.list_persons` and `MemoryClient.create_person`
**File:** `memory_client/client.py`

#### Steps

18. Add `list_persons` method after `list_strands`:
    ```python
    def list_persons(self) -> list[dict]:
        """GET /person. Returns list of person dicts: id, name, description."""
        response = self._http.get("/person")
        response.raise_for_status()
        return response.json()["persons"]
    ```

19. Add `create_person` method immediately after:
    ```python
    def create_person(self, person_id: str, name: str, description: str | None = None) -> dict:
        """POST /person. Creates or merges a Person node. Returns person dict."""
        body: dict = {"id": person_id, "name": name}
        if description is not None:
            body["description"] = description
        response = self._http.post("/person", json=body)
        response.raise_for_status()
        return response.json()
    ```

20. Run `pytest tests/test_wp037_person_nodes.py -k "TestMemoryClient" -v` — all 10 should pass.

---

### Task 8 — Unit tests for CLI commands
**File:** `tests/test_wp037_person_nodes.py`

Uses `respx` + `typer.testing.CliRunner`.

#### Steps

21. Write `TestListPersonsCLI` (6 tests):
    - `test_exits_zero_on_success` — 200 response; exit code 0
    - `test_renders_person_id_in_output` — `_PERSON_ID_A` in output
    - `test_renders_person_name_in_output` — `"Test Person A"` in output
    - `test_empty_persons_prints_no_persons_found` — `{"persons": []}` → `"No persons found."` in output
    - `test_service_error_exits_nonzero` — 503 → exit 1
    - `test_connect_error_exits_nonzero` — `ConnectError` → exit 1

22. Write `TestCreatePersonCLI` (5 tests):
    - `test_exits_zero_and_prints_id` — 200 response; exit 0; person id in output
    - `test_name_option_is_required` — missing `--name` → exit non-zero before HTTP
    - `test_sends_correct_body_without_description` — body has `id` and `name`, no `description`
    - `test_sends_description_when_provided` — `--description "bio"` → body has `"description": "bio"`
    - `test_service_error_exits_nonzero` — 422 → exit 1

---

### Task 9 — CLI commands in `memory_client/cli.py`
**File:** `memory_client/cli.py`

#### Steps

23. Add `list-persons` command after the `list-strands` command (before `wake-up`):
    ```python
    @app.command("list-persons")
    def list_persons() -> None:
        """List all Person nodes in the memory fabric."""
        try:
            with _make_client() as client:
                persons = client.list_persons()
        except httpx.HTTPStatusError as exc:
            err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
            raise typer.Exit(1)
        except httpx.ConnectError:
            err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
            raise typer.Exit(1)

        if not persons:
            console.print("No persons found.")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="dim")
        table.add_column("Name")
        table.add_column("Description")
        for p in persons:
            table.add_row(p["id"], p["name"], p.get("description") or "")
        console.print(table)
    ```

24. Add `create-person` command immediately after `list-persons`:
    ```python
    @app.command("create-person")
    def create_person(
        person_id: str = typer.Argument(..., help="Kebab-case person ID, e.g. oliver-james"),
        name: str = typer.Option(..., "--name", "-n", help="Display name"),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="Optional bio"),
    ) -> None:
        """Create or update a Person node."""
        try:
            with _make_client() as client:
                person = client.create_person(person_id, name, description=description)
            console.print(person["id"])
        except httpx.HTTPStatusError as exc:
            err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
            raise typer.Exit(1)
        except httpx.ConnectError:
            err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
            raise typer.Exit(1)
    ```

25. Run `pytest tests/test_wp037_person_nodes.py -k "CLI" -v` — all 11 should pass.

---

### Task 10 — Unit tests for MCP tools
**File:** `tests/test_wp037_person_nodes.py`

Uses `unittest.mock.patch("mcp_server.server.MemoryClient")`.

#### Steps

26. Write `TestMcpListPersons` (3 tests):
    - `test_memory_list_persons_calls_client` — `list_persons()` called exactly once
    - `test_memory_list_persons_returns_list` — return value is `list`
    - `test_memory_list_persons_returns_dicts_with_id` — each item has `"id"` key

27. Write `TestMcpCreatePerson` (4 tests):
    - `test_memory_create_person_calls_client` — `client.create_person()` called once
    - `test_memory_create_person_passes_person_id_and_name` — correct positional/keyword args
    - `test_memory_create_person_passes_description` — description forwarded when supplied
    - `test_memory_create_person_returns_dict` — return is a dict with `"id"` key

---

### Task 11 — MCP tools in `mcp_server/server.py`
**File:** `mcp_server/server.py`

#### Steps

28. Add `memory_list_persons` tool after `memory_list_strands`:
    ```python
    @mcp.tool
    def memory_list_persons() -> list[dict]:
        """Return all Person nodes. Use person IDs when calling memory_add."""
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.list_persons()
    ```

29. Add `memory_create_person` tool immediately after:
    ```python
    @mcp.tool
    def memory_create_person(person_id: str, name: str, description: str | None = None) -> dict:
        """Create or merge a Person node. Returns the person dict."""
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.create_person(person_id, name, description=description)
    ```

30. Run `pytest tests/test_wp037_person_nodes.py -k "Mcp" -v` — all 7 should pass.

---

### Task 12 — Integration tests for migration script
**File:** `tests/test_wp037_person_nodes.py`

#### Steps

31. Write `TestMigratePersonNodesScript` (6 tests) importing `fetch_batch` and `write_about_edge` directly from the script module:
    - `test_fetch_batch_returns_memories_without_about_person` — seed one wired + one unwired memory; fetch returns only the unwired one
    - `test_fetch_batch_respects_batch_size_limit` — seed 3 unwired; batch_size=2 returns 2
    - `test_write_about_edge_creates_edge_and_person` — `write_about_edge(session, memory_id, "test-p-wp037")` → edge exists
    - `test_write_about_edge_is_idempotent` — call twice; exactly 1 ABOUT edge
    - `test_write_creates_person_node_with_name_heuristic` — id `"oliver-james"` without pre-creation; `p.name == "Oliver James"`
    - `test_dry_run_does_not_write_edges` — capture stdout (monkeypatch sys.stdout); confirm JSON emitted; confirm no edge written

---

### Task 13 — Migration script `scripts/migrate_person_nodes.py`
**File:** `scripts/migrate_person_nodes.py` (new)

#### Steps

32. Write the migration script with these internals:

    **`fetch_batch(session, batch_size) -> list[dict]`**
    ```python
    def fetch_batch(session, batch_size: int) -> list[dict]:
        # Always SKIP 0: wired memories leave the result set
        result = session.run(
            """
            MATCH (m:Memory)
            WHERE NOT (m)-[:ABOUT]->(:Person)
            RETURN m.id AS id, m.fact AS fact
            ORDER BY m.created_at
            LIMIT $limit
            """,
            limit=batch_size,
        )
        return [{"id": r["id"], "fact": r["fact"]} for r in result]
    ```

    **`id_to_name(person_id: str) -> str`**
    ```python
    def id_to_name(person_id: str) -> str:
        return " ".join(w.capitalize() for w in person_id.split("-"))
    ```

    **`write_about_edge(session, memory_id: str, person_id: str, pre_created: bool = False) -> None`**
    ```python
    def write_about_edge(session, memory_id: str, person_id: str, pre_created: bool = False) -> None:
        if not pre_created:
            session.run(
                "MERGE (p:Person {id: $id}) SET p.name = coalesce(p.name, $name)",
                id=person_id,
                name=id_to_name(person_id),
            )
        session.run(
            """
            MATCH (m:Memory {id: $memory_id})
            MATCH (p:Person {id: $person_id})
            MERGE (m)-[:ABOUT]->(p)
            """,
            memory_id=memory_id,
            person_id=person_id,
        )
    ```

    **`main()`** — JSON-line stdin/stdout protocol identical to `migrate_fact_so_what.py`:
    - Emit `{"id": memory_id, "fact": fact}` per node
    - Read back `{"memory_id": ..., "person_ids": [...]}` or `{"memory_id": ..., "person_ids": []}` to skip
    - `--dry-run`: emit without reading stdin
    - `--batch-size N` (default 100)
    - `--pre-created-persons`: pass `pre_created=True` to `write_about_edge`

33. Run `pytest tests/test_wp037_person_nodes.py -k "Migrate" -v` — all 6 should pass.

---

### Task 14 — Full test suite + live smoke tests

#### Steps

34. Restart the FastAPI service to pick up new code:
    ```bash
    pkill -f "uvicorn memory_service.main:app" || true
    sleep 1
    python3 -m uvicorn memory_service.main:app --host 0.0.0.0 --port 8000 &
    sleep 5
    curl -s http://localhost:8000/health
    ```

35. Run full test suite:
    ```bash
    pytest tests/ -v 2>&1 | tail -20
    ```
    Expected: all 59 new tests pass; existing 117 continue to pass; 3 pre-existing mock failures remain.

36. Smoke test — live service:
    ```bash
    # Create a person
    curl -s -X POST http://localhost:8000/person \
      -H "Content-Type: application/json" \
      -d '{"id":"smoke-oliver","name":"Oliver James","description":"Project owner"}' | python3 -m json.tool

    # List persons
    curl -s http://localhost:8000/person | python3 -m json.tool

    # Create memory about that person
    MID=$(memory add-memory "Oliver is the project owner." --type fact --person-id smoke-oliver)
    echo "Memory ID: $MID"

    # Verify in Memgraph
    memory search-memory "project owner" --max-hops 0
    ```

37. Smoke test — CLI:
    ```bash
    memory create-person smoke-sarah --name "Sarah Chen" --description "Colleague"
    memory list-persons
    ```

38. Run migration script dry-run (seed a memory first if none exist without ABOUT edges):
    ```bash
    python3 scripts/migrate_person_nodes.py --dry-run 2>&1 | head -5
    ```

39. Update BACKLOG.md: move WP-037 from Currently In Progress to Completed; add retrospective.

40. Git commit: `WP-037: Person nodes + ABOUT edges — GET/POST /person + migration script`

---

## Definition of Done checklist

- [ ] Task 1–2: `TestCreatePersonRequestModel` (4 unit tests) passing
- [ ] Task 3–5: `TestGetPersonEndpoint` (5), `TestPostPersonEndpoint` (10), `TestAboutEdge*` (6) passing
- [ ] Task 6–7: `TestMemoryClientListPersons` (4), `TestMemoryClientCreatePerson` (6) passing
- [ ] Task 8–9: `TestListPersonsCLI` (6), `TestCreatePersonCLI` (5) passing
- [ ] Task 10–11: `TestMcpListPersons` (3), `TestMcpCreatePerson` (4) passing
- [ ] Task 12–13: `TestMigratePersonNodesScript` (6) passing
- [ ] Full suite: 59 new tests pass; existing 117 unaffected
- [ ] Live smoke tests: all 9 acceptance criteria verified
- [ ] Migration script dry-run run against live graph
- [ ] BACKLOG updated; git commit created

---

## Notes for implementer subagents

- **`init_schema.py` unchanged** — `Person.id` uniqueness constraint already exists
- **`AddMemoryRequest.person_ids` unchanged** — already in model
- **`memory_repo.add_memory` step 3 unchanged** — ABOUT edge via add_memory already works
- **New `POST /person` endpoint** uses MERGE + SET (not CREATE + SET) to ensure idempotency
- **Migration script** uses `coalesce(p.name, $name)` so explicit `POST /person` names are not overwritten
- **Test cleanup** for multiple Person nodes: `extra_ids` accepts one label per key, so use separate `session.run(DETACH DELETE)` calls for each person id
- **Test constant prefix** `"test-person-wp037-"` distinguishes test nodes from production data
