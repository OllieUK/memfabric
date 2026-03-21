# WP-037 Design Spec — Person nodes + `ABOUT` edges

**Date:** 2026-03-21
**Status:** Draft
**Depends on:** WP-028 ✅

---

## 1. Current state (what already exists)

A lot of WP-037 is already implemented — because `POST /memory` has always accepted `person_ids`. The gaps are purely the Person-management endpoints and migration script.

| Area | Already done | Missing |
|------|-------------|---------|
| `init_schema.py` | `Person.id` uniqueness constraint ✅ | — |
| `AddMemoryRequest.person_ids` | Field exists ✅ | — |
| `memory_repo.add_memory` step 3 | MERGE Person + ABOUT edge ✅ | — |
| `client.add_memory(person_ids=...)` | Param exists ✅ | — |
| `cli.py add-memory --person-id` | Option exists ✅ | — |
| `GET /person` | — | **Missing** |
| `POST /person` | — | **Missing** |
| `memory_repo.list_persons()` | — | **Missing** |
| `memory_repo.upsert_person()` | — | **Missing** |
| `client.list_persons()` | — | **Missing** |
| `client.create_person()` | — | **Missing** |
| `cli.py list-persons` | — | **Missing** |
| `mcp_server memory_list_persons` | — | **Missing** |
| `scripts/migrate_person_nodes.py` | — | **Missing** |

---

## 2. Data model

**`Person` node** (already in Memgraph schema):

| Property | Type | Notes |
|----------|------|-------|
| `id` | `str` (kebab-case) | e.g. `oliver-james`. Uniqueness constraint already exists. |
| `name` | `str` | Display name, e.g. `"Oliver James"` |
| `description` | `str \| None` | Optional free-text bio |

**`ABOUT` edge** (Memory → Person) — already created by `add_memory` step 3. No changes.

---

## 3. API changes

### 3.1 `GET /person`

Returns all Person nodes ordered by `id`.

**Response:**
```json
{
  "persons": [
    {"id": "oliver-james", "name": "Oliver James", "description": "..."},
    {"id": "sarah-chen", "name": "Sarah Chen", "description": null}
  ]
}
```

**Pydantic models to add in `main.py`:**
```python
class PersonItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None

class PersonsResponse(BaseModel):
    persons: List[PersonItem]
```

**Endpoint:**
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

### 3.2 `POST /person`

Creates or merges a Person node by id. Idempotent (MERGE semantics). Returns the person.

**Request body:**
```json
{"id": "oliver-james", "name": "Oliver James", "description": "Project owner"}
```

**Response:**
```json
{"id": "oliver-james", "name": "Oliver James", "description": "Project owner"}
```

`description` is optional in the request. If the node already exists, `name` and `description` are updated (SET).

**Pydantic models:**
```python
class CreatePersonRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
```

**Endpoint:**
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

---

## 4. Repository layer

### 4.1 `list_persons(session) -> list[dict]`

```python
def list_persons(session) -> list[dict]:
    result = session.run(
        "MATCH (p:Person) RETURN p.id AS id, p.name AS name, "
        "p.description AS description ORDER BY p.id"
    )
    return [
        {"id": r["id"], "name": r["name"], "description": r["description"]}
        for r in result
    ]
```

### 4.2 `upsert_person(session, req) -> dict`

```python
def upsert_person(session, req) -> dict:
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

**Note:** `MERGE + SET` is intentional — updates name/description if node already exists. This is correct upsert semantics.

---

## 5. Client layer

### 5.1 `client.py` additions

```python
def list_persons(self) -> list[dict]:
    """GET /person. Returns list of person dicts: id, name, description."""
    response = self._http.get("/person")
    response.raise_for_status()
    return response.json()["persons"]

def create_person(self, person_id: str, name: str, description: str | None = None) -> dict:
    """POST /person. Creates or merges a Person node. Returns person dict."""
    body: dict = {"id": person_id, "name": name}
    if description is not None:
        body["description"] = description
    response = self._http.post("/person", json=body)
    response.raise_for_status()
    return response.json()
