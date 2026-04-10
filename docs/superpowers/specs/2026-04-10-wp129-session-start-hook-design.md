# WP-129 — SessionStart Context Injection Hook

**Date:** 2026-04-10  
**Status:** Approved — ready for implementation planning  
**Depends on:** —  
**Gates:** nothing directly; enables unconditional session continuity

---

## Motivation

The session startup protocol (read COMPANION.md, run wake-up) relies on model discipline. When a session starts with an immediately urgent user message, the wake-up is silently skipped and the model begins without continuity context.

A `SessionStart` hook that calls wake-up automatically and injects the digest as a `<system-reminder>` preamble makes continuity unconditional — the model receives context regardless of whether it remembers to ask for it.

---

## Design Overview

Three components:

1. **`memory_client/formatting.py`** — shared wake-up formatter, extracted from `cli.py`
2. **`hooks/session_start.py`** — thin hook script, ~35 lines
3. **`.claude/settings.json` registration** — one `SessionStart` hook entry

---

## Component 1: `memory_client/formatting.py`

Extract the rendering logic currently embedded in `cli.py`'s `wake_up` command into a standalone module.

```python
def format_wake_up(result: dict, topic: str | None = None, plain: bool = False) -> str:
    """Format a wake_up_split result dict as a readable briefing.

    Args:
        result: Dict with keys 'memories', 'topic_memories', 'companion_anchors',
                'conversant_anchors' — as returned by MemoryClient.wake_up_split().
        topic: Optional topic string used as section heading.
        plain: If True, output plain text (no Rich markup). Used by hooks.
                If False (default), output Rich markup for CLI rendering.
    """
```

**Section structure (same as today's CLI output):**

```
## Memory briefing — <topic or "general session">

### Core context
<strand-id>
  [<importance>] <type> (<timestamp>) — <text>
  ...

### Relevant to today        ← only if topic provided and topic_memories non-empty
### Companion                ← only if companion_anchors present
### Conversant               ← only if conversant_anchors present
```

**Plain mode** (`plain=True`): strips all Rich markup tags (`[bold]`, `[dim]`, `[red]`, etc.) before returning. The structure and content are identical — only the markup characters are removed. Uses a simple regex: `re.sub(r'\[/?[a-zA-Z_ ]+\]', '', text)`.

**`cli.py` change:** the `wake_up` command is updated to call `format_wake_up` and print the result:

```python
output = format_wake_up(result, topic=topic, plain=False)
console.print(output)
```

No visible behaviour change to CLI users.

---

## Component 2: `hooks/session_start.py`

Located at: `hooks/session_start.py` in the project root.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `API_BASE_URL` | `http://localhost:8000` | Memory service URL |
| `HOOK_AGENT_ID` | `claude-code` | Agent ID for the wake-up call |
| `HOOK_WAKE_UP_LIMIT` | `8` | Max memories to fetch |
| `HOOK_WAKE_UP_TOPIC` | _(unset)_ | Optional topic for topic-scoped wake-up |

These are read from the shell environment — not from `.env`. Set them in `~/.bashrc` or the Windows Terminal profile if non-default values are needed.

### Behaviour

```
1. Read env vars
2. Construct MemoryClient(base_url=API_BASE_URL)
3. Call wake_up_split(limit=HOOK_WAKE_UP_LIMIT, topic=HOOK_WAKE_UP_TOPIC)
4. Call format_wake_up(result, topic=..., plain=True)
5. Print to stdout
6. Exit 0
```

On `ConnectError` or HTTP error:

```
print("Memory service unreachable — operating without context briefing.")
exit(0)
```

Always exits 0. A failed hook must never block the session.

### How Claude Code uses the output

Claude Code's `SessionStart` hook captures stdout and injects it as a `<system-reminder>` block before the first user prompt. Plain text (no Rich markup, no ANSI codes) is required — Rich markup would appear as raw tag characters in the system context.

---

## Component 3: Registration

Add to project `.claude/settings.json`:

```json
"hooks": {
  "SessionStart": [
    {
      "command": "python3 /home/oliver/projects/graph-memory-fabric/hooks/session_start.py"
    }
  ]
}
```

The hook runs in the project's working directory. The `memory_client` package is editable-installed at the project root, so it is importable without path manipulation.

**Note for portability:** the absolute path in `command` is specific to this installation. If the project moves, update the path. A future improvement (not in scope here) could use a `memory-session-start` console script entry point instead.

---

## Out of Scope

- Injecting knowledge layer content (wake-up covers episodic memories; knowledge layer is queried on demand)
- Automatic topic detection from the session's first message (topic is configured statically via env var)
- Rich/ANSI formatting in hook output (not rendered by Claude Code's hook injection)
- A `memory-session-start` console script entry point (packaging polish, separate WP)

---

## Tests

### Unit

1. `format_wake_up(result, plain=True)` produces no Rich markup tags (`[bold]`, `[dim]`, etc.)
2. `format_wake_up(result, plain=False)` preserves Rich markup tags (CLI path unchanged)
3. Strand grouping is preserved in both modes — memories without a strand_id appear under `(no strand)`
4. `format_wake_up` with all sections empty returns a non-empty string (at minimum the heading line)
5. `format_wake_up` with `companion_anchors=None` omits the `### Companion` section
6. `format_wake_up` with `topic=None` and empty `topic_memories` omits the `### Relevant to today` section

### Manual verification

Start a fresh Claude Code session in the project directory and confirm:
- The wake-up digest appears in context before the first user prompt (visible in system-reminder preamble)
- When the memory service is stopped, the hook prints the fallback notice and the session starts normally

### Acceptance Criteria

- Session context includes a wake-up briefing automatically, without the model needing to call wake-up explicitly
- CLI `memory wake-up` output is visually unchanged
- A disconnected memory service does not block session start
- `format_wake_up` is the single source of wake-up rendering — no duplication between CLI and hook
