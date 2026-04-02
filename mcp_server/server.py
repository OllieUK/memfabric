"""MCP server for graph-memory-fabric.

Exposes tools via FastMCP over STDIO transport:
  memory_add, memory_search, memory_wake_up, memory_list_strands, memory_close_session,
  memory_list_persons, memory_create_person,
  memory_short_rest, memory_long_rest, memory_maintenance_stats,
  memory_update, memory_archive, memory_restore, memory_merge
"""
from datetime import datetime, timezone
from itertools import groupby

from fastmcp import FastMCP

from memory_client.client import MemoryClient
from mcp_server.config import settings


mcp = FastMCP("graph-memory-fabric")


def _format_memory_timestamp(created_at: str | None) -> str:
    """Render created_at as a compact UTC label for wake-up output."""
    if not created_at:
        return ""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return created_at
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


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
) -> str:
    """Add a memory to the fabric.

    agent_id is required — pass your own agent identifier (e.g. "claude-code",
    "engineering-implementer"). Do NOT omit it or pass "claude-code" unless you
    ARE the main Claude Code session. Returns the memory_id (existing if a
    duplicate was detected).
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
        )
    return str(result)


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
) -> str:
    """Return the session wake-up briefing as plain text. Read fully before responding to the user."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        core, topic_memories, maintenance_status = client.wake_up_split(limit=limit, topic=topic)

    lines = []

    # Maintenance alert — shown prominently at the top when action needed
    action = maintenance_status.get("recommended_action") if maintenance_status else None
    if action:
        lines += [
            "## ⚠ Maintenance required",
            "",
            f"  {action}",
            "",
        ]

    heading = f"## Memory briefing — {topic if topic else 'general session'}"
    lines += [heading, "", "### Core context", ""]
    lines.extend(_render_section(core))

    if topic and topic_memories:
        lines += ["", "### Relevant to today", ""]
        lines.extend(_render_section(topic_memories))

    return "\n".join(lines)


def _render_section(memories: list[dict]) -> list[str]:
    """Render a flat list of memory dicts as grouped plain-text lines."""
    if not memories:
        return ["  No memories found."]

    lines = []
    sorted_mems = sorted(memories, key=lambda m: m.get("strand_id") or "(no strand)")
    for strand_id, group in groupby(
        sorted_mems, key=lambda m: m.get("strand_id") or "(no strand)"
    ):
        lines.append(strand_id)
        for mem in group:
            imp = mem.get("importance", "-")
            mem_type = mem.get("type", "")
            mem_text = mem.get("text", "")
            timestamp = _format_memory_timestamp(mem.get("created_at"))
            timestamp_label = f" ({timestamp})" if timestamp else ""
            lines.append(f"  [{imp}] {mem_type}{timestamp_label} — {mem_text}")
        lines.append("")  # blank line between strand groups

    # Remove trailing blank line
    if lines and lines[-1] == "":
        lines.pop()

    return lines


@mcp.tool
def memory_list_strands() -> list[dict]:
    """Return all strands. Use strand IDs when calling memory_add."""
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
    return (
        f"Long Rest{dr}: {result['nodes_decayed']} nodes decayed, "
        f"{result['edges_decayed']} edges decayed, "
        f"{result['edges_discovered']} edges discovered, "
        f"{result['edges_pruned']} edges pruned."
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
) -> dict:
    """Update an existing active memory's content. Only include fields you want to change.
    fact/so_what changes trigger embedding recomputation. person_ids and strand_ids are full
    replacements (existing edges are removed and recreated). Returns {memory_id, updated_at}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.update_memory(
            memory_id,
            fact=fact,
            so_what=so_what,
            tags=tags,
            importance=importance,
            person_ids=person_ids,
            strand_ids=strand_ids,
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
def memory_merge(source_id: str, target_id: str) -> dict:
    """Merge source memory into target. The source is marked merged and its edges
    (ABOUT, IN_STRAND, LEADS_TO, RELATED_TO) are rewired to the target.
    Returns {source_id, target_id}."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.merge_memory(source_id, target_id)


@mcp.tool
def memory_close_session() -> str:
    """Return the session close-out scaffold as plain text. Work through it before ending the session."""
    return _CLOSE_SESSION_SCAFFOLD


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
