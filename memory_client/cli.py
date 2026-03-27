# memory_client/cli.py
import json
from datetime import datetime, timezone
from itertools import groupby
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from memory_client.client import MemoryClient
from memory_client.config import settings

app = typer.Typer(name="memory", help="Graph Memory Fabric CLI")
console = Console()
err_console = Console(stderr=True)


def _make_client() -> MemoryClient:
    return MemoryClient(base_url=settings.api_base_url)


@app.command("add-memory")
def add_memory(
    fact: str = typer.Argument(..., help="Memory fact (the raw statement)"),
    type: str = typer.Option(..., "--type", "-t", help="fact|decision|insight|todo|event|observation"),
    agent_id: str = typer.Option(settings.agent_id, "--agent-id", "-a", help="Agent ID producing this memory"),
    so_what: Optional[str] = typer.Option(None, "--so-what", help="Impact or meaning of this fact"),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Tag (repeatable: --tag a --tag b)"),
    importance: int = typer.Option(3, "--importance", "-i", min=1, max=5, help="Importance 1-5"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project node ID"),
    person_ids: Optional[list[str]] = typer.Option(None, "--person-id", help="Person ID (repeatable)"),
    strand_ids: Optional[list[str]] = typer.Option(None, "--strand-id", help="Strand ID (repeatable)"),
    related_ids: Optional[list[str]] = typer.Option(None, "--related-id", help="Explicit related memory ID (repeatable)"),
    cause_ids: Optional[list[str]] = typer.Option(None, "--cause-id", help="Memory IDs that causally led to this one (repeatable)"),
    effect_ids: Optional[list[str]] = typer.Option(None, "--effect-id", help="Memory IDs that this one causally leads to (repeatable)"),
) -> None:
    """Add a new memory to the graph."""
    try:
        with _make_client() as client:
            memory_id = client.add_memory(
                fact,
                type,
                agent_id,
                so_what=so_what,
                cause_ids=cause_ids,
                effect_ids=effect_ids,
                tags=tags,
                importance=importance,
                project_id=project_id,
                person_ids=person_ids,
                strand_ids=strand_ids,
                related_ids=related_ids,
            )
        console.print(memory_id)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("search-memory")
def search_memory(
    query: str = typer.Argument(..., help="Search query text"),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Filter by tag (repeatable)"),
    agent_ids: Optional[list[str]] = typer.Option(None, "--agent-id", help="Filter by agent ID (repeatable)"),
    project_ids: Optional[list[str]] = typer.Option(None, "--project-id", help="Filter by project ID (repeatable)"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, max=100, help="Maximum results"),
    max_hops: int = typer.Option(1, "--max-hops", min=0, max=3, help="Neighbour expansion depth"),
    traversal_direction: str = typer.Option(
        "none", "--traversal-direction",
        help="LEADS_TO traversal: none|causes|effects|both",
    ),
) -> None:
    """Search memories by semantic similarity."""
    try:
        with _make_client() as client:
            results = client.search_memory(
                query=query,
                tags=tags,
                agent_ids=agent_ids,
                project_ids=project_ids,
                limit=limit,
                max_hops=max_hops,
                traversal_direction=traversal_direction,
            )
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("No memories found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Type", width=12)
    table.add_column("Imp", justify="center", width=4)
    table.add_column("Tags", width=20)
    table.add_column("Text")
    table.add_column("Neighbours", justify="right", width=10)

    for hit in results:
        short_id = hit["id"][:8]
        tags_str = ", ".join(hit.get("tags") or [])
        imp = str(hit.get("importance") or "")
        neighbours_count = str(len(hit.get("neighbours") or []))
        table.add_row(short_id, hit["type"], imp, tags_str, hit["text"], neighbours_count)

    console.print(table)


@app.command("list-strands")
def list_strands() -> None:
    """List all strands in the memory fabric."""
    try:
        with _make_client() as client:
            strands = client.list_strands()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not strands:
        console.print("No strands found.")
        return

    for category, group in groupby(strands, key=lambda s: s["category"]):
        console.print(f"\n[bold cyan]{category}[/bold cyan]")
        for strand in group:
            console.print(f"  [dim]{strand['id']}[/dim]")
            console.print(f"  [bold]{strand['name']}[/bold] — {strand['description']}")


@app.command("list-persons")
def list_persons() -> None:
    """List all Person nodes in the memory fabric."""
    try:
        with _make_client() as client:
            persons = client.list_persons()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not persons:
        console.print("No persons found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Description")
    for p in persons:
        table.add_row(p["id"], p["name"], p.get("description") or "")
    console.print(table)


@app.command("create-person")
def create_person(
    person_id: str = typer.Argument(..., help="Kebab-case person ID, e.g. oliver-james"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Optional bio"),
) -> None:
    """Create or update a Person node."""
    try:
        with _make_client() as client:
            person = client.create_person(person_id, name, description=description)
        console.print(person["id"])
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("reinforce-memory")
def reinforce_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to reinforce"),
    co_recalled_id: Optional[list[str]] = typer.Option(
        None, "--co-recalled-id", help="Co-recalled memory ID (repeatable)"
    ),
) -> None:
    """Explicitly reinforce a memory (Hebbian signal)."""
    try:
        with _make_client() as client:
            result = client.reinforce_memory(memory_id, co_recalled_ids=co_recalled_id)
        console.print(f"Strength: {result['new_strength']:.3f}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("run-decay")
def run_decay() -> None:
    """Trigger a full-graph decay pass (maintenance operation)."""
    try:
        with _make_client() as client:
            result = client.run_decay()
        console.print(f"Nodes updated: {result['nodes_updated']}, Edges updated: {result['edges_updated']}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("short-rest")
def short_rest(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute but do not write"),
) -> None:
    """Run a Short Rest decay pass on recently-active memories."""
    try:
        with _make_client() as client:
            result = client.short_rest(dry_run=dry_run)
        dr_label = " [dim](dry-run)[/dim]" if result.get("dry_run") else ""
        console.print(
            f"Nodes decayed: {result['nodes_decayed']}, "
            f"Edges decayed: {result['edges_decayed']}{dr_label}"
        )
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("long-rest")
def long_rest(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute but do not write"),
    prune: bool = typer.Option(False, "--prune", help="Hard-delete eligible weak edges"),
) -> None:
    """Run a Long Rest: full decay + edge rediscovery + optional prune."""
    try:
        with _make_client() as client:
            result = client.long_rest(dry_run=dry_run, prune=prune)
        dr_label = " [dim](dry-run)[/dim]" if result.get("dry_run") else ""
        console.print(
            f"Nodes decayed: {result['nodes_decayed']}, "
            f"Edges decayed: {result['edges_decayed']}, "
            f"Edges discovered: {result['edges_discovered']}, "
            f"Edges pruned: {result['edges_pruned']}{dr_label}"
        )
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("status")
def status() -> None:
    """Show a health summary of the memory fabric."""
    try:
        with _make_client() as client:
            data = client.maintenance_stats()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    nodes = data["nodes"]
    edges = data["edges"]
    maint = data["maintenance"]

    console.print("\n[bold]Memory Fabric Health[/bold]")
    console.print(
        f"  Nodes: {nodes['total']} total  "
        f"mean strength: {nodes['mean_strength']:.2f}  "
        f"median: {nodes['median_strength']:.2f}  "
        f"at-max: {nodes['at_max_strength']}  "
        f"below-floor: {nodes['below_prune_floor']}"
    )
    console.print(
        f"  Edges: {edges['total']} total  "
        f"mean weight: {edges['mean_weight']:.2f}  "
        f"weak: {edges['weak_count']}"
    )

    sr_overdue = "[red]OVERDUE[/red]" if maint["short_rest_overdue"] else "[green]ok[/green]"
    lr_overdue = "[red]OVERDUE[/red]" if maint["long_rest_overdue"] else "[green]ok[/green]"
    console.print(f"\n  Short rest: {maint.get('last_short_rest_at') or 'never'} — {sr_overdue}")
    console.print(f"  Long rest:  {maint.get('last_long_rest_at') or 'never'} — {lr_overdue}")


@app.command("wake-up")
def wake_up(
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Topic to focus the session on"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="Max memories to return"),
) -> None:
    """Print a memory briefing for session start."""
    try:
        with _make_client() as client:
            core, topic_memories = client.wake_up_split(limit=limit, topic=topic)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    heading = f"[bold]## Memory briefing — {topic if topic else 'general session'}[/bold]"
    console.print(heading)

    def _render_section(items: list) -> None:
        if not items:
            console.print("  No memories found.")
            return
        # Sort before groupby: itertools.groupby only groups consecutive equal-key items
        sorted_items = sorted(items, key=lambda m: m.get("strand_id") or "(no strand)")
        for strand_id, group in groupby(sorted_items, key=lambda m: m.get("strand_id") or "(no strand)"):
            console.print(f"\n[dim]{strand_id}[/dim]")
            for mem in group:
                imp = str(mem.get("importance") or "")
                console.print(f"  [{imp}] [bold]{mem['type']}[/bold] — {mem['text']}")

    console.print("\n[bold cyan]### Core context[/bold cyan]")
    _render_section(core)

    # Render topic section only when topic was provided AND there are topic-only results
    if topic and topic_memories:
        console.print("\n[bold cyan]### Relevant to today[/bold cyan]")
        _render_section(topic_memories)


@app.command("close-session")
def close_session() -> None:
    """Print a structured scaffold for end-of-session memory storage."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    console.print(f"\n[bold]## Session close-out[/bold] — {now}")
    console.print("""
Review this session and answer the following before ending:

1. What decisions were made? (store as type: decision)
   → memory add-memory "..." --type decision --strand-id <strand-id>

2. What was learned or observed about Oliver? (store as type: insight or observation)
   → memory add-memory "..." --type insight --strand-id <strand-id>
   → Use --so-what "..." to capture the impact or meaning

3. What actions were committed to? (store as type: todo)
   → memory add-memory "..." --type todo --strand-id <strand-id>

4. What context should a future session know that isn't already in the fabric?
   → memory add-memory "..." --type fact --strand-id <strand-id>

5. Are there causal links between memories? (use --cause-id / --effect-id)
   → memory add-memory "..." --type fact --cause-id <uuid> --effect-id <uuid>

Run `memory list-strands` if strand IDs are uncertain.
Do not end the session without running at least one `memory add-memory` if any of the above apply.""")


@app.command("update-memory")
def update_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to update"),
    fact: Optional[str] = typer.Option(None, "--fact", help="New fact text"),
    so_what: Optional[str] = typer.Option(None, "--so-what", help="New impact/meaning"),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Replacement tag list (repeatable)"),
    importance: Optional[int] = typer.Option(None, "--importance", "-i", min=1, max=5, help="New importance 1-5"),
    person_ids: Optional[list[str]] = typer.Option(None, "--person-id", help="Replacement person IDs (repeatable)"),
    strand_ids: Optional[list[str]] = typer.Option(None, "--strand-id", help="Replacement strand IDs (repeatable)"),
) -> None:
    """Update fields on an existing memory (in-place)."""
    if all(v is None for v in [fact, so_what, tags, importance, person_ids, strand_ids]):
        err_console.print("[red]Error:[/red] Provide at least one field to update.")
        raise typer.Exit(1)
    try:
        with _make_client() as client:
            result = client.update_memory(
                memory_id,
                fact=fact,
                so_what=so_what,
                tags=tags,
                importance=importance,
                person_ids=person_ids,
                strand_ids=strand_ids,
            )
        console.print(f"Updated at: {result['updated_at']}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("merge-memory")
def merge_memory(
    source_id: str = typer.Argument(..., help="Source memory UUID (will be marked merged)"),
    target_id: str = typer.Argument(..., help="Target memory UUID (survives)"),
    strategy: str = typer.Option("replace", "--strategy", help="Merge strategy (default: replace)"),
) -> None:
    """Merge source memory into target, rewiring all edges."""
    try:
        with _make_client() as client:
            client.merge_memory(source_id, target_id, strategy=strategy)
        console.print(f"Merged {source_id[:8]} → {target_id[:8]}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("archive-memory")
def archive_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to archive"),
) -> None:
    """Archive a memory (excluded from search and wake-up; restorable)."""
    try:
        with _make_client() as client:
            result = client.archive_memory(memory_id)
        console.print(f"Archived {memory_id[:8]} at {result['archived_at']}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("restore-memory")
def restore_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to restore to active"),
) -> None:
    """Restore an archived memory to active status."""
    try:
        with _make_client() as client:
            client.restore_memory(memory_id)
        console.print(f"Restored {memory_id[:8]} to active")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("dump-graph")
def dump_graph(
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Filter by project ID"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", help="Filter by agent ID"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter by tag"),
) -> None:
    """Export the memory graph as JSON (requires WP-006 to be complete)."""
    try:
        with _make_client() as client:
            data = client.get_graph(project_id=project_id, agent_id=agent_id, tag=tag)
        console.print(json.dumps(data, indent=2))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (500, 501):
            err_console.print("GET /memory/graph is not yet implemented (see WP-006).")
            raise typer.Exit(1)
        else:
            err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
            raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
