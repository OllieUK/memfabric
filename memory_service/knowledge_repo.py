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
    """MERGE Framework on id; SET all properties ON CREATE only.
    If parent_id is set, creates CONTAINS edge from parent Framework to this node.
    """
    result = session.run(
        """
        MERGE (f:Framework {id: $id})
        ON CREATE SET
            f.name = $name,
            f.version = $version,
            f.description = $description,
            f.level = $level,
            f.body = $body,
            f.created_at = $created_at
        RETURN f.id AS id, f.name AS name, f.version AS version,
               f.description AS description, f.level AS level,
               f.body AS body, f.created_at AS created_at
        """,
        id=req.id,
        name=req.name,
        version=req.version,
        description=req.description,
        level=req.level,
        body=req.body,
        created_at=now,
    )
    record = dict(result.single())

    if req.parent_id:
        session.run(
            """
            MATCH (parent:Framework {id: $parent_id}), (child:Framework {id: $child_id})
            MERGE (parent)-[:CONTAINS]->(child)
            """,
            parent_id=req.parent_id,
            child_id=req.id,
        )

    return record


def get_framework(session, framework_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (f:Framework {id: $id})
        RETURN f.id AS id, f.name AS name, f.version AS version,
               f.description AS description, f.level AS level,
               f.body AS body, f.created_at AS created_at
        """,
        id=framework_id,
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


# ---------------------------------------------------------------------------
# Search functions (vector search over embeddings)
# ---------------------------------------------------------------------------


def search_frameworks(
    session,
    query_embedding: list[float],
    limit: int,
    framework_id: str | None,
) -> list[dict]:
    """Vector search over framework_embedding_idx (Framework nodes with body text).
    Returns list of dicts: {id, name, level, body, created_at, distance}.
    NOTE: vector_search returns up to $limit nodes before any filter is applied.
    framework_id filter is not supported in MVP — pass None.
    """
    result = session.run(
        """
        CALL vector_search.search("framework_embedding_idx", $limit, $query_vec)
        YIELD node AS f, distance
        RETURN f.id AS id, f.name AS name, f.level AS level,
               f.body AS body, f.created_at AS created_at,
               distance
        ORDER BY distance ASC
        """,
        limit=limit,
        query_vec=query_embedding,
    )
    return [dict(r) for r in result]


def search_chunks(
    session,
    query_embedding: list[float],
    limit: int,
    doc_id: str | None,
) -> list[dict]:
    """Vector search over chunk_embedding_idx.
    Returns list of dicts: {id, text, sequence, doc_id, created_at, distance}.
    No recall_count increment.
    NOTE: Same post-index filter caveat as search_controls.
    """
    result = session.run(
        """
        CALL vector_search.search("chunk_embedding_idx", $limit, $query_vec)
        YIELD node AS ch, distance
        WITH ch, distance
        WHERE ($doc_id IS NULL OR ch.doc_id = $doc_id)
        RETURN ch.id AS id, ch.text AS text, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.created_at AS created_at,
               distance
        ORDER BY distance ASC
        """,
        limit=limit,
        query_vec=query_embedding,
        doc_id=doc_id,
    )
    return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# List functions (enumerate all nodes)
# ---------------------------------------------------------------------------


def list_norms(session) -> list[dict]:
    """Return all Norm nodes, ordered by name.
    Returns list of dicts: {id, name, text, status, effective_date, created_at}.
    """
    result = session.run(
        """
        MATCH (n:Norm)
        RETURN n.id AS id, n.name AS name, n.text AS text, n.status AS status,
               n.effective_date AS effective_date, n.created_at AS created_at
        ORDER BY n.name ASC
        """
    )
    return [dict(r) for r in result]


def list_documents(session) -> list[dict]:
    """Return all Document nodes, ordered by title.
    Returns list of dicts: {id, title, doc_type, source_url, created_at}.
    """
    result = session.run(
        """
        MATCH (d:Document)
        RETURN d.id AS id, d.title AS title, d.doc_type AS doc_type,
               d.source_url AS source_url, d.created_at AS created_at
        ORDER BY d.title ASC
        """
    )
    return [dict(r) for r in result]


def create_supports_edge_framework(
    session,
    chunk_id: str,
    framework_id: str,
    confidence: float,
    status: str,
    now: str,
) -> dict | None:
    """MERGE SUPPORTS edge Chunk→Framework; SET all properties ON CREATE only.

    Returns {chunk_id, framework_id, confidence, status, created_at}.
    Returns None if either Chunk or Framework node does not exist.
    Callers must check for None and raise HTTP 404.
    """
    result = session.run(
        """
        MATCH (ch:Chunk {id: $chunk_id}), (f:Framework {id: $framework_id})
        MERGE (ch)-[s:SUPPORTS]->(f)
        ON CREATE SET
            s.confidence  = $confidence,
            s.status      = $status,
            s.created_at  = $created_at
        RETURN ch.id AS chunk_id, f.id AS framework_id,
               s.confidence AS confidence, s.status AS status,
               s.created_at AS created_at
        """,
        chunk_id=chunk_id,
        framework_id=framework_id,
        confidence=confidence,
        status=status,
        created_at=now,
    )
    record = result.single()
    if record is None:
        return None
    return dict(record)


def get_chunks_for_framework(session, framework_id: str) -> list[dict]:
    """Return all Chunk nodes with a SUPPORTS edge to this Framework,
    ordered by confidence DESC.

    Returns list of dicts: {id, text, sequence, doc_id, created_at, confidence, status}.
    """
    result = session.run(
        """
        MATCH (ch:Chunk)-[s:SUPPORTS]->(f:Framework {id: $framework_id})
        RETURN ch.id AS id, ch.text AS text, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.created_at AS created_at,
               s.confidence AS confidence, s.status AS status
        ORDER BY s.confidence DESC
        """,
        framework_id=framework_id,
    )
    return [dict(r) for r in result]


def list_incomplete_jurisdictions(session) -> dict:
    """Return Norms with no APPLIES_IN edges.
    Returns:
      {
        "norms_without_jurisdiction": [{"id": ..., "name": ...}, ...],
      }
    """
    norms_result = session.run(
        """
        MATCH (n:Norm)
        WHERE NOT (n)-[:APPLIES_IN]->(:Jurisdiction)
        RETURN n.id AS id, n.name AS name
        ORDER BY n.name ASC
        """
    )
    return {
        "norms_without_jurisdiction": [dict(r) for r in norms_result],
    }


def get_business_attribute(session, attribute_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (ba:BusinessAttribute {id: $id})
        RETURN ba.id AS id, ba.name AS name
        """,
        id=attribute_id,
    )
    record = result.single()
    return dict(record) if record else None


