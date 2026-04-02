# memory_service/memory_repo.py
#
# Repository layer: all Cypher operations for the /memory endpoint.
# All functions receive an already-open neo4j.Session; callers own the session lifecycle.

import json
import math
from collections import defaultdict
from datetime import datetime, timezone

_AUTO_RELATED_K = 5
_AUTO_RELATED_MAX_DISTANCE = 0.5


def add_memory(
    session,
    req,
    memory_id: str,
    embedding: list,
    now: str,
    decay_rate: float,
    initial_strength_factor: float = 0.4,
    importance_floor_factor: float = 0.3,
) -> None:
    """Write a Memory node and all related nodes/edges in a single session.

    Steps:
    1. Upsert Agent + create Memory + PRODUCED_BY edge (single round-trip)
    2. Upsert Project + ABOUT edge (if project_id)
    3. Upsert each Person + ABOUT edge
    4. Link to each Strand via IN_STRAND edge (strand must already exist)
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
            min_strength: $min_strength,
            recall_count: 0,
            reinforcement_count: 0,
            last_reinforced_at: $last_reinforced_at,
            decay_rate: $decay_rate,
            status: 'active'
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
        strength=initial_strength_factor * (req.importance / 5.0),
        min_strength=importance_floor_factor * (req.importance / 5.0),
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

    # Step 4 — Link to each Strand via IN_STRAND edge (strand must already exist)
    for strand_id in req.strand_ids:
        session.run(
            """
            MATCH (s:Strand {id: $strand_id})
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
WHERE (m.status IS NULL OR m.status = 'active')
AND   ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
AND   ($min_importance IS NULL OR m.importance >= $min_importance)
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, distance, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(p:Project)
WITH m, distance, p
WHERE ($project_ids IS NULL OR p.id IN $project_ids)
OPTIONAL MATCH (m)-[:ABOUT]->(per:Person)
WITH m, distance, per
WHERE ($person_ids IS NULL OR per.id IN $person_ids)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
WITH DISTINCT m, distance, collect(DISTINCT s.id) AS strand_ids
{neighbour_clause}
RETURN m.id AS id, m.text AS text, m.type AS type, m.tags AS tags, m.importance AS importance, distance, strand_ids, {neighbour_return}
ORDER BY distance ASC\
"""

# Used when person_ids is provided: start from Person nodes via ABOUT edges.
# Bypasses the vector index so all memories linked to the specified persons are
# returned, not just those that happen to rank in the top-N by embedding distance.
# Ordered by importance DESC, strength DESC (distance is irrelevant for this path).
# Deduplication: aggregate on m after agent filter to collapse multiple Person rows;
# strand_ids collected in the same aggregation step to avoid re-fan-out.
_PERSON_SEARCH_QUERY_TEMPLATE = """\
MATCH (m:Memory)-[:ABOUT]->(per:Person)
WHERE per.id IN $person_ids
AND   (m.status IS NULL OR m.status = 'active')
AND   ($tags IS NULL OR ANY(t IN m.tags WHERE t IN $tags))
AND   ($min_importance IS NULL OR m.importance >= $min_importance)
OPTIONAL MATCH (m)-[:PRODUCED_BY]->(a:Agent)
WITH m, a
WHERE ($agent_ids IS NULL OR a.id IN $agent_ids)
OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
WITH DISTINCT m, collect(DISTINCT s.id) AS strand_ids
{neighbour_clause}
RETURN m.id AS id, m.text AS text, m.type AS type, m.tags AS tags, m.importance AS importance, coalesce(m.strength, 0.0) AS strength, strand_ids, {neighbour_return}
ORDER BY importance DESC, strength DESC
LIMIT $limit\
"""


def search_memories(session, req, query_embedding: list, neighbour_cap: int) -> list:
    """Run vector search with optional filters and graph expansion.

    Args:
        session: open neo4j Session
        req: SearchMemoryRequest (query, tags, agent_ids, project_ids, person_ids, limit, max_hops,
             traversal_direction, min_importance)
        query_embedding: pre-computed embedding for req.query
        neighbour_cap: max neighbours returned per traversal direction; total per hit
            is at most 3 × neighbour_cap (RELATED_TO + causes + effects)

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
        collect_parts.append(f"collect(DISTINCT n.id)[..{neighbour_cap}]")
    if direction in ("causes", "both"):
        collect_parts.append(f"collect(DISTINCT c.id)[..{neighbour_cap}]")
    if direction in ("effects", "both"):
        collect_parts.append(f"collect(DISTINCT e.id)[..{neighbour_cap}]")

    if collect_parts:
        neighbour_return = " + ".join(collect_parts) + " AS neighbours"
    else:
        neighbour_return = "[] AS neighbours"

    if req.person_ids:
        # Graph path: start from Person nodes, bypass vector index.
        query = _PERSON_SEARCH_QUERY_TEMPLATE.format(
            neighbour_clause=neighbour_clauses,
            neighbour_return=neighbour_return,
        )
        result = session.run(
            query,
            person_ids=req.person_ids,
            limit=req.limit,
            tags=req.tags,
            agent_ids=req.agent_ids,
            min_importance=req.min_importance,
        )
    else:
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
            person_ids=None,
            min_importance=req.min_importance,
        )

    min_score = req.min_score
    use_min_score = min_score is not None and not req.person_ids

    seen: set[str] = set()
    rows = []
    for record in result:
        rid = record["id"]
        if rid in seen:
            continue
        seen.add(rid)

        score = round(1.0 - record["distance"], 4) if "distance" in record.keys() else None

        if use_min_score and score is not None and score < min_score:
            continue

        rows.append(
            {
                "id": rid,
                "text": record["text"],
                "type": record["type"],
                "tags": record["tags"],
                "importance": record["importance"],
                "strand_ids": list(record["strand_ids"]),
                "neighbours": record["neighbours"],
                "score": score,
            }
        )
    return rows


