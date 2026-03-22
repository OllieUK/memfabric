# memory_service/memory_repo.py
#
# Repository layer: all Cypher operations for the /memory endpoint.
# All functions receive an already-open neo4j.Session; callers own the session lifecycle.

import math
from datetime import datetime, timezone

_AUTO_RELATED_K = 5
_AUTO_RELATED_MAX_DISTANCE = 0.5


def add_memory(session, req, memory_id: str, embedding: list, now: str, decay_rate: float) -> None:
    """Write a Memory node and all related nodes/edges in a single session.

    Steps:
    1. Upsert Agent + create Memory + PRODUCED_BY edge (single round-trip)
    2. Upsert Project + ABOUT edge (if project_id)
    3. Upsert each Person + ABOUT edge
    4. Upsert each Strand + IN_STRAND edge
    5a. Explicit RELATED_TO edges (if related_ids provided)
    5b. Auto RELATED_TO via vector search (if related_ids is None)
    """
    # Step 1 — Upsert Agent + create Memory + PRODUCED_BY edge (single round-trip)
    session.run(
        """
        MERGE (a:Agent {id: $agent_id})
        CREATE (m:Memory {
            id: $id,
            fact: $fact,
            so_what: $so_what,
            text: $text,
            type: $type,
            tags: $tags,
            importance: $importance,
            created_at: $created_at,
            last_used_at: $last_used_at,
            embedding: $embedding,
            strength: $strength,
            recall_count: 0,
            reinforcement_count: 0,
            last_reinforced_at: $last_reinforced_at,
            decay_rate: $decay_rate
        })
        CREATE (m)-[:PRODUCED_BY]->(a)
        """,
        agent_id=req.agent_id,
        id=memory_id,
        fact=req.fact,
        so_what=req.so_what,
        text=req.text,
        type=req.type.value,
        tags=req.tags,
        importance=req.importance,
        created_at=now,
        last_used_at=now,
        embedding=embedding,
        strength=req.importance / 5.0,
        last_reinforced_at=now,
        decay_rate=decay_rate,
    )

    # Step 2 — Upsert Project + ABOUT edge
    if req.project_id:
        session.run(
            """
            MERGE (p:Project {id: $project_id})
            WITH p
            MATCH (m:Memory {id: $memory_id})
            CREATE (m)-[:ABOUT]->(p)
            """,
            project_id=req.project_id,
            memory_id=memory_id,
        )

    # Step 3 — Upsert each Person + ABOUT edge
    for person_id in req.person_ids:
        session.run(
            """
            MERGE (p:Person {id: $person_id})
            WITH p
            MATCH (m:Memory {id: $memory_id})
            CREATE (m)-[:ABOUT]->(p)
            """,
            person_id=person_id,
            memory_id=memory_id,
        )

    # Step 4 — Upsert each Strand + IN_STRAND edge
    for strand_id in req.strand_ids:
        session.run(
            """
            MERGE (s:Strand {id: $strand_id})
            WITH s
            MATCH (m:Memory {id: $memory_id})
            CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)
            """,
            strand_id=strand_id,
            memory_id=memory_id,
        )

    # Step 5 — RELATED_TO edges
    if req.related_ids is not None:
        # 5a: explicit — use provided ids
        for related_id in req.related_ids:
            session.run(
                """
                MATCH (m:Memory {id: $memory_id})
                MATCH (r:Memory {id: $related_id})
                MERGE (m)-[:RELATED_TO {weight: 1.0}]->(r)
                """,
                memory_id=memory_id,
                related_id=related_id,
            )
    else:
        # 5b: auto — vector search, exclude self, only close neighbours
        session.run(
            """
            CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
            YIELD node, distance
            WITH node, distance
            WHERE node.id <> $memory_id AND distance < $max_distance
            MATCH (m:Memory {id: $memory_id})
            MERGE (m)-[r:RELATED_TO]->(node)
            SET r.weight = 1.0 - distance
            """,
            k=_AUTO_RELATED_K,
            query_vec=embedding,
            memory_id=memory_id,
            max_distance=_AUTO_RELATED_MAX_DISTANCE,
        )

    # Step 6 — LEADS_TO edges: cause_ids → this memory (this memory is the effect)
    for cause_id in req.cause_ids:
        session.run(
            """
            OPTIONAL MATCH (cause:Memory {id: $cause_id})
            WITH cause
            WHERE cause IS NOT NULL
            MATCH (effect:Memory {id: $new_memory_id})
            MERGE (cause)-[:LEADS_TO]->(effect)
            """,
            cause_id=cause_id,
            new_memory_id=memory_id,
        )

    # Step 7 — LEADS_TO edges: this memory → effect_ids (this memory is the cause)
    for effect_id in req.effect_ids:
        session.run(
            """
            OPTIONAL MATCH (effect:Memory {id: $effect_id})
            WITH effect
            WHERE effect IS NOT NULL
            MATCH (cause:Memory {id: $new_memory_id})
            MERGE (cause)-[:LEADS_TO]->(effect)
            """,
            effect_id=effect_id,
            new_memory_id=memory_id,
        )


