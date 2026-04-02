# WP-078: Project Node CRUD Endpoints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class CRUD endpoints for Project nodes (list + upsert), matching the existing Person pattern, with CLI, client, and MCP support.

**Architecture:** Mirror the Person node pattern exactly — Pydantic models in `main.py`, repo functions in `memory_repo.py`, client methods in `client.py`, CLI commands in `cli.py`, MCP tools in `server.py`. Project nodes already exist (created as side-effects of `add_memory` with `project_id`), but have no dedicated endpoints and store only `id`. This WP adds `name` and `description` properties and full CRUD surface.

**Tech Stack:** FastAPI, Pydantic, neo4j Python driver (Bolt), Typer CLI, FastMCP, pytest + respx

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `memory_service/main.py:361-404` | Add `ProjectItem`, `ProjectsResponse`, `CreateProjectRequest` models + `GET /project`, `POST /project` endpoints (after Person block) |
| Modify | `memory_service/memory_repo.py:424-452` | Add `list_projects()` and `upsert_project()` functions (after Person equivalents) |
| Modify | `memory_client/client.py:125-138` | Add `list_projects()` and `create_project()` methods (after Person equivalents) |
| Modify | `memory_client/cli.py:155-197` | Add `list-projects` and `create-project` commands (after Person equivalents) |
| Modify | `mcp_server/server.py:157-168` | Add `memory_list_projects()` and `memory_create_project()` tools (after Person equivalents) |
| Modify | `mcp_server/server.py:1-8` | Update module docstring to list new tools |
| Create | `tests/test_wp078_project_nodes.py` | Unit + integration tests for all layers |

---

### Task 1: Repository layer — `list_projects` and `upsert_project`

**Files:**
- Modify: `memory_service/memory_repo.py` (after line 452)
- Test: `tests/test_wp078_project_nodes.py`

- [ ] **Step 1: Create test file with unit tests for repo functions**

Create `tests/test_wp078_project_nodes.py`:

```python
# tests/test_wp078_project_nodes.py
import json

import httpx
import pytest
import respx
from pydantic import ValidationError
from typer.testing import CliRunner

from memory_client.cli import app as cli_app
from memory_client.client import MemoryClient

_BASE_URL = "http://localhost:8000"
_PROJECTS_RESPONSE = {
    "projects": [
        {"id": "test-project-wp078-a", "name": "Test Project A", "description": None},
        {"id": "test-project-wp078-b", "name": "Test Project B", "description": "Description B"},
    ]
}
_CREATE_PROJECT_RESPONSE = {"id": "test-project-wp078-a", "name": "Test Project A", "description": None}

_cli_runner = CliRunner()

# Shared constants
_PROJECT_ID_A = "test-project-wp078-a"
_PROJECT_ID_B = "test-project-wp078-b"
_AGENT_ID = "test-agent-wp078"


def _cleanup_projects(driver, *project_ids, memory_ids=()):
    """Clean up test Project nodes and optionally Memory nodes."""
    from tests.conftest import cleanup_nodes
    if memory_ids:
        cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)
    with driver.session() as session:
        for pid in project_ids:
            session.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=pid)


# ---------------------------------------------------------------------------
# Task 1 — Unit tests: CreateProjectRequest model
# ---------------------------------------------------------------------------
class TestCreateProjectRequestModel:
    def test_valid_request(self):
        from memory_service.main import CreateProjectRequest
        req = CreateProjectRequest(id="proj-a", name="Project A")
        assert req.id == "proj-a"
        assert req.name == "Project A"
        assert req.description is None

    def test_valid_request_with_description(self):
        from memory_service.main import CreateProjectRequest
        req = CreateProjectRequest(id="proj-a", name="Project A", description="A description")
        assert req.description == "A description"

    def test_missing_id_raises(self):
        from memory_service.main import CreateProjectRequest
        with pytest.raises(ValidationError):
            CreateProjectRequest(name="Project A")

    def test_missing_name_raises(self):
        from memory_service.main import CreateProjectRequest
        with pytest.raises(ValidationError):
            CreateProjectRequest(id="proj-a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wp078_project_nodes.py::TestCreateProjectRequestModel -v`
