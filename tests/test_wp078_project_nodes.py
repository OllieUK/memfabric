import json
from unittest.mock import MagicMock, patch

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


# ---------------------------------------------------------------------------
# Task 3 — Unit tests: GET /project endpoint
# ---------------------------------------------------------------------------
@pytest.mark.integration
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
@pytest.mark.integration
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


# ---------------------------------------------------------------------------
# Task 6 — Unit tests: MCP tools memory_list_projects / memory_create_project
# ---------------------------------------------------------------------------

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
