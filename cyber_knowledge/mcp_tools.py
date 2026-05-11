"""Cyber knowledge MCP tools — door 2 of the ADR-003 bridge contract.

Consumed only by `mcp_server.server`. Exposes a single `register(mcp_app)`
entry point that the MCP server calls under the `ENABLE_KNOWLEDGE_LAYER`
feature flag. No other module in this package may be imported from
`mcp_server`.
"""

from __future__ import annotations

from cyber_knowledge import bridge, repo as knowledge_repo
from memory_service.config import get_driver, settings

# Re-export the bridge module so `mcp_server.server` can satisfy ADR-003 §2
# "door 2" by importing only from `cyber_knowledge.mcp_tools`. The bridge
# surface remains stable per ADR-003.
__all__ = ["register", "bridge"]

_cached_driver = None


def _driver():
    """Lazy-init shared driver for cyber MCP tools."""
    global _cached_driver
    if _cached_driver is None:
        _cached_driver = get_driver(settings)
    return _cached_driver


def register(mcp_app) -> None:
    """Register the cyber-knowledge MCP tools against the given FastMCP app.

    Called from `mcp_server.server` only when `settings.enable_knowledge_layer`
    is true. Registers five tools:
    `knowledge_search_controls`, `knowledge_search_chunks`,
    `knowledge_list_norms`, `knowledge_get_control`, `knowledge_get_norm`.
    """

    @mcp_app.tool
    def knowledge_search_controls(
        query: str,
        limit: int = 10,
        framework_id: str | None = None,
    ) -> list[dict]:
        """Search InfoSec controls by semantic similarity.

        Use this tool when an agent needs to find controls relevant to a topic,
        threat, or gap (e.g. "access control for privileged accounts"). Returns
        controls ranked by vector distance to the query, optionally filtered to a
        single framework (e.g. "nist-csf-2.0" or "iso-27001-2022").

        Do NOT use this for searching episodic memories — call memory_search instead.
        Requires ENABLE_KNOWLEDGE_LAYER=true and at least one framework loaded via
        ingest_framework.py.
        """
        with _driver().session() as session:
            return knowledge_repo.search_controls(session, query, limit=limit, framework_id=framework_id)

    @mcp_app.tool
    def knowledge_search_chunks(
        query: str,
        limit: int = 10,
        doc_id: str | None = None,
    ) -> list[dict]:
        """Search policy/procedure document chunks by semantic similarity.

        Use when an agent needs to find specific passages in loaded documents that
        are relevant to a topic (e.g. "data retention requirements" or "incident
        escalation procedure"). Returns chunks ranked by vector distance, optionally
        filtered to a single document by its doc_id.

        Do NOT use this for searching episodic memories — call memory_search instead.
        Requires ENABLE_KNOWLEDGE_LAYER=true and at least one document ingested.
        """
        with _driver().session() as session:
            return knowledge_repo.search_chunks(session, query, limit=limit, doc_id=doc_id)

    @mcp_app.tool
    def knowledge_list_norms() -> list[dict]:
        """Return all regulatory norms in the knowledge layer.

        Use when an agent needs the full catalogue of norms to present options to
        the user or to identify which norms apply to a given control. Each norm has
        id, name, text, status, and effective_date.

        This is a catalogue listing, not a search. For semantic search over norm
        text, use knowledge_search_controls (norms are linked to controls via
        IMPLEMENTS edges; searching controls surfaces related norms indirectly).
        """
        with _driver().session() as session:
            return knowledge_repo.list_norms(session)

    @mcp_app.tool
    def knowledge_get_control(control_id: str) -> dict:
        """Fetch a single InfoSec control by its ID.

        Use when an agent already has a control_id (e.g. from knowledge_search_controls)
        and needs its full details: name, description, framework_id, and created_at.
        Returns 404 detail if the control does not exist.
        """
        with _driver().session() as session:
            return knowledge_repo.get_control(session, control_id)

    @mcp_app.tool
    def knowledge_get_norm(norm_id: str) -> dict:
        """Fetch a single regulatory norm by its ID.

        Use when an agent already has a norm_id (e.g. from knowledge_list_norms)
        and needs its full details: name, text, status, and effective_date.
        Returns 404 detail if the norm does not exist.
        """
        with _driver().session() as session:
            return knowledge_repo.get_norm(session, norm_id)