def fetch_associated(
    session, memory_ids: list, cap: int, exclude_ids: set
) -> dict:
    """For each memory_id, fetch up to cap associated memories via RELATED_TO/LEADS_TO.

    Returns dict mapping memory_id -> list of associated dicts.
    Excludes any node whose id is in exclude_ids (primary hit dedup).
    """
    if not memory_ids or cap <= 0:
        return {mid: [] for mid in memory_ids}

    result = session.run(
        """
        UNWIND $ids AS src_id
        MATCH (m:Memory {id: src_id})-[r:RELATED_TO|LEADS_TO]->(n:Memory)
        WHERE (n.status IS NULL OR n.status = 'active')
          AND (n.ephemeral IS NULL OR n.ephemeral = false)
        RETURN src_id,
               n.id AS assoc_id, n.text AS text, n.type AS type,
               n.importance AS importance,
               coalesce(r.weight, 0.5) AS edge_weight
        ORDER BY src_id, edge_weight DESC
        """,
        ids=memory_ids,
    )
    # Note: only outgoing edges are followed. RELATED_TO is auto-linked in one
    # direction at ingest time, so results are intentionally asymmetric for that
    # edge type. LEADS_TO is always directional by design.

    grouped: dict = defaultdict(list)
    for record in result:
        src = record["src_id"]
        aid = record["assoc_id"]
        if aid in exclude_ids:
            continue
        if len(grouped[src]) >= cap:
            continue
        grouped[src].append({
            "id": aid,
            "text": record["text"],
            "type": record["type"],
            "importance": record["importance"],
            "edge_weight": round(record["edge_weight"], 4),
        })

    return {mid: grouped.get(mid, []) for mid in memory_ids}


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
        WHERE (m.status IS NULL OR m.status = 'active')
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH DISTINCT m, collect(s.id)[0] AS strand_id
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        ORDER BY m.importance DESC,
                 coalesce(m.strength, 0.0) DESC,
                 coalesce(m.reinforcement_count, 0) DESC,
                 coalesce(m.recall_count, 0) DESC,
                 m.created_at DESC
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
        WITH m, distance
        WHERE (m.status IS NULL OR m.status = 'active')
        OPTIONAL MATCH (m)-[:IN_STRAND]->(s:Strand)
        WITH DISTINCT m, collect(s.id)[0] AS strand_id, min(distance) AS dist
        RETURN m.id AS id, m.text AS text, m.type AS type,
               m.tags AS tags, m.importance AS importance,
               m.created_at AS created_at, strand_id
        ORDER BY dist ASC
        """,
        limit=limit,
        query_vec=topic_embedding,
    )
    topic = [_record_to_memory_dict(r) for r in topic_result if r["id"] not in core_ids]

    return {"core": core, "topic": topic}


def list_strands(session) -> list:
    """Return all Strand nodes with non-null name, ordered by category then name.

    Returns:
        List of dicts with keys: id, name, description, category
    """
    result = session.run(
        "MATCH (s:Strand) WHERE s.name IS NOT NULL "
        "RETURN s.id AS id, s.name AS name, "
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
    """Return all Person nodes with a non-null name, ordered by id."""
    result = session.run(
        "MATCH (p:Person) WHERE p.name IS NOT NULL "
        "RETURN p.id AS id, p.name AS name, "
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


def get_memory_for_update(session, memory_id: str) -> dict | None:
    """Return current fact and so_what for an active memory, or None if not found/active."""
    result = session.run(
        """
        MATCH (m:Memory {id: $id})
        WHERE (m.status IS NULL OR m.status = 'active')
        RETURN m.fact AS fact, m.so_what AS so_what
        """,
        id=memory_id,
    )
    record = result.single()
    if record is None:
        return None
    return {"fact": record["fact"], "so_what": record["so_what"]}


def update_memory(
    session,
    memory_id: str,
    patch_fields: dict,
    new_embedding: list | None,
    now: str,
) -> None:
    """In-place update of an active memory's fields.

    patch_fields must contain only the fields to update. person_ids and
    strand_ids (if present) are full replacements: existing edges are
    deleted and the new set is created.

    new_embedding must be provided when fact or so_what changed; it is
    written along with the recomputed text field (also in patch_fields).

    Raises ValueError if the memory is not found or not active.
    """
    # Build scalar SET clause (all fields except person_ids/strand_ids)
    scalar_keys = [k for k in patch_fields if k not in ("person_ids", "strand_ids")]
    if new_embedding is not None:
        scalar_keys.append("embedding")

    if scalar_keys or new_embedding is not None:
        set_parts = [f"m.{k} = ${k}" for k in scalar_keys if k in patch_fields]
        if new_embedding is not None:
            set_parts.append("m.embedding = $embedding")
        set_parts.append("m.updated_at = $updated_at")
        set_clause = ", ".join(set_parts)
        params = {k: patch_fields[k] for k in scalar_keys if k in patch_fields}
        params["id"] = memory_id
        params["updated_at"] = now
        if new_embedding is not None:
            params["embedding"] = new_embedding
        session.run(f"MATCH (m:Memory {{id: $id}}) SET {set_clause}", **params)

    # Replace person_ids: delete existing ABOUT→Person edges, recreate
    if "person_ids" in patch_fields:
        session.run(
            "MATCH (m:Memory {id: $id})-[r:ABOUT]->(p:Person) DELETE r",
            id=memory_id,
        )
        for person_id in patch_fields["person_ids"]:
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

    # Replace strand_ids: delete existing IN_STRAND edges, recreate
    if "strand_ids" in patch_fields:
        session.run(
            "MATCH (m:Memory {id: $id})-[r:IN_STRAND]->(s:Strand) DELETE r",
            id=memory_id,
        )
        for strand_id in patch_fields["strand_ids"]:
            session.run(
                """
                MATCH (s:Strand {id: $strand_id})
                WITH s
                MATCH (m:Memory {id: $memory_id})
                CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)
                """,
                strand_id=strand_id,
                memory_id=memory_id,
            )


def archive_memory(session, memory_id: str, now: str) -> None:
    """Set status=archived on an active memory.

    Raises ValueError if the memory is not found or not active.
    """
    result = session.run(
        """
        MATCH (m:Memory {id: $id})
        WHERE (m.status IS NULL OR m.status = 'active')
        SET m.status = 'archived', m.archived_at = $now
        RETURN m.id AS id
        """,
        id=memory_id,
        now=now,
    )
    if result.single() is None:
        raise ValueError(f"Memory {memory_id!r} not found or not active")


def restore_memory(session, memory_id: str) -> None:
    """Return an archived memory to active status.

    Raises ValueError if the memory is not found or not archived.
    Only archived memories can be restored; merged memories cannot.
    """
    result = session.run(
        """
        MATCH (m:Memory {id: $id})
        WHERE m.status = 'archived'
        SET m.status = 'active'
        REMOVE m.archived_at
        RETURN m.id AS id
        """,
        id=memory_id,
    )
    if result.single() is None:
        raise ValueError(f"Memory {memory_id!r} not found or not archived")


def merge_memory(
    session,
    source_id: str,
    target_id: str,
    strategy: str,
    default_edge_decay_rate: float = 0.005,
) -> None:
    """Merge source memory into target: rewire edges, mark source as merged.

    All ABOUT, IN_STRAND, LEADS_TO, and RELATED_TO edges from/to source are
    rewired to target, deduplicating on topology (not properties).  When the
    target already has the same edge, properties are reconciled deterministically:
    weight = max, activation_count = sum, last_activated_at = more recent,
    decay_rate = min (lower rate = more consolidated).

    strategy is accepted for API compatibility but only 'replace' semantics
    are implemented in v1.

    Raises ValueError if source or target is not found or not active.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    # Validate both nodes exist and are active
    check = session.run(
        """
        MATCH (src:Memory {id: $src_id})
        MATCH (tgt:Memory {id: $tgt_id})
        WHERE (src.status IS NULL OR src.status = 'active')
          AND (tgt.status IS NULL OR tgt.status = 'active')
        RETURN src.id AS src_id
        """,
        src_id=source_id,
        tgt_id=target_id,
    )
    if check.single() is None:
        raise ValueError(f"Source {source_id!r} or target {target_id!r} not found or not active")

    # Rewire ABOUT edges (to Person and Project)
    session.run(
        """
        MATCH (src:Memory {id: $src_id})-[r:ABOUT]->(x)
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (tgt)-[:ABOUT]->(x)
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
    )

    # Rewire IN_STRAND edges — MERGE on topology only, reconcile weight as max
    session.run(
        """
        MATCH (src:Memory {id: $src_id})-[r:IN_STRAND]->(s:Strand)
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (tgt)-[existing:IN_STRAND]->(s)
        ON CREATE SET existing.weight = coalesce(r.weight, 1.0)
        ON MATCH SET  existing.weight = CASE
                        WHEN coalesce(existing.weight, 1.0) >= coalesce(r.weight, 1.0)
                        THEN existing.weight
                        ELSE coalesce(r.weight, 1.0)
                      END
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
    )

    # Rewire outgoing LEADS_TO edges (source → effect)
    session.run(
        """
        MATCH (src:Memory {id: $src_id})-[r:LEADS_TO]->(e:Memory)
        WHERE e.id <> $tgt_id
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (tgt)-[:LEADS_TO]->(e)
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
    )

    # Rewire incoming LEADS_TO edges (cause → source)
    session.run(
        """
        MATCH (c:Memory)-[r:LEADS_TO]->(src:Memory {id: $src_id})
        WHERE c.id <> $tgt_id
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (c)-[:LEADS_TO]->(tgt)
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
    )

    # Rewire outgoing RELATED_TO edges — MERGE on topology, reconcile all properties
    session.run(
        """
        MATCH (src:Memory {id: $src_id})-[r:RELATED_TO]->(rel:Memory)
        WHERE rel.id <> $tgt_id
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (tgt)-[existing:RELATED_TO]->(rel)
        ON CREATE SET
            existing.weight            = coalesce(r.weight, 0.5),
            existing.activation_count  = coalesce(r.activation_count, 0),
            existing.last_activated_at = coalesce(r.last_activated_at, $now_iso),
            existing.decay_rate        = coalesce(r.decay_rate, $default_edge_decay_rate)
        ON MATCH SET
            existing.weight            = CASE
                                           WHEN coalesce(existing.weight, 0.5) >= coalesce(r.weight, 0.5)
                                           THEN existing.weight
                                           ELSE coalesce(r.weight, 0.5)
                                         END,
            existing.activation_count  = coalesce(existing.activation_count, 0)
                                         + coalesce(r.activation_count, 0),
            existing.last_activated_at = CASE
                                           WHEN existing.last_activated_at IS NULL
                                             THEN coalesce(r.last_activated_at, $now_iso)
                                           WHEN r.last_activated_at IS NULL
                                             THEN existing.last_activated_at
                                           WHEN r.last_activated_at > existing.last_activated_at
                                             THEN r.last_activated_at
                                           ELSE existing.last_activated_at
                                         END,
            existing.decay_rate        = CASE
                                           WHEN coalesce(existing.decay_rate, $default_edge_decay_rate)
                                                <= coalesce(r.decay_rate, $default_edge_decay_rate)
                                           THEN existing.decay_rate
                                           ELSE coalesce(r.decay_rate, $default_edge_decay_rate)
                                         END
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
        now_iso=now_iso,
        default_edge_decay_rate=default_edge_decay_rate,
    )

    # Rewire incoming RELATED_TO edges — same reconciliation, direction flipped
    session.run(
        """
        MATCH (rel:Memory)-[r:RELATED_TO]->(src:Memory {id: $src_id})
        WHERE rel.id <> $tgt_id
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (rel)-[existing:RELATED_TO]->(tgt)
        ON CREATE SET
            existing.weight            = coalesce(r.weight, 0.5),
            existing.activation_count  = coalesce(r.activation_count, 0),
            existing.last_activated_at = coalesce(r.last_activated_at, $now_iso),
            existing.decay_rate        = coalesce(r.decay_rate, $default_edge_decay_rate)
        ON MATCH SET
            existing.weight            = CASE
                                           WHEN coalesce(existing.weight, 0.5) >= coalesce(r.weight, 0.5)
                                           THEN existing.weight
                                           ELSE coalesce(r.weight, 0.5)
                                         END,
            existing.activation_count  = coalesce(existing.activation_count, 0)
                                         + coalesce(r.activation_count, 0),
            existing.last_activated_at = CASE
                                           WHEN existing.last_activated_at IS NULL
                                             THEN coalesce(r.last_activated_at, $now_iso)
                                           WHEN r.last_activated_at IS NULL
                                             THEN existing.last_activated_at
                                           WHEN r.last_activated_at > existing.last_activated_at
                                             THEN r.last_activated_at
                                           ELSE existing.last_activated_at
                                         END,
            existing.decay_rate        = CASE
                                           WHEN coalesce(existing.decay_rate, $default_edge_decay_rate)
                                                <= coalesce(r.decay_rate, $default_edge_decay_rate)
                                           THEN existing.decay_rate
                                           ELSE coalesce(r.decay_rate, $default_edge_decay_rate)
                                         END
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
        now_iso=now_iso,
        default_edge_decay_rate=default_edge_decay_rate,
    )

    # Create MERGED_INTO edge and mark source
    session.run(
        """
        MATCH (src:Memory {id: $src_id})
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (src)-[:MERGED_INTO]->(tgt)
        SET src.status = 'merged', src.superseded_by = $tgt_id
        """,
        src_id=source_id,
        tgt_id=target_id,
    )


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


