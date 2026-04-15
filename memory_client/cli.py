# memory_client/cli.py
import json
import sys
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

from memory_client.client import MemoryClient
from memory_client.config import settings
from memory_client.formatting import format_wake_up

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
            result = client.add_memory(
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
        memory_id = result["memory_id"]
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


@app.command("list-projects")
def list_projects() -> None:
    """List all Project nodes in the memory fabric."""
    try:
        with _make_client() as client:
            projects = client.list_projects()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not projects:
        console.print("No projects found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Description")
    for p in projects:
        table.add_row(p["id"], p["name"], p.get("description") or "")
    console.print(table)


@app.command("create-project")
def create_project(
    project_id: str = typer.Argument(..., help="Kebab-case project ID, e.g. graph-memory-fabric"),
    name: str = typer.Option(..., "--name", "-n", help="Display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Optional description"),
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="Short slug for source_ref namespace, e.g. gmf"),
    weight: Optional[float] = typer.Option(None, "--weight", "-w", help="Priority multiplier (default 1.0, must be > 0)"),
) -> None:
    """Create or update a Project node."""
    try:
        with _make_client() as client:
            project = client.create_project(project_id, name, description=description, slug=slug, weight=weight)
        console.print(project["id"])
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("create-task")
def create_task(
    title: str = typer.Argument(..., help="Task title"),
    agent_id: str = typer.Option(..., "--agent-id", "-a", help="Agent ID that owns this task"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Task detail"),
    status: str = typer.Option("open", "--status", help="open|active|blocked|done|abandoned"),
    value: Optional[str] = typer.Option(None, "--value", help="Value axis: H|M|L"),
    effort: Optional[str] = typer.Option(None, "--effort", help="Effort axis: H|M|L"),
    urgency: Optional[float] = typer.Option(None, "--urgency", help="Time-sensitivity 0-5"),
    due_at: Optional[str] = typer.Option(None, "--due-at", help="ISO deadline datetime"),
    committed_at: Optional[str] = typer.Option(None, "--committed-at", help="ISO datetime when commitment was made"),
    committed_by: Optional[str] = typer.Option(None, "--committed-by", help="Agent ID that made the commitment"),
    source_ref: Optional[str] = typer.Option(None, "--source-ref", help="Qualified back-ref e.g. gmf:WP-143"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project node ID"),
    recurrence: Optional[str] = typer.Option(None, "--recurrence", help="Recurrence pattern e.g. weekly"),
    is_template: bool = typer.Option(False, "--is-template", help="Mark as recurring template parent"),
) -> None:
    """Create a Task node."""
    kwargs: dict = {"status": status}
    if description is not None:
        kwargs["description"] = description
    if value is not None:
        kwargs["value"] = value
    if effort is not None:
        kwargs["effort"] = effort
    if urgency is not None:
        kwargs["urgency"] = urgency
    if due_at is not None:
        kwargs["due_at"] = due_at
    if committed_at is not None:
        kwargs["committed_at"] = committed_at
    if committed_by is not None:
        kwargs["committed_by"] = committed_by
    if source_ref is not None:
        kwargs["source_ref"] = source_ref
    if project_id is not None:
        kwargs["project_id"] = project_id
    if recurrence is not None:
        kwargs["recurrence"] = recurrence
    if is_template:
        kwargs["is_template"] = True
    try:
        with _make_client() as client:
            task = client.create_task(title, agent_id, **kwargs)
        console.print(task["id"])
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("list-tasks")
def list_tasks(
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status: open|active|blocked|done|abandoned"),
    agent_id: Optional[str] = typer.Option(None, "--agent-id", "-a", help="Filter by agent ID"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Filter by project ID"),
    committed_only: bool = typer.Option(False, "--committed-only", help="Only show committed tasks"),
) -> None:
    """List Task nodes."""
    try:
        with _make_client() as client:
            tasks = client.list_tasks(
                status=status, agent_id=agent_id,
                project_id=project_id, committed_only=committed_only,
            )
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not tasks:
        console.print("No tasks found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Title")
    table.add_column("Status", width=10)
    table.add_column("V/E", width=5)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Urgency", justify="right", width=7)
    table.add_column("Due", width=12)
    table.add_column("Source", width=16)
    for t in tasks:
        ve = f"{t.get('value') or '-'}/{t.get('effort') or '-'}"
        score = f"{t['priority_score']:.1f}" if t.get("priority_score") is not None else "-"
        urgency = f"{t['urgency']:.1f}" if t.get("urgency") is not None else "-"
        table.add_row(
            t["id"][:8], t["title"], t["status"], ve, score, urgency,
            t.get("due_at") or "", t.get("source_ref") or "",
        )
    console.print(table)


@app.command("next-task")
def next_task(
    limit: int = typer.Option(10, "--limit", "-n", help="Max tasks to show"),
) -> None:
    """Show the cross-project prioritised task queue."""
    try:
        with _make_client() as client:
            tasks = client.list_next_tasks(limit=limit)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not tasks:
        console.print("No open tasks found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Title")
    table.add_column("Status", width=10)
    table.add_column("V/E", width=5)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Project", width=20)
    table.add_column("Eff.Score", justify="right", width=9)
    table.add_column("Due", width=12)
    for t in tasks:
        ve = f"{t.get('value') or '-'}/{t.get('effort') or '-'}"
        score = f"{t['priority_score']:.1f}" if t.get("priority_score") is not None else "-"
        pw = t.get("project_weight") or 1.0
        eff = (t.get("priority_score") or 1.0) * pw
        table.add_row(
            t["id"][:8], t["title"], t["status"], ve, score,
            t.get("project_id") or "",
            f"{eff:.2f}",
            t.get("due_at") or "",
        )
    console.print(table)


@app.command("update-task")
def update_task(
    task_id: str = typer.Argument(..., help="Task UUID"),
    status: Optional[str] = typer.Option(None, "--status", help="New status"),
    value: Optional[str] = typer.Option(None, "--value", help="Value axis: H|M|L"),
    effort: Optional[str] = typer.Option(None, "--effort", help="Effort axis: H|M|L"),
    urgency: Optional[float] = typer.Option(None, "--urgency", help="Time-sensitivity 0-5"),
    due_at: Optional[str] = typer.Option(None, "--due-at", help="ISO deadline datetime"),
    source_ref: Optional[str] = typer.Option(None, "--source-ref", help="Qualified back-ref"),
    committed_at: Optional[str] = typer.Option(None, "--committed-at", help="ISO commitment datetime"),
    committed_by: Optional[str] = typer.Option(None, "--committed-by", help="Agent ID that committed"),
) -> None:
    """Update a Task node's fields."""
    kwargs: dict = {}
    if status is not None:
        kwargs["status"] = status
    if value is not None:
        kwargs["value"] = value
    if effort is not None:
        kwargs["effort"] = effort
    if urgency is not None:
        kwargs["urgency"] = urgency
    if due_at is not None:
        kwargs["due_at"] = due_at
    if source_ref is not None:
        kwargs["source_ref"] = source_ref
    if committed_at is not None:
        kwargs["committed_at"] = committed_at
    if committed_by is not None:
        kwargs["committed_by"] = committed_by
    if not kwargs:
        err_console.print("[red]No fields to update — provide at least one option.[/red]")
        raise typer.Exit(1)
    try:
        with _make_client() as client:
            task = client.update_task(task_id, **kwargs)
        console.print(task["id"])
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("complete-task")
def complete_task(
    task_id: str = typer.Argument(..., help="Task UUID to mark as done"),
) -> None:
    """Mark a Task as done."""
    try:
        with _make_client() as client:
            task = client.update_task(task_id, status="done")
        console.print(task["id"])
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


@app.command("purge-ephemeral")
def purge_ephemeral() -> None:
    """Hard-delete all ephemeral memories from the graph."""
    try:
        with _make_client() as client:
            result = client.purge_ephemeral()
        console.print(f"Deleted {result['deleted']} ephemeral memories.")
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
        util_pct = result.get("index_utilisation_pct")
        util_str = f"{util_pct}%" if util_pct is not None else "n/a"
        near_cap = result.get("index_near_capacity", False)
        cap_label = " [yellow bold]⚠ near capacity[/yellow bold]" if near_cap else ""
        dup_count = result.get("near_duplicate_count", 0)
        dup_label = f" [yellow]({dup_count} near-duplicate pairs — run `memory duplicates` to review)[/yellow]" if dup_count else ""
        console.print(
            f"Nodes decayed: {result['nodes_decayed']}, "
            f"Edges decayed: {result['edges_decayed']}, "
            f"Edges discovered: {result['edges_discovered']}, "
            f"Edges pruned: {result['edges_pruned']}{dr_label}"
        )
        console.print(
            f"Index: {result.get('embedded_memory_count', '?')} / "
            f"{result.get('index_capacity', '?')} nodes ({util_str}){cap_label}"
        )
        console.print(f"Dedup queue: {dup_count} pairs above threshold{dup_label}")
        auto_count = result.get("auto_merged_count", 0)
        if auto_count:
            console.print(f"Auto-merged: {auto_count} pairs above threshold")
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
    person_id: Optional[str] = typer.Option(
        None, "--person-id", help="Person ID for conversant anchors"
    ),
) -> None:
    """Print a memory briefing for session start."""
    try:
        with _make_client() as client:
            result = client.wake_up_split(limit=limit, topic=topic, person_id=person_id)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    console.print(format_wake_up(result, topic=topic, plain=False))


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


@app.command("delete")
def delete_memory(
    memory_id: str = typer.Argument(..., help="Memory UUID to permanently delete"),
) -> None:
    """Permanently delete a memory and all its edges (irreversible)."""
    try:
        with _make_client() as client:
            client.delete_memory(memory_id)
        console.print(f"Deleted {memory_id[:8]}")
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)


@app.command("find-duplicates")
def find_duplicates(
    threshold: Optional[float] = typer.Option(None, "--threshold", "-t", help="Similarity threshold (0-1)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max pairs to return"),
) -> None:
    """Find near-duplicate memory pairs for review."""
    try:
        with _make_client() as client:
            pairs = client.find_duplicates(threshold=threshold, limit=limit)
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    if not pairs:
        console.print("No near-duplicate pairs found.")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Similarity", style="bold")
    table.add_column("Memory A ID", style="dim")
    table.add_column("Memory A Text")
    table.add_column("Memory B ID", style="dim")
    table.add_column("Memory B Text")
    for p in pairs:
        table.add_row(
            f"{p['similarity']:.4f}",
            p["a"]["id"][:12],
            p["a"]["text"][:60],
            p["b"]["id"][:12],
            p["b"]["text"][:60],
        )
    console.print(table)


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


schedule_app = typer.Typer(help="Manage scheduled maintenance timers.")
app.add_typer(schedule_app, name="schedule")

_DEFAULT_SYSTEMD_DIR = str(Path.home() / ".config" / "systemd" / "user")


@schedule_app.command("install")
def schedule_install(
    target_dir: str = typer.Option(
        None, "--target-dir",
        help="Directory for unit files (default: ~/.config/systemd/user)",
    ),
) -> None:
    """Install systemd timer units for maintenance."""
    if target_dir is None:
        target_dir = _DEFAULT_SYSTEMD_DIR

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    templates_dir = Path(__file__).resolve().parent.parent / "scripts" / "templates"
    project_dir = str(Path(__file__).resolve().parent.parent)
    python_path = sys.executable

    for template_file in templates_dir.glob("memory-*.*"):
        content = template_file.read_text()
        if template_file.suffix == ".service":
            content = content.replace("{{PROJECT_DIR}}", project_dir)
            content = content.replace("{{PYTHON}}", python_path)
        (target / template_file.name).write_text(content)

    console.print(f"Installed timer units to {target_dir}")
    console.print("Enable with:")
    console.print("  systemctl --user enable --now memory-short-rest.timer")
    console.print("  systemctl --user enable --now memory-long-rest.timer")


@schedule_app.command("uninstall")
def schedule_uninstall(
    target_dir: str = typer.Option(
        None, "--target-dir",
        help="Directory containing unit files (default: ~/.config/systemd/user)",
    ),
) -> None:
    """Remove installed systemd timer units."""
    if target_dir is None:
        target_dir = _DEFAULT_SYSTEMD_DIR

    target = Path(target_dir)
    removed = 0
    for name in [
        "memory-short-rest.service", "memory-short-rest.timer",
        "memory-long-rest.service", "memory-long-rest.timer",
    ]:
        try:
            (target / name).unlink()
            removed += 1
        except FileNotFoundError:
            pass

    console.print(f"Removed {removed} unit files from {target_dir}")
    console.print("Remember to run: systemctl --user daemon-reload")


@schedule_app.command("status")
def schedule_status() -> None:
    """Show maintenance schedule status and last-run timestamps."""
    try:
        with _make_client() as client:
            stats = client.maintenance_stats()
    except httpx.HTTPStatusError as exc:
        err_console.print(f"[red]Error {exc.response.status_code}:[/red] {exc.response.text}")
        raise typer.Exit(1)
    except httpx.ConnectError:
        err_console.print(f"[red]Could not connect to memory service at {settings.api_base_url}[/red]")
        raise typer.Exit(1)

    maint = stats.get("maintenance", {})
    console.print("[bold]Maintenance Schedule Status[/bold]")
    console.print(f"  Last short-rest: {maint.get('last_short_rest_at', 'never')}")
    console.print(f"  Last long-rest:  {maint.get('last_long_rest_at', 'never')}")


knowledge_app = typer.Typer(help="Search and manage the InfoSec knowledge layer.")
app.add_typer(knowledge_app, name="knowledge")


@knowledge_app.command("search-controls")
def knowledge_search_controls(
    query: str = typer.Option(..., "--query", "-q", help="Semantic search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to return"),
    framework_id: Optional[str] = typer.Option(None, "--framework-id", help="Filter to a single framework ID"),
) -> None:
    """Search InfoSec controls by semantic similarity."""
    try:
        with _make_client() as client:
            hits = client.search_controls(query, limit=limit, framework_id=framework_id)
    except httpx.ConnectError:
        console.print("[red]Connection error: is the memory service running?[/red]")
        raise typer.Exit(1)
    if not hits:
        console.print("No controls found.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Framework")
    table.add_column("Distance", justify="right")
    for h in hits:
        table.add_row(h["id"], h["name"], h.get("framework_id", ""), f"{h['distance']:.4f}")
    console.print(table)


@knowledge_app.command("search-chunks")
def knowledge_search_chunks(
    query: str = typer.Option(..., "--query", "-q", help="Semantic search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to return"),
    doc_id: Optional[str] = typer.Option(None, "--doc-id", help="Filter to a single document ID"),
) -> None:
    """Search document chunks by semantic similarity."""
    try:
        with _make_client() as client:
            hits = client.search_chunks(query, limit=limit, doc_id=doc_id)
    except httpx.ConnectError:
        console.print("[red]Connection error: is the memory service running?[/red]")
        raise typer.Exit(1)
    if not hits:
        console.print("No chunks found.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Doc ID")
    table.add_column("Seq", justify="right")
    table.add_column("Distance", justify="right")
    table.add_column("Text (truncated)")
    for h in hits:
        table.add_row(h["id"], h.get("doc_id", ""), str(h.get("sequence", "")), f"{h['distance']:.4f}", h["text"][:80])
    console.print(table)


@knowledge_app.command("list-norms")
def knowledge_list_norms() -> None:
    """List all regulatory norms in the knowledge layer."""
    try:
        with _make_client() as client:
            norms = client.list_norms()
    except httpx.ConnectError:
        console.print("[red]Connection error: is the memory service running?[/red]")
        raise typer.Exit(1)
    if not norms:
        console.print("No norms found.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Effective Date")
    for n in norms:
        table.add_row(n["id"], n["name"], n.get("status", ""), n.get("effective_date") or "")
    console.print(table)


@knowledge_app.command("list-documents")
def knowledge_list_documents() -> None:
    """List all documents in the knowledge layer."""
    try:
        with _make_client() as client:
            docs = client.list_documents()
    except httpx.ConnectError:
        console.print("[red]Connection error: is the memory service running?[/red]")
        raise typer.Exit(1)
    if not docs:
        console.print("No documents found.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Type")
    table.add_column("Source URL")
    for d in docs:
        table.add_row(d["id"], d["title"], d.get("doc_type", ""), d.get("source_url") or "")
    console.print(table)


@knowledge_app.command("review-supports")
def knowledge_review_supports() -> None:
    """Interactively review and confirm/reject auto-inferred SUPPORTS edges."""
    console.print("[yellow]review-supports is not yet available — coming in a future release.[/yellow]")
    raise typer.Exit(0)


if __name__ == "__main__":
    app()
