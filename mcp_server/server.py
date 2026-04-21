"""MCP server for graph-memory-fabric.

Exposes tools via FastMCP over STDIO transport (default) or streamable-HTTP when
mounted as a sub-application in memory_service/main.py:

  memory_add, memory_search, memory_wake_up, memory_list_strands, memory_close_session,
  memory_list_persons, memory_create_person,
  memory_list_projects, memory_create_project,
  task_add, task_list, task_get, task_update, task_complete, task_stale, task_next,
  memory_short_rest, memory_long_rest, memory_maintenance_stats,
  memory_update, memory_archive, memory_restore, memory_delete, memory_merge,
  memory_find_duplicates, memory_purge_ephemeral, memory_reinforce, memory_run_decay,
  memory_operation_log, memory_maintenance_log
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastmcp import FastMCP

from memory_client.formatting import format_wake_up
from memory_service import memory_repo
from memory_service.config import get_driver, settings
from memory_service.embeddings import get_embedding


mcp = FastMCP("graph-memory-fabric")

_cached_driver = None


def _driver():
    """Return the shared Bolt driver, creating it once at module level."""
    global _cached_driver
    if _cached_driver is None:
        _cached_driver = get_driver(settings)
    return _cached_driver


_compute_maintenance_status = memory_repo.compute_maintenance_status


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
    text = fact + (" " + so_what if so_what else "")
    embedding = get_embedding(text)
    now = datetime.now(tz=timezone.utc).isoformat()
    memory_id_to_return = None
    deduplicated = False

    req = SimpleNamespace(
        fact=fact,
        so_what=so_what,
        text=text,
        type=SimpleNamespace(value=type),
        tags=tags or [],
        agent_id=agent_id,
        project_id=None,
        person_ids=person_ids or [],
        strand_ids=strand_ids or [],
        importance=importance,
        related_ids=None,
        cause_ids=cause_ids or [],
        effect_ids=effect_ids or [],
        control_ids=control_ids or [],
        doc_ids=doc_ids or [],
        control_relationship_type=control_relationship_type,
        org_id=org_id,
        ephemeral=False,
        files_modified=[],
        files_read=[],
    )

    with _driver().session() as session:
        existing_id = memory_repo.find_duplicate_memory(
            session, fact, embedding, settings.memory_dedup_threshold,
        )
        if existing_id is not None:
            memory_repo.reinforce_memory(
                session, existing_id,
                strength_increment=settings.explicit_strength_increment,
                edge_increment=settings.edge_explicit_increment,
                co_recalled_ids=[],
                now_iso=now,
                consolidated_decay_rate=settings.memory_consolidated_decay_rate,
            )
            memory_id_to_return = existing_id
            deduplicated = True
        else:
            memory_id_to_return = str(uuid.uuid4())
            memory_repo.add_memory(
                session, req, memory_id_to_return, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
            if settings.enable_knowledge_layer and (req.control_ids or req.doc_ids):
                from memory_service import knowledge_bridge
                if req.control_ids:
                    knowledge_bridge.link_controls(
                        session, memory_id_to_return, req.control_ids,
                        req.control_relationship_type, req.org_id,
                    )
                if req.doc_ids:
                    knowledge_bridge.link_documents(session, memory_id_to_return, req.doc_ids)

    result = {
        "memory_id": memory_id_to_return,
        "deduplicated": deduplicated,
        "strand_ids": strand_ids or [],
    }
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
    query_embedding = get_embedding(query)
    req = SimpleNamespace(
        query=query,
        tags=tags,
        agent_ids=agent_ids,
        project_ids=None,
        person_ids=person_ids,
        limit=limit,
        max_hops=1,
        traversal_direction=traversal_direction,
        min_importance=None,
        min_score=None,
        neighbour_cap=3,
        files_modified=None,
        files_read=None,
    )
    with _driver().session() as session:
        results = memory_repo.search_memories(
            session, req, query_embedding, settings.search_neighbour_cap
        )
        primary_ids = {r["id"] for r in results}
        cap = req.neighbour_cap if not req.person_ids else 0
        associated_map = memory_repo.fetch_associated(
            session, list(primary_ids), cap, primary_ids
        )
    return [
        {**r, "associated": associated_map.get(r["id"], [])}
        for r in results
    ]


@mcp.tool
def memory_wake_up(
    topic: str | None = None,
    limit: int = 20,
    person_id: str | None = None,
) -> str:
    """Return the session wake-up briefing as plain text. Read fully before responding to the user."""
    topic_embedding = get_embedding(topic) if topic else None
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    with _driver().session() as session:
        result = memory_repo.wake_up(
            session,
            limit=limit,
            topic_embedding=topic_embedding,
            agent_id=settings.agent_id,
            companion_anchor_limit=settings.wake_up_companion_anchor_limit,
            person_id=person_id,
            conversant_anchor_limit=settings.wake_up_conversant_anchor_limit,
        )

    maintenance_status_data = {
        "short_rest_overdue": False,
        "long_rest_overdue": False,
        "short_rest_days_ago": None,
        "long_rest_days_ago": None,
        "recommended_action": None,
    }
    try:
        with _driver().session() as maint_session:
            ts = memory_repo.get_system_timestamps(maint_session)
        maintenance_status_data = _compute_maintenance_status(
            last_short_rest_at=ts.get("last_short_rest_at"),
            last_long_rest_at=ts.get("last_long_rest_at"),
            now_iso=now_iso,
            short_rest_recency_days=settings.short_rest_recency_days,
            long_rest_recency_days=settings.long_rest_recency_days,
        )
    except Exception:
        pass

    wake_up_dict = {
        "memories": result.get("core", []),
        "topic_memories": result.get("topic", []),
        "maintenance_status": maintenance_status_data,
        "companion_anchors": result.get("companion_anchors"),
        "conversant_anchors": result.get("conversant_anchors"),
        "global_mara_baseline": result.get("global_mara_baseline"),
        "global_user_baseline": result.get("global_user_baseline"),
        "project_mara_persona": result.get("project_mara_persona"),
        "project_baseline": result.get("project_baseline"),
    }

    lines = []
    action = maintenance_status_data.get("recommended_action")
    if action:
        lines += ["## Maintenance required", "", f"  {action}", ""]

    lines.append(format_wake_up(wake_up_dict, topic=topic, plain=True))
    return "\n".join(lines)


@mcp.tool
def memory_list_strands() -> list[dict]:
    """Return all strands from the graph (authoritative live list).

    Call this before memory_add or memory_update to get current strand IDs,
    names, descriptions, and categories. Do not guess or hard-code strand IDs.
    """
    with _driver().session() as session:
        return memory_repo.list_strands(session)


@mcp.tool
def memory_list_persons() -> list[dict]:
    """Return all Person nodes. Use person IDs when calling memory_add."""
    with _driver().session() as session:
        return memory_repo.list_persons(session)


@mcp.tool
def memory_create_person(person_id: str, name: str, description: str | None = None) -> dict:
    """Create or merge a Person node. Returns the person dict."""
    req = SimpleNamespace(id=person_id, name=name, description=description)
    with _driver().session() as session:
        return memory_repo.upsert_person(session, req)


@mcp.tool
def memory_list_projects() -> list[dict]:
    """Return all Project nodes. Use project IDs when calling memory_add."""
    with _driver().session() as session:
        return memory_repo.list_projects(session)


@mcp.tool
def memory_create_project(
    project_id: str,
    name: str,
    description: str | None = None,
    slug: str | None = None,
    weight: float | None = None,
) -> dict:
    """Create or merge a Project node. slug is a short alias for source_ref namespace (e.g. 'gmf').
    weight is a cross-project priority multiplier (default 1.0, must be > 0).
    Returns the project dict."""
    req = SimpleNamespace(id=project_id, name=name, description=description, slug=slug, weight=weight)
    with _driver().session() as session:
        return memory_repo.upsert_project(session, req)


@mcp.tool
def task_add(
    title: str,
    agent_id: str,
    description: str | None = None,
    status: str = "open",
    value: str | None = None,
    effort: str | None = None,
    urgency: float | None = None,
    due_at: str | None = None,
    snooze_until: str | None = None,
    committed_at: str | None = None,
    committed_by: str | None = None,
    source_ref: str | None = None,
    project_id: str | None = None,
    memory_ids: list[str] | None = None,
    recurrence: str | None = None,
    is_template: bool = False,
) -> dict:
    """Create a Task node. value/effort are H|M|L for priority scoring.
    source_ref format: '{project-slug}:WP-NNN' (e.g. 'gmf:WP-143').
    committed_at starts the accountability clock; committed_by records which agent made the commitment.
    Returns the task dict including computed priority_score."""
    priority_score = None
    if value and effort:
        priority_score = memory_repo._VE_MAP.get(value, 2.0) / memory_repo._VE_MAP.get(effort, 2.0)

    req = SimpleNamespace(
        title=title,
        agent_id=agent_id,
        description=description,
        status=SimpleNamespace(value=status),
        value=SimpleNamespace(value=value) if value else None,
        effort=SimpleNamespace(value=effort) if effort else None,
        urgency=urgency,
        due_at=due_at,
        snooze_until=snooze_until,
        committed_at=committed_at,
        committed_by=committed_by,
        source_ref=source_ref,
        project_id=project_id,
        memory_ids=memory_ids or [],
        recurrence=recurrence,
        is_template=is_template,
        priority_score=priority_score,
    )
    task_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        return memory_repo.create_task(session, req, task_id, now)


@mcp.tool
def task_list(
    status: str | None = None,
    agent_id: str | None = None,
    project_id: str | None = None,
    committed_only: bool = False,
) -> list[dict]:
    """List Task nodes. Filter by status (open|active|blocked|done|abandoned),
    agent_id, project_id, or committed_only (tasks with committed_at set).
    Templates are excluded. Returns list of task dicts."""
    with _driver().session() as session:
        return memory_repo.list_tasks(
            session,
            status=status,
            agent_id=agent_id,
            project_id=project_id,
            committed_only=committed_only,
        )


@mcp.tool
def task_get(task_id: str) -> dict:
    """Get a single Task node by UUID. Returns the task dict or raises 404."""
    with _driver().session() as session:
        task = memory_repo.get_task(session, task_id)
    if task is None:
        raise ValueError(f"Task {task_id!r} not found")
    return task


@mcp.tool
def task_update(
    task_id: str,
    status: str | None = None,
    value: str | None = None,
    effort: str | None = None,
    urgency: float | None = None,
    due_at: str | None = None,
    committed_at: str | None = None,
    committed_by: str | None = None,
    last_checked_at: str | None = None,
    source_ref: str | None = None,
) -> dict:
    """Update Task node fields. priority_score is recomputed automatically when value or effort changes.
    Returns the updated task dict."""
    patch_fields = {k: v for k, v in {
        "status": status, "value": value, "effort": effort, "urgency": urgency,
        "due_at": due_at, "committed_at": committed_at, "committed_by": committed_by,
        "last_checked_at": last_checked_at, "source_ref": source_ref,
    }.items() if v is not None}
    now = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        task = memory_repo.update_task(session, task_id, patch_fields, now)
    if task is None:
        raise ValueError(f"Task {task_id!r} not found")
    return task


@mcp.tool
def task_complete(task_id: str) -> dict:
    """Mark a Task as done. Shorthand for task_update(task_id, status='done').
    Returns the updated task dict."""
    now = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        task = memory_repo.update_task(session, task_id, {"status": "done"}, now)
    if task is None:
        raise ValueError(f"Task {task_id!r} not found")
    return task


@mcp.tool
def task_stale() -> list[dict]:
    """Return tasks with committed_at set but no status update since — the accountability cron signal.
    Returns list of task dicts ordered by committed_at ASC (oldest commitment first)."""
    with _driver().session() as session:
        return memory_repo.list_stale_tasks(session)


@mcp.tool
def task_next(limit: int = 10) -> list[dict]:
    """Return the cross-project prioritised task queue: open/active tasks sorted by
    priority_score × project.weight DESC, then due_at ASC.
    Use this to answer 'what should I work on next?' across all projects."""
    with _driver().session() as session:
        return memory_repo.list_next_tasks(session, limit=limit)


@mcp.tool
def memory_reinforce(memory_id: str, co_recalled_ids: list[str] | None = None) -> dict:
    """Explicitly reinforce a memory. Pass co_recalled_ids for Hebbian edge strengthening."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        new_strength = memory_repo.reinforce_memory(
            session, memory_id,
            strength_increment=settings.explicit_strength_increment,
            edge_increment=settings.edge_explicit_increment,
            co_recalled_ids=co_recalled_ids or [],
            now_iso=now_iso,
            consolidated_decay_rate=settings.memory_consolidated_decay_rate,
        )
    return {"memory_id": memory_id, "new_strength": new_strength}