Expected: FAIL — `CreateProjectRequest` does not exist yet.

- [ ] **Step 3: Add Pydantic models to main.py**

In `memory_service/main.py`, after the `CreatePersonRequest` class (line 374), add:

```python
class ProjectItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class ProjectsResponse(BaseModel):
    projects: List[ProjectItem]


class CreateProjectRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wp078_project_nodes.py::TestCreateProjectRequestModel -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add memory_service/main.py tests/test_wp078_project_nodes.py
git commit -m "WP-078: add Project Pydantic models + model unit tests"
```

---

### Task 2: Repository functions

**Files:**
- Modify: `memory_service/memory_repo.py` (after line 452)

- [ ] **Step 1: Add `list_projects` and `upsert_project` to memory_repo.py**

In `memory_service/memory_repo.py`, after `upsert_person` (line 452), add:

```python
def list_projects(session) -> list[dict]:
    """Return all Project nodes with a non-null name, ordered by id."""
    result = session.run(
        "MATCH (p:Project) WHERE p.name IS NOT NULL "
        "RETURN p.id AS id, p.name AS name, "
        "p.description AS description ORDER BY p.id"
    )
    return [
        {"id": r["id"], "name": r["name"], "description": r["description"]}
        for r in result
    ]


def upsert_project(session, req) -> dict:
    """Create or update a Project node by id. Returns the stored values."""
    result = session.run(
        """
        MERGE (p:Project {id: $id})
        SET p.name = $name, p.description = $description
        RETURN p.id AS id, p.name AS name, p.description AS description
        """,
        id=req.id,
        name=req.name,
        description=req.description,
    )
    record = result.single()
    if record is None:
        raise RuntimeError(f"upsert_project: MERGE returned no record for id={req.id!r}")
    return {"id": record["id"], "name": record["name"], "description": record["description"]}
```

- [ ] **Step 2: Commit**

```bash
git add memory_service/memory_repo.py
git commit -m "WP-078: add list_projects and upsert_project repo functions"
```

---

### Task 3: HTTP endpoints — `GET /project` and `POST /project`

**Files:**
- Modify: `memory_service/main.py` (after `create_person` endpoint, line 404)
- Test: `tests/test_wp078_project_nodes.py`

- [ ] **Step 1: Add endpoint unit tests to test file**

Append to `tests/test_wp078_project_nodes.py`:

```python
# ---------------------------------------------------------------------------
# Task 3 — Unit tests: GET /project endpoint
# ---------------------------------------------------------------------------
class TestGetProjectEndpoint:
    def test_returns_projects_list(self, client):
        """GET /project returns a list of projects."""
        response = client.get("/project")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)


# ---------------------------------------------------------------------------
# Task 3 — Unit tests: POST /project endpoint
# ---------------------------------------------------------------------------
class TestPostProjectEndpoint:
    def test_create_project_returns_project(self, client, test_driver):
        """POST /project creates a project and returns it."""
        body = {"id": _PROJECT_ID_A, "name": "Test Project A"}
        response = client.post("/project", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == _PROJECT_ID_A
        assert data["name"] == "Test Project A"
        assert data["description"] is None
        _cleanup_projects(test_driver, _PROJECT_ID_A)

    def test_create_project_with_description(self, client, test_driver):
        """POST /project with description stores it."""
        body = {"id": _PROJECT_ID_A, "name": "Test Project A", "description": "A test project"}
        response = client.post("/project", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "A test project"
        _cleanup_projects(test_driver, _PROJECT_ID_A)

    def test_upsert_updates_existing(self, client, test_driver):
        """POST /project with same id updates name and description."""
        client.post("/project", json={"id": _PROJECT_ID_A, "name": "Original"})
        response = client.post("/project", json={"id": _PROJECT_ID_A, "name": "Updated", "description": "New desc"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"
        assert data["description"] == "New desc"
        _cleanup_projects(test_driver, _PROJECT_ID_A)

    def test_missing_id_returns_422(self, client):
        """POST /project without id returns 422."""
        response = client.post("/project", json={"name": "No ID"})
        assert response.status_code == 422

    def test_missing_name_returns_422(self, client):
        """POST /project without name returns 422."""
        response = client.post("/project", json={"id": _PROJECT_ID_A})
        assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wp078_project_nodes.py::TestGetProjectEndpoint tests/test_wp078_project_nodes.py::TestPostProjectEndpoint -v`
