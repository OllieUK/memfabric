# memory_service/knowledge_repo.py
#
# Repository layer: all Cypher operations for the /knowledge endpoint.
# All functions receive an already-open neo4j.Session; callers own the session lifecycle.
#
# ADR-001: this file must NOT import from memory_repo. Cross-layer edges live exclusively
# in knowledge_bridge.py.

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Framework
# ---------------------------------------------------------------------------


def upsert_framework(session, req, now: str) -> dict:
    """MERGE Framework on id; SET all properties ON CREATE, update classification ON MATCH.
    If parent_id is set, creates CONTAINS edge from parent Framework to this node.
    """
    result = session.run(
        """
        MERGE (f:Framework {id: $id})
        ON CREATE SET
            f.title = $title,
            f.version = $version,
            f.level = $level,
            f.body = $body,
            f.statement_type = $statement_type,
            f.modality = $modality,
            f.external_id = $external_id,
            f.domain = $domain,
            f.created_at = $created_at
        ON MATCH SET
            f.statement_type = $statement_type,
            f.modality = $modality
        RETURN f.id AS id, f.title AS title, f.version AS version,
               f.level AS level, f.body AS body,
               f.statement_type AS statement_type,
               f.modality AS modality,
               f.external_id AS external_id,
               f.domain AS domain,
               f.created_at AS created_at
        """,
        id=req.id,
        title=req.title,
        version=req.version,
        level=req.level,
        body=req.body,
        statement_type=req.statement_type,
        modality=req.modality,
        external_id=getattr(req, "external_id", None),
        domain=getattr(req, "domain", None),
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


def create_mitigates_edge(session, control_id: str, framework_id: str, now: str) -> dict | None:
    """MERGE MITIGATES edge Control→Framework. Returns edge details or None if either node missing."""
    result = session.run(
        """
        MATCH (c:Control {id: $control_id}), (f:Framework {id: $framework_id})
        MERGE (c)-[r:MITIGATES]->(f)
        ON CREATE SET r.created_at = $created_at
        RETURN c.id AS control_id, f.id AS framework_id, r.created_at AS created_at
        """,
        control_id=control_id,
        framework_id=framework_id,
        created_at=now,
    )
    record = result.single()
    return dict(record) if record else None


def create_informs_edge(session, framework_id: str, control_id: str, now: str) -> dict | None:
    """MERGE INFORMS edge Framework→Control. Returns edge details or None if either node missing."""
    result = session.run(
        """
        MATCH (f:Framework {id: $framework_id}), (c:Control {id: $control_id})
        MERGE (f)-[r:INFORMS]->(c)
        ON CREATE SET r.created_at = $created_at
        RETURN f.id AS framework_id, c.id AS control_id, r.created_at AS created_at
        """,
        framework_id=framework_id,
        control_id=control_id,
        created_at=now,
    )
    record = result.single()
    return dict(record) if record else None


def get_framework(session, framework_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (f:Framework {id: $id})
        RETURN f.id AS id, f.title AS title, f.version AS version,
               f.level AS level, f.body AS body,
               f.statement_type AS statement_type,
               f.modality AS modality,
               f.external_id AS external_id,
               f.domain AS domain,
               f.created_at AS created_at
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
    """MERGE Norm; optionally create MAPS_TO (→Control) and REFERENCES (→Framework)."""
    result = session.run(
        """
        MERGE (n:Norm {id: $id})
        ON CREATE SET
            n.title = $title,
            n.body = $body,
            n.level = $level,
            n.version = $version,
            n.valid_from = $valid_from,
            n.valid_until = $valid_until,
            n.announced_at = $announced_at,
            n.text_hash = $text_hash,
            n.lang = $lang,
            n.domain = $domain,
            n.embedding = $embedding,
            n.created_at = $created_at
        RETURN n.id AS id, n.title AS title, n.body AS body, n.level AS level,
               n.version AS version, n.valid_from AS valid_from,
               n.valid_until AS valid_until, n.announced_at AS announced_at,
               n.text_hash AS text_hash, n.lang AS lang, n.domain AS domain,
               n.created_at AS created_at
        """,
        id=req.id,
        title=req.title,
        body=req.body,
        level=req.level,
        version=req.version,
        valid_from=req.valid_from,
        valid_until=req.valid_until,
        announced_at=req.announced_at,
        text_hash=req.text_hash,
        lang=req.lang,
        domain=req.domain,
        embedding=embedding,
        created_at=now,
    )
    record = dict(result.single())

    if req.maps_to_control_id:
        session.run(
            """
            MATCH (n:Norm {id: $norm_id}), (c:Control {id: $control_id})
            MERGE (n)-[:MAPS_TO]->(c)
            """,
            norm_id=req.id,
            control_id=req.maps_to_control_id,
        )

    if req.references_framework_id:
        session.run(
            """
            MATCH (n:Norm {id: $norm_id}), (f:Framework {id: $framework_id})
            MERGE (n)-[r:REFERENCES]->(f)
            ON CREATE SET r.version_pinned = $version_pinned
            """,
            norm_id=req.id,
            framework_id=req.references_framework_id,
            version_pinned=req.references_version_pinned,
        )

    return record


def get_norm(session, norm_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (n:Norm {id: $id})
        RETURN n.id AS id, n.title AS title, n.body AS body, n.level AS level,
               n.version AS version, n.valid_from AS valid_from,
               n.valid_until AS valid_until, n.announced_at AS announced_at,
               n.text_hash AS text_hash, n.lang AS lang, n.domain AS domain,
               n.created_at AS created_at
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
            d.policy_level = $policy_level,
            d.source_url = $source_url,
            d.created_at = $created_at
        RETURN d.id AS id, d.title AS title, d.policy_level AS policy_level,
               d.source_url AS source_url, d.created_at AS created_at
        """,
        id=req.id,
        title=req.title,
        policy_level=req.policy_level,
        source_url=req.source_url,
        created_at=now,
    )
    return dict(result.single())


def get_document(session, doc_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (d:Document {id: $id})
        RETURN d.id AS id, d.title AS title, d.policy_level AS policy_level,
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
            ch.body = $body,
            ch.sequence = $sequence,
            ch.doc_id = $doc_id,
            ch.heading = $heading,
            ch.section_ref = $section_ref,
            ch.status = $status,
            ch.embedding = $embedding,
            ch.created_at = $created_at
        RETURN ch.id AS id, ch.body AS body, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.heading AS heading,
               ch.section_ref AS section_ref, ch.status AS status,
               ch.created_at AS created_at
        """,
        id=req.id,
        body=req.body,
        sequence=req.sequence,
        doc_id=req.doc_id,
        heading=req.heading,
        section_ref=req.section_ref,
        status=req.status,
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
        RETURN ch.id AS id, ch.body AS body, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.heading AS heading,
               ch.section_ref AS section_ref, ch.status AS status,
               ch.created_at AS created_at
        """,
        id=chunk_id,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# Search functions (vector search over embeddings)
# ---------------------------------------------------------------------------


def search_controls(
    session,
    query_embedding: list[float],
    limit: int,
    framework_id: str | None,
) -> list[dict]:
    """Vector search over ctrl_embedding_idx.
    Returns list of dicts: {id, name, description, framework_id, created_at, distance}.
    NOTE: vector_search returns up to $limit nodes before the WHERE filter is applied.
    framework_id filter is applied post-index; when filters are tight, result may be empty.
    """
    result = session.run(
        """
        CALL vector_search.search("ctrl_embedding_idx", $limit, $query_vec)
        YIELD node AS c, distance
        WITH c, distance
        WHERE ($framework_id IS NULL OR c.framework_id = $framework_id)
        RETURN c.id AS id, c.name AS name, c.description AS description,
               c.framework_id AS framework_id, c.created_at AS created_at,
               distance
        ORDER BY distance ASC
        """,
        limit=limit,
        query_vec=query_embedding,
        framework_id=framework_id,
    )
    return [dict(r) for r in result]


def search_frameworks(
    session,
    query_embedding: list[float],
    limit: int,
    framework_id: str | None,
    statement_type: str | None = None,
) -> list[dict]:
    """Vector search over framework_embedding_idx (Framework nodes with body text).
    Returns list of dicts: {id, title, level, body, created_at, distance}.
    NOTE: vector_search returns up to $limit nodes before any filter is applied.
    framework_id filter is not supported in MVP — pass None.
    statement_type filter is applied post-index as a WHERE clause.
    """
    result = session.run(
        """
        CALL vector_search.search("framework_embedding_idx", $limit, $query_vec)
        YIELD node AS f, distance
        WITH f, distance
        WHERE ($statement_type IS NULL OR f.statement_type = $statement_type)
        RETURN f.id AS id, f.title AS title, f.level AS level,
               f.body AS body, f.created_at AS created_at,
               f.external_id AS external_id, f.domain AS domain,
               distance
        ORDER BY distance ASC
        """,
        limit=limit,
        query_vec=query_embedding,
        statement_type=statement_type,
    )
    return [dict(r) for r in result]


def search_chunks(
    session,
    query_embedding: list[float],
    limit: int,
    doc_id: str | None,
) -> list[dict]:
    """Vector search over chunk_embedding_idx.
    Returns list of dicts: {id, body, sequence, doc_id, heading, section_ref, status, created_at, distance}.
    No recall_count increment.
    NOTE: Same post-index filter caveat as search_frameworks.
    """
    result = session.run(
        """
        CALL vector_search.search("chunk_embedding_idx", $limit, $query_vec)
        YIELD node AS ch, distance
        WITH ch, distance
        WHERE ($doc_id IS NULL OR ch.doc_id = $doc_id)
        RETURN ch.id AS id, ch.body AS body, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.heading AS heading,
               ch.section_ref AS section_ref, ch.status AS status,
               ch.created_at AS created_at,
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


def list_controls(session) -> list[dict]:
    """Return all Control nodes as a list of {id, name} dicts."""
    result = session.run(
        "MATCH (c:Control) RETURN c.id AS id, c.name AS name ORDER BY c.name ASC"
    )
    return [dict(r) for r in result]


def list_norms(session) -> list[dict]:
    """Return all Norm nodes, ordered by title.
    Returns list of dicts matching NormResponse fields.
    """
    result = session.run(
        """
        MATCH (n:Norm)
        RETURN n.id AS id, n.title AS title, n.body AS body, n.level AS level,
               n.version AS version, n.valid_from AS valid_from,
               n.valid_until AS valid_until, n.announced_at AS announced_at,
               n.text_hash AS text_hash, n.lang AS lang, n.domain AS domain,
               n.created_at AS created_at
        ORDER BY n.title ASC
        """
    )
    return [dict(r) for r in result]


def list_documents(session) -> list[dict]:
    """Return all Document nodes, ordered by title.
    Returns list of dicts: {id, title, policy_level, source_url, created_at}.
    """
    result = session.run(
        """
        MATCH (d:Document)
        RETURN d.id AS id, d.title AS title, d.policy_level AS policy_level,
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
    raw_score: float | None,
    status: str,
    now: str,
) -> dict | None:
    """MERGE SUPPORTS edge Chunk→Framework; SET all properties ON CREATE only.

    Returns {chunk_id, framework_id, confidence, raw_score, status, created_at}.
    Returns None if either Chunk or Framework node does not exist.
    Callers must check for None and raise HTTP 404.
    """
    result = session.run(
        """
        MATCH (ch:Chunk {id: $chunk_id}), (f:Framework {id: $framework_id})
        MERGE (ch)-[s:SUPPORTS]->(f)
        ON CREATE SET
            s.confidence  = $confidence,
            s.raw_score   = $raw_score,
            s.status      = $status,
            s.created_at  = $created_at
        RETURN ch.id AS chunk_id, f.id AS framework_id,
               s.confidence AS confidence, s.raw_score AS raw_score,
               s.status AS status, s.created_at AS created_at
        """,
        chunk_id=chunk_id,
        framework_id=framework_id,
        confidence=confidence,
        raw_score=raw_score,
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

    Returns list of dicts: {id, body, sequence, doc_id, heading, section_ref, status, created_at, confidence}.
    """
    result = session.run(
        """
        MATCH (ch:Chunk)-[s:SUPPORTS]->(f:Framework {id: $framework_id})
        RETURN ch.id AS id, ch.body AS body, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.heading AS heading,
               ch.section_ref AS section_ref, ch.status AS status,
               ch.created_at AS created_at,
               s.confidence AS confidence
        ORDER BY s.confidence DESC
        """,
        framework_id=framework_id,
    )
    return [dict(r) for r in result]


def get_chunks_for_control(session, control_id: str) -> list[dict]:
    """Return all Chunk nodes with a SUPPORTS edge to this Control,
    ordered by confidence DESC.

    Returns list of dicts: {id, body, sequence, doc_id, heading, section_ref, status, created_at, confidence}.
    """
    result = session.run(
        """
        MATCH (ch:Chunk)-[s:SUPPORTS]->(c:Control {id: $control_id})
        RETURN ch.id AS id, ch.body AS body, ch.sequence AS sequence,
               ch.doc_id AS doc_id, ch.heading AS heading,
               ch.section_ref AS section_ref, ch.status AS status,
               ch.created_at AS created_at,
               s.confidence AS confidence
        ORDER BY s.confidence DESC
        """,
        control_id=control_id,
    )
    return [dict(r) for r in result]


def list_incomplete_jurisdictions(session) -> dict:
    """Return Norms with no APPLIES_IN edges.
    Returns:
      {
        "norms_without_jurisdiction": [{"id": ..., "title": ...}, ...],
      }
    """
    norms_result = session.run(
        """
        MATCH (n:Norm)
        WHERE NOT (n)-[:APPLIES_IN]->(:Jurisdiction)
        RETURN n.id AS id, n.title AS title
        ORDER BY n.title ASC
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
          collect(DISTINCT CASE WHEN n IS NOT NULL THEN {id: n.id, title: n.title} END) AS norms
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
          WHERE r.relationship_type IN ['evidence', 'gap']
            AND ($org_id IS NULL OR r.org_id = $org_id OR r.org_id IS NULL)
        RETURN
          $control_id AS control_id,
          collect(DISTINCT CASE WHEN d IS NOT NULL THEN {
            doc_id: d.id,
            doc_title: d.title,
            chunk_id: ch.id,
            chunk_body: ch.body,
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
            "body": row["chunk_body"],
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


# ---------------------------------------------------------------------------
# ThreatReport
# ---------------------------------------------------------------------------


def upsert_threat_report(session, req, now: str) -> dict:
    """MERGE ThreatReport on id; SET all properties ON CREATE."""
    result = session.run(
        """
        MERGE (tr:ThreatReport {id: $id})
        ON CREATE SET
            tr.title = $title, tr.publisher = $publisher,
            tr.published_at = $published_at, tr.valid_from = $valid_from,
            tr.valid_until = $valid_until, tr.scope = $scope,
            tr.perspective_notes = $perspective_notes, tr.created_at = $created_at
        RETURN tr.id AS id, tr.title AS title, tr.publisher AS publisher,
               tr.published_at AS published_at, tr.valid_from AS valid_from,
               tr.valid_until AS valid_until, tr.scope AS scope,
               tr.perspective_notes AS perspective_notes, tr.created_at AS created_at
        """,
        id=req.id,
        title=req.title,
        publisher=req.publisher,
        published_at=req.published_at,
        valid_from=req.valid_from,
        valid_until=req.valid_until,
        scope=req.scope,
        perspective_notes=req.perspective_notes,
        created_at=now,
    )
    return dict(result.single())


def get_threat_report(session, threat_report_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (tr:ThreatReport {id: $threat_report_id})
        RETURN tr.id AS id, tr.title AS title, tr.publisher AS publisher,
               tr.published_at AS published_at, tr.valid_from AS valid_from,
               tr.valid_until AS valid_until, tr.scope AS scope,
               tr.perspective_notes AS perspective_notes, tr.created_at AS created_at
        """,
        threat_report_id=threat_report_id,
    )
    record = result.single()
    return dict(record) if record else None


def list_threat_reports(session) -> list[dict]:
    """Return all ThreatReport nodes ordered by title."""
    result = session.run(
        """
        MATCH (tr:ThreatReport)
        RETURN tr.id AS id, tr.title AS title, tr.publisher AS publisher,
               tr.published_at AS published_at, tr.valid_from AS valid_from,
               tr.valid_until AS valid_until, tr.scope AS scope,
               tr.perspective_notes AS perspective_notes, tr.created_at AS created_at
        ORDER BY tr.title ASC
        """
    )
    return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Threat
# ---------------------------------------------------------------------------


def upsert_threat(session, req, embedding: list[float], now: str) -> dict:
    """MERGE Threat on id; SET all properties ON CREATE."""
    result = session.run(
        """
        MERGE (t:Threat {id: $id})
        ON CREATE SET t.text = $text, t.tags = $tags,
                      t.embedding = $embedding, t.created_at = $created_at
        RETURN t.id AS id, t.text AS text, t.tags AS tags, t.created_at AS created_at
        """,
        id=req.id,
        text=req.text,
        tags=req.tags or [],
        embedding=embedding,
        created_at=now,
    )
    return dict(result.single())


def get_threat(session, threat_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (t:Threat {id: $threat_id})
        RETURN t.id AS id, t.text AS text, t.tags AS tags, t.created_at AS created_at
        """,
        threat_id=threat_id,
    )
    record = result.single()
    return dict(record) if record else None


def list_threats(session) -> list[dict]:
    """Return all Threat nodes ordered by text."""
    result = session.run(
        """
        MATCH (t:Threat)
        RETURN t.id AS id, t.text AS text, t.tags AS tags, t.created_at AS created_at
        ORDER BY t.text ASC
        """
    )
    return [dict(r) for r in result]


def search_threats(session, embedding: list[float], limit: int) -> list[dict]:
    """Vector search over threat_embedding_idx."""
    result = session.run(
        """
        CALL vector_search.search("threat_embedding_idx", $limit, $embedding)
        YIELD node AS t, distance
        RETURN t.id AS id, t.text AS text, t.tags AS tags,
               t.created_at AS created_at, distance
        ORDER BY distance ASC
        """,
        embedding=embedding,
        limit=limit,
    )
    return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------


def upsert_asset(session, req, now: str) -> dict:
    """MERGE Asset on id; SET all properties ON CREATE."""
    result = session.run(
        """
        MERGE (a:Asset {id: $id})
        ON CREATE SET
            a.title = $title, a.asset_type = $asset_type,
            a.exposure = $exposure, a.data_classification = $data_classification,
            a.created_at = $created_at
        RETURN a.id AS id, a.title AS title, a.asset_type AS asset_type,
               a.exposure AS exposure, a.data_classification AS data_classification,
               a.created_at AS created_at
        """,
        id=req.id,
        title=req.title,
        asset_type=req.asset_type,
        exposure=req.exposure,
        data_classification=req.data_classification,
        created_at=now,
    )
    return dict(result.single())


def get_asset(session, asset_id: str) -> dict | None:
    result = session.run(
        """
        MATCH (a:Asset {id: $asset_id})
        RETURN a.id AS id, a.title AS title, a.asset_type AS asset_type,
               a.exposure AS exposure, a.data_classification AS data_classification,
               a.created_at AS created_at
        """,
        asset_id=asset_id,
    )
    record = result.single()
    return dict(record) if record else None


def list_assets(session) -> list[dict]:
    """Return all Asset nodes ordered by title."""
    result = session.run(
        """
        MATCH (a:Asset)
        RETURN a.id AS id, a.title AS title, a.asset_type AS asset_type,
               a.exposure AS exposure, a.data_classification AS data_classification,
               a.created_at AS created_at
        ORDER BY a.title ASC
        """
    )
    return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# IDENTIFIES edge (ThreatReport → Threat)
# ---------------------------------------------------------------------------


def create_identifies_edge(
    session,
    threat_report_id: str,
    threat_id: str,
    severity: str,
    confidence: str,
    trend: str,
    source_terminology: str | None,
    now: str,
) -> dict | None:
    """MERGE IDENTIFIES edge ThreatReport→Threat. Returns edge details or None if either node missing."""
    result = session.run(
        """
        MATCH (tr:ThreatReport {id: $tr_id}), (t:Threat {id: $t_id})
        MERGE (tr)-[r:IDENTIFIES]->(t)
        ON CREATE SET r.severity = $severity, r.confidence = $confidence,
                      r.trend = $trend, r.source_terminology = $source_terminology,
                      r.created_at = $created_at
        ON MATCH SET  r.severity = $severity, r.confidence = $confidence,
                      r.trend = $trend, r.source_terminology = $source_terminology
        RETURN tr.id AS threat_report_id, t.id AS threat_id,
               r.severity AS severity, r.confidence AS confidence,
               r.trend AS trend, r.source_terminology AS source_terminology,
               r.created_at AS created_at
        """,
        tr_id=threat_report_id,
        t_id=threat_id,
        severity=severity,
        confidence=confidence,
        trend=trend,
        source_terminology=source_terminology,
        created_at=now,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# MAPPED_TO_TECHNIQUE edge (Threat → Framework)
# ---------------------------------------------------------------------------


def create_mapped_to_technique_edge(session, threat_id: str, framework_id: str, now: str) -> dict | None:
    """MERGE MAPPED_TO_TECHNIQUE edge Threat→Framework. Returns edge details or None if either node missing."""
    result = session.run(
        """
        MATCH (t:Threat {id: $threat_id}), (f:Framework {id: $framework_id})
        MERGE (t)-[r:MAPPED_TO_TECHNIQUE]->(f)
        ON CREATE SET r.created_at = $created_at
        RETURN t.id AS threat_id, f.id AS framework_id, r.created_at AS created_at
        """,
        threat_id=threat_id,
        framework_id=framework_id,
        created_at=now,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# TARGETS edge (Threat → Asset)
# ---------------------------------------------------------------------------


def create_targets_edge(session, threat_id: str, asset_id: str, now: str) -> dict | None:
    """MERGE TARGETS edge Threat→Asset. Returns edge details or None if either node missing."""
    result = session.run(
        """
        MATCH (t:Threat {id: $threat_id}), (a:Asset {id: $asset_id})
        MERGE (t)-[r:TARGETS]->(a)
        ON CREATE SET r.created_at = $created_at
        RETURN t.id AS threat_id, a.id AS asset_id, r.created_at AS created_at
        """,
        threat_id=threat_id,
        asset_id=asset_id,
        created_at=now,
    )
    record = result.single()
    return dict(record) if record else None


# ---------------------------------------------------------------------------
# Traversal helpers
# ---------------------------------------------------------------------------


def list_threat_reports_for_threat(session, threat_id: str) -> list[dict]:
    """Return all ThreatReports with an IDENTIFIES edge to the given Threat,
    including edge properties severity, confidence, trend.
    """
    result = session.run(
        """
        MATCH (tr:ThreatReport)-[r:IDENTIFIES]->(t:Threat {id: $threat_id})
        RETURN tr.id AS id, tr.title AS title, tr.publisher AS publisher,
               tr.published_at AS published_at, tr.valid_from AS valid_from,
               tr.valid_until AS valid_until, tr.scope AS scope,
               tr.perspective_notes AS perspective_notes, tr.created_at AS created_at,
               r.severity AS severity, r.confidence AS confidence, r.trend AS trend
        ORDER BY tr.title ASC
        """,
        threat_id=threat_id,
    )
    return [dict(r) for r in result]


def list_threats_for_report(session, report_id: str) -> list[dict]:
    """Return all Threats identified by the given ThreatReport, including edge severity."""
    result = session.run(
        """
        MATCH (tr:ThreatReport {id: $report_id})-[r:IDENTIFIES]->(t:Threat)
        RETURN t.id AS id, t.text AS text, t.tags AS tags, t.created_at AS created_at,
               r.severity AS severity
        ORDER BY t.text ASC
        """,
        report_id=report_id,
    )
    return [dict(r) for r in result]


# ---------------------------------------------------------------------------
# Merge threat (WP-138b)
# ---------------------------------------------------------------------------


def merge_threat(session, source_id: str, target_id: str) -> dict:
    """Merge source Threat into target Threat.

    Steps (each a separate session.run — no DETACH DELETE + RETURN):
    1. Validate both nodes exist and neither is already archived.
    2. Pre-count IDENTIFIES edges on source, then MERGE each ThreatReport→source
       edge as ThreatReport→target (ON CREATE SET only — existing target properties
       are intentionally preserved; see R2 in WP-138b plan). DELETE source edge.
    3. Pre-count MAPPED_TO_TECHNIQUE edges on source, then MERGE each
       source→Framework edge as target→Framework (ON CREATE SET only). DELETE
       source edge.
    4. Archive source: SET archived=true, merged_into, merged_at.
    5. Return {source_id, target_id, identifies_rewired, techniques_rewired}.

    Raises ValueError if either node is missing or already archived.

    NOTE on ON MATCH for IDENTIFIES: intentionally omitted. When the target
    already has an IDENTIFIES edge from the same ThreatReport, that edge's
    severity/confidence/trend/source_terminology are left unchanged. This
    preserves the canonical node's original assessment from that report and
    avoids ambiguity. This differs from create_identifies_edge which uses
    ON MATCH SET — do NOT "fix" this to match that function's behaviour.
    """
    if source_id == target_id:
        raise ValueError("Source and target must differ")

    now = datetime.now(tz=timezone.utc).isoformat()

    # Step 1 — validate
    check = session.run(
        """
        MATCH (src:Threat {id: $source_id})
        WHERE src.archived IS NULL OR src.archived = false
        MATCH (tgt:Threat {id: $target_id})
        WHERE tgt.archived IS NULL OR tgt.archived = false
        RETURN src.id AS src_id
        """,
        source_id=source_id,
        target_id=target_id,
    )
    if check.single() is None:
        raise ValueError(
            f"Source {source_id!r} or target {target_id!r} not found or already archived"
        )

    # Step 2 — IDENTIFIES: pre-count then rewire
    count_result = session.run(
        """
        MATCH (tr:ThreatReport)-[r:IDENTIFIES]->(src:Threat {id: $source_id})
        RETURN count(r) AS identifies_count
        """,
        source_id=source_id,
    )
    identifies_rewired = (count_result.single() or {"identifies_count": 0})["identifies_count"]

    session.run(
        """
        MATCH (tr:ThreatReport)-[r:IDENTIFIES]->(src:Threat {id: $source_id})
        MATCH (tgt:Threat {id: $target_id})
        MERGE (tr)-[new_r:IDENTIFIES]->(tgt)
        ON CREATE SET
            new_r.severity           = r.severity,
            new_r.confidence         = r.confidence,
            new_r.trend              = r.trend,
            new_r.source_terminology = r.source_terminology,
            new_r.created_at         = r.created_at
        DELETE r
        """,
        source_id=source_id,
        target_id=target_id,
    )

    # Step 3 — MAPPED_TO_TECHNIQUE: pre-count then rewire
    tech_count_result = session.run(
        """
        MATCH (src:Threat {id: $source_id})-[r:MAPPED_TO_TECHNIQUE]->(f:Framework)
        RETURN count(r) AS techniques_count
        """,
        source_id=source_id,
    )
    techniques_rewired = (tech_count_result.single() or {"techniques_count": 0})["techniques_count"]

    session.run(
        """
        MATCH (src:Threat {id: $source_id})-[r:MAPPED_TO_TECHNIQUE]->(f:Framework)
        MATCH (tgt:Threat {id: $target_id})
        MERGE (tgt)-[new_r:MAPPED_TO_TECHNIQUE]->(f)
        ON CREATE SET new_r.created_at = r.created_at
        DELETE r
        """,
        source_id=source_id,
        target_id=target_id,
    )

    # Step 4 — archive source
    session.run(
        """
        MATCH (src:Threat {id: $source_id})
        SET src.archived    = true,
            src.merged_into = $target_id,
            src.merged_at   = $now
        """,
        source_id=source_id,
        target_id=target_id,
        now=now,
    )

    return {
        "source_id": source_id,
        "target_id": target_id,
        "identifies_rewired": identifies_rewired,
        "techniques_rewired": techniques_rewired,
    }


# ---------------------------------------------------------------------------
# Gap analysis (existing)
# ---------------------------------------------------------------------------


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
          WHERE r.relationship_type = 'evidence'
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