def _apply_decay(current: float, rate: float, days: float, min_strength: float = 0.0) -> float:
    """Return decayed value clamped to [min_strength, 1]."""
    return max(min_strength, min(1.0, current * math.exp(-rate * days)))


def _apply_decay_modulated(
    current: float,
    base_rate: float,
    days: float,
    incoming_weight_sum: float,
    factor: float,
    cap: float,
    min_strength: float = 0.0,
) -> float:
    """Apply Ebbinghaus decay with edge-modulated rate.

    effective_rate = base_rate / min(1 + factor * incoming_weight_sum, cap)
    A node with more/stronger incoming edges decays slower (elaborative encoding).
    factor=0 disables modulation (effective_rate == base_rate).
    """
    modulation = max(min(1.0 + factor * incoming_weight_sum, cap), 1e-9)
    effective_rate = base_rate / modulation
    return _apply_decay(current, effective_rate, days, min_strength)


def decay_pass(
    session,
    now_naive: str,
    now_iso: str,
    min_strength: float = 0.0,
    node_ids: list[str] | None = None,
    edge_modulation_factor: float = 0.0,
    edge_modulation_cap: float = 10.0,
    dry_run: bool = False,
) -> dict:
    """Recompute and write strength for all Memory nodes and weight for all edges.

    Formula: new_value = current_value * exp(-effective_rate * days_since_anchor)
    Anchors: Memory.last_reinforced_at, edge.last_activated_at.
    After writing, resets anchors to now_iso so future inline calcs stay numerically stable.

    Memgraph does not support duration.between() or epochSeconds on datetime types, so
    the days computation is performed in Python after fetching the anchor timestamps.

    Args:
        now_naive: unused (kept for API compatibility); computation uses now_iso
        now_iso: full ISO string representing the current time, e.g. "2026-03-22T10:30:00+00:00"
        min_strength: floor for node strength after decay (default 0.0)
        node_ids: if provided, restrict node decay to this list of Memory ids
        edge_modulation_factor: multiplier controlling how much incoming edge weight slows decay;
            0.0 disables modulation (backward compatible default)
        edge_modulation_cap: maximum denominator for modulation (caps the slowdown effect)
        dry_run: if True, compute updates but do not write to the database

    Returns dict with keys: nodes_updated, edges_updated (int counts).
    """
    now = _parse_iso(now_iso)

    # --- Node decay ---
    # Build node scope filter
    node_filter = "AND m.id IN $node_ids" if node_ids is not None else ""

    node_rows = list(session.run(
        f"""
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
        {node_filter}
        OPTIONAL MATCH (pred:Memory)-[inc:RELATED_TO|LEADS_TO]->(m)
        WITH m, coalesce(sum(inc.weight), 0.0) AS incoming_weight_sum
        RETURN m.id AS id, m.strength AS strength,
               m.last_reinforced_at AS anchor, m.decay_rate AS rate,
               m.min_strength AS min_strength,
               incoming_weight_sum
        """,
        node_ids=node_ids if node_ids is not None else [],
    ))

    node_updates = []
    for row in node_rows:
        try:
            anchor = _parse_iso(row["anchor"])
        except (ValueError, TypeError):
            continue
        days = (now - anchor).total_seconds() / 86400.0
        node_floor = row["min_strength"] if row["min_strength"] is not None else min_strength
        node_updates.append({
            "id": row["id"],
            "new_val": _apply_decay_modulated(
                row["strength"], row["rate"], days,
                row["incoming_weight_sum"],
                edge_modulation_factor, edge_modulation_cap,
                node_floor,
            ),
        })

    if node_updates and not dry_run:
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

    if edge_updates and not dry_run:
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


