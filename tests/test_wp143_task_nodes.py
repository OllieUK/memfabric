"""WP-143: First-class Task nodes for commitment and backlog stewardship."""
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx
from pydantic import ValidationError
from typer.testing import CliRunner

from memory_client.cli import app as cli_app
from memory_client.client import MemoryClient

_BASE_URL = "https://memfabric.carr-it.net"

_TASK_ID_A = "11111111-1111-1111-1111-111111111143"
_TASK_ID_B = "22222222-2222-2222-2222-222222222143"
_AGENT_ID = "test-agent-wp143"
_PROJECT_ID = "test-project-wp143"
_MEMORY_ID = "33333333-3333-3333-3333-333333333143"

_TASK_RESPONSE = {
    "id": _TASK_ID_A,
    "title": "Test task A",
    "description": None,
    "status": "open",
    "value": "H",
    "effort": "L",
    "priority_score": 3.0,
    "urgency": None,
    "due_at": None,
    "snooze_until": None,
    "created_at": "2026-04-15T10:00:00+00:00",
    "updated_at": "2026-04-15T10:00:00+00:00",
    "committed_at": None,
    "committed_by": None,
    "last_checked_at": None,
    "source_ref": None,
    "recurrence": None,
    "is_template": False,
    "agent_id": _AGENT_ID,
    "project_id": None,
    "project_weight": None,
}

_TASKS_RESPONSE = {"tasks": [_TASK_RESPONSE]}

_cli_runner = CliRunner()


def _cleanup_tasks(driver, *task_ids, project_ids=(), memory_ids=()):
    """Clean up test Task nodes and optionally Project/Memory nodes."""
    from tests.conftest import cleanup_nodes
    if memory_ids:
        cleanup_nodes(driver, *memory_ids)
    with driver.session() as session:
        for tid in task_ids:
            session.run("MATCH (t:Task {id: $id}) DETACH DELETE t", id=tid)
        for pid in project_ids:
            session.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=pid)
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)


# ---------------------------------------------------------------------------
# Pydantic model validation (unit)
# ---------------------------------------------------------------------------

class TestCreateTaskRequestModel:
    def test_minimal_valid_request(self):
        from memory_service.main import CreateTaskRequest
        req = CreateTaskRequest(title="Do the thing", agent_id=_AGENT_ID)
        assert req.title == "Do the thing"
        assert req.agent_id == _AGENT_ID
        assert req.status.value == "open"
        assert req.is_template is False
        assert req.memory_ids == []

    def test_missing_title_raises(self):
        from memory_service.main import CreateTaskRequest
        with pytest.raises(ValidationError):
            CreateTaskRequest(agent_id=_AGENT_ID)

    def test_missing_agent_id_raises(self):
        from memory_service.main import CreateTaskRequest
        with pytest.raises(ValidationError):
            CreateTaskRequest(title="Do the thing")

    def test_invalid_status_raises(self):
        from memory_service.main import CreateTaskRequest
        with pytest.raises(ValidationError):
            CreateTaskRequest(title="x", agent_id=_AGENT_ID, status="invalid")

    def test_invalid_value_raises(self):
        from memory_service.main import CreateTaskRequest
        with pytest.raises(ValidationError):
            CreateTaskRequest(title="x", agent_id=_AGENT_ID, value="X")

    def test_priority_score_computed_h_l(self):
        from memory_service.main import CreateTaskRequest
        req = CreateTaskRequest(title="x", agent_id=_AGENT_ID, value="H", effort="L")
        assert req.priority_score == 3.0

    def test_priority_score_computed_m_m(self):
        from memory_service.main import CreateTaskRequest
        req = CreateTaskRequest(title="x", agent_id=_AGENT_ID, value="M", effort="M")
        assert req.priority_score == 1.0

    def test_priority_score_none_when_missing_effort(self):
        from memory_service.main import CreateTaskRequest
        req = CreateTaskRequest(title="x", agent_id=_AGENT_ID, value="H")
        assert req.priority_score is None

    def test_all_optional_fields_accepted(self):
        from memory_service.main import CreateTaskRequest
        req = CreateTaskRequest(
            title="x", agent_id=_AGENT_ID,
            description="desc", status="active",
            value="M", effort="H",
            urgency=2.5, due_at="2026-05-01T00:00:00Z",
            snooze_until="2026-04-20T00:00:00Z",
            committed_at="2026-04-15T10:00:00Z",
            committed_by=_AGENT_ID,
            source_ref="gmf:WP-143",
            project_id=_PROJECT_ID,
            memory_ids=[_MEMORY_ID],
            recurrence="weekly",
            is_template=True,
        )
        assert req.source_ref == "gmf:WP-143"
        assert req.is_template is True