@mcp.tool
def memory_run_decay() -> dict:
    """Trigger a full-graph decay pass. Returns nodes_updated and edges_updated counts."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        return memory_repo.decay_pass(session, "", now_iso, settings.min_memory_strength)


@mcp.tool
def memory_short_rest(dry_run: bool = False) -> str:
    """Run Short Rest decay pass on recently-active memories.
    Returns a plain-text summary. Use dry_run=True to preview without writing."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        result = memory_repo.short_rest(
            session,
            now_iso=now_iso,
            recency_days=settings.short_rest_recency_days,
            min_strength=settings.min_memory_strength,
            edge_modulation_factor=settings.edge_modulation_factor,
            edge_modulation_cap=settings.edge_modulation_cap,
            dry_run=dry_run,
        )
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
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        result = memory_repo.long_rest(
            session,
            now_iso=now_iso,
            min_strength=settings.min_memory_strength,
            edge_modulation_factor=settings.edge_modulation_factor,
            edge_modulation_cap=settings.edge_modulation_cap,
            rediscovery_strength_threshold=settings.rediscovery_strength_threshold,
            edge_hard_prune_floor=settings.edge_hard_prune_floor,
            edge_hard_prune_min_days=settings.edge_hard_prune_min_days,
            edge_decay_rate=settings.edge_decay_rate,
            memory_index_capacity=settings.memory_index_capacity,
            near_duplicate_threshold=settings.near_duplicate_threshold,
            near_duplicate_preview_limit=settings.near_duplicate_limit,
            dry_run=dry_run,
            prune=prune,
            auto_merge_threshold=settings.auto_merge_threshold,
        )
    dr = " (dry-run)" if result.get("dry_run") else ""
    util_pct = result.get("index_utilisation_pct")
    util_str = f"{util_pct}%" if util_pct is not None else "n/a"
    near_cap = " index near capacity" if result.get("index_near_capacity") else ""
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
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        return memory_repo.maintenance_stats(
            session,
            now_iso=now_iso,
            edge_prune_threshold=settings.edge_hard_prune_floor,
            short_rest_recency_days=settings.short_rest_recency_days,
            long_rest_recency_days=settings.long_rest_recency_days,
            near_duplicate_threshold=settings.near_duplicate_threshold,
        )


