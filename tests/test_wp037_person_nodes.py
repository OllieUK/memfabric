# tests/test_wp037_person_nodes.py
import pytest
from pydantic import ValidationError


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
