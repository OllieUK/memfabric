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
