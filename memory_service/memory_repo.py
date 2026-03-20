# memory_service/memory_repo.py
#
# Repository layer: all Cypher operations for the /memory endpoint.
# All functions receive an already-open neo4j.Session; callers own the session lifecycle.

_AUTO_RELATED_K = 5
_AUTO_RELATED_MAX_DISTANCE = 0.5


def add_memory(session, req, memory_id: str, embedding: list, now: str) -> None:
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
            text: $text,
            type: $type,
            tags: $tags,
            importance: $importance,
            created_at: $created_at,
            last_used_at: $last_used_at,
            embedding: $embedding
        })
        CREATE (m)-[:PRODUCED_BY]->(a)
        """,
        agent_id=req.agent_id,
        id=memory_id,
        text=req.text,
        type=req.type.value,
        tags=req.tags,
        importance=req.importance,
        created_at=now,
        last_used_at=now,
        embedding=embedding,
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
        req: SearchMemoryRequest (query, tags, agent_ids, project_ids, limit, max_hops)
        query_embedding: pre-computed embedding for req.query

    Returns:
        List of dicts with keys: id, text, type, tags, importance, neighbours
    """
    if req.max_hops == 0:
        neighbour_clause = ""
        neighbour_return = "[] AS neighbours"
    else:
        neighbour_clause = f"OPTIONAL MATCH (m)-[:RELATED_TO*1..{req.max_hops}]->(n:Memory)"
        neighbour_return = "collect(DISTINCT n.id) AS neighbours"

    query = _SEARCH_QUERY_TEMPLATE.format(
        neighbour_clause=neighbour_clause,
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
