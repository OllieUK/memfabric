# tests/test_wp037_person_nodes.py
import json

import httpx
import pytest
import respx
from pydantic import ValidationError
from typer.testing import CliRunner

from memory_client.cli import app as cli_app
from memory_client.client import MemoryClient

_BASE_URL = "http://localhost:8000"
_PERSONS_RESPONSE = {
    "persons": [
        {"id": "test-person-wp037-a", "name": "Test Person A", "description": None},
        {"id": "test-person-wp037-b", "name": "Test Person B", "description": "Bio B"},
    ]
}
_CREATE_PERSON_RESPONSE = {"id": "test-person-wp037-a", "name": "Test Person A", "description": None}

_cli_runner = CliRunner()

# Shared constants
_PERSON_ID_A = "test-person-wp037-a"
_PERSON_ID_B = "test-person-wp037-b"
_AGENT_ID = "test-agent-wp037"


def _cleanup_persons(driver, *person_ids, memory_ids=()):
    """Clean up test Person nodes and optionally Memory nodes."""
    from tests.conftest import cleanup_nodes
    # Clean up memories
    if memory_ids:
        cleanup_nodes(driver, *memory_ids)
    # Clean up Agent node
    with driver.session() as session:
        session.run("MATCH (a:Agent {id: $id}) DETACH DELETE a", id=_AGENT_ID)
    # Clean up Person nodes (one at a time since extra_ids supports only one per label)
    with driver.session() as session:
        for pid in person_ids:
            session.run("MATCH (p:Person {id: $id}) DETACH DELETE p", id=pid)


def _add_memory_body(fact: str, person_ids: list = None) -> dict:
    body = {
        "fact": fact,
        "type": "fact",
        "agent_id": _AGENT_ID,
        "importance": 1,
    }
    if person_ids is not None:
        body["person_ids"] = person_ids
    return body


# ---------------------------------------------------------------------------
# Task 1 — Unit tests: CreatePersonRequest model
# ---------------------------------------------------------------------------

class TestCreatePersonRequestModel:
    def test_id_and_name_required_fields(self):
        from memory_service.main import CreatePersonRequest
        with pytest.raises(ValidationError):
            CreatePersonRequest()

    def test_name_required_field(self):
        from memory_service.main import CreatePersonRequest
        with pytest.raises(ValidationError):
            CreatePersonRequest(id="x")

    def test_description_defaults_to_none(self):
        from memory_service.main import CreatePersonRequest
        req = CreatePersonRequest(id="oliver-james", name="Oliver James")
        assert req.description is None

    def test_description_accepted_as_string(self):
        from memory_service.main import CreatePersonRequest
        req = CreatePersonRequest(id="oliver-james", name="Oliver James", description="Project owner")
        assert req.description == "Project owner"


# ---------------------------------------------------------------------------
# Task 4 — Integration tests: GET /person
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestGetPersonEndpoint:
    def test_returns_200_with_persons_key(self, client):
        response = client.get("/person")
        assert response.status_code == 200
        assert "persons" in response.json()

    def test_returns_list_type(self, client):
        response = client.get("/person")
        assert isinstance(response.json()["persons"], list)

    def test_newly_created_person_appears_in_list(self, client, test_driver):
        # Create a person then verify it appears in the list
        client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
        try:
            response = client.get("/person")
            ids = [p["id"] for p in response.json()["persons"]]
            assert _PERSON_ID_A in ids
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_list_ordered_by_id(self, client, test_driver):
        # Insert in reverse alphabetical order
        client.post("/person", json={"id": "zzz-test-wp037", "name": "ZZZ"})
        client.post("/person", json={"id": "aaa-test-wp037", "name": "AAA"})
        try:
            response = client.get("/person")
            persons = response.json()["persons"]
            test_persons = [p for p in persons if p["id"] in ("zzz-test-wp037", "aaa-test-wp037")]
            ids = [p["id"] for p in test_persons]
            assert ids == sorted(ids)
        finally:
            _cleanup_persons(test_driver, "aaa-test-wp037", "zzz-test-wp037")

    def test_person_item_has_required_fields(self, client, test_driver):
        client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
        try:
            response = client.get("/person")
            persons = response.json()["persons"]
            item = next(p for p in persons if p["id"] == _PERSON_ID_A)
            assert "id" in item and isinstance(item["id"], str)
            assert "name" in item and isinstance(item["name"], str)
            assert "description" in item  # may be null
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)