def trace_up(session, control_id: str) -> dict | None:
    """Return {control_id, business_attributes, norms} tracing up the SABSA hierarchy.

    Walks all ancestors via CONTAINS*0.. then collects Precepts and linked
    BusinessAttributes/Norms. Returns None if the control does not exist.
    """
    if get_control(session, control_id) is None:
        return None

    result = session.run(
        """
        MATCH (c:Control {id: $control_id})
        OPTIONAL MATCH (anc:Control)-[:CONTAINS*0..]->(c)
        WITH c, collect(DISTINCT anc) + [c] AS all_ancestors
        UNWIND all_ancestors AS a
        OPTIONAL MATCH (a)-[:ADDRESSES]->(p:Precept)-[:FULFILS]->(ba:BusinessAttribute)
        OPTIONAL MATCH (n:Norm)-[:REQUIRES]->(p)
        RETURN
          $control_id AS control_id,
          collect(DISTINCT CASE WHEN ba IS NOT NULL THEN {id: ba.id, name: ba.name} END) AS business_attributes,
          collect(DISTINCT CASE WHEN n IS NOT NULL THEN {id: n.id, name: n.name, status: n.status} END) AS norms
        """,
        control_id=control_id,
    ).single()

    if result is None:
        return {"control_id": control_id, "business_attributes": [], "norms": []}

    return {
        "control_id": control_id,
        "business_attributes": [x for x in result["business_attributes"] if x is not None],
        "norms": [x for x in result["norms"] if x is not None],
    }


def trace_down(session, control_id: str, org_id: str | None) -> dict | None:
    """Return {control_id, documents, evidence_memories, gap_memories}.

    Always uses OPTIONAL MATCH for Memory path — works with zero Memory nodes
    (knowledge-only mode per ADR-001). org_id filters ABOUT_CONTROL edges; when
    None, returns all edges regardless of org_id.

    Returns None if the control does not exist.
    """
    result = session.run(
        """
        MATCH (c:Control {id: $control_id})
        OPTIONAL MATCH (ch:Chunk)-[sup:SUPPORTS]->(c)
        OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(ch)
        OPTIONAL MATCH (m:Memory)-[r:ABOUT_CONTROL]->(c)
          WHERE r.relationship_type IN ["evidence", "gap"]
            AND ($org_id IS NULL OR r.org_id = $org_id OR r.org_id IS NULL)
        RETURN
          $control_id AS control_id,
          collect(DISTINCT CASE WHEN d IS NOT NULL THEN {
            doc_id: d.id,
            doc_title: d.title,
            chunk_id: ch.id,
            chunk_text: ch.text,
            confidence: sup.confidence,
            sup_status: sup.status
          } END) AS doc_chunks,
          collect(DISTINCT CASE WHEN m IS NOT NULL THEN {
            id: m.id,
            text: m.text,
            relationship_type: r.relationship_type
          } END) AS memory_refs
        """,
        control_id=control_id,
        org_id=org_id,
    ).single()

    if result is None:
        return None  # MATCH (c:Control) found no rows → control does not exist

    doc_map: dict = {}
    for row in (result["doc_chunks"] or []):
        if row is None:
            continue
        did = row["doc_id"]
        if did not in doc_map:
            doc_map[did] = {"id": did, "title": row["doc_title"], "chunks": []}
        doc_map[did]["chunks"].append({
            "id": row["chunk_id"],
            "text": row["chunk_text"],
            "confidence": row["confidence"],
            "status": row["sup_status"],
        })

    evidence_memories, gap_memories = [], []
    for ref in (result["memory_refs"] or []):
        if ref is None:
            continue
        entry = {"id": ref["id"], "text": ref["text"], "relationship_type": ref["relationship_type"]}
        if ref["relationship_type"] == "evidence":
            evidence_memories.append(entry)
        else:
            gap_memories.append(entry)

    return {
        "control_id": control_id,
        "documents": list(doc_map.values()),
        "evidence_memories": evidence_memories,
        "gap_memories": gap_memories,
    }