Expected: FAIL — endpoints don't exist yet (404).

- [ ] **Step 3: Add endpoints to main.py**

In `memory_service/main.py`, after `create_person` (line 404), add:

```python
@app.get("/project", response_model=ProjectsResponse)
async def list_projects(request: Request) -> ProjectsResponse:
    try:
        with request.app.state.driver.session() as session:
            projects = memory_repo.list_projects(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ProjectsResponse(projects=[ProjectItem(**p) for p in projects])


@app.post("/project", response_model=ProjectItem)
async def create_project(req: CreateProjectRequest, request: Request) -> ProjectItem:
    try:
        with request.app.state.driver.session() as session:
            project = memory_repo.upsert_project(session, req)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ProjectItem(**project)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wp078_project_nodes.py::TestGetProjectEndpoint tests/test_wp078_project_nodes.py::TestPostProjectEndpoint -v`
Expected: PASS (all 5 endpoint tests)

- [ ] **Step 5: Commit**

```bash
git add memory_service/main.py tests/test_wp078_project_nodes.py
git commit -m "WP-078: add GET /project and POST /project endpoints"
```

---

### Task 4: Client methods — `list_projects` and `create_project`

**Files:**
- Modify: `memory_client/client.py` (after `create_person`, line 138)
- Test: `tests/test_wp078_project_nodes.py`

- [ ] **Step 1: Add client unit tests**

Append to `tests/test_wp078_project_nodes.py`:

```python
# ---------------------------------------------------------------------------
# Task 4 — Unit tests: MemoryClient.list_projects / create_project
# ---------------------------------------------------------------------------
class TestClientListProjects:
    @respx.mock
    def test_list_projects_returns_list(self):
        respx.get(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json=_PROJECTS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            projects = client.list_projects()
        assert len(projects) == 2
        assert projects[0]["id"] == "test-project-wp078-a"

    @respx.mock
    def test_list_projects_empty(self):
        respx.get(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json={"projects": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            projects = client.list_projects()
        assert projects == []


class TestClientCreateProject:
    @respx.mock
    def test_create_project_minimal(self):
        respx.post(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json=_CREATE_PROJECT_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.create_project("test-project-wp078-a", "Test Project A")
        assert result["id"] == "test-project-wp078-a"
        assert result["name"] == "Test Project A"

    @respx.mock
    def test_create_project_with_description(self):
        expected = {**_CREATE_PROJECT_RESPONSE, "description": "A desc"}
        respx.post(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json=expected)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.create_project("test-project-wp078-a", "Test Project A", description="A desc")
        assert result["description"] == "A desc"
        # Verify description was sent in request body
        req_body = json.loads(respx.calls.last.request.content)
        assert req_body["description"] == "A desc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wp078_project_nodes.py::TestClientListProjects tests/test_wp078_project_nodes.py::TestClientCreateProject -v`
Expected: FAIL — `list_projects` / `create_project` methods don't exist on `MemoryClient`.

- [ ] **Step 3: Add client methods**

In `memory_client/client.py`, after `create_person` (line 138), add:

```python
    def list_projects(self) -> list[dict]:
        """GET /project. Returns list of project dicts: id, name, description."""
        response = self._http.get("/project")
        response.raise_for_status()
        return response.json()["projects"]

    def create_project(self, project_id: str, name: str, description: str | None = None) -> dict:
        """POST /project. Creates or merges a Project node. Returns project dict."""
        body: dict = {"id": project_id, "name": name}
        if description is not None:
            body["description"] = description
        response = self._http.post("/project", json=body)
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wp078_project_nodes.py::TestClientListProjects tests/test_wp078_project_nodes.py::TestClientCreateProject -v`
Expected: PASS (all 4 client tests)

- [ ] **Step 5: Commit**

```bash
git add memory_client/client.py tests/test_wp078_project_nodes.py
git commit -m "WP-078: add list_projects and create_project client methods"
```

---

### Task 5: CLI commands — `list-projects` and `create-project`

**Files:**
- Modify: `memory_client/cli.py` (after `create-person`, line 197)
- Test: `tests/test_wp078_project_nodes.py`

- [ ] **Step 1: Add CLI unit tests**

Append to `tests/test_wp078_project_nodes.py`:

```python
# ---------------------------------------------------------------------------
# Task 5 — Unit tests: CLI list-projects / create-project
# ---------------------------------------------------------------------------
class TestCliListProjects:
    @respx.mock
    def test_list_projects_table_output(self):
        respx.get(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json=_PROJECTS_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["list-projects"])
        assert result.exit_code == 0
        assert "test-project-wp078-a" in result.output
        assert "Test Project A" in result.output

    @respx.mock
    def test_list_projects_empty(self):
        respx.get(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json={"projects": []})
        )
        result = _cli_runner.invoke(cli_app, ["list-projects"])
        assert result.exit_code == 0
        assert "No projects found" in result.output


class TestCliCreateProject:
    @respx.mock
    def test_create_project_prints_id(self):
        respx.post(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json=_CREATE_PROJECT_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["create-project", _PROJECT_ID_A, "--name", "Test Project A"])
        assert result.exit_code == 0
        assert _PROJECT_ID_A in result.output

    @respx.mock
    def test_create_project_with_description(self):
        expected = {**_CREATE_PROJECT_RESPONSE, "description": "A desc"}
        respx.post(f"{_BASE_URL}/project").mock(
            return_value=httpx.Response(200, json=expected)
        )
        result = _cli_runner.invoke(
            cli_app, ["create-project", _PROJECT_ID_A, "--name", "Test Project A", "--description", "A desc"]
        )
        assert result.exit_code == 0
        assert _PROJECT_ID_A in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wp078_project_nodes.py::TestCliListProjects tests/test_wp078_project_nodes.py::TestCliCreateProject -v`
Expected: FAIL — CLI commands don't exist.

- [ ] **Step 3: Add CLI commands**

In `memory_client/cli.py`, after `create_person` (line 197), add:

```python
@app.command("list-projects")
def list_projects() -> None:
    """List all Project nodes in the memory fabric."""
    try:
        with _make_client() as client:
            projects = client.list_projects()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not projects:
        console.print("No projects found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Description")
    for p in projects:
        table.add_row(p["id"], p["name"], p.get("description") or "")
    console.print(table)


@app.command("create-project")
def create_project(
    project_id: str = typer.Argument(..., help="Kebab-case project ID, e.g. graph-memory-fabric"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Optional description"),
) -> None:
    """Create or update a Project node."""
    try:
        with _make_client() as client:
            project = client.create_project(project_id, name, description=description)
        console.print(project["id"])
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wp078_project_nodes.py::TestCliListProjects tests/test_wp078_project_nodes.py::TestCliCreateProject -v`
Expected: PASS (all 4 CLI tests)

- [ ] **Step 5: Commit**

```bash
git add memory_client/cli.py tests/test_wp078_project_nodes.py
git commit -m "WP-078: add list-projects and create-project CLI commands"
```

---

### Task 6: MCP tools — `memory_list_projects` and `memory_create_project`

**Files:**
- Modify: `mcp_server/server.py:1-8` (docstring), after line 168 (new tools)
- Test: `tests/test_wp078_project_nodes.py`

