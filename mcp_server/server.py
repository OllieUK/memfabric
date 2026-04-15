"""MCP server for graph-memory-fabric.

Exposes tools via FastMCP over STDIO transport:
  memory_add, memory_search, memory_wake_up, memory_list_strands, memory_close_session,
  memory_list_persons, memory_create_person,
  memory_list_projects, memory_create_project,
  memory_short_rest, memory_long_rest, memory_maintenance_stats,
  memory_update, memory_archive, memory_restore, memory_delete, memory_merge,
  memory_find_duplicates, memory_purge_ephemeral
"""
from fastmcp import FastMCP

from memory_client.client import MemoryClient
from memory_client.formatting import format_wake_up, _format_timestamp
from mcp_server.config import settings


mcp = FastMCP("graph-memory-fabric")



@mcp.tool
def memory_add(
    fact: str,
    agent_id: str,
    type: str = "fact",
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
    person_ids: list[str] | None = None,
    control_ids: list[str] | None = None,
    doc_ids: list[str] | None = None,
    control_relationship_type: str | None = None,
    org_id: str | None = None,
) -> dict:
    """Add a memory to the fabric.

    agent_id is required — pass your own agent identifier (e.g. "claude-code",
    "engineering-implementer"). Do NOT omit it or pass "claude-code" unless you
    ARE the main Claude Code session. Returns the memory_id (existing if a
    duplicate was detected).

    strand_ids should always be provided so the memory is correctly threaded.
    ALWAYS call memory_list_strands() first to get the current strand catalogue
    with IDs, names, and descriptions — do not guess strand IDs. If strand_ids
    is omitted, the memory is auto-assigned to strand-inbox (weight=0.3) and
    flagged for review; re-thread it via memory_update() once you know the
    correct strand.
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.add_memory(
            fact,
            type,
            agent_id,
            so_what=so_what,
            cause_ids=cause_ids,
            effect_ids=effect_ids,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
            person_ids=person_ids,
            control_ids=control_ids,
            doc_ids=doc_ids,
            control_relationship_type=control_relationship_type,
            org_id=org_id,
        )
    if not strand_ids:
        result["warning"] = (
            "No strand_ids provided — memory auto-assigned to strand-inbox. "
            "Call memory_list_strands() and re-thread via memory_update() with the correct strand."
        )
    return result


@mcp.tool
def memory_search(
    query: str,
    tags: list[str] | None = None,
    agent_ids: list[str] | None = None,
    person_ids: list[str] | None = None,
    limit: int = 10,
    traversal_direction: str = "none",
) -> list[dict]:
    """Search the memory fabric by semantic similarity.

    Pass person_ids to restrict results to memories linked via ABOUT edges
    to the specified Person nodes (e.g. ["mara", "oliver"]).
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.search_memory(
            query,
            tags=tags,
            agent_ids=agent_ids,
            person_ids=person_ids,
            limit=limit,
            traversal_direction=traversal_direction,
        )


@mcp.tool
def memory_wake_up(
    topic: str | None = None,
    limit: int = 20,
    person_id: str | None = None,
) -> str:
    """Return the session wake-up briefing as plain text. Read fully before responding to the user."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.wake_up_split(limit=limit, topic=topic, person_id=person_id)

    lines = []

    # Maintenance alert — shown prominently at the top when action needed
    maintenance_status = result.get("maintenance_status") or {}
    action = maintenance_status.get("recommended_action")
    if action:
        lines += ["## ⚠ Maintenance required", "", f"  {action}", ""]

    lines.append(format_wake_up(result, topic=topic, plain=True))
    return "\n".join(lines)


@mcp.tool
def memory_list_strands() -> list[dict]:
    """Return all strands from the graph (authoritative live list).

    Call this before memory_add or memory_update to get current strand IDs,
    names, descriptions, and categories. Do not guess or hard-code strand IDs.
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.list_strands()


@mcp.tool
def memory_list_persons() -> list[dict]:
    """Return all Person nodes. Use person IDs when calling memory_add."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.list_persons()


@mcp.tool
def memory_create_person(person_id: str, name: str, description: str | None = None) -> dict:
    """Create or merge a Person node. Returns the person dict."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.create_person(person_id, name, description=description)


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


@mcp.tool
def memory_reinforce(memory_id: str, co_recalled_ids: list[str] | None = None) -> dict:
    """Explicitly reinforce a memory. Pass co_recalled_ids for Hebbian edge strengthening."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.reinforce_memory(memory_id, co_recalled_ids=co_recalled_ids)


@mcp.tool
def memory_run_decay() -> dict:
    """Trigger a full-graph decay pass. Returns nodes_updated and edges_updated counts."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.run_decay()