```

### 5.2 `cli.py` additions

Two new commands: `list-persons` and `create-person`.

**`list-persons`:**
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

**`create-person`:**
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

### 5.3 `mcp_server/server.py` additions

```python
@mcp.tool
def memory_list_persons() -> list[dict]:
    """Return all Person nodes. Use person IDs when calling memory_add."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.list_persons()

@mcp.tool
def memory_create_person(person_id: str, name: str, description: str | None = None) -> dict:
    """Create or merge a Person node. Returns the person dict."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.create_person(person_id, name, description=description)
```

---

## 6. Migration script — `scripts/migrate_person_nodes.py`

**Purpose:** Scan all existing Memory nodes and wire `ABOUT` edges to named Person nodes where the memory's `fact` mentions a known individual.

**Protocol:** Unlike the WP-028 script, this migration knows the target Person entities in advance (the caller supplies them). The script outputs each memory's `id + fact` as JSON lines on stdout and reads back `{"memory_id": "...", "person_ids": ["oliver-james"]}` (or `null` to skip) on stdin. The caller (contextual intelligence) decides which people each memory is about.

```
stdout: {"id": "<uuid>", "fact": "<text>"}
stdin:  {"memory_id": "<uuid>", "person_ids": ["<person-id>", ...]}
        (or: {"memory_id": "<uuid>", "person_ids": []}) to skip
```

The script:
1. Fetches all Memory nodes that have NO existing `ABOUT` edge to any Person (`WHERE NOT (m)-[:ABOUT]->(:Person)`)
2. Emits each as a JSON line on stdout
3. Reads back the decision on stdin; for each non-empty `person_ids` list:
   - `MERGE` the Person node (with a default `name` derived from the id, e.g. `oliver-james` → `Oliver James`)
   - `MERGE` the `ABOUT` edge
4. `--dry-run` flag: prints decisions without writing
5. `--pre-created-persons` flag: if set, only MERGEs edges (does not create Person nodes — caller must have pre-created them via `POST /person`)

**Pagination:** Same pattern as WP-028 — always fetches from SKIP 0 because wired memories leave the `WHERE NOT (m)-[:ABOUT]->(:Person)` result set.

**`id` → `name` heuristic:** Used when creating a Person node implicitly (without `--pre-created-persons`). Converts `oliver-james` → `Oliver James` via `" ".join(w.capitalize() for w in person_id.split("-"))`.

---

## 7. Files changed

| File | Change |
|------|--------|
| `memory_service/main.py` | Add `PersonItem`, `PersonsResponse`, `CreatePersonRequest`; add `GET /person` and `POST /person` endpoints |
| `memory_service/memory_repo.py` | Add `list_persons()` and `upsert_person()` |
| `memory_client/client.py` | Add `list_persons()` and `create_person()` |
| `memory_client/cli.py` | Add `list-persons` and `create-person` commands |
| `mcp_server/server.py` | Add `memory_list_persons` and `memory_create_person` tools |
| `scripts/migrate_person_nodes.py` | New migration script |
| `scripts/init_schema.py` | No change — Person constraint already exists |

---

## 8. Backwards compatibility

- `POST /memory` with `person_ids` already works — no change
- Person nodes already created via `add_memory` have correct structure
- `GET /person` will surface any pre-existing Person nodes immediately
- Migration script is idempotent — safe to re-run

---

## 9. Definition of Success

- [ ] `GET /person` returns all Person nodes ordered by id
- [ ] `POST /person` creates a new Person node and returns it
- [ ] `POST /person` on existing id updates name/description (upsert semantics)
- [ ] `POST /memory` with `person_ids` creates ABOUT edges (already works — regression check)
- [ ] `memory list-persons` CLI command renders a table
- [ ] `memory create-person` CLI command prints the created id
- [ ] `memory_list_persons` and `memory_create_person` MCP tools work
- [ ] Migration script dry-run emits JSON lines for all un-ABOUT-wired memories
- [ ] Integration test: POST /person, POST /memory with person_id, verify ABOUT edge
- [ ] Migration script run against live graph; ABOUT edges verified in Memgraph Lab