# Query template — {neighbour_clause} and {neighbour_return} are filled in at call time.
# max_hops is interpolated as an integer (Pydantic-validated ge=0, le=3); all other
# filter values are passed as named Cypher parameters to avoid injection risk.
# NOTE: agent_ids / project_ids filters use EXISTS{} subquery syntax (Memgraph 2.4+).
# If your Memgraph version predates this, see the fallback comment in the function body.
# NOTE: vector_search returns up to $limit nodes *before* filtering. When filters are
# tight, the response may be empty even if matching nodes exist further down the ranking.
# This is expected behaviour for this architecture.
_SEARCH_QUERY_TEMPLATE = """\
CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
YIELD node AS m, distance
WITH m, distance
WHERE ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, distance, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
WITH m.id AS id, m.text AS text, m.type AS type, m.tags AS tags, m.importance AS importance, distance, m
{neighbour_clause}
RETURN id, text, type, tags, importance, distance, {neighbour_return}
ORDER BY distance ASC\
"""


def search_memories(session, req, query_embedding: list) -> list:
    """Run vector search with optional filters and graph expansion.

    Args:
        session: open neo4j Session
        req: SearchMemoryRequest (query, tags, agent_ids, project_ids, limit, max_hops,
             traversal_direction)
        query_embedding: pre-computed embedding for req.query

    Returns:
        List of dicts with keys: id, text, type, tags, importance, neighbours
    """
    direction = getattr(req, "traversal_direction", "none")
    hops = req.max_hops

    # Build RELATED_TO clause (existing logic)
    related_clause = f"OPTIONAL MATCH (m)-[:RELATED_TO*1..{hops}]->(n:Memory)" if hops > 0 else ""

    # Build LEADS_TO clause(s) based on traversal_direction
    causes_clause = ""
    effects_clause = ""
    hop_depth = max(hops, 1)  # when max_hops=0, LEADS_TO still traverses 1 hop
    if direction in ("causes", "both"):
        causes_clause = f"OPTIONAL MATCH (m)<-[:LEADS_TO*1..{hop_depth}]-(c:Memory)"
    if direction in ("effects", "both"):
        effects_clause = f"OPTIONAL MATCH (m)-[:LEADS_TO*1..{hop_depth}]->(e:Memory)"

    # Combine neighbour clauses and collect expressions
    neighbour_clauses = "\n".join(
        c for c in [related_clause, causes_clause, effects_clause] if c
    )

    collect_parts = []
    if hops > 0:
        collect_parts.append("collect(DISTINCT n.id)")
    if direction in ("causes", "both"):
        collect_parts.append("collect(DISTINCT c.id)")
    if direction in ("effects", "both"):
        collect_parts.append("collect(DISTINCT e.id)")

    if collect_parts:
        neighbour_return = " + ".join(collect_parts) + " AS neighbours"
    else:
        neighbour_return = "[] AS neighbours"

    query = _SEARCH_QUERY_TEMPLATE.format(
        neighbour_clause=neighbour_clauses,
        neighbour_return=neighbour_return,
    )

    result = session.run(
        query,
        query_vec=query_embedding,
        limit=req.limit,
        tags=req.tags,
        agent_ids=req.agent_ids,
        project_ids=req.project_ids,
    )

    return [
        {
            "id": record["id"],
            "text": record["text"],
            "type": record["type"],
            "tags": record["tags"],
            "importance": record["importance"],
            "neighbours": record["neighbours"],
        }
        for record in result
    ]