class TestUpdateTaskRequestModel:
    def test_all_fields_optional(self):
        from memory_service.main import UpdateTaskRequest
        req = UpdateTaskRequest()
        assert req.status is None
        assert req.title is None

    def test_status_validated(self):
        from memory_service.main import UpdateTaskRequest
        req = UpdateTaskRequest(status="done")
        assert req.status.value == "done"

    def test_invalid_status_raises(self):
        from memory_service.main import UpdateTaskRequest
        with pytest.raises(ValidationError):
            UpdateTaskRequest(status="nope")

    def test_invalid_value_raises(self):
        from memory_service.main import UpdateTaskRequest
        with pytest.raises(ValidationError):
            UpdateTaskRequest(value="Z")


class TestLinkTasksRequestModel:
    def test_valid_blocks(self):
        from memory_service.main import LinkTasksRequest
        req = LinkTasksRequest(target_id=_TASK_ID_B, rel_type="BLOCKS")
        assert req.rel_type == "BLOCKS"

    def test_valid_depends_on(self):
        from memory_service.main import LinkTasksRequest
        req = LinkTasksRequest(target_id=_TASK_ID_B, rel_type="DEPENDS_ON")
        assert req.rel_type == "DEPENDS_ON"

    def test_invalid_rel_type_raises(self):
        from memory_service.main import LinkTasksRequest
        with pytest.raises(ValidationError):
            LinkTasksRequest(target_id=_TASK_ID_B, rel_type="HACKS")


# ---------------------------------------------------------------------------
# MemoryClient unit tests (respx mocked)
# ---------------------------------------------------------------------------