- [ ] **Step 1: Add MCP unit tests**

Append to `tests/test_wp078_project_nodes.py`:

```python
# ---------------------------------------------------------------------------
# Task 6 — Unit tests: MCP tools memory_list_projects / memory_create_project
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock, patch


class TestMcpListProjects:
    def test_list_projects_calls_client(self):
        from mcp_server.server import memory_list_projects

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_projects.return_value = [
            {"id": "proj-a", "name": "Project A", "description": None},
        ]

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_list_projects()

        mock_client.list_projects.assert_called_once()
        assert len(result) == 1
        assert result[0]["id"] == "proj-a"


class TestMcpCreateProject:
    def test_create_project_passes_args(self):
        from mcp_server.server import memory_create_project

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.create_project.return_value = {
            "id": "proj-a", "name": "Project A", "description": None,
        }

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_create_project("proj-a", "Project A")

        mock_client.create_project.assert_called_once_with("proj-a", "Project A", description=None)
        assert result["id"] == "proj-a"

    def test_create_project_with_description(self):
        from mcp_server.server import memory_create_project

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.create_project.return_value = {
            "id": "proj-a", "name": "Project A", "description": "A desc",
        }

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = memory_create_project("proj-a", "Project A", description="A desc")

        mock_client.create_project.assert_called_once_with("proj-a", "Project A", description="A desc")
        assert result["description"] == "A desc"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wp078_project_nodes.py::TestMcpListProjects tests/test_wp078_project_nodes.py::TestMcpCreateProject -v`
Expected: FAIL — `memory_list_projects` / `memory_create_project` don't exist.

- [ ] **Step 3: Add MCP tools to server.py**

In `mcp_server/server.py`, after `memory_create_person` (line 168), add:

```python
@mcp.tool
def memory_list_projects() -> list[dict]:
    """Return all Project nodes. Use project IDs when calling memory_add."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.list_projects()


@mcp.tool
def memory_create_project(project_id: str, name: str, description: str | None = None) -> dict:
    """Create or merge a Project node. Returns the project dict."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.create_project(project_id, name, description=description)
```

Update the module docstring at line 4-5 to include the new tools:

```python
"""MCP server for graph-memory-fabric.

Exposes tools via FastMCP over STDIO transport:
  memory_add, memory_search, memory_wake_up, memory_list_strands, memory_close_session,
  memory_list_persons, memory_create_person,
  memory_list_projects, memory_create_project,
  memory_short_rest, memory_long_rest, memory_maintenance_stats,
  memory_update, memory_archive, memory_restore, memory_merge
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wp078_project_nodes.py::TestMcpListProjects tests/test_wp078_project_nodes.py::TestMcpCreateProject -v`
Expected: PASS (all 3 MCP tests)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py tests/test_wp078_project_nodes.py
git commit -m "WP-078: add memory_list_projects and memory_create_project MCP tools"
```

---

### Task 7: Integration tests — live stack

**Files:**
- Test: `tests/test_wp078_project_nodes.py`

- [ ] **Step 1: Add integration tests**

Append to `tests/test_wp078_project_nodes.py`:

```python
# ---------------------------------------------------------------------------
# Task 7 — Integration tests: live stack
# ---------------------------------------------------------------------------
class TestProjectIntegration:
    @pytest.mark.integration
    def test_upsert_and_list_projects(self, client, test_driver):
        """POST /project upserts, GET /project lists it."""
        try:
            # Create two projects
            r1 = client.post("/project", json={"id": _PROJECT_ID_A, "name": "Project A"})
            assert r1.status_code == 200
            r2 = client.post("/project", json={"id": _PROJECT_ID_B, "name": "Project B", "description": "Desc B"})
            assert r2.status_code == 200

            # List and verify both appear
            r3 = client.get("/project")
            assert r3.status_code == 200
            projects = r3.json()["projects"]
            ids = [p["id"] for p in projects]
            assert _PROJECT_ID_A in ids
            assert _PROJECT_ID_B in ids

            # Verify description
            proj_b = next(p for p in projects if p["id"] == _PROJECT_ID_B)
            assert proj_b["description"] == "Desc B"
        finally:
            _cleanup_projects(test_driver, _PROJECT_ID_A, _PROJECT_ID_B)

    @pytest.mark.integration
    def test_upsert_updates_name_and_description(self, client, test_driver):
        """POST /project with existing id updates name and description."""
        try:
            client.post("/project", json={"id": _PROJECT_ID_A, "name": "Original"})
            r = client.post("/project", json={"id": _PROJECT_ID_A, "name": "Updated", "description": "New"})
            assert r.status_code == 200
            data = r.json()
            assert data["name"] == "Updated"
            assert data["description"] == "New"

            # Verify via GET that the change persisted
            r2 = client.get("/project")
            proj = next(p for p in r2.json()["projects"] if p["id"] == _PROJECT_ID_A)
            assert proj["name"] == "Updated"
        finally:
            _cleanup_projects(test_driver, _PROJECT_ID_A)

    @pytest.mark.integration
    def test_memory_with_project_id_gets_name_via_upsert(self, client, test_driver):
        """A project created via add_memory (no name) can be enriched via POST /project."""
        memory_id = None
        try:
            # Create memory with project_id — creates bare Project node
            r = client.post("/memory", json={
                "fact": "WP-078 integration: project enrichment",
                "type": "fact",
                "agent_id": _AGENT_ID,
                "project_id": _PROJECT_ID_A,
                "importance": 1,
            })
            memory_id = r.json()["memory_id"]

            # Enrich via POST /project
            r2 = client.post("/project", json={"id": _PROJECT_ID_A, "name": "Enriched Project"})
            assert r2.status_code == 200
            assert r2.json()["name"] == "Enriched Project"

            # Verify it shows in list
            r3 = client.get("/project")
            proj = next(p for p in r3.json()["projects"] if p["id"] == _PROJECT_ID_A)
            assert proj["name"] == "Enriched Project"
        finally:
            _cleanup_projects(test_driver, _PROJECT_ID_A, memory_ids=(memory_id,) if memory_id else ())

    @pytest.mark.integration
    def test_mcp_create_project_live(self, test_driver):
        """MCP memory_create_project creates a Project node on the live stack."""
        from mcp_server.server import memory_create_project, memory_list_projects

        try:
            result = memory_create_project(_PROJECT_ID_A, "MCP Project", description="Via MCP")
            assert result["id"] == _PROJECT_ID_A
            assert result["name"] == "MCP Project"
            assert result["description"] == "Via MCP"

            # Verify via list
            projects = memory_list_projects()
            ids = [p["id"] for p in projects]
            assert _PROJECT_ID_A in ids
        finally:
            _cleanup_projects(test_driver, _PROJECT_ID_A)
```

- [ ] **Step 2: Run all unit tests first**

Run: `pytest tests/test_wp078_project_nodes.py -v -k "not integration"`
Expected: PASS (all unit tests)

- [ ] **Step 3: Run integration tests against live stack**

Run: `pytest tests/test_wp078_project_nodes.py -v -m integration`
Expected: PASS (all 4 integration tests). Requires Memgraph + FastAPI to be running.

- [ ] **Step 4: Run full test suite to check for regressions**

Run: `pytest tests/ -v --timeout=30`
Expected: All existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_wp078_project_nodes.py
git commit -m "WP-078: add integration tests for project CRUD endpoints"
```

---

### Task 8: Finalise — BACKLOG update and /simplify

- [ ] **Step 1: Move WP-078 to Completed in BACKLOG.md**

Remove WP-078 from the priority table and add to Completed section.

- [ ] **Step 2: Run `/simplify`**

Review all changed code for quality, reuse, and efficiency.

- [ ] **Step 3: Final commit**

```bash
git add BACKLOG.md
git commit -m "WP-078: update BACKLOG — mark complete"
```