def _record_to_memory_dict(record) -> dict:
    """Extract the standard Memory field set from a neo4j Record.

    Caller MUST select: id, text, type, tags, importance, created_at, strand_id
    in the Cypher query. strand_id may be None (from OPTIONAL MATCH).
    """
    return {
        "id": record["id"],
        "text": record["text"],
        "type": record["type"],
        "tags": record["tags"],
        "importance": record["importance"],
        "created_at": record["created_at"],
        "strand_id": record["strand_id"],  # always present: OPTIONAL MATCH returns None if no strand
    }


def wake_up(session, limit: int, topic_embedding: list | None = None) -> dict:
    """Return memories for session start as two separate lists.

    Returns:
        dict with keys:
          "core"  — importance-ranked list, up to `limit` items
          "topic" — topic-only items (not in core), up to `limit` items;
                    empty list when topic_embedding is None
        Each item dict: id, text, type, tags, importance, created_at, strand_id
    """
    result = session.run(
        """
        MATCH (m:Memory)
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        ORDER BY m.importance DESC, m.created_at DESC
        LIMIT $limit
        """,
        limit=limit,
    )
    core = [_record_to_memory_dict(r) for r in result]

    if topic_embedding is None:
        return {"core": core, "topic": []}

    core_ids = {item["id"] for item in core}

    topic_result = session.run(
        """
        CALL vector_search.search("mem_embedding_idx", $limit, $query_vec)
        YIELD node AS m, distance
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        """,
        limit=limit,
        query_vec=topic_embedding,
    )
    topic = [_record_to_memory_dict(r) for r in topic_result if r["id"] not in core_ids]

    return {"core": core, "topic": topic}


def list_strands(session) -> list:
    """Return all Strand nodes ordered by category then name.

    Returns:
        List of dicts with keys: id, name, description, category
    """
    result = session.run(
        "MATCH (s:Strand) RETURN s.id AS id, s.name AS name, "
        "s.description AS description, s.category AS category "
        "ORDER BY s.category, s.name"
    )
    return [
        {
            "id": record["id"],
            "name": record["name"],
            "description": record["description"],
            "category": record["category"],
        }
        for record in result
    ]


def list_persons(session) -> list[dict]:
    """Return all Person nodes ordered by id."""
    result = session.run(
        "MATCH (p:Person) RETURN p.id AS id, p.name AS name, "
        "p.description AS description ORDER BY p.id"
    )
    return [
        {"id": r["id"], "name": r["name"], "description": r["description"]}
        for r in result
    ]


def upsert_person(session, req) -> dict:
    """Create or update a Person node by id. Returns the stored values."""
    result = session.run(
        """
        MERGE (p:Person {id: $id})
        SET p.name = $name, p.description = $description
        RETURN p.id AS id, p.name AS name, p.description AS description
        """,
        id=req.id,
        name=req.name,
        description=req.description,
    )
    record = result.single()
    if record is None:
        raise RuntimeError(f"upsert_person: MERGE returned no record for id={req.id!r}")
    return {"id": record["id"], "name": record["name"], "description": record["description"]}


def recall_increment(
    session,
    memory_ids: list[str],
    strength_increment: float,
    edge_increment: float,
) -> None:
    """Increment recall_count and strength on recalled memories; activate traversed edges.

    Called in a background task after search — does not block the response.
    Strength is capped at 1.0. last_reinforced_at is NOT updated (recall != explicit reinforcement).
    Edge activation covers RELATED_TO and LEADS_TO edges between members of the result set.
    """
    if not memory_ids:
        return

    now = datetime.now(timezone.utc).isoformat()

    # Node increment
    session.run(
        """
        UNWIND $ids AS mid
        MATCH (m:Memory {id: mid})
        SET m.recall_count = coalesce(m.recall_count, 0) + 1,
            m.strength = CASE
                WHEN coalesce(m.strength, m.importance / 5.0) + $increment >= 1.0
                THEN 1.0
                ELSE coalesce(m.strength, m.importance / 5.0) + $increment
            END
        """,
        ids=memory_ids,
        increment=strength_increment,
    )

    # Edge activation — RELATED_TO and LEADS_TO edges within the result set
    if len(memory_ids) > 1:
        session.run(
            """
            UNWIND $ids AS src
            UNWIND $ids AS tgt
            WITH src, tgt
            WHERE src <> tgt
            OPTIONAL MATCH (a:Memory {id: src})-[r:RELATED_TO|LEADS_TO]->(b:Memory {id: tgt})
            WITH r, $edge_increment AS inc, $now AS ts
            WHERE r IS NOT NULL
            SET r.activation_count = coalesce(r.activation_count, 0) + 1,
                r.last_activated_at = ts,
                r.weight = CASE
                    WHEN coalesce(r.weight, 0.5) + inc >= 1.0 THEN 1.0
                    ELSE coalesce(r.weight, 0.5) + inc
                END
            """,
            ids=memory_ids,
            edge_increment=edge_increment,
            now=now,
        )


