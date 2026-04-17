"""Wake-up output formatting for CLI and hook consumers.

format_wake_up() is the single source of truth for rendering a wake_up_split()
result. The CLI uses it with plain=False (Rich markup). The SessionStart hook
uses it with plain=True (stripped plain text).
"""
from datetime import datetime, timezone
from difflib import SequenceMatcher
from itertools import groupby
import re


SEMANTIC_DUPLICATE_THRESHOLD = 0.9


def _format_timestamp(created_at: str | None) -> str | None:
    """Return a compact UTC label like '2026-04-10 10:00 UTC', or None."""
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return None


def _heading(text: str, plain: bool, bold_only: bool = False) -> str:
    """Wrap a heading string in Rich markup, or return it plain."""
    if plain:
        return text
    markup = "bold" if bold_only else "bold cyan"
    return f"[{markup}]{text}[/{markup}]"


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


def _normalize_for_similarity(text: str) -> str:
    normalized = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (text or "").lower())).strip()
    return normalized


def _is_semantic_duplicate(a: dict, b: dict) -> bool:
    text_a = _normalize_for_similarity(a.get("text", ""))
    text_b = _normalize_for_similarity(b.get("text", ""))
    if not text_a or not text_b:
        return False
    if text_a == text_b:
        return True
    return SequenceMatcher(None, text_a, text_b).ratio() >= SEMANTIC_DUPLICATE_THRESHOLD


def _compress_section_items(items: list[dict]) -> list[dict]:
    compressed: list[dict] = []
    for item in items:
        matched = None
        for existing in compressed:
            if _is_semantic_duplicate(existing, item):
                matched = existing
                break
        if matched is None:
            cloned = dict(item)
            cloned["_source_ids"] = [item.get("id")]
            compressed.append(cloned)
            continue

        source_ids = matched.setdefault("_source_ids", [matched.get("id")])
        if item.get("id") not in source_ids:
            source_ids.append(item.get("id"))
        if (item.get("importance") or 0) > (matched.get("importance") or 0):
            matched.update({k: v for k, v in item.items() if not k.startswith("_")})
            matched["_source_ids"] = source_ids
    return compressed


def _compress_mara_startup_sections(result: dict) -> dict:
    section_order = [
        "global_mara_baseline",
        "global_user_baseline",
        "project_mara_persona",
        "project_baseline",
    ]
    seen_items: list[dict] = []
    compressed = dict(result)
    for key in section_order:
        items = compressed.get(key)
        if not items:
            continue
        filtered: list[dict] = []
        for item in items:
            if any(_is_semantic_duplicate(item, seen) for seen in seen_items):
                continue
            filtered.append(item)
            seen_items.append(item)
        compressed[key] = _compress_section_items(filtered) if filtered else None
    return compressed


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
    has_mara_startup_sections = any(
        result.get(key) is not None
        for key in ("global_mara_baseline", "global_user_baseline", "project_mara_persona", "project_baseline")
    )

    lines = []
    if has_mara_startup_sections:
        compressed = _compress_mara_startup_sections(result)
        lines.append(_heading(f"## Memory briefing — {topic_label}", plain, bold_only=True))
        lines.append(_heading("\n### Global Mara baseline", plain))
        lines.append(_render_section(compressed.get("global_mara_baseline") or [], plain=plain))
        lines.append(_heading("\n### Global user baseline", plain))
        lines.append(_render_section(compressed.get("global_user_baseline") or [], plain=plain))
        lines.append(_heading("\n### Project Mara persona", plain))
        lines.append(_render_section(compressed.get("project_mara_persona") or [], plain=plain))
        lines.append(_heading("\n### Project baseline", plain))
        lines.append(_render_section(compressed.get("project_baseline") or [], plain=plain))
        return "\n".join(lines)

    core = result.get("memories", [])
    topic_memories = result.get("topic_memories", [])
    companion_anchors = result.get("companion_anchors")
    conversant_anchors = result.get("conversant_anchors")

    lines.append(_heading(f"## Memory briefing — {topic_label}", plain, bold_only=True))
    lines.append(_heading("\n### Core context", plain))
    lines.append(_render_section(core, plain=plain))

    if topic and topic_memories:
        lines.append(_heading("\n### Relevant to today", plain))
        lines.append(_render_section(topic_memories, plain=plain))

    if companion_anchors is not None:
        lines.append(_heading("\n### Companion", plain))
        lines.append(_render_section(companion_anchors, plain=plain))

    if conversant_anchors is not None:
        lines.append(_heading("\n### Conversant", plain))
        lines.append(_render_section(conversant_anchors, plain=plain))

    return "\n".join(lines)
