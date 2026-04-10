"""Wake-up output formatting for CLI and hook consumers.

format_wake_up() is the single source of truth for rendering a wake_up_split()
result. The CLI uses it with plain=False (Rich markup). The SessionStart hook
uses it with plain=True (stripped plain text).
"""
import re
from itertools import groupby


def _strip_rich(text: str) -> str:
    """Remove Rich markup tags like [bold], [/dim], [cyan], etc."""
    return re.sub(r'\[/?[a-zA-Z0-9_ ]+\]', '', text)


def _format_timestamp(created_at: str | None) -> str | None:
    """Return a compact UTC label like '2026-04-10 10:00 UTC', or None."""
    if not created_at:
        return None
    try:
        dt = created_at[:16].replace("T", " ")
        return f"{dt} UTC"
    except Exception:
        return None


def _render_section(items: list, plain: bool) -> str:
    """Render a list of memory dicts as a strand-grouped text block."""
    if not items:
        if plain:
            return "  No memories found."
        return "  [dim]No memories found.[/dim]"

    lines = []
    sorted_items = sorted(items, key=lambda m: m.get("strand_id") or "(no strand)")
    for strand_id, group in groupby(sorted_items, key=lambda m: m.get("strand_id") or "(no strand)"):
        if plain:
            lines.append(f"{strand_id}")
        else:
            lines.append(f"[dim]{strand_id}[/dim]")
        for mem in group:
            imp = str(mem.get("importance") or "")
            timestamp = _format_timestamp(mem.get("created_at"))
            mem_type = mem.get("type", "")
            text = mem.get("text", "")
            if plain:
                ts_label = f" ({timestamp})" if timestamp else ""
                lines.append(f"  [{imp}] {mem_type}{ts_label} — {text}")
            else:
                ts_label = f" [dim]({timestamp})[/dim]" if timestamp else ""
                lines.append(f"  [{imp}] [bold]{mem_type}[/bold]{ts_label} — {text}")
    return "\n".join(lines)


def format_wake_up(
    result: dict,
    topic: str | None = None,
    plain: bool = False,
) -> str:
    """Format a wake_up_split() result dict as a readable briefing string.

    Args:
        result: Dict with keys 'memories', 'topic_memories', 'companion_anchors',
                'conversant_anchors' — as returned by MemoryClient.wake_up_split().
        topic: Optional topic string used in the heading and to gate the
               'Relevant to today' section.
        plain: If True, emit plain text (no Rich markup). Used by hooks.
               If False (default), emit Rich markup for CLI rendering.

    Returns:
        A multi-line string ready to print or inject.
    """
    topic_label = topic if topic else "general session"

    core = result.get("memories", [])
    topic_memories = result.get("topic_memories", [])
    companion_anchors = result.get("companion_anchors")
    conversant_anchors = result.get("conversant_anchors")

    lines = []

    if plain:
        lines.append(f"## Memory briefing — {topic_label}")
    else:
        lines.append(f"[bold]## Memory briefing — {topic_label}[/bold]")

    if plain:
        lines.append("\n### Core context")
    else:
        lines.append("\n[bold cyan]### Core context[/bold cyan]")
    lines.append(_render_section(core, plain=plain))

    if topic and topic_memories:
        if plain:
            lines.append("\n### Relevant to today")
        else:
            lines.append("\n[bold cyan]### Relevant to today[/bold cyan]")
        lines.append(_render_section(topic_memories, plain=plain))

    if companion_anchors is not None:
        if plain:
            lines.append("\n### Companion")
        else:
            lines.append("\n[bold cyan]### Companion[/bold cyan]")
        lines.append(_render_section(companion_anchors, plain=plain))

    if conversant_anchors is not None:
        if plain:
            lines.append("\n### Conversant")
        else:
            lines.append("\n[bold cyan]### Conversant[/bold cyan]")
        lines.append(_render_section(conversant_anchors, plain=plain))

    return "\n".join(lines)