def reinforce_memory(
    session,
    memory_id: str,
    strength_increment: float,
    edge_increment: float,
    co_recalled_ids: list[str],
    now_iso: str,
    consolidated_decay_rate: float | None = None,
) -> float:
    """Explicitly reinforce a memory node and its co-recalled edges.

    Updates last_reinforced_at (unlike recall_increment, which does not).
    On the first reinforcement (reinforcement_count == 0 before increment),
    switches decay_rate to consolidated_decay_rate if provided.
    Returns the new stored strength value (float).
    """
    result = session.run(
        """
        MATCH (m:Memory {id: $id})
        WITH m,
             coalesce(m.reinforcement_count, 0) AS pre_count
        SET m.reinforcement_count = pre_count + 1,
            m.last_reinforced_at = $now,
            m.strength = CASE
                WHEN coalesce(m.strength, m.importance / 5.0) + $increment >= 1.0
                THEN 1.0
                ELSE coalesce(m.strength, m.importance / 5.0) + $increment
            END,
            m.decay_rate = CASE
                WHEN $consolidated_rate IS NOT NULL AND pre_count = 0
                THEN $consolidated_rate
                ELSE m.decay_rate
            END
        RETURN m.strength AS strength
        """,
        id=memory_id,
        increment=strength_increment,
        now=now_iso,
        consolidated_rate=consolidated_decay_rate,
    )
    row = result.single()
    if row is None:
        raise ValueError(f"Memory not found: {memory_id}")
    new_strength = row["strength"]

    # Hebbian step — bump edges between this memory and co-recalled memories
    if co_recalled_ids:
        all_ids = [memory_id] + co_recalled_ids
        session.run(
            """
            UNWIND $all_ids AS src
            UNWIND $all_ids AS tgt
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
            all_ids=all_ids,
            edge_increment=edge_increment,
            now=now_iso,
        )

    return new_strength


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


def upsert_system_node(session, **kwargs) -> None:
    """Create or update the singleton System node with the given properties.

    Typical kwargs: last_short_rest_at="...", last_long_rest_at="..."
    """
    if not kwargs:
        return
    set_clause = ", ".join(f"sys.{k} = ${k}" for k in kwargs)
    session.run(
        f"""
        MERGE (sys:System {{id: "system"}})
        SET {set_clause}
        """,
        **kwargs,
    )


_MAINTENANCE_LOG_CAP = 100


def get_maintenance_log(session) -> list:
    """Return the maintenance audit log from the System node as a list of dicts.

    Returns a parsed list. Empty list if not set, null, or unparseable.
    System node is expected to be a singleton (id="system").
    """
    result = session.run(
        """
        OPTIONAL MATCH (sys:System {id: "system"})
        RETURN sys.maintenance_log AS maintenance_log
        """
    )
    record = result.single()
    if record is None:
        return []
    raw = record["maintenance_log"]
    if raw is None:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def append_maintenance_log(session, entry: dict) -> None:
    """Append an audit entry to the System node maintenance_log (capped at 100).

    Reads current log, appends entry, caps at _MAINTENANCE_LOG_CAP (oldest dropped),
    and writes back within the same session. entry must be JSON-serialisable.
    System node is expected to be a singleton (id="system").
    """
    existing = get_maintenance_log(session)
    existing.append(entry)
    if len(existing) > _MAINTENANCE_LOG_CAP:
        existing = existing[-_MAINTENANCE_LOG_CAP:]
    log_json = json.dumps(existing)
    session.run(
        """
        MERGE (sys:System {id: "system"})
        SET sys.maintenance_log = $log_json
        """,
        log_json=log_json,
    )


_OPERATION_LOG_CAP = 200


def get_operation_log(session) -> list:
    """Return the operation audit log from the System node as a list of dicts.

    Returns a parsed list. Empty list if not set, null, or unparseable.
    System node is expected to be a singleton (id="system").
    """
    result = session.run(
        """
        OPTIONAL MATCH (sys:System {id: "system"})
        RETURN sys.operation_log AS operation_log
        """
    )
    record = result.single()
    if record is None:
        return []
    raw = record["operation_log"]
    if raw is None:
        return []
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return []


def append_operation_log(session, entry: dict) -> None:
    """Append an audit entry to the System node operation_log (capped at 200).

    Reads current log, appends entry, caps at _OPERATION_LOG_CAP (oldest dropped),
    and writes back within the same session. entry must be JSON-serialisable.
    System node is expected to be a singleton (id="system").
    """
    existing = get_operation_log(session)
    existing.append(entry)
    if len(existing) > _OPERATION_LOG_CAP:
        existing = existing[-_OPERATION_LOG_CAP:]
    log_json = json.dumps(existing)
    session.run(
        """
        MERGE (sys:System {id: "system"})
        SET sys.operation_log = $log_json
        """,
        log_json=log_json,
    )


def short_rest(
    session,
    now_iso: str,
    recency_days: int,
    min_strength: float,
    edge_modulation_factor: float,
    edge_modulation_cap: float,
    dry_run: bool = False,
) -> dict:
    """Decay recently-active Memory nodes and their adjacent edges.

    Scope: nodes where recall_count > 0 OR last_used_at within recency_days days.
    Required fields (strength, last_reinforced_at, decay_rate) must be present.
    Edge scope: RELATED_TO and LEADS_TO edges between nodes in the scoped set.
    """
    now = _parse_iso(now_iso)

    node_rows = list(session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.last_reinforced_at IS NOT NULL AND m.decay_rate IS NOT NULL
        AND (
            (m.recall_count IS NOT NULL AND m.recall_count > 0)
            OR m.last_used_at IS NOT NULL
        )
        OPTIONAL MATCH (pred:Memory)-[inc:RELATED_TO|LEADS_TO]->(m)
        WITH m, coalesce(sum(inc.weight), 0.0) AS incoming_weight_sum
        RETURN m.id AS id, m.strength AS strength,
               m.last_reinforced_at AS anchor, m.decay_rate AS rate,
               m.last_used_at AS last_used_at, m.recall_count AS recall_count,
               m.min_strength AS min_strength,
               incoming_weight_sum
        """
    ))

    in_scope_ids = []
    node_updates = []

    for row in node_rows:
        # Check scope: recall_count > 0 OR last_used_at within recency window
        in_scope = False
        if row["recall_count"] and row["recall_count"] > 0:
            in_scope = True
        if not in_scope and row["last_used_at"]:
            try:
                lu = _parse_iso(row["last_used_at"])
                if (now - lu).total_seconds() / 86400.0 <= recency_days:
                    in_scope = True
            except (ValueError, TypeError):
                pass

        if not in_scope:
            continue

        in_scope_ids.append(row["id"])

        try:
            anchor = _parse_iso(row["anchor"])
        except (ValueError, TypeError):
            continue

        days = (now - anchor).total_seconds() / 86400.0
        node_floor = row["min_strength"] if row["min_strength"] is not None else min_strength
        new_val = _apply_decay_modulated(
            row["strength"], row["rate"], days,
            row["incoming_weight_sum"],
            edge_modulation_factor, edge_modulation_cap,
            node_floor,
        )
        node_updates.append({"id": row["id"], "new_val": new_val})

    if node_updates and not dry_run:
        session.run(
            """
            UNWIND $updates AS upd
            MATCH (m:Memory {id: upd.id})
            SET m.strength = upd.new_val, m.last_reinforced_at = $now_iso
            """,
            updates=node_updates,
            now_iso=now_iso,
        )

    # Edge decay — only edges between in-scope nodes
    edge_updates = []
    if in_scope_ids:
        edge_rows = list(session.run(
            """
            MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
            WHERE src.id IN $ids AND tgt.id IN $ids
            AND r.weight IS NOT NULL AND r.last_activated_at IS NOT NULL AND r.decay_rate IS NOT NULL
            RETURN id(r) AS rid, r.weight AS weight,
                   r.last_activated_at AS anchor, r.decay_rate AS rate
            """,
            ids=in_scope_ids,
        ))

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

        if edge_updates and not dry_run:
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

    if not dry_run:
        upsert_system_node(session, last_short_rest_at=now_iso)
        append_maintenance_log(session, {
            "operation": "short_rest",
            "ran_at": now_iso,
            "dry_run": False,
            "nodes_affected": len(node_updates),
            "edges_affected": len(edge_updates),
            "edges_discovered": 0,
            "edges_pruned": 0,
        })

    return {
        "nodes_decayed": len(node_updates),
        "edges_decayed": len(edge_updates),
        "dry_run": dry_run,
    }


