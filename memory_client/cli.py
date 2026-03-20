# memory_client/cli.py
import json
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
    text: str = typer.Argument(..., help="Memory text content"),
    type: str = typer.Option(..., "--type", "-t", help="fact|decision|insight|todo|event|observation"),
    agent_id: str = typer.Option(settings.agent_id, "--agent-id", "-a", help="Agent ID producing this memory"),
    tags: Optional[list[str]] = typer.Option(None, "--tag", help="Tag (repeatable: --tag a --tag b)"),
    importance: int = typer.Option(3, "--importance", "-i", min=1, max=5, help="Importance 1-5"),
    project_id: Optional[str] = typer.Option(None, "--project-id", help="Project node ID"),
    person_ids: Optional[list[str]] = typer.Option(None, "--person-id", help="Person ID (repeatable)"),
    strand_ids: Optional[list[str]] = typer.Option(None, "--strand-id", help="Strand ID (repeatable)"),
    related_ids: Optional[list[str]] = typer.Option(None, "--related-id", help="Explicit related memory ID (repeatable)"),
) -> None:
    """Add a new memory to the graph."""
    try:
        with _make_client() as client:
            memory_id = client.add_memory(
                text=text,
                type=type,
                agent_id=agent_id,
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