@mcp.tool
def memory_operation_log() -> str:
    """Return the operation log (update/merge/archive/restore events) as plain text, most recent first."""
    with _driver().session() as session:
        entries = memory_repo.get_operation_log(session)

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
    with _driver().session() as session:
        entries = memory_repo.get_maintenance_log(session)

    if not entries:
        return "No maintenance runs recorded yet."

    lines = ["## Maintenance audit log", ""]
    for entry in reversed(entries):
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
    now = datetime.now(tz=timezone.utc).isoformat()
    patch_fields: dict = {}
    if fact is not None:
        patch_fields["fact"] = fact
    if so_what is not None:
        patch_fields["so_what"] = so_what
    if tags is not None:
        patch_fields["tags"] = tags
    if importance is not None:
        patch_fields["importance"] = importance
    if person_ids is not None:
        patch_fields["person_ids"] = person_ids
    if strand_ids is not None:
        patch_fields["strand_ids"] = strand_ids

    _BRIDGE_FIELDS = {"control_ids", "doc_ids", "control_relationship_type", "org_id"}
    bridge_fields: dict = {}
    if control_ids is not None:
        bridge_fields["control_ids"] = control_ids
    if doc_ids is not None:
        bridge_fields["doc_ids"] = doc_ids
    if control_relationship_type is not None:
        bridge_fields["control_relationship_type"] = control_relationship_type
    if org_id is not None:
        bridge_fields["org_id"] = org_id

    new_embedding = None
    with _driver().session() as session:
        if "fact" in patch_fields or "so_what" in patch_fields:
            current = memory_repo.get_memory_for_update(session, memory_id)
            if current is None:
                raise ValueError(f"Memory {memory_id!r} not found or not active")
            merged_fact = patch_fields.get("fact", current["fact"] or "")
            merged_so_what = patch_fields.get("so_what", current["so_what"])
            merged_text = merged_fact + (" " + merged_so_what if merged_so_what else "")
            patch_fields["text"] = merged_text
            new_embedding = get_embedding(merged_text)

        memory_repo.update_memory(session, memory_id, patch_fields, new_embedding, now)

        if settings.enable_knowledge_layer and bridge_fields:
            from memory_service import knowledge_bridge
            if "control_ids" in bridge_fields:
                knowledge_bridge.replace_control_edges(
                    session, memory_id,
                    bridge_fields["control_ids"],
                    bridge_fields.get("control_relationship_type"),
                    bridge_fields.get("org_id"),
                )
            if "doc_ids" in bridge_fields:
                knowledge_bridge.replace_doc_edges(
                    session, memory_id, bridge_fields["doc_ids"],
                )

        memory_repo.append_operation_log(session, {
            "operation": "update",
            "memory_id": memory_id,
            "ran_at": now,
            "fields_updated": list(patch_fields.keys()) + list(bridge_fields.keys()),
        })

    return {"memory_id": memory_id, "updated_at": now}