# ---------------------------------------------------------------------------
# Task 4 — Integration tests: POST /person
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPostPersonEndpoint:
    def test_returns_200_with_person_fields(self, client, test_driver):
        try:
            response = client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == _PERSON_ID_A
            assert data["name"] == "Test Person A"
            assert "description" in data
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_person_node_exists_in_graph_after_create(self, client, test_driver):
        from tests.conftest import node_exists
        try:
            client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
            assert node_exists(test_driver, "Person", _PERSON_ID_A)
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_create_without_description_stores_null(self, client, test_driver):
        try:
            response = client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
            assert response.json()["description"] is None
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_create_with_description_stores_value(self, client, test_driver):
        try:
            response = client.post("/person", json={
                "id": _PERSON_ID_A, "name": "Test Person A", "description": "Bio text"
            })
            assert response.json()["description"] == "Bio text"
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_upsert_updates_name_on_second_call(self, client, test_driver):
        try:
            client.post("/person", json={"id": _PERSON_ID_A, "name": "Original Name"})
            response = client.post("/person", json={"id": _PERSON_ID_A, "name": "Updated Name"})
            assert response.json()["name"] == "Updated Name"
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_upsert_updates_description_on_second_call(self, client, test_driver):
        try:
            client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A", "description": "First"})
            response = client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A", "description": "Second"})
            assert response.json()["description"] == "Second"
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_upsert_does_not_create_duplicate_node(self, client, test_driver):
        try:
            client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
            client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A Again"})
            with test_driver.session() as session:
                result = session.run(
                    "MATCH (p:Person {id: $id}) RETURN count(p) AS cnt",
                    id=_PERSON_ID_A,
                )
                assert result.single()["cnt"] == 1
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A)

    def test_missing_id_returns_422(self, client):
        response = client.post("/person", json={"name": "No ID"})
        assert response.status_code == 422

    def test_missing_name_returns_422(self, client):
        response = client.post("/person", json={"id": "some-id"})
        assert response.status_code == 422

    def test_503_when_db_unavailable(self, client):
        from unittest.mock import MagicMock
        from neo4j.exceptions import ServiceUnavailable
        from memory_service.main import app
        mock_driver = MagicMock()
        mock_driver.session.side_effect = ServiceUnavailable("connection refused")
        original = app.state.driver
        app.state.driver = mock_driver
        try:
            response = client.post("/person", json={"id": "test-id", "name": "Test"})
            assert response.status_code == 503
        finally:
            app.state.driver = original


# ---------------------------------------------------------------------------
# Task 5 — ABOUT edge regression tests: POST /memory with person_ids
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAboutEdgeViaPostMemory:
    def test_about_edge_created_when_person_id_provided(self, client, test_driver):
        from tests.conftest import edge_exists
        response = client.post("/memory", json=_add_memory_body(
            "WP-037 about edge test", person_ids=[_PERSON_ID_A]
        ))
        memory_id = response.json()["memory_id"]
        try:
            assert edge_exists(test_driver, memory_id, "ABOUT", _PERSON_ID_A)
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A, memory_ids=(memory_id,))

    def test_person_node_created_implicitly_by_add_memory(self, client, test_driver):
        from tests.conftest import node_exists
        response = client.post("/memory", json=_add_memory_body(
            "WP-037 implicit person test", person_ids=[_PERSON_ID_A]
        ))
        memory_id = response.json()["memory_id"]
        try:
            assert node_exists(test_driver, "Person", _PERSON_ID_A)
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A, memory_ids=(memory_id,))

    def test_no_about_edge_when_person_ids_empty(self, client, test_driver):
        response = client.post("/memory", json=_add_memory_body(
            "WP-037 no person test", person_ids=[]
        ))
        memory_id = response.json()["memory_id"]
        try:
            with test_driver.session() as session:
                result = session.run(
                    "MATCH (m:Memory {id: $mid})-[:ABOUT]->(p:Person) RETURN count(p) AS cnt",
                    mid=memory_id,
                )
                assert result.single()["cnt"] == 0
        finally:
            _cleanup_persons(test_driver, memory_ids=(memory_id,))

    def test_multiple_person_ids_create_multiple_about_edges(self, client, test_driver):
        from tests.conftest import edge_exists
        response = client.post("/memory", json=_add_memory_body(
            "WP-037 multi-person test", person_ids=[_PERSON_ID_A, _PERSON_ID_B]
        ))
        memory_id = response.json()["memory_id"]
        try:
            assert edge_exists(test_driver, memory_id, "ABOUT", _PERSON_ID_A)
            assert edge_exists(test_driver, memory_id, "ABOUT", _PERSON_ID_B)
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A, _PERSON_ID_B, memory_ids=(memory_id,))