@mcp.tool
def memory_short_rest(dry_run: bool = False) -> str:
    """Run Short Rest decay pass on recently-active memories.
    Returns a plain-text summary. Use dry_run=True to preview without writing."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.short_rest(dry_run=dry_run)
    dr = " (dry-run)" if result.get("dry_run") else ""
    return (
        f"Short Rest{dr}: {result['nodes_decayed']} nodes decayed, "
        f"{result['edges_decayed']} edges decayed."
    )


@mcp.tool
def memory_long_rest(dry_run: bool = False, prune: bool = False) -> str:
    """Run Long Rest: full decay + edge rediscovery + optional prune.
    Returns a plain-text summary. Use dry_run=True to preview without writing.
    Use prune=True to hard-delete eligible weak edges (only when dry_run=False)."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.long_rest(dry_run=dry_run, prune=prune)
    dr = " (dry-run)" if result.get("dry_run") else ""
    util_pct = result.get("index_utilisation_pct")
    util_str = f"{util_pct}%" if util_pct is not None else "n/a"
    near_cap = " ⚠ index near capacity" if result.get("index_near_capacity") else ""
    dup_count = result.get("near_duplicate_count", 0)
    dup_note = f" {dup_count} near-duplicate pairs pending review." if dup_count else ""
    auto_count = result.get("auto_merged_count", 0)
    auto_note = f" Auto-merged {auto_count} pairs." if auto_count else ""
    return (
        f"Long Rest{dr}: {result['nodes_decayed']} nodes decayed, "
        f"{result['edges_decayed']} edges decayed, "
        f"{result['edges_discovered']} edges discovered, "
        f"{result['edges_pruned']} edges pruned. "
        f"Index: {result.get('embedded_memory_count', '?')}/{result.get('index_capacity', '?')} "
        f"({util_str}){near_cap}.{dup_note}{auto_note}"
    )


@mcp.tool
def memory_maintenance_stats() -> dict:
    """Return a health snapshot of the memory fabric including node/edge stats and maintenance timestamps."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.maintenance_stats()


@mcp.tool
def memory_operation_log() -> str:
    """Return the operation log (update/merge/archive/restore events) as plain text, most recent first."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        entries = client.operation_log()

    if not entries:
        return "No operation log entries yet."

    lines = []
    for entry in reversed(entries):
        ran_at = entry.get("ran_at", "unknown")
        operation = entry.get("operation", "unknown")
        memory_id = entry.get("memory_id", "unknown")
        line = f"{ran_at}  {operation}  {memory_id}"
        fields_updated = entry.get("fields_updated")
        if fields_updated:
            line += f"  fields_updated: {fields_updated}"
        target_id = entry.get("target_id")
        if target_id:
            line += f"  target_id: {target_id}"
        lines.append(line)

    return "\n".join(lines)


@mcp.tool
def memory_maintenance_log() -> str:
    """Return the maintenance audit log as plain text (most recent runs first)."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        entries = client.maintenance_log()

    if not entries:
        return "No maintenance runs recorded yet."

    lines = ["## Maintenance audit log", ""]
    for entry in reversed(entries):  # most recent first
        dr = " (dry-run)" if entry.get("dry_run") else ""
        op = entry.get("operation", "unknown").replace("_", "-")
        ran_at = entry.get("ran_at", "unknown")[:19].replace("T", " ")
        nodes = entry.get("nodes_affected", 0)
        edges = entry.get("edges_affected", 0)
        discovered = entry.get("edges_discovered", 0)
        pruned = entry.get("edges_pruned", 0)
        summary = f"{nodes} nodes, {edges} edges decayed"
        if discovered:
            summary += f", {discovered} edges discovered"
        if pruned:
            summary += f", {pruned} edges pruned"
        lines.append(f"  {ran_at}  {op}{dr}: {summary}")

    return "\n".join(lines)


_CLOSE_SESSION_SCAFFOLD = """\
## Session close-out

Review this session and answer the following before ending:

1. What decisions were made? (store as type: decision)
   → memory_add(fact="...", type="decision", strand_ids=["<strand-id>"])

2. What was learned or observed about the user? (store as type: insight or observation)
   → memory_add(fact="...", so_what="...", type="insight", strand_ids=["<strand-id>"])

3. What actions were committed to? (store as type: todo)
   → memory_add(fact="...", type="todo", strand_ids=["<strand-id>"])

4. What context should a future session know that isn't already in the fabric?
   → memory_add(fact="...", so_what="...", type="fact", strand_ids=["<strand-id>"])

5. Are there causal links between memories? Link them explicitly.
   → memory_add(fact="...", type="fact", cause_ids=["<uuid>"], effect_ids=["<uuid>"])