def attribute_coverage(session, attribute_id: str) -> dict | None:
    """Return coverage statistics for a BusinessAttribute.

    Returns {attribute_id, total_controls, covered_controls, coverage_pct,
    uncovered_control_ids} or None if the attribute does not exist.
    """
    if get_business_attribute(session, attribute_id) is None:
        return None

    controls_result = session.run(
        """
        MATCH (ba:BusinessAttribute {id: $attribute_id})
        OPTIONAL MATCH (ba)<-[:FULFILS]-(p:Precept)<-[:ADDRESSES]-(ctrl:Control)
        RETURN ctrl.id AS control_id
        """,
        attribute_id=attribute_id,
    )
    control_ids = [r["control_id"] for r in controls_result if r["control_id"] is not None]

    if not control_ids:
        return {
            "attribute_id": attribute_id,
            "total_controls": 0,
            "covered_controls": 0,
            "coverage_pct": 0.0,
            "uncovered_control_ids": [],
        }

    coverage_result = session.run(
        """
        UNWIND $control_ids AS cid
        MATCH (ctrl:Control {id: cid})
        OPTIONAL MATCH (ch:Chunk)-[:SUPPORTS]->(ctrl)
        RETURN ctrl.id AS control_id, count(DISTINCT ch) AS chunk_count
        """,
        control_ids=control_ids,
    )
    rows = list(coverage_result)
    total = len(rows)
    covered = sum(1 for r in rows if r["chunk_count"] > 0)
    uncovered_ids = [r["control_id"] for r in rows if r["chunk_count"] == 0]
    coverage_pct = round((covered / total * 100) if total > 0 else 0.0, 2)

    return {
        "attribute_id": attribute_id,
        "total_controls": total,
        "covered_controls": covered,
        "coverage_pct": coverage_pct,
        "uncovered_control_ids": uncovered_ids,
    }


def gap_analysis(session, control_ids: list[str], org_id: str | None) -> dict:
    """Three-way reconciliation: {covered, partial, uncovered}.

    If control_ids is empty, analyses all controls.
    covered = has both SUPPORTS chunks AND evidence Memory nodes
    partial = has one but not both
    uncovered = has neither
    """
    if not control_ids:
        control_ids = [r["id"] for r in list_controls(session)]

    if not control_ids:
        return {"covered": [], "partial": [], "uncovered": []}

    result = session.run(
        """
        UNWIND $control_ids AS cid
        MATCH (c:Control {id: cid})
        OPTIONAL MATCH (ch:Chunk)-[:SUPPORTS]->(c)
        OPTIONAL MATCH (m:Memory)-[r:ABOUT_CONTROL]->(c)
          WHERE r.relationship_type = "evidence"
            AND ($org_id IS NULL OR r.org_id = $org_id OR r.org_id IS NULL)
        RETURN
          c.id AS control_id,
          c.name AS control_name,
          count(DISTINCT ch) AS chunk_count,
          count(DISTINCT m) AS memory_count
        """,
        control_ids=control_ids,
        org_id=org_id,
    )

    covered, partial, uncovered = [], [], []
    for row in result:
        entry = {
            "control_id": row["control_id"],
            "control_name": row["control_name"],
            "has_chunks": row["chunk_count"] > 0,
            "has_evidence_memories": row["memory_count"] > 0,
        }
        if entry["has_chunks"] and entry["has_evidence_memories"]:
            covered.append(entry)
        elif not entry["has_chunks"] and not entry["has_evidence_memories"]:
            uncovered.append(entry)
        else:
            partial.append(entry)

    return {"covered": covered, "partial": partial, "uncovered": uncovered}
