"""Tests for scripts/schema_utils.py (WP-077).

Unit tests only — no live Memgraph required.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from neo4j.exceptions import ClientError

# Allow importing from scripts/ directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_create_constraint_runs_query():
    """create_constraint calls session.run with correct Cypher."""
    from schema_utils import create_constraint

    session = MagicMock()
    create_constraint(session, "Memory", "id")
    session.run.assert_called_once()
    call_args = session.run.call_args[0][0]
    assert "Memory" in call_args
    assert "id" in call_args
    assert "UNIQUE" in call_args


def test_create_constraint_skips_existing():
    """create_constraint does not raise when constraint already exists."""
    from schema_utils import create_constraint

    session = MagicMock()
    session.run.side_effect = ClientError("already exists")
    # Must not raise
    create_constraint(session, "Memory", "id")


def test_create_constraint_reraises_other_errors():
    """create_constraint re-raises ClientError for non-duplicate errors."""
    from schema_utils import create_constraint

    session = MagicMock()
    session.run.side_effect = ClientError("some other db error")
    with pytest.raises(ClientError):
        create_constraint(session, "Memory", "id")


def test_get_embedding_dimension_returns_int():
    """get_embedding_dimension returns the model's embedding dimension as int."""
    with patch("schema_utils.SentenceTransformer") as mock_st:
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_st.return_value = mock_model
        from schema_utils import get_embedding_dimension

        result = get_embedding_dimension("all-MiniLM-L6-v2")
        assert result == 384
        assert isinstance(result, int)
        mock_st.assert_called_once_with("all-MiniLM-L6-v2")
