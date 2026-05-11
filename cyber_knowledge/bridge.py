# memory_service/knowledge_bridge.py
#
# ADR-001 Guardrail 3: this is the ONLY module that imports from both
# memory_repo and knowledge_repo. All cross-layer Cypher lives here.
# Called from routes in main.py — never imported by memory_repo or knowledge_repo.


def validate_controls(session, control_ids: list[str]) -> list[str]:
    """Return control_ids that do NOT exist in the graph.
    Callers raise HTTP 400 if the returned list is non-empty.
    """
    if not control_ids:
        return []
    result = session.run(
        """
        UNWIND $control_ids AS cid
        OPTIONAL MATCH (c:Control {id: cid})
        WITH cid, c
        WHERE c IS NULL
        RETURN cid AS missing_id
        """,
        control_ids=control_ids,
    )
    return [r["missing_id"] for r in result]


def validate_documents(session, doc_ids: list[str]) -> list[str]:
    """Return doc_ids that do NOT exist in the graph.
    Callers raise HTTP 400 if the returned list is non-empty.
    """
    if not doc_ids:
        return []
    result = session.run(
        """
        UNWIND $doc_ids AS did
        OPTIONAL MATCH (d:Document {id: did})
        WITH did, d
        WHERE d IS NULL
        RETURN did AS missing_id
        """,
        doc_ids=doc_ids,
    )
    return [r["missing_id"] for r in result]


def link_controls(
    session,
    memory_id: str,
    control_ids: list[str],
    relationship_type: str | None,
    org_id: str | None,
) -> None:
    """MERGE ABOUT_CONTROL edges from Memory to each Control.
    Silently skips control_ids that do not exist (existence pre-validated by validate_controls).
    """
    for control_id in control_ids:
        session.run(
            """
            MATCH (m:Memory {id: $memory_id})
            MATCH (c:Control {id: $control_id})
            MERGE (m)-[r:ABOUT_CONTROL]->(c)
            ON CREATE SET
                r.relationship_type = $relationship_type,
                r.org_id            = $org_id
            """,
            memory_id=memory_id,
            control_id=control_id,
            relationship_type=relationship_type,
            org_id=org_id,
        )


def link_documents(session, memory_id: str, doc_ids: list[str]) -> None:
    """MERGE CITES_DOC edges from Memory to each Document.
    Silently skips doc_ids that do not exist (existence pre-validated by validate_documents).
    """
    for doc_id in doc_ids:
        session.run(
            """
            MATCH (m:Memory {id: $memory_id})
            MATCH (d:Document {id: $doc_id})
            MERGE (m)-[:CITES_DOC]->(d)
            """,
            memory_id=memory_id,
            doc_id=doc_id,
        )


def replace_control_edges(
    session,
    memory_id: str,
    control_ids: list[str],
    relationship_type: str | None,
    org_id: str | None,
) -> None:
    """Delete all ABOUT_CONTROL edges from this Memory, then recreate for control_ids."""
    session.run(
        "MATCH (m:Memory {id: $memory_id})-[r:ABOUT_CONTROL]->(:Control) DELETE r",
        memory_id=memory_id,
    )
    for control_id in control_ids:
        session.run(
            """
            MATCH (m:Memory {id: $memory_id})
            MATCH (c:Control {id: $control_id})
            MERGE (m)-[r:ABOUT_CONTROL]->(c)
            ON CREATE SET
                r.relationship_type = $relationship_type,
                r.org_id            = $org_id
            """,
            memory_id=memory_id,
            control_id=control_id,
            relationship_type=relationship_type,
            org_id=org_id,
        )


def replace_doc_edges(session, memory_id: str, doc_ids: list[str]) -> None:
    """Delete all CITES_DOC edges from this Memory, then recreate for doc_ids."""
    session.run(
        "MATCH (m:Memory {id: $memory_id})-[r:CITES_DOC]->(:Document) DELETE r",
        memory_id=memory_id,
    )
    for doc_id in doc_ids:
        session.run(
            """
            MATCH (m:Memory {id: $memory_id})
            MATCH (d:Document {id: $doc_id})
            MERGE (m)-[:CITES_DOC]->(d)
            """,
            memory_id=memory_id,
            doc_id=doc_id,
        )


def rewire_cross_layer_edges(session, source_id: str, target_id: str) -> None:
    """Rewire ABOUT_CONTROL and CITES_DOC edges from source Memory to target Memory.
    Called by merge_memory route after memory_repo.merge_memory completes.
    ON CREATE only for properties — if target already has the edge, keep target's properties.
    """
    session.run(
        """
        MATCH (src:Memory {id: $src_id})-[r:ABOUT_CONTROL]->(c:Control)
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (tgt)-[existing:ABOUT_CONTROL]->(c)
        ON CREATE SET
            existing.relationship_type = r.relationship_type,
            existing.org_id            = r.org_id
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
    )
    session.run(
        """
        MATCH (src:Memory {id: $src_id})-[r:CITES_DOC]->(d:Document)
        MATCH (tgt:Memory {id: $tgt_id})
        MERGE (tgt)-[:CITES_DOC]->(d)
        DELETE r
        """,
        src_id=source_id,
        tgt_id=target_id,
    )


def hydrate_controls_and_documents(
    session,
    memory_ids: list[str],
) -> dict[str, dict]:
    """For each memory_id, return its linked controls and documents.

    Returns: {memory_id: {"controls": [...], "documents": [...]}}

    NOTE: collect(DISTINCT {...}) with nullable OPTIONAL MATCH nodes produces dicts
    with all-null values when no edges exist. Filter these out (id IS None) before
    placing in MemoryHit.
    """
    if not memory_ids:
        return {}
    result = session.run(
        """
        UNWIND $memory_ids AS mid
        MATCH (m:Memory {id: mid})
        OPTIONAL MATCH (m)-[r:ABOUT_CONTROL]->(c:Control)
        OPTIONAL MATCH (m)-[:CITES_DOC]->(d:Document)
        RETURN mid,
               collect(DISTINCT {id: c.id, name: c.name, relationship_type: r.relationship_type, org_id: r.org_id}) AS controls,
               collect(DISTINCT {id: d.id, title: d.title}) AS documents
        """,
        memory_ids=memory_ids,
    )
    hydration = {}
    for record in result:
        mid = record["mid"]
        controls = [c for c in record["controls"] if c.get("id") is not None]
        documents = [d for d in record["documents"] if d.get("id") is not None]
        hydration[mid] = {"controls": controls, "documents": documents}
    return hydration