class TestClientCreateTask:
    @respx.mock
    def test_create_task_minimal(self):
        respx.post(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASK_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.create_task("Test task A", _AGENT_ID)
        assert result["id"] == _TASK_ID_A
        body = json.loads(respx.calls.last.request.content)
        assert body["title"] == "Test task A"
        assert body["agent_id"] == _AGENT_ID

    @respx.mock
    def test_create_task_with_value_effort(self):
        respx.post(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASK_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.create_task("Test task A", _AGENT_ID, value="H", effort="L")
        body = json.loads(respx.calls.last.request.content)
        assert body["value"] == "H"
        assert body["effort"] == "L"
        assert result["priority_score"] == 3.0

    @respx.mock
    def test_optional_fields_omitted_when_none(self):
        respx.post(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASK_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.create_task("Test task A", _AGENT_ID)
        body = json.loads(respx.calls.last.request.content)
        assert "due_at" not in body
        assert "description" not in body


class TestClientListTasks:
    @respx.mock
    def test_list_tasks_no_filters(self):
        respx.get(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASKS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            tasks = client.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == _TASK_ID_A

    @respx.mock
    def test_list_tasks_with_status_filter(self):
        respx.get(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASKS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.list_tasks(status="open")
        params = respx.calls.last.request.url.params
        assert params.get("status") == "open"

    @respx.mock
    def test_list_tasks_committed_only(self):
        respx.get(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASKS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.list_tasks(committed_only=True)
        params = respx.calls.last.request.url.params
        assert params.get("committed_only") == "true"


class TestClientListNextTasks:
    @respx.mock
    def test_list_next_tasks(self):
        respx.get(f"{_BASE_URL}/task/next").mock(
            return_value=httpx.Response(200, json=_TASKS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            tasks = client.list_next_tasks(limit=5)
        params = respx.calls.last.request.url.params
        assert params.get("limit") == "5"
        assert len(tasks) == 1


class TestClientUpdateTask:
    @respx.mock
    def test_update_task_status(self):
        updated = {**_TASK_RESPONSE, "status": "done"}
        respx.patch(f"{_BASE_URL}/task/{_TASK_ID_A}").mock(
            return_value=httpx.Response(200, json=updated)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.update_task(_TASK_ID_A, status="done")
        assert result["status"] == "done"
        body = json.loads(respx.calls.last.request.content)
        assert body["status"] == "done"


# ---------------------------------------------------------------------------
# CLI unit tests (CliRunner + respx)
# ---------------------------------------------------------------------------

class TestCliCreateTask:
    @respx.mock
    def test_create_task_prints_id(self):
        respx.post(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASK_RESPONSE)
        )
        result = _cli_runner.invoke(
            cli_app,
            ["create-task", "Test task A", "--agent-id", _AGENT_ID],
        )
        assert result.exit_code == 0
        assert _TASK_ID_A in result.output

    @respx.mock
    def test_create_task_with_value_effort(self):
        respx.post(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASK_RESPONSE)
        )
        result = _cli_runner.invoke(
            cli_app,
            ["create-task", "Test task A", "--agent-id", _AGENT_ID,
             "--value", "H", "--effort", "L"],
        )
        assert result.exit_code == 0
        body = json.loads(respx.calls.last.request.content)
        assert body["value"] == "H"
        assert body["effort"] == "L"

    def test_missing_agent_id_fails(self):
        result = _cli_runner.invoke(cli_app, ["create-task", "Test task A"])
        assert result.exit_code != 0


class TestCliListTasks:
    @respx.mock
    def test_list_tasks_table_output(self):
        respx.get(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json=_TASKS_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["list-tasks"])
        assert result.exit_code == 0
        assert "open" in result.output
        assert "H/L" in result.output

    @respx.mock
    def test_list_tasks_empty(self):
        respx.get(f"{_BASE_URL}/task").mock(
            return_value=httpx.Response(200, json={"tasks": []})
        )
        result = _cli_runner.invoke(cli_app, ["list-tasks"])
        assert result.exit_code == 0
        assert "No tasks found" in result.output


class TestCliNextTask:
    @respx.mock
    def test_next_task_output(self):
        next_resp = {"tasks": [{**_TASK_RESPONSE, "project_weight": 1.0}]}
        respx.get(f"{_BASE_URL}/task/next").mock(
            return_value=httpx.Response(200, json=next_resp)
        )
        result = _cli_runner.invoke(cli_app, ["next-task"])
        assert result.exit_code == 0
        assert "open" in result.output
        assert "3.00" in result.output


class TestCliCompleteTask:
    @respx.mock
    def test_complete_task_sends_done(self):
        updated = {**_TASK_RESPONSE, "status": "done"}
        respx.patch(f"{_BASE_URL}/task/{_TASK_ID_A}").mock(
            return_value=httpx.Response(200, json=updated)
        )
        result = _cli_runner.invoke(cli_app, ["complete-task", _TASK_ID_A])
        assert result.exit_code == 0
        body = json.loads(respx.calls.last.request.content)
        assert body["status"] == "done"


# ---------------------------------------------------------------------------
# MCP tool unit tests (mock client)
# ---------------------------------------------------------------------------

class TestMcpTaskAdd:
    def test_task_add_forwards_args(self):
        from mcp_server.server import task_add

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.create_task.return_value = _TASK_RESPONSE

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = task_add("Test task A", _AGENT_ID, value="H", effort="L")

        mock_client.create_task.assert_called_once_with(
            "Test task A", _AGENT_ID,
            description=None, status="open",
            value="H", effort="L",
            urgency=None, due_at=None,
            snooze_until=None, committed_at=None, committed_by=None,
            source_ref=None, project_id=None, memory_ids=None,
            recurrence=None, is_template=False,
        )
        assert result["id"] == _TASK_ID_A


class TestMcpTaskComplete:
    def test_task_complete_sends_done(self):
        from mcp_server.server import task_complete

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.update_task.return_value = {**_TASK_RESPONSE, "status": "done"}

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = task_complete(_TASK_ID_A)

        mock_client.update_task.assert_called_once_with(_TASK_ID_A, status="done")
        assert result["status"] == "done"


class TestMcpTaskNext:
    def test_task_next_forwards_limit(self):
        from mcp_server.server import task_next

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.list_next_tasks.return_value = [_TASK_RESPONSE]

        with patch("mcp_server.server.MemoryClient", return_value=mock_client):
            result = task_next(limit=5)

        mock_client.list_next_tasks.assert_called_once_with(limit=5)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration tests (live stack required)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPostTaskEndpoint:
    def test_create_task_minimal(self, client, test_driver):
        try:
            body = {"title": "Integration task A", "agent_id": _AGENT_ID}
            r = client.post("/task", json=body)
            assert r.status_code == 200
            data = r.json()
            assert data["title"] == "Integration task A"
            assert data["status"] == "open"
            assert data["is_template"] is False
            task_id = data["id"]
        finally:
            _cleanup_tasks(test_driver, task_id)

    def test_create_task_with_value_effort_computes_score(self, client, test_driver):
        task_id = None
        try:
            body = {"title": "Scored task", "agent_id": _AGENT_ID, "value": "H", "effort": "L"}
            r = client.post("/task", json=body)
            assert r.status_code == 200
            data = r.json()
            assert data["value"] == "H"
            assert data["effort"] == "L"
            assert data["priority_score"] == 3.0
            task_id = data["id"]
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_create_task_missing_title_returns_422(self, client):
        r = client.post("/task", json={"agent_id": _AGENT_ID})
        assert r.status_code == 422

    def test_create_task_missing_agent_id_returns_422(self, client):
        r = client.post("/task", json={"title": "No agent"})
        assert r.status_code == 422


@pytest.mark.integration
class TestGetTaskListEndpoint:
    def test_returns_tasks_list(self, client, test_driver):
        task_id = None
        try:
            r_create = client.post("/task", json={"title": "List test", "agent_id": _AGENT_ID})
            task_id = r_create.json()["id"]
            r = client.get("/task")
            assert r.status_code == 200
            data = r.json()
            assert "tasks" in data
            ids = [t["id"] for t in data["tasks"]]
            assert task_id in ids
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_filter_by_status(self, client, test_driver):
        task_id = None
        try:
            r_create = client.post("/task", json={"title": "Open task", "agent_id": _AGENT_ID, "status": "open"})
            task_id = r_create.json()["id"]
            r = client.get("/task", params={"status": "open"})
            assert r.status_code == 200
            ids = [t["id"] for t in r.json()["tasks"]]
            assert task_id in ids
            r_done = client.get("/task", params={"status": "done"})
            ids_done = [t["id"] for t in r_done.json()["tasks"]]
            assert task_id not in ids_done
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_template_excluded_from_default_list(self, client, test_driver):
        task_id = None
        try:
            r = client.post("/task", json={
                "title": "Template task", "agent_id": _AGENT_ID, "is_template": True
            })
            task_id = r.json()["id"]
            r_list = client.get("/task")
            ids = [t["id"] for t in r_list.json()["tasks"]]
            assert task_id not in ids
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)


@pytest.mark.integration
class TestGetNextTasks:
    def test_returns_open_tasks_sorted_by_score(self, client, test_driver):
        id_h = id_l = None
        try:
            r1 = client.post("/task", json={
                "title": "High value task", "agent_id": _AGENT_ID,
                "value": "H", "effort": "L",
            })
            id_h = r1.json()["id"]
            r2 = client.post("/task", json={
                "title": "Low value task", "agent_id": _AGENT_ID,
                "value": "L", "effort": "H",
            })
            id_l = r2.json()["id"]
            r = client.get("/task/next")
            assert r.status_code == 200
            tasks = r.json()["tasks"]
            ids = [t["id"] for t in tasks]
            assert id_h in ids
            assert id_l in ids
            # Higher score should rank first
            assert ids.index(id_h) < ids.index(id_l)
        finally:
            _cleanup_tasks(test_driver, *[i for i in [id_h, id_l] if i])


@pytest.mark.integration
class TestGetSingleTask:
    def test_get_existing_task(self, client, test_driver):
        task_id = None
        try:
            r = client.post("/task", json={"title": "Single task", "agent_id": _AGENT_ID})
            task_id = r.json()["id"]
            r2 = client.get(f"/task/{task_id}")
            assert r2.status_code == 200
            assert r2.json()["id"] == task_id
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_get_unknown_task_returns_404(self, client):
        r = client.get("/task/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


@pytest.mark.integration
class TestPatchTaskEndpoint:
    def test_patch_updates_status(self, client, test_driver):
        task_id = None
        try:
            r = client.post("/task", json={"title": "Patchable task", "agent_id": _AGENT_ID})
            task_id = r.json()["id"]
            original_updated_at = r.json()["updated_at"]

            r2 = client.patch(f"/task/{task_id}", json={"status": "active"})
            assert r2.status_code == 200
            assert r2.json()["status"] == "active"
            assert r2.json()["updated_at"] >= original_updated_at
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_patch_recomputes_priority_score(self, client, test_driver):
        task_id = None
        try:
            r = client.post("/task", json={
                "title": "Score task", "agent_id": _AGENT_ID, "value": "M", "effort": "M"
            })
            task_id = r.json()["id"]
            assert r.json()["priority_score"] == 1.0

            # Patch only value — effort (M) should be read from stored node
            r2 = client.patch(f"/task/{task_id}", json={"value": "H"})
            assert r2.status_code == 200
            assert r2.json()["priority_score"] == pytest.approx(1.5)  # H/M = 3/2
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_patch_unknown_task_returns_404(self, client):
        r = client.patch("/task/00000000-0000-0000-0000-000000000000", json={"status": "done"})
        assert r.status_code == 404


@pytest.mark.integration
class TestDeleteTaskEndpoint:
    def test_delete_removes_task(self, client, test_driver):
        from tests.conftest import node_exists
        task_id = None
        try:
            r = client.post("/task", json={"title": "Deletable task", "agent_id": _AGENT_ID})
            task_id = r.json()["id"]
            r2 = client.delete(f"/task/{task_id}")
            assert r2.status_code == 200
            assert r2.json()["deleted"] is True
            assert not node_exists(test_driver, "Task", task_id)
        finally:
            # Node should already be gone; cleanup is safe to call anyway
            _cleanup_tasks(test_driver, task_id)

    def test_delete_unknown_task_returns_404(self, client):
        r = client.delete("/task/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


@pytest.mark.integration
class TestStaleTaskEndpoint:
    def test_stale_task_appears_in_stale_list(self, client, test_driver):
        task_id = None
        try:
            # committed_at set at creation, never updated → stale
            r = client.post("/task", json={
                "title": "Stale committed task", "agent_id": _AGENT_ID,
                "committed_at": "2026-04-14T10:00:00+00:00",
                "committed_by": _AGENT_ID,
            })
            task_id = r.json()["id"]
            r2 = client.get("/task/stale")
            assert r2.status_code == 200
            ids = [t["id"] for t in r2.json()["tasks"]]
            assert task_id in ids
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_updated_task_not_in_stale_list(self, client, test_driver):
        task_id = None
        try:
            r = client.post("/task", json={
                "title": "Updated committed task", "agent_id": _AGENT_ID,
                "committed_at": "2026-04-14T10:00:00+00:00",
                "committed_by": _AGENT_ID,
            })
            task_id = r.json()["id"]
            # Update the task status — this advances updated_at past committed_at
            client.patch(f"/task/{task_id}", json={"status": "active"})
            r2 = client.get("/task/stale")
            ids = [t["id"] for t in r2.json()["tasks"]]
            assert task_id not in ids
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)


@pytest.mark.integration
class TestTaskEdges:
    def test_owned_by_agent_edge_exists(self, client, test_driver):
        from tests.conftest import edge_exists
        task_id = None
        try:
            r = client.post("/task", json={"title": "Edge test", "agent_id": _AGENT_ID})
            task_id = r.json()["id"]
            assert edge_exists(test_driver, task_id, "OWNED_BY", _AGENT_ID)
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)

    def test_for_project_edge_when_project_id_supplied(self, client, test_driver):
        from tests.conftest import edge_exists
        task_id = None
        try:
            r = client.post("/task", json={
                "title": "Project task", "agent_id": _AGENT_ID,
                "project_id": _PROJECT_ID,
            })
            task_id = r.json()["id"]
            assert r.json()["project_id"] == _PROJECT_ID
            assert edge_exists(test_driver, task_id, "FOR_PROJECT", _PROJECT_ID)
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id, project_ids=(_PROJECT_ID,))


@pytest.mark.integration
class TestTaskLinkEndpoint:
    def test_blocks_edge_created(self, client, test_driver):
        from tests.conftest import edge_exists
        id_a = id_b = None
        try:
            id_a = client.post("/task", json={"title": "Blocker", "agent_id": _AGENT_ID}).json()["id"]
            id_b = client.post("/task", json={"title": "Blocked", "agent_id": _AGENT_ID}).json()["id"]
            r = client.post(f"/task/{id_a}/link", json={"target_id": id_b, "rel_type": "BLOCKS"})
            assert r.status_code == 200
            assert edge_exists(test_driver, id_a, "BLOCKS", id_b)
        finally:
            _cleanup_tasks(test_driver, *[i for i in [id_a, id_b] if i])

    def test_invalid_rel_type_returns_422(self, client, test_driver):
        task_id = None
        try:
            task_id = client.post("/task", json={"title": "Link test", "agent_id": _AGENT_ID}).json()["id"]
            r = client.post(f"/task/{task_id}/link", json={
                "target_id": "00000000-0000-0000-0000-000000000000", "rel_type": "HACKS"
            })
            assert r.status_code == 422
        finally:
            if task_id:
                _cleanup_tasks(test_driver, task_id)


@pytest.mark.integration
class TestProjectExtension:
    def test_create_project_with_slug_and_weight(self, client, test_driver):
        try:
            r = client.post("/project", json={
                "id": _PROJECT_ID, "name": "Test Project WP143",
                "slug": "gmf", "weight": 1.5,
            })
            assert r.status_code == 200
            data = r.json()
            assert data["slug"] == "gmf"
            assert data["weight"] == 1.5
        finally:
            with test_driver.session() as s:
                s.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=_PROJECT_ID)

    def test_list_projects_includes_slug_weight(self, client, test_driver):
        try:
            client.post("/project", json={
                "id": _PROJECT_ID, "name": "Test Project WP143",
                "slug": "gmf", "weight": 2.0,
            })
            r = client.get("/project")
            proj = next(p for p in r.json()["projects"] if p["id"] == _PROJECT_ID)
            assert proj["slug"] == "gmf"
            assert proj["weight"] == 2.0
        finally:
            with test_driver.session() as s:
                s.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=_PROJECT_ID)
