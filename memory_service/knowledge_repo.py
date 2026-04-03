# memory_service/knowledge_repo.py
#
# Repository layer: all Cypher operations for the /knowledge endpoint.
# All functions receive an already-open neo4j.Session; callers own the session lifecycle.
#
# ADR-001: this file must NOT import from memory_repo. Cross-layer edges live exclusively
# in knowledge_bridge.py.


# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------


def upsert_framework(session, req, now: str) -> dict:
    """MERGE Framework on id; SET all properties on CREATE only."""
    result = session.run(
        """
        MERGE (f:Framework {id: $id})
        ON CREATE SET
            f.name = $name,
            f.version = $version,
            f.description = $description,
            f.created_at = $created_at
        RETURN f.id AS id, f.name AS name, f.version AS version,
               f.description AS description, f.created_at AS created_at
        """,
        id=req.id,
        name=req.name,
        version=req.version,
        description=req.description,
        created_at=now,
    )
    return dict(result.single())


def get_framework(session, framework_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (f:Framework {id: $id})
        RETURN f.id AS id, f.name AS name, f.version AS version,
               f.description AS description, f.created_at AS created_at
        """,
        id=framework_id,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------


def upsert_control(session, req, embedding: list[float], now: str) -> dict:
    """MERGE Control; optionally create CONTAINS edge from parent Control."""
    result = session.run(
        """
        MERGE (c:Control {id: $id})
        ON CREATE SET
            c.name = $name,
            c.description = $description,
            c.framework_id = $framework_id,
            c.embedding = $embedding,
            c.created_at = $created_at
        RETURN c.id AS id, c.name AS name, c.description AS description,
               c.framework_id AS framework_id, c.created_at AS created_at
        """,
        id=req.id,
        name=req.name,
        description=req.description,
        framework_id=req.framework_id,
        embedding=embedding,
        created_at=now,
    )
    record = dict(result.single())

    if req.parent_id:
        session.run(
            """
            MATCH (parent:Control {id: $parent_id}), (child:Control {id: $child_id})
            MERGE (parent)-[:CONTAINS]->(child)
            """,
            parent_id=req.parent_id,
            child_id=req.id,
        )

    return record


def get_control(session, control_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (c:Control {id: $id})
        RETURN c.id AS id, c.name AS name, c.description AS description,
               c.framework_id AS framework_id, c.created_at AS created_at
        """,
        id=control_id,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# Norm
# ---------------------------------------------------------------------------


def upsert_norm(session, req, embedding: list[float], now: str) -> dict:
    """MERGE Norm; optionally create IMPLEMENTS (→Control) and SOURCED_FROM (→Document)."""
    result = session.run(
        """
        MERGE (n:Norm {id: $id})
        ON CREATE SET
            n.name = $name,
            n.text = $text,
            n.status = $status,
            n.effective_date = $effective_date,
            n.embedding = $embedding,
            n.created_at = $created_at
        RETURN n.id AS id, n.name AS name, n.text AS text, n.status AS status,
               n.effective_date AS effective_date, n.created_at AS created_at
        """,
        id=req.id,
        name=req.name,
        text=req.text,
        status=req.status,
        effective_date=req.effective_date,
        embedding=embedding,
        created_at=now,
    )
    record = dict(result.single())

    if req.control_id:
        session.run(
            """
            MATCH (n:Norm {id: $norm_id}), (c:Control {id: $control_id})
            MERGE (n)-[:IMPLEMENTS]->(c)
            """,
            norm_id=req.id,
            control_id=req.control_id,
        )

    if req.doc_id:
        session.run(
            """
            MATCH (n:Norm {id: $norm_id}), (d:Document {id: $doc_id})
            MERGE (n)-[:SOURCED_FROM]->(d)
            """,
            norm_id=req.id,
            doc_id=req.doc_id,
        )

    return record


def get_norm(session, norm_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (n:Norm {id: $id})
        RETURN n.id AS id, n.name AS name, n.text AS text, n.status AS status,
               n.effective_date AS effective_date, n.created_at AS created_at
        """,
        id=norm_id,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def upsert_document(session, req, now: str) -> dict:
    """MERGE Document on id. Documents carry no embedding — chunks hold the vectors."""
    result = session.run(
        """
        MERGE (d:Document {id: $id})
        ON CREATE SET
            d.title = $title,
            d.doc_type = $doc_type,
            d.source_url = $source_url,
            d.created_at = $created_at
        RETURN d.id AS id, d.title AS title, d.doc_type AS doc_type,
               d.source_url AS source_url, d.created_at AS created_at
        """,
        id=req.id,
        title=req.title,
        doc_type=req.doc_type,
        source_url=req.source_url,
        created_at=now,
    )
    return dict(result.single())


def get_document(session, doc_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (d:Document {id: $id})
        RETURN d.id AS id, d.title AS title, d.doc_type AS doc_type,
               d.source_url AS source_url, d.created_at AS created_at
        """,
        id=doc_id,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# Chunk
# ---------------------------------------------------------------------------


def upsert_chunk(session, req, embedding: list[float], now: str) -> dict:
    """MERGE Chunk; create HAS_CHUNK (Document→Chunk) and optionally HAS_NEXT (prev→this)."""
    result = session.run(
        """
        MERGE (ch:Chunk {id: $id})
        ON CREATE SET
            ch.text = $text,
            ch.sequence = $sequence,
            ch.doc_id = $doc_id,
            ch.embedding = $embedding,
            ch.created_at = $created_at
        RETURN ch.id AS id, ch.text AS text, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.created_at AS created_at
        """,
        id=req.id,
        text=req.text,
        sequence=req.sequence,
        doc_id=req.doc_id,
        embedding=embedding,
        created_at=now,
    )
    record = dict(result.single())

    session.run(
        """
        MATCH (d:Document {id: $doc_id}), (ch:Chunk {id: $chunk_id})
        MERGE (d)-[:HAS_CHUNK]->(ch)
        """,
        doc_id=req.doc_id,
        chunk_id=req.id,
    )

    if req.prev_chunk_id:
        session.run(
            """
            MATCH (prev:Chunk {id: $prev_id}), (curr:Chunk {id: $curr_id})
            MERGE (prev)-[:HAS_NEXT]->(curr)
            """,
            prev_id=req.prev_chunk_id,
            curr_id=req.id,
        )

    return record


def get_chunk(session, chunk_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (ch:Chunk {id: $id})
        RETURN ch.id AS id, ch.text AS text, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.created_at AS created_at
        """,
        id=chunk_id,
    )
    record = result.single()
    return dict(record) if record else None
