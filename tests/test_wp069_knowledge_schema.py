"""
tests/test_wp069_knowledge_schema.py — Tests for WP-069 + WP-094: knowledge layer schema.

Unit tests verify enum values, allowlists, and schema constants without a live DB.
Integration tests (require live Memgraph + FastAPI) verify that constraints and vector
indexes are created correctly and that the separation invariant holds.
"""

import pytest

from memory_service import main as service_main
from memory_service.knowledge_schemas import (
    CONTROL_DOMAINS,
    CONTROL_RELATIONSHIP_TYPES,
    DOCUMENT_POLICY_LEVELS,
    JURISDICTION_TYPES,
    ORGANISATION_TYPES,
    SABSA_LAYERS,
)
from scripts import dump_db, restore_db


# ---------------------------------------------------------------------------
# Unit tests — config new settings (WP-094)
# ---------------------------------------------------------------------------

def test_config_has_knowledge_embedding_model():
    from memory_service.config import Settings
    s = Settings()
    assert s.knowledge_embedding_model == "paraphrase-multilingual-MiniLM-L12-v2"


def test_config_has_enable_knowledge_layer_default_false():
    from memory_service.config import Settings
    s = Settings()
    assert s.enable_knowledge_layer is False