# ---------------------------------------------------------------------------
# Task 5 — ABOUT edge combined flow tests: POST /person then POST /memory
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAboutEdgeViaPostPerson:
    def test_post_person_then_post_memory_creates_about_edge(self, client, test_driver):
        from tests.conftest import edge_exists
        client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
        response = client.post("/memory", json=_add_memory_body(
            "WP-037 combined flow test", person_ids=[_PERSON_ID_A]
        ))
        memory_id = response.json()["memory_id"]
        try:
            assert edge_exists(test_driver, memory_id, "ABOUT", _PERSON_ID_A)
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A, memory_ids=(memory_id,))

    def test_about_edge_is_idempotent(self, client, test_driver):
        from tests.conftest import edge_exists
        client.post("/person", json={"id": _PERSON_ID_A, "name": "Test Person A"})
        # Two separate memories about the same person
        resp1 = client.post("/memory", json=_add_memory_body("WP-037 idempotent 1", person_ids=[_PERSON_ID_A]))
        resp2 = client.post("/memory", json=_add_memory_body("WP-037 idempotent 2", person_ids=[_PERSON_ID_A]))
        mid1 = resp1.json()["memory_id"]
        mid2 = resp2.json()["memory_id"]
        try:
            # The Person node should still exist exactly once
            with test_driver.session() as session:
                result = session.run(
                    "MATCH (p:Person {id: $id}) RETURN count(p) AS cnt",
                    id=_PERSON_ID_A,
                )
                assert result.single()["cnt"] == 1
            # Both ABOUT edges should exist
            assert edge_exists(test_driver, mid1, "ABOUT", _PERSON_ID_A)
            assert edge_exists(test_driver, mid2, "ABOUT", _PERSON_ID_A)
        finally:
            _cleanup_persons(test_driver, _PERSON_ID_A, memory_ids=(mid1, mid2))


# ---------------------------------------------------------------------------
# Task 6 — Unit tests: MemoryClient.list_persons and MemoryClient.create_person
# ---------------------------------------------------------------------------


