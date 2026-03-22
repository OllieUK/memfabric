"""MCP server for graph-memory-fabric.

Exposes tools via FastMCP over STDIO transport:
  memory_add, memory_search, memory_wake_up, memory_list_strands, memory_close_session,
  memory_list_persons, memory_create_person,
  memory_short_rest, memory_long_rest, memory_maintenance_stats
"""
from itertools import groupby

from fastmcp import FastMCP

from memory_client.client import MemoryClient
from mcp_server.config import settings


mcp = FastMCP("graph-memory-fabric")


@mcp.tool
def memory_add(
    fact: str,
    type: str = "fact",
    strand_ids: list[str] | None = None,
    tags: list[str] | None = None,
    importance: int = 3,
    agent_id: str | None = None,
    so_what: str | None = None,
    cause_ids: list[str] | None = None,
    effect_ids: list[str] | None = None,
) -> str:
    """Add a memory to the fabric. Returns the created memory ID."""
    resolved_agent_id = agent_id or settings.agent_id
    with MemoryClient(base_url=settings.api_base_url) as client:
        mid = client.add_memory(
            fact,
            type,
            resolved_agent_id,
            so_what=so_what,
            cause_ids=cause_ids,
            effect_ids=effect_ids,
            tags=tags,
            importance=importance,
            strand_ids=strand_ids,
        )
    return mid


@mcp.tool
def memory_search(
    query: str,
    tags: list[str] | None = None,
    agent_ids: list[str] | None = None,
    limit: int = 10,
    traversal_direction: str = "none",
) -> list[dict]:
    """Search the memory fabric by semantic similarity."""
    with MemoryClient(base_url=settings.api_base_url) as client:
        return client.search_memory(
            query,
            tags=tags,
            agent_ids=agent_ids,
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
        core, topic_memories = client.wake_up_split(limit=limit, topic=topic)

    heading = f"## Memory briefing — {topic if topic else 'general session'}"
    lines = [heading, "", "### Core context", ""]
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
            lines.append(f"  [{imp}] {mem_type} — {mem_text}")
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
def memory_close_session() -> str:
    """Return the session close-out scaffold as plain text. Work through it before ending the session."""
    return _CLOSE_SESSION_SCAFFOLD


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
