"""WP-174 unit tests — new enum frozensets in cyber_knowledge.schemas."""

import pytest

from cyber_knowledge import schemas


@pytest.mark.parametrize(
    "name,expected",
    [
        ("POLICY_STATUS", {"draft", "active", "deprecated", "retired"}),
        ("PARAM_TYPE", {"string", "integer", "enum", "select", "datetime", "duration"}),
        (
            "ASSET_CLASS_KIND",
            {"it", "ot", "iot", "integration", "data", "process", "people", "facility"},
        ),
    ],
)
def test_enum_frozenset_members(name, expected):
    value = getattr(schemas, name)
    assert isinstance(value, frozenset)
    assert value == frozenset(expected)