Run memory_list_strands() if strand IDs are uncertain.
Do not end the session without calling memory_add at least once if any of the above apply.\
"""


@mcp.tool
def memory_update(
    memory_id: str,
    fact: str | None = None,
    so_what: str | None = None,
    tags: list[str] | None = None,
    importance: int | None = None,
    person_ids: list[str] | None = None,
    strand_ids: list[str] | None = None,
    control_ids: list[str] | None = None,
    doc_ids: list[str] | None = None,
    control_relationship_type: str | None = None,
    org_id: str | None = None,
) -> dict:
    """Update an existing active memory's content. Only include fields you want to change.
    fact/so_what changes trigger embedding recomputation. person_ids and strand_ids are full
    replacements (existing edges are removed and recreated). control_ids and doc_ids replace
    cross-layer edges to knowledge controls and documents respectively.
    Returns {memory_id, updated_at}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.update_memory(
            memory_id,
            fact=fact,
            so_what=so_what,
            tags=tags,
            importance=importance,
            person_ids=person_ids,
            strand_ids=strand_ids,
            control_ids=control_ids,
            doc_ids=doc_ids,
            control_relationship_type=control_relationship_type,
            org_id=org_id,
        )


@mcp.tool
def memory_archive(memory_id: str) -> dict:
    """Archive a memory. Archived memories are excluded from search and wake-up.
    Use memory_restore to make it active again. Returns {memory_id, archived_at}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.archive_memory(memory_id)


@mcp.tool
def memory_restore(memory_id: str) -> dict:
    """Restore an archived memory to active status. Returns {memory_id, status}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.restore_memory(memory_id)


@mcp.tool
def memory_delete(memory_id: str) -> str:
    """Permanently delete a memory and all its edges from the graph.

    This is irreversible — use memory_archive if you want a reversible path.
    Returns a plain-text confirmation string.
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        client.delete_memory(memory_id)
    return f"Deleted memory {memory_id}"


@mcp.tool
def memory_merge(source_id: str, target_id: str) -> dict:
    """Merge source memory into target. The source is marked merged and its edges
    (ABOUT, IN_STRAND, LEADS_TO, RELATED_TO) are rewired to the target.
    Returns {source_id, target_id}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.merge_memory(source_id, target_id)


@mcp.tool
def memory_find_duplicates(
    threshold: float | None = None, limit: int | None = None
) -> list[dict]:
    """Find near-duplicate memory pairs above a similarity threshold for review and merge."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.find_duplicates(threshold=threshold, limit=limit)


@mcp.tool
def memory_purge_ephemeral() -> str:
    """Hard-delete all ephemeral memories from the graph.

    Ephemeral memories are test artefacts created with ephemeral=true.
    Returns a plain-text summary of the count deleted.

    Warning: deletes ALL ephemeral memories globally — not safe for concurrent
    test sessions against the same Memgraph instance.
    """
    with MemoryClient(base_url=settings.api_base_url) as client:
        result = client.purge_ephemeral()
    return f"Purged {result['deleted']} ephemeral memories."


@mcp.tool
def memory_close_session() -> str:
    """Return the session close-out scaffold as plain text. Work through it before ending the session."""
    return _CLOSE_SESSION_SCAFFOLD


if settings.enable_knowledge_layer:
    @mcp.tool
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
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.search_controls(query, limit=limit, framework_id=framework_id)

    @mcp.tool
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
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.search_chunks(query, limit=limit, doc_id=doc_id)

    @mcp.tool
    def knowledge_list_norms() -> list[dict]:
        """Return all regulatory norms in the knowledge layer.

        Use when an agent needs the full catalogue of norms to present options to
        the user or to identify which norms apply to a given control. Each norm has
        id, name, text, status, and effective_date.

        This is a catalogue listing, not a search. For semantic search over norm
        text, use knowledge_search_controls (norms are linked to controls via
        IMPLEMENTS edges; searching controls surfaces related norms indirectly).
        """
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.list_norms()

    @mcp.tool
    def knowledge_get_control(control_id: str) -> dict:
        """Fetch a single InfoSec control by its ID.

        Use when an agent already has a control_id (e.g. from knowledge_search_controls)
        and needs its full details: name, description, framework_id, and created_at.
        Returns 404 detail if the control does not exist.
        """
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.get_control(control_id)

    @mcp.tool
    def knowledge_get_norm(norm_id: str) -> dict:
        """Fetch a single regulatory norm by its ID.

        Use when an agent already has a norm_id (e.g. from knowledge_list_norms)
        and needs its full details: name, text, status, and effective_date.
        Returns 404 detail if the norm does not exist.
        """
        with MemoryClient(base_url=settings.api_base_url) as client:
            return client.get_norm(norm_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