def _parse_iso(ts: str) -> datetime:
    """Parse an ISO datetime string to a timezone-aware datetime.

    Handles both offset-aware ('2026-03-22T10:00:00+00:00') and
    naive ('2026-03-22T10:00:00') formats by assuming UTC for naive strings.
    """
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _apply_decay(current: float, rate: float, days: float) -> float:
    """Return decayed value clamped to [0, 1]."""
    return max(0.0, min(1.0, current * math.exp(-rate * days)))


def decay_pass(session, now_naive: str, now_iso: str) -> dict:
    """Recompute and write strength for all Memory nodes and weight for all edges.

    Formula: new_value = current_value * exp(-decay_rate * days_since_anchor)
    Anchors: Memory.last_reinforced_at, edge.last_activated_at.
    After writing, resets anchors to now_iso so future inline calcs stay numerically stable.

    Memgraph does not support duration.between() or epochSeconds on datetime types, so
    the days computation is performed in Python after fetching the anchor timestamps.

    Args:
        now_naive: unused (kept for API compatibility); computation uses now_iso
        now_iso: full ISO string representing the current time, e.g. "2026-03-22T10:30:00+00:00"

    Returns dict with keys: nodes_updated, edges_updated (int counts).
    """
    now = _parse_iso(now_iso)

    # --- Node decay ---
    node_rows = list(session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
        RETURN m.id AS id, m.strength AS strength,
               m.last_reinforced_at AS anchor, m.decay_rate AS rate
        """
    ))

    node_updates = []
    for row in node_rows:
        try:
            anchor = _parse_iso(row["anchor"])
        except (ValueError, TypeError):
            continue
        days = (now - anchor).total_seconds() / 86400.0
        node_updates.append({
            "id": row["id"],
            "new_val": _apply_decay(row["strength"], row["rate"], days),
        })

    if node_updates:
        session.run(
            """
            UNWIND $updates AS upd
            MATCH (m:Memory {id: upd.id})
            SET m.strength = upd.new_val, m.last_reinforced_at = $now_iso
            """,
            updates=node_updates,
            now_iso=now_iso,
        )

    # --- Edge decay ---
    edge_rows = list(session.run(
        """
        MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
        WHERE r.weight IS NOT NULL AND r.last_activated_at IS NOT NULL AND r.decay_rate IS NOT NULL
        RETURN id(r) AS rid, r.weight AS weight,
               r.last_activated_at AS anchor, r.decay_rate AS rate
        """
    ))

    edge_updates = []
    for row in edge_rows:
        try:
            anchor = _parse_iso(row["anchor"])
        except (ValueError, TypeError):
            continue
        days = (now - anchor).total_seconds() / 86400.0
        edge_updates.append({
            "rid": row["rid"],
            "new_val": _apply_decay(row["weight"], row["rate"], days),
        })

    if edge_updates:
        session.run(
            """
            UNWIND $updates AS upd
            MATCH ()-[r:RELATED_TO|LEADS_TO]->()
            WHERE id(r) = upd.rid
            SET r.weight = upd.new_val, r.last_activated_at = $now_iso
            """,
            updates=edge_updates,
            now_iso=now_iso,
        )

    return {"nodes_updated": len(node_updates), "edges_updated": len(edge_updates)}


def list_weak_edges(session, threshold: float) -> list[dict]:
    """Return edges whose stored weight is below threshold (up to 200 results).

    Run a decay pass first for accurate results.
    """
    result = session.run(
        """
        MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
        WHERE r.weight IS NOT NULL AND r.weight < $threshold
        RETURN src.id AS source_id, tgt.id AS target_id,
               type(r) AS relation, r.weight AS weight,
               r.activation_count AS activation_count
        ORDER BY r.weight ASC
        LIMIT 200
        """,
        threshold=threshold,
    )
    return [
        {
            "source_id": row["source_id"],
            "target_id": row["target_id"],
            "relation": row["relation"],
            "weight": row["weight"],
            "activation_count": row["activation_count"],
        }
        for row in result
    ]