def long_rest(
    session,
    now_iso: str,
    min_strength: float,
    edge_modulation_factor: float,
    edge_modulation_cap: float,
    rediscovery_strength_threshold: float,
    edge_hard_prune_floor: float,
    edge_hard_prune_min_days: int,
    edge_decay_rate: float,
    dry_run: bool = False,
    prune: bool = False,
) -> dict:
    """Full maintenance pass: decay all nodes/edges, edge rediscovery, optional prune.

    Steps:
    1. Full decay pass on all nodes + edges (edge-modulated)
    2. Edge rediscovery: for strong nodes, vector search and MERGE new RELATED_TO edges
    3. Weak-edge candidate identification (prune if prune=True and not dry_run)
    4. Update System node last_long_rest_at (skipped when dry_run)
    """
    now = _parse_iso(now_iso)

    # Step 1: Full decay pass
    decay_result = decay_pass(
        session, "", now_iso, min_strength,
        node_ids=None,
        edge_modulation_factor=edge_modulation_factor,
        edge_modulation_cap=edge_modulation_cap,
        dry_run=dry_run,
    )
    nodes_decayed = decay_result["nodes_updated"]
    edges_decayed = decay_result["edges_updated"]

    # Step 2: Edge rediscovery — nodes with strength >= threshold
    strong_nodes = list(session.run(
        """
        MATCH (m:Memory)
        WHERE m.strength IS NOT NULL AND m.strength >= $threshold
        AND m.embedding IS NOT NULL AND size(m.embedding) > 0
        RETURN m.id AS id, m.embedding AS embedding
        """,
        threshold=rediscovery_strength_threshold,
    ))

    edges_discovered = 0
    for node in strong_nodes:
        if dry_run:
            # Dry-run: count edges that would be discovered
            result = session.run(
                """
                CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                YIELD node AS candidate, distance
                WITH candidate, distance
                WHERE candidate.id <> $src_id AND distance < $max_distance
                OPTIONAL MATCH (src:Memory {id: $src_id})-[existing:RELATED_TO]->(candidate)
                WITH existing
                WHERE existing IS NULL
                RETURN count(*) AS would_discover
                """,
                k=_AUTO_RELATED_K,
                query_vec=node["embedding"],
                src_id=node["id"],
                max_distance=_AUTO_RELATED_MAX_DISTANCE,
            )
            row = result.single()
            if row:
                edges_discovered += row["would_discover"] or 0
        else:
            session.run(
                """
                CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                YIELD node AS candidate, distance
                WITH candidate, distance
                WHERE candidate.id <> $src_id AND distance < $max_distance
                MATCH (src:Memory {id: $src_id})
                OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
                WITH src, candidate, existing, distance
                WHERE existing IS NULL
                MERGE (src)-[r:RELATED_TO]->(candidate)
                ON CREATE SET r.weight = 1.0 - distance,
                              r.activation_count = 0,
                              r.last_activated_at = $now_iso,
                              r.decay_rate = $edge_decay_rate
                """,
                k=_AUTO_RELATED_K,
                query_vec=node["embedding"],
                src_id=node["id"],
                max_distance=_AUTO_RELATED_MAX_DISTANCE,
                now_iso=now_iso,
                edge_decay_rate=edge_decay_rate,
            )

    if not dry_run:
        # Invariant: activation_count=0 on a RELATED_TO edge means it was created
        # (ON CREATE) but never subsequently reinforced. long_rest is the only writer
        # of these edges during a run, and now_iso is unique per API call, so the
        # conjunction (last_activated_at = now_iso AND activation_count = 0) exactly
        # identifies edges written by this invocation. If future code initialises
        # activation_count=0 on RELATED_TO edges via another path, this count will
        # need a more specific sentinel (e.g. a run-id property).
        count_row = session.run(
            """
            MATCH ()-[r:RELATED_TO]->()
            WHERE r.last_activated_at = $now_iso AND r.activation_count = 0
            RETURN count(r) AS n
            """,
            now_iso=now_iso,
        ).single()
        edges_discovered = count_row["n"] if count_row else 0

    # Step 3: Weak-edge pruning
    prune_rows = list(session.run(
        """
        MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory)
        WHERE r.weight IS NOT NULL AND r.weight < $floor
        AND r.last_activated_at IS NOT NULL
        RETURN id(r) AS rid, r.last_activated_at AS last_activated
        """,
        floor=edge_hard_prune_floor,
    ))

    prune_candidates = []
    for row in prune_rows:
        try:
            last_act = _parse_iso(row["last_activated"])
        except (ValueError, TypeError):
            continue
        if (now - last_act).total_seconds() / 86400.0 >= edge_hard_prune_min_days:
            prune_candidates.append(row["rid"])

    edges_pruned = len(prune_candidates)
    if prune_candidates and prune and not dry_run:
        session.run(
            """
            UNWIND $rids AS rid
            MATCH ()-[r:RELATED_TO|LEADS_TO]->()
            WHERE id(r) = rid
            DELETE r
            """,
            rids=prune_candidates,
        )

    # Step 4: Update System node
    if not dry_run:
        upsert_system_node(session, last_long_rest_at=now_iso)
        append_maintenance_log(session, {
            "operation": "long_rest",
            "ran_at": now_iso,
            "dry_run": False,
            "nodes_affected": nodes_decayed,
            "edges_affected": edges_decayed,
            "edges_discovered": edges_discovered,
            "edges_pruned": edges_pruned,
        })

    return {
        "nodes_decayed": nodes_decayed,
        "edges_decayed": edges_decayed,
        "edges_discovered": edges_discovered,
        "edges_pruned": edges_pruned,
        "dry_run": dry_run,
    }