@mcp.tool
def memory_archive(memory_id: str) -> dict:
    """Archive a memory. Archived memories are excluded from search and wake-up.
    Use memory_restore to make it active again. Returns {memory_id, archived_at}."""
    now = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        memory_repo.archive_memory(session, memory_id, now)
        memory_repo.append_operation_log(session, {
            "operation": "archive",
            "memory_id": memory_id,
            "ran_at": now,
        })
    return {"memory_id": memory_id, "archived_at": now}


@mcp.tool
def memory_restore(memory_id: str) -> dict:
    """Restore an archived memory to active status. Returns {memory_id, status}."""
    now = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        memory_repo.restore_memory(session, memory_id)
        memory_repo.append_operation_log(session, {
            "operation": "restore",
            "memory_id": memory_id,
            "ran_at": now,
        })
    return {"memory_id": memory_id, "status": "active"}


@mcp.tool
def memory_delete(memory_id: str) -> str:
    """Permanently delete a memory and all its edges from the graph.

    This is irreversible — use memory_archive if you want a reversible path.
    Returns a plain-text confirmation string.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    with _driver().session() as session:
        memory_repo.delete_memory(session, memory_id)
        memory_repo.append_operation_log(session, {
            "operation": "delete",
            "memory_id": memory_id,
            "ran_at": now,
        })
    return f"Deleted memory {memory_id}"


@mcp.tool
def memory_merge(source_id: str, target_id: str) -> dict:
    """Merge source memory into target. The source is marked merged and its edges
    (ABOUT, IN_STRAND, LEADS_TO, RELATED_TO) are rewired to the target.
    Returns {source_id, target_id}."""
    now = datetime.now(tz=timezone.utc).isoformat()
    if source_id == target_id:
        raise ValueError("Source and target must differ")
    with _driver().session() as session:
        memory_repo.merge_memory(
            session, source_id, target_id, "replace",
            default_edge_decay_rate=settings.edge_decay_rate,
        )
        if settings.enable_knowledge_layer:
            from memory_service import knowledge_bridge
            knowledge_bridge.rewire_cross_layer_edges(session, source_id, target_id)
        memory_repo.append_operation_log(session, {
            "operation": "merge",
            "memory_id": source_id,
            "ran_at": now,
            "target_id": target_id,
        })
    return {"source_id": source_id, "target_id": target_id}


@mcp.tool
def memory_find_duplicates(
    threshold: float | None = None, limit: int | None = None
) -> list[dict]:
    """Find near-duplicate memory pairs above a similarity threshold for review and merge."""
    effective_threshold = threshold if threshold is not None else settings.near_duplicate_threshold
    effective_limit = limit if limit is not None else settings.near_duplicate_limit
    with _driver().session() as session:
        return memory_repo.find_near_duplicates(session, effective_threshold, effective_limit)


@mcp.tool
def memory_purge_ephemeral() -> str:
    """Hard-delete all ephemeral memories from the graph.

    Ephemeral memories are test artefacts created with ephemeral=true.
    Returns a plain-text summary of the count deleted.

    Warning: deletes ALL ephemeral memories globally — not safe for concurrent
    test sessions against the same Memgraph instance.
    """
    with _driver().session() as session:
        deleted = memory_repo.purge_ephemeral_memories(session)
    return f"Purged {deleted} ephemeral memories."


@mcp.tool
def memory_close_session() -> str:
    """Return the session close-out scaffold as plain text. Work through it before ending the session."""
    return _CLOSE_SESSION_SCAFFOLD


if settings.enable_knowledge_layer:
    from memory_service import knowledge_repo

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
        with _driver().session() as session:
            return knowledge_repo.search_controls(session, query, limit=limit, framework_id=framework_id)

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
        with _driver().session() as session:
            return knowledge_repo.search_chunks(session, query, limit=limit, doc_id=doc_id)

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
        with _driver().session() as session:
            return knowledge_repo.list_norms(session)

    @mcp.tool
    def knowledge_get_control(control_id: str) -> dict:
        """Fetch a single InfoSec control by its ID.

        Use when an agent already has a control_id (e.g. from knowledge_search_controls)
        and needs its full details: name, description, framework_id, and created_at.
        Returns 404 detail if the control does not exist.
        """
        with _driver().session() as session:
            return knowledge_repo.get_control(session, control_id)

    @mcp.tool
    def knowledge_get_norm(norm_id: str) -> dict:
        """Fetch a single regulatory norm by its ID.

        Use when an agent already has a norm_id (e.g. from knowledge_list_norms)
        and needs its full details: name, text, status, and effective_date.
        Returns 404 detail if the norm does not exist.
        """
        with _driver().session() as session:
            return knowledge_repo.get_norm(session, norm_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