class TestMemoryClientListPersons:
    @respx.mock
    def test_calls_get_person_endpoint(self):
        route = respx.get(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json=_PERSONS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.list_persons()
        assert route.called

    @respx.mock
    def test_returns_list_of_person_dicts(self):
        respx.get(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json=_PERSONS_RESPONSE)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.list_persons()
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == "test-person-wp037-a"

    @respx.mock
    def test_returns_empty_list_when_no_persons(self):
        respx.get(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json={"persons": []})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.list_persons()
        assert result == []

    @respx.mock
    def test_raises_on_503(self):
        respx.get(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.list_persons()


class TestMemoryClientCreatePerson:
    @respx.mock
    def test_calls_post_person_endpoint(self):
        route = respx.post(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json={"id": "test-person-wp037-a", "name": "Test Person A", "description": None})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.create_person("test-person-wp037-a", "Test Person A")
        assert route.called

    @respx.mock
    def test_body_contains_id_and_name(self):
        route = respx.post(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json={"id": "test-person-wp037-a", "name": "Test Person A", "description": None})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.create_person("test-person-wp037-a", "Test Person A")
        body = route.calls[0].request.content
        parsed = json.loads(body)
        assert parsed["id"] == "test-person-wp037-a"
        assert parsed["name"] == "Test Person A"

    @respx.mock
    def test_description_omitted_when_none(self):
        route = respx.post(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json={"id": "x", "name": "X", "description": None})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.create_person("x", "X")
        body = json.loads(route.calls[0].request.content)
        assert "description" not in body

    @respx.mock
    def test_description_sent_when_provided(self):
        route = respx.post(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json={"id": "x", "name": "X", "description": "bio"})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            client.create_person("x", "X", description="bio")
        body = json.loads(route.calls[0].request.content)
        assert body["description"] == "bio"

    @respx.mock
    def test_returns_person_dict_from_response(self):
        person = {"id": "test-person-wp037-a", "name": "Test Person A", "description": "Bio"}
        respx.post(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(200, json=person)
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            result = client.create_person("test-person-wp037-a", "Test Person A", description="Bio")
        assert result == person

    @respx.mock
    def test_raises_on_422(self):
        respx.post(f"{_BASE_URL}/person").mock(
            return_value=httpx.Response(422, json={"detail": "Validation error"})
        )
        with MemoryClient(base_url=_BASE_URL) as client:
            with pytest.raises(httpx.HTTPStatusError):
                client.create_person("", "")


# ---------------------------------------------------------------------------
# Task 8 — Unit tests: CLI list-persons and create-person commands
# ---------------------------------------------------------------------------


class TestListPersonsCLI:
    @respx.mock
    def test_exits_zero_on_success(self):
        respx.get("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json=_PERSONS_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["list-persons"])
        assert result.exit_code == 0

    @respx.mock
    def test_renders_person_id_in_output(self):
        respx.get("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json=_PERSONS_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["list-persons"])
        assert "test-person-wp037-a" in result.output

    @respx.mock
    def test_renders_person_name_in_output(self):
        respx.get("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json=_PERSONS_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["list-persons"])
        assert "Test Person A" in result.output

    @respx.mock
    def test_empty_persons_prints_no_persons_found(self):
        respx.get("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json={"persons": []})
        )
        result = _cli_runner.invoke(cli_app, ["list-persons"])
        assert "No persons found" in result.output

    @respx.mock
    def test_service_error_exits_nonzero(self):
        respx.get("http://localhost:8000/person").mock(
            return_value=httpx.Response(503, text="Service Unavailable")
        )
        result = _cli_runner.invoke(cli_app, ["list-persons"])
        assert result.exit_code != 0

    def test_connect_error_exits_nonzero(self):
        result = _cli_runner.invoke(
            cli_app,
            ["list-persons"],
            env={"API_BASE_URL": "http://localhost:19999"},
        )
        assert result.exit_code != 0


class TestCreatePersonCLI:
    @respx.mock
    def test_exits_zero_and_prints_id(self):
        respx.post("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json=_CREATE_PERSON_RESPONSE)
        )
        result = _cli_runner.invoke(cli_app, ["create-person", "test-person-wp037-a", "--name", "Test Person A"])
        assert result.exit_code == 0
        assert "test-person-wp037-a" in result.output

    def test_name_option_is_required(self):
        result = _cli_runner.invoke(cli_app, ["create-person", "test-person-wp037-a"])
        assert result.exit_code != 0

    @respx.mock
    def test_sends_correct_body_without_description(self):
        route = respx.post("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json=_CREATE_PERSON_RESPONSE)
        )
        _cli_runner.invoke(cli_app, ["create-person", "test-person-wp037-a", "--name", "Test Person A"])
        body = json.loads(route.calls[0].request.content)
        assert body["id"] == "test-person-wp037-a"
        assert body["name"] == "Test Person A"
        assert "description" not in body

    @respx.mock
    def test_sends_description_when_provided(self):
        route = respx.post("http://localhost:8000/person").mock(
            return_value=httpx.Response(200, json={**_CREATE_PERSON_RESPONSE, "description": "bio"})
        )
        _cli_runner.invoke(cli_app, [
            "create-person", "test-person-wp037-a", "--name", "Test Person A", "--description", "bio"
        ])
        body = json.loads(route.calls[0].request.content)
        assert body["description"] == "bio"

    @respx.mock
    def test_service_error_exits_nonzero(self):
        respx.post("http://localhost:8000/person").mock(
            return_value=httpx.Response(422, json={"detail": "Unprocessable"})
        )
        result = _cli_runner.invoke(cli_app, ["create-person", "bad-id", "--name", "Bad"])
        assert result.exit_code != 0