def get_system_timestamps(session) -> dict:
    """Return last_short_rest_at and last_long_rest_at from the System node.

    Returns dict with keys last_short_rest_at, last_long_rest_at.
    Values are ISO strings or None if not set.
    """
    result = session.run(
        """
        OPTIONAL MATCH (sys:System {id: "system"})
        RETURN sys.last_short_rest_at AS last_short_rest_at,
               sys.last_long_rest_at AS last_long_rest_at
        """
    )
    record = result.single()
    if record is None:
        return {"last_short_rest_at": None, "last_long_rest_at": None}
    return {
        "last_short_rest_at": record["last_short_rest_at"],
        "last_long_rest_at": record["last_long_rest_at"],
    }


def maintenance_stats(
    session,
    now_iso: str,
    edge_prune_threshold: float,
    short_rest_recency_days: int,
    long_rest_recency_days: int,
) -> dict:
    """Return a health snapshot of the memory graph for monitoring.

    edge_prune_threshold is used for both below_prune_floor (nodes) and weak_count (edges).
    Pass settings.edge_hard_prune_floor (not edge_prune_threshold) from the endpoint.
    """
    now = _parse_iso(now_iso)

    # Node stats — fetch all strengths
    node_rows = list(session.run(
        "MATCH (m:Memory) WHERE m.strength IS NOT NULL RETURN m.strength AS s"
    ))
    strengths = [r["s"] for r in node_rows]
    total_nodes = len(strengths)
    mean_strength = sum(strengths) / total_nodes if strengths else 0.0
    sorted_s = sorted(strengths)
    if sorted_s:
        n = len(sorted_s)
        median_strength = sorted_s[n // 2] if n % 2 else (sorted_s[n // 2 - 1] + sorted_s[n // 2]) / 2.0
    else:
        median_strength = 0.0
    below_prune_floor = sum(1 for s in strengths if s < edge_prune_threshold)
    at_max_strength = sum(1 for s in strengths if s >= 1.0)

    # Edge stats — fetch all weights
    edge_rows = list(session.run(
        "MATCH (src:Memory)-[r:RELATED_TO|LEADS_TO]->(tgt:Memory) "
        "WHERE r.weight IS NOT NULL RETURN r.weight AS w"
    ))
    weights = [r["w"] for r in edge_rows]
    total_edges = len(weights)
    mean_weight = sum(weights) / total_edges if weights else 0.0
    weak_count = sum(1 for w in weights if w < edge_prune_threshold)

    # System timestamps + overdue flags
    ts = get_system_timestamps(session)
    last_short = ts["last_short_rest_at"]
    last_long = ts["last_long_rest_at"]

    def _is_overdue(ts_str: str | None, days: int) -> bool:
        if ts_str is None:
            return True
        try:
            last = _parse_iso(ts_str)
            return (now - last).total_seconds() / 86400.0 > days
        except (ValueError, TypeError):
            return True

    return {
        "nodes": {
            "total": total_nodes,
            "mean_strength": round(mean_strength, 4),
            "median_strength": round(median_strength, 4),
            "below_prune_floor": below_prune_floor,
            "at_max_strength": at_max_strength,
        },
        "edges": {
            "total": total_edges,
            "mean_weight": round(mean_weight, 4),
            "weak_count": weak_count,
        },
        "maintenance": {
            "last_short_rest_at": last_short,
            "last_long_rest_at": last_long,
            "short_rest_overdue": _is_overdue(last_short, short_rest_recency_days),
            "long_rest_overdue": _is_overdue(last_long, long_rest_recency_days),
        },
    }


def find_duplicate_memory(
    session,
    fact: str,
    embedding: list[float],
    threshold: float,
) -> str | None:
    """Return the id of an existing active Memory with identical or near-identical fact.

    Checks in order:
    1. Exact case-insensitive match on the 'fact' field.
    2. Vector similarity — nearest neighbour with cosine distance <= threshold.

    Returns None if no duplicate is found.
    Excludes merged and archived nodes from both checks.
    """
    # Step 1: exact match
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE toLower(m.fact) = toLower($fact)
          AND (m.status IS NULL OR m.status = 'active')
        RETURN m.id AS id
        LIMIT 1
        """,
        fact=fact,
    )
    record = result.single()
    if record:
        return record["id"]

    # Step 2: vector similarity (only if exact match missed)
    result = session.run(
        """
        CALL vector_search.search("mem_embedding_idx", 1, $query_vec)
        YIELD node, distance
        WITH node, distance
        WHERE (node.status IS NULL OR node.status = 'active')
          AND distance <= $threshold
        RETURN node.id AS id
        LIMIT 1
        """,
        query_vec=embedding,
        threshold=threshold,
    )
    record = result.single()
    if record:
        return record["id"]

    return None
