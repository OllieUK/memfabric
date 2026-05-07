# memory_service/knowledge_routes.py
#
# FastAPI router for the /knowledge endpoints.
# Registered in main.py only when ENABLE_KNOWLEDGE_LAYER=true.
#
# ADR-001: this file must NOT import from memory_repo. All cross-layer
# logic lives in knowledge_bridge.py.

from datetime import datetime, timezone
from typing import Optional, List, Literal

from fastapi import APIRouter, HTTPException, Request
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel, Field, field_validator, model_validator

from memory_service import knowledge_repo
from memory_service.config import settings
from memory_service.embeddings import get_embedding
from memory_service.knowledge_schemas import (
    STATEMENT_TYPES,
    NORMATIVE_MODALITIES,
    CHUNK_STATUSES,
    DOCUMENT_POLICY_LEVELS,
    THREAT_REPORT_SCOPES,
    IDENTIFIES_SEVERITIES,
    IDENTIFIES_CONFIDENCES,
    IDENTIFIES_TRENDS,
    ASSET_TYPES,
    ASSET_EXPOSURES,
    ASSET_DATA_CLASSIFICATIONS,
    BA_STATUSES,
    BA_TIERS,
    BA_GROUPS,
    T100_STEREOTYPES,
    INFLUENCE_POLARITIES,
    INFLUENCE_STATUSES,
    SABSA_PERSPECTIVES,
    SABSA_MATRICES,
    MATRIX_LAYERS_MAIN,
    MATRIX_LAYERS_SERVICE_MGMT,
    CELL_ROLES,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FrameworkCreate(BaseModel):
    id: str
    title: str
    version: Optional[str] = None
    level: str = "framework"           # framework | category | technique | sub-technique
    body: Optional[str] = None         # requirement text; used for embedding when present
    parent_id: Optional[str] = None    # if set, creates CONTAINS edge parent→this
    statement_type: Optional[str] = None
    modality: Optional[str] = None
    external_id: Optional[str] = None  # e.g. T1566.001, TA0001 — human-readable ID from source
    domain: Optional[str] = None       # e.g. enterprise, ics, mobile — for ATT&CK matrices
    # WP-113: T100-aligned SABSA matrix coordinate properties
    layer: Optional[str] = None
    perspective: Optional[str] = None
    matrix: Optional[str] = None
    cell_role: Optional[str] = None
    t100_stereotype: Optional[str] = None

    @field_validator("cell_role")
    @classmethod
    def validate_cell_role(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CELL_ROLES:
            raise ValueError(f"cell_role must be one of {sorted(CELL_ROLES)} or null")
        return v

    @field_validator("perspective")
    @classmethod
    def validate_perspective(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SABSA_PERSPECTIVES:
            raise ValueError(f"perspective must be one of {sorted(SABSA_PERSPECTIVES)} or null")
        return v

    @field_validator("matrix")
    @classmethod
    def validate_matrix(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SABSA_MATRICES:
            raise ValueError(f"matrix must be one of {sorted(SABSA_MATRICES)} or null")
        return v

    @model_validator(mode="after")
    def validate_layer_for_cell_role(self) -> "FrameworkCreate":
        if self.cell_role == "main-matrix-cell":
            if self.layer is None or self.layer not in MATRIX_LAYERS_MAIN:
                raise ValueError(
                    f"layer must be one of {sorted(MATRIX_LAYERS_MAIN)} "
                    f"when cell_role='main-matrix-cell'"
                )
        elif self.cell_role == "service-mgmt-cell":
            if self.layer is None or self.layer not in MATRIX_LAYERS_SERVICE_MGMT:
                raise ValueError(
                    f"layer must be one of {sorted(MATRIX_LAYERS_SERVICE_MGMT)} "
                    f"when cell_role='service-mgmt-cell'"
                )
        elif self.layer is not None:
            if self.layer not in MATRIX_LAYERS_MAIN and self.layer not in MATRIX_LAYERS_SERVICE_MGMT:
                raise ValueError(
                    f"layer must be a valid SABSA layer name or null"
                )
        return self


class FrameworkResponse(BaseModel):
    id: str
    title: str
    version: Optional[str] = None
    level: str
    body: Optional[str] = None
    created_at: str
    statement_type: Optional[str] = None
    modality: Optional[str] = None
    external_id: Optional[str] = None
    domain: Optional[str] = None
    layer: Optional[str] = None
    perspective: Optional[str] = None
    matrix: Optional[str] = None
    cell_role: Optional[str] = None
    t100_stereotype: Optional[str] = None


class NormCreate(BaseModel):
    id: str
    title: str
    body: str                                       # requirement text; used for embedding
    level: str = "article"                          # article | clause | sub-clause | annex
    version: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    announced_at: Optional[str] = None
    text_hash: Optional[str] = None
    lang: Optional[str] = None
    domain: Optional[str] = None
    maps_to_control_id: Optional[str] = None       # creates MAPS_TO edge norm→control
    references_framework_id: Optional[str] = None  # creates REFERENCES edge norm→framework
    references_version_pinned: bool = False         # version_pinned property on REFERENCES edge


class NormResponse(BaseModel):
    id: str
    title: str
    body: str
    level: str
    version: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    announced_at: Optional[str] = None
    text_hash: Optional[str] = None
    lang: Optional[str] = None
    domain: Optional[str] = None
    created_at: str


class DocumentCreate(BaseModel):
    id: str
    title: str
    policy_level: str                  # strategic | tactical | operational | procedure
    source_url: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    policy_level: str
    source_url: Optional[str] = None
    created_at: str


class ChunkCreate(BaseModel):
    id: str
    body: str                           # chunk content; used for embedding
    sequence: int
    doc_id: str                         # parent document; creates HAS_CHUNK edge
    heading: Optional[str] = None
    section_ref: Optional[str] = None
    status: Optional[str] = "unmatched"
    prev_chunk_id: Optional[str] = None  # if set, creates HAS_NEXT edge prev→this


class ChunkResponse(BaseModel):
    id: str
    body: str
    sequence: int
    doc_id: str
    heading: Optional[str] = None
    section_ref: Optional[str] = None
    status: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# Search request/response models
# ---------------------------------------------------------------------------


class FrameworkSearchRequest(BaseModel):
    query: str
    limit: int = 10
    framework_id: Optional[str] = None
    statement_type: Optional[str] = None


class ChunkSearchRequest(BaseModel):
    query: str
    limit: int = 10
    doc_id: Optional[str] = None


class FrameworkHit(BaseModel):
    id: str
    title: str
    level: str
    body: Optional[str] = None
    created_at: str
    distance: float
    external_id: Optional[str] = None
    domain: Optional[str] = None


class ChunkHit(BaseModel):
    id: str
    body: str
    sequence: int
    doc_id: str
    heading: Optional[str] = None
    section_ref: Optional[str] = None
    status: Optional[str] = None
    created_at: str
    distance: float


class MitigatesCreate(BaseModel):
    control_id: str
    framework_id: str   # ATT&CK technique/sub-technique Framework node id


class MitigatesResponse(BaseModel):
    control_id: str
    framework_id: str
    created_at: str


class InformsCreate(BaseModel):
    framework_id: str   # Framework node that informs the control
    control_id: str


class InformsResponse(BaseModel):
    framework_id: str
    control_id: str
    created_at: str


class InformsBACreate(BaseModel):
    framework_id: str
    ba_id: str
    rationale: str
    similarity: Optional[float] = None
    source: str = "embedding-similarity"


class InformsBAResponse(BaseModel):
    framework_id: str
    ba_id: str
    created_at: str


class SupportsCreate(BaseModel):
    chunk_id: str
    framework_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    raw_score: Optional[float] = None
    status: str = "auto-inferred"


class SupportsResponse(BaseModel):
    chunk_id: str
    framework_id: str
    confidence: float
    raw_score: Optional[float] = None
    status: str
    created_at: str


class ChunkWithSupports(BaseModel):
    id: str
    body: str
    sequence: int
    doc_id: str
    heading: Optional[str] = None
    section_ref: Optional[str] = None
    status: Optional[str] = None
    created_at: str
    confidence: float


# ---------------------------------------------------------------------------
# Control CRUD models
# ---------------------------------------------------------------------------


class ControlCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework_id: str
    parent_id: Optional[str] = None    # if set, creates CONTAINS edge parent→this


class ControlResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework_id: str
    created_at: str


class ControlSearchRequest(BaseModel):
    query: str
    limit: int = 10
    framework_id: Optional[str] = None


class ControlHit(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework_id: str
    created_at: str
    distance: float


# ---------------------------------------------------------------------------
# Traceability models
# ---------------------------------------------------------------------------


class BusinessAttributeRef(BaseModel):
    id: str
    name: str


class NormRef(BaseModel):
    id: str
    title: str


class TraceUpResponse(BaseModel):
    control_id: str
    business_attributes: List[BusinessAttributeRef]
    norms: List[NormRef]


class ChunkRef(BaseModel):
    id: str
    body: str
    confidence: Optional[float] = None
    status: Optional[str] = None


class DocumentWithChunks(BaseModel):
    id: str
    title: str
    chunks: List[ChunkRef]


class MemoryRef(BaseModel):
    id: str
    text: str
    relationship_type: Literal["context", "evidence", "gap"]


class TraceDownResponse(BaseModel):
    control_id: str
    documents: List[DocumentWithChunks]
    evidence_memories: List[MemoryRef]
    gap_memories: List[MemoryRef]


class AttributeCoverageResponse(BaseModel):
    attribute_id: str
    total_controls: int
    covered_controls: int
    coverage_pct: float
    uncovered_control_ids: List[str]


class GapAnalysisRequest(BaseModel):
    control_ids: List[str] = []
    org_id: Optional[str] = None


class ControlGapEntry(BaseModel):
    control_id: str
    control_name: str
    has_chunks: bool
    has_evidence_memories: bool


class GapAnalysisResponse(BaseModel):
    covered: List[ControlGapEntry]
    partial: List[ControlGapEntry]
    uncovered: List[ControlGapEntry]


# ---------------------------------------------------------------------------
# WP-113 — BusinessAttribute / INFLUENCE / CONTAINS Pydantic models
# ---------------------------------------------------------------------------


class BusinessAttributeCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    source_ref: Optional[str] = None
    status: str = "active"
    superseded_by: Optional[str] = None
    tier: str
    group: Optional[str] = None
    t100_stereotype: Optional[str] = None

    @field_validator("tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in BA_TIERS:
            raise ValueError(f"tier must be one of {sorted(BA_TIERS)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in BA_STATUSES:
            raise ValueError(f"status must be one of {sorted(BA_STATUSES)}")
        return v

    @field_validator("group")
    @classmethod
    def validate_group(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in BA_GROUPS:
            raise ValueError(f"group must be one of {sorted(BA_GROUPS)} or null")
        return v

    @field_validator("t100_stereotype")
    @classmethod
    def validate_t100_stereotype(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in T100_STEREOTYPES:
            raise ValueError(f"t100_stereotype must be one of {sorted(T100_STEREOTYPES)} or null")
        return v


class BusinessAttributeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    source_ref: Optional[str]
    status: str
    superseded_by: Optional[str]
    tier: str
    group: Optional[str]
    t100_stereotype: Optional[str]
    created_at: str


class InfluenceCreate(BaseModel):
    source_id: str
    target_id: str
    polarity: str
    severity: Optional[str] = None
    rationale: str
    status: str = "curated"

    @field_validator("polarity")
    @classmethod
    def validate_polarity(cls, v: str) -> str:
        if v not in INFLUENCE_POLARITIES:
            raise ValueError(f"polarity must be one of {sorted(INFLUENCE_POLARITIES)}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in IDENTIFIES_SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(IDENTIFIES_SEVERITIES)} or null")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in INFLUENCE_STATUSES:
            raise ValueError(f"status must be one of {sorted(INFLUENCE_STATUSES)}")
        return v


class InfluenceResponse(BaseModel):
    source_id: str
    target_id: str
    polarity: str
    severity: Optional[str]
    rationale: str
    status: str
    created_at: str


class ContainsCreate(BaseModel):
    parent_id: str
    child_id: str
    rationale: Optional[str] = None


class ContainsResponse(BaseModel):
    parent_id: str
    child_id: str
    rationale: Optional[str]
    created_at: str


# ---------------------------------------------------------------------------
# ThreatReport / Threat / Asset Pydantic models
# ---------------------------------------------------------------------------


class ThreatReportCreate(BaseModel):
    id: str
    title: str
    publisher: str
    published_at: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    scope: Optional[str] = None
    perspective_notes: Optional[str] = None


class ThreatReportResponse(BaseModel):
    id: str
    title: str
    publisher: str
    published_at: Optional[str]
    valid_from: Optional[str]
    valid_until: Optional[str]
    scope: Optional[str]
    perspective_notes: Optional[str]
    created_at: str


class ThreatCreate(BaseModel):
    id: str
    text: str
    tags: Optional[List[str]] = None


class ThreatResponse(BaseModel):
    id: str
    text: str
    tags: Optional[List[str]]
    created_at: str


class AssetCreate(BaseModel):
    id: str
    title: str
    asset_type: str
    exposure: Optional[str] = None
    data_classification: Optional[str] = None

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, v: str) -> str:
        if v not in ASSET_TYPES:
            raise ValueError(f"asset_type must be one of {sorted(ASSET_TYPES)}")
        return v


class AssetResponse(BaseModel):
    id: str
    title: str
    asset_type: str
    exposure: Optional[str]
    data_classification: Optional[str]
    created_at: str


class IdentifiesCreate(BaseModel):
    threat_report_id: str
    threat_id: str
    severity: str
    confidence: str
    trend: str
    source_terminology: Optional[str] = None


class IdentifiesResponse(BaseModel):
    threat_report_id: str
    threat_id: str
    severity: str
    confidence: str
    trend: str
    source_terminology: Optional[str]
    created_at: str


class MappedToTechniqueCreate(BaseModel):
    threat_id: str
    framework_id: str


class MappedToTechniqueResponse(BaseModel):
    threat_id: str
    framework_id: str
    created_at: str


class TargetsCreate(BaseModel):
    threat_id: str
    asset_id: str


class TargetsResponse(BaseModel):
    threat_id: str
    asset_id: str
    created_at: str


class ThreatSearchRequest(BaseModel):
    query: str
    limit: int = 10


class ThreatHit(BaseModel):
    id: str
    text: str
    tags: Optional[List[str]]
    created_at: str
    distance: float


class ThreatMergeRequest(BaseModel):
    target_id: str


class ThreatMergeResponse(BaseModel):
    source_id: str
    target_id: str
    identifies_rewired: int
    techniques_rewired: int


class ThreatReportWithEdge(BaseModel):
    id: str
    title: str
    publisher: str
    published_at: Optional[str]
    valid_from: Optional[str]
    valid_until: Optional[str]
    scope: Optional[str]
    perspective_notes: Optional[str]
    created_at: str
    severity: Optional[str]
    confidence: Optional[str]
    trend: Optional[str]


class ThreatWithSeverity(BaseModel):
    id: str
    text: str
    tags: Optional[List[str]]
    created_at: str
    severity: Optional[str]


# ---------------------------------------------------------------------------
# Framework endpoints
# ---------------------------------------------------------------------------


@router.post("/frameworks", response_model=FrameworkResponse)
async def upsert_framework(req: FrameworkCreate, request: Request) -> FrameworkResponse:
    if req.statement_type and req.statement_type not in STATEMENT_TYPES:
        raise HTTPException(400, f"Invalid statement_type: {req.statement_type}. Must be one of: {sorted(STATEMENT_TYPES)}")
    if req.modality:
        if req.modality not in NORMATIVE_MODALITIES:
            raise HTTPException(400, f"Invalid modality: {req.modality}. Must be one of: {sorted(NORMATIVE_MODALITIES)}")
        if req.statement_type != "normative":
            raise HTTPException(400, "modality can only be set when statement_type is 'normative'")
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_framework(session, req, now)
        if req.body:
            embedding = get_embedding(req.body, model_name=settings.knowledge_embedding_model)
            with request.app.state.driver.session() as session:
                session.run(
                    "MATCH (f:Framework {id: $id}) SET f.embedding = $emb",
                    id=req.id,
                    emb=embedding,
                )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return FrameworkResponse(**record)


@router.get("/frameworks/{framework_id}", response_model=FrameworkResponse)
async def get_framework(framework_id: str, request: Request) -> FrameworkResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_framework(session, framework_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")
    return FrameworkResponse(**record)


# ---------------------------------------------------------------------------
# Norm endpoints
# ---------------------------------------------------------------------------


@router.post("/norms", response_model=NormResponse)
async def upsert_norm(req: NormCreate, request: Request) -> NormResponse:
    embedding = get_embedding(req.body, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_norm(session, req, embedding, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return NormResponse(**record)


@router.get("/norms/{norm_id}", response_model=NormResponse)
async def get_norm(norm_id: str, request: Request) -> NormResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_norm(session, norm_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Norm '{norm_id}' not found")
    return NormResponse(**record)


# ---------------------------------------------------------------------------
# Document endpoints
# ---------------------------------------------------------------------------


@router.post("/documents", response_model=DocumentResponse)
async def upsert_document(req: DocumentCreate, request: Request) -> DocumentResponse:
    if req.policy_level not in DOCUMENT_POLICY_LEVELS:
        raise HTTPException(400, f"Invalid policy_level: {req.policy_level}. Must be one of: {sorted(DOCUMENT_POLICY_LEVELS)}")
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_document(session, req, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return DocumentResponse(**record)


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, request: Request) -> DocumentResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_document(session, doc_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return DocumentResponse(**record)


# ---------------------------------------------------------------------------
# Chunk endpoints
# ---------------------------------------------------------------------------


@router.post("/chunks", response_model=ChunkResponse)
async def upsert_chunk(req: ChunkCreate, request: Request) -> ChunkResponse:
    if req.status and req.status not in CHUNK_STATUSES:
        raise HTTPException(400, f"Invalid status: {req.status}. Must be one of: {sorted(CHUNK_STATUSES)}")
    embedding = get_embedding(req.body, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_chunk(session, req, embedding, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ChunkResponse(**record)


@router.get("/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(chunk_id: str, request: Request) -> ChunkResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_chunk(session, chunk_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Chunk '{chunk_id}' not found")
    return ChunkResponse(**record)


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------


@router.post("/search/chunks", response_model=List[ChunkHit])
async def search_chunks(req: ChunkSearchRequest, request: Request) -> List[ChunkHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    try:
        with request.app.state.driver.session() as session:
            hits = knowledge_repo.search_chunks(session, query_vec, req.limit, req.doc_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ChunkHit(**h) for h in hits]


@router.post("/search/frameworks", response_model=List[FrameworkHit])
async def search_frameworks(req: FrameworkSearchRequest, request: Request) -> List[FrameworkHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    try:
        with request.app.state.driver.session() as session:
            hits = knowledge_repo.search_frameworks(session, query_vec, req.limit, req.framework_id, req.statement_type)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [FrameworkHit(**h) for h in hits]


# ---------------------------------------------------------------------------
# Catalogue list endpoints
# ---------------------------------------------------------------------------


@router.get("/norms", response_model=List[NormResponse])
async def list_norms(request: Request) -> List[NormResponse]:
    try:
        with request.app.state.driver.session() as session:
            norms = knowledge_repo.list_norms(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [NormResponse(**n) for n in norms]


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(request: Request) -> List[DocumentResponse]:
    try:
        with request.app.state.driver.session() as session:
            docs = knowledge_repo.list_documents(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [DocumentResponse(**d) for d in docs]


# ---------------------------------------------------------------------------
# Diagnostic endpoints
# ---------------------------------------------------------------------------


@router.get("/incomplete-jurisdictions")
async def list_incomplete_jurisdictions(request: Request) -> dict:
    try:
        with request.app.state.driver.session() as session:
            result = knowledge_repo.list_incomplete_jurisdictions(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return result


# ---------------------------------------------------------------------------
# SUPPORTS edge endpoints
# ---------------------------------------------------------------------------


@router.post("/chunks/supports", response_model=SupportsResponse)
async def create_supports(req: SupportsCreate, request: Request) -> SupportsResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            if knowledge_repo.get_chunk(session, req.chunk_id) is None:
                raise HTTPException(status_code=404, detail=f"Chunk not found: {req.chunk_id}")
            if knowledge_repo.get_framework(session, req.framework_id) is None:
                raise HTTPException(status_code=404, detail=f"Framework not found: {req.framework_id}")
            record = knowledge_repo.create_supports_edge_framework(
                session, req.chunk_id, req.framework_id, req.confidence, req.raw_score, req.status, now
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return SupportsResponse(**record)


@router.post("/mitigates", response_model=MitigatesResponse)
async def create_mitigates(req: MitigatesCreate, request: Request) -> MitigatesResponse:
    """Create a MITIGATES edge from a Control to a Framework (ATT&CK technique).

    Direction: Control → Framework. Semantics: this control counters this technique.
    Idempotent: calling twice with the same ids is safe.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_mitigates_edge(session, req.control_id, req.framework_id, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Control or Framework node not found")
    return MitigatesResponse(**record)


@router.post("/informs", response_model=InformsResponse)
async def create_informs(req: InformsCreate, request: Request) -> InformsResponse:
    """Create an INFORMS edge from a Framework to a Control.

    Direction: Framework → Control. Semantics: this framework element shapes or guides
    this part of the control tree. Non-prescriptive — no normative weight.
    Idempotent: calling twice with the same ids is safe.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_informs_edge(session, req.framework_id, req.control_id, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Framework or Control node not found")
    return InformsResponse(**record)


@router.post("/informs/ba", response_model=InformsBAResponse, status_code=200)
async def create_informs_ba(req: InformsBACreate, request: Request) -> InformsBAResponse:
    """Create an INFORMS edge from a Framework leaf to a BusinessAttribute (tier=ict-leaf).

    Direction: Framework → BusinessAttribute. Semantics: this framework element is
    grounded in / informs this business attribute. Extends INFORMS semantically per
    ADR-004 / OQ-4 resolution. Idempotent.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_informs_ba_edge(
                session,
                req.framework_id,
                req.ba_id,
                req.rationale,
                req.similarity,
                req.source,
                now,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Framework or BusinessAttribute node not found")
    return InformsBAResponse(**record)


@router.get("/frameworks/{framework_id}/chunks", response_model=List[ChunkWithSupports])
async def get_chunks_for_framework(framework_id: str, request: Request) -> List[ChunkWithSupports]:
    try:
        with request.app.state.driver.session() as session:
            if knowledge_repo.get_framework(session, framework_id) is None:
                raise HTTPException(status_code=404, detail=f"Framework not found: {framework_id}")
            chunks = knowledge_repo.get_chunks_for_framework(session, framework_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ChunkWithSupports(**c) for c in chunks]


# ---------------------------------------------------------------------------
# Control endpoints
# ---------------------------------------------------------------------------


@router.post("/controls", response_model=ControlResponse)
async def upsert_control(req: ControlCreate, request: Request) -> ControlResponse:
    embedding = get_embedding(req.name, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_control(session, req, embedding, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ControlResponse(**record)


@router.get("/controls/{control_id}", response_model=ControlResponse)
async def get_control(control_id: str, request: Request) -> ControlResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_control(session, control_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Control '{control_id}' not found")
    return ControlResponse(**record)


@router.post("/search/controls", response_model=List[ControlHit])
async def search_controls(req: ControlSearchRequest, request: Request) -> List[ControlHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    try:
        with request.app.state.driver.session() as session:
            hits = knowledge_repo.search_controls(session, query_vec, req.limit, req.framework_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ControlHit(**h) for h in hits]


@router.get("/controls/{control_id}/chunks", response_model=List[ChunkWithSupports])
async def get_chunks_for_control(control_id: str, request: Request) -> List[ChunkWithSupports]:
    try:
        with request.app.state.driver.session() as session:
            if knowledge_repo.get_control(session, control_id) is None:
                raise HTTPException(status_code=404, detail=f"Control not found: {control_id}")
            chunks = knowledge_repo.get_chunks_for_control(session, control_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ChunkWithSupports(**c) for c in chunks]


# ---------------------------------------------------------------------------
# Traceability endpoints
# ---------------------------------------------------------------------------


@router.get("/controls/{control_id}/trace-up", response_model=TraceUpResponse)
async def trace_up(control_id: str, request: Request) -> TraceUpResponse:
    try:
        with request.app.state.driver.session() as session:
            result = knowledge_repo.trace_up(session, control_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"Control '{control_id}' not found")
    return TraceUpResponse(
        control_id=result["control_id"],
        business_attributes=[BusinessAttributeRef(**ba) for ba in result["business_attributes"]],
        norms=[NormRef(**n) for n in result["norms"]],
    )


@router.get("/controls/{control_id}/trace-down", response_model=TraceDownResponse)
async def trace_down(
    control_id: str,
    request: Request,
    org_id: Optional[str] = None,
) -> TraceDownResponse:
    try:
        with request.app.state.driver.session() as session:
            result = knowledge_repo.trace_down(session, control_id, org_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"Control '{control_id}' not found")
    return TraceDownResponse(
        control_id=result["control_id"],
        documents=[
            DocumentWithChunks(
                id=d["id"],
                title=d["title"],
                chunks=[ChunkRef(**ch) for ch in d["chunks"]],
            )
            for d in result["documents"]
        ],
        evidence_memories=[MemoryRef(**m) for m in result["evidence_memories"]],
        gap_memories=[MemoryRef(**m) for m in result["gap_memories"]],
    )


@router.get("/attributes/{attribute_id}/coverage", response_model=AttributeCoverageResponse)
async def attribute_coverage(attribute_id: str, request: Request) -> AttributeCoverageResponse:
    try:
        with request.app.state.driver.session() as session:
            result = knowledge_repo.attribute_coverage(session, attribute_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"BusinessAttribute '{attribute_id}' not found")
    return AttributeCoverageResponse(**result)


@router.post("/gap-analysis", response_model=GapAnalysisResponse)
async def gap_analysis(req: GapAnalysisRequest, request: Request) -> GapAnalysisResponse:
    try:
        with request.app.state.driver.session() as session:
            result = knowledge_repo.gap_analysis(session, req.control_ids, req.org_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return GapAnalysisResponse(
        covered=[ControlGapEntry(**e) for e in result["covered"]],
        partial=[ControlGapEntry(**e) for e in result["partial"]],
        uncovered=[ControlGapEntry(**e) for e in result["uncovered"]],
    )


# ---------------------------------------------------------------------------
# ThreatReport endpoints
# ---------------------------------------------------------------------------


@router.post("/threat-reports", response_model=ThreatReportResponse)
async def upsert_threat_report(req: ThreatReportCreate, request: Request) -> ThreatReportResponse:
    if req.scope and req.scope not in THREAT_REPORT_SCOPES:
        raise HTTPException(400, f"Invalid scope: {req.scope}. Must be one of: {sorted(THREAT_REPORT_SCOPES)}")
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_threat_report(session, req, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ThreatReportResponse(**record)


@router.get("/threat-reports/{id}", response_model=ThreatReportResponse)
async def get_threat_report(id: str, request: Request) -> ThreatReportResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_threat_report(session, threat_report_id=id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"ThreatReport '{id}' not found")
    return ThreatReportResponse(**record)


@router.get("/threat-reports", response_model=List[ThreatReportResponse])
async def list_threat_reports(request: Request) -> List[ThreatReportResponse]:
    try:
        with request.app.state.driver.session() as session:
            records = knowledge_repo.list_threat_reports(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ThreatReportResponse(**r) for r in records]


# ---------------------------------------------------------------------------
# Threat endpoints
# ---------------------------------------------------------------------------


@router.post("/threats", response_model=ThreatResponse)
async def upsert_threat(req: ThreatCreate, request: Request) -> ThreatResponse:
    embedding = get_embedding(req.text, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_threat(session, req, embedding, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ThreatResponse(**record)


@router.get("/threats/{id}", response_model=ThreatResponse)
async def get_threat(id: str, request: Request) -> ThreatResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_threat(session, threat_id=id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Threat '{id}' not found")
    return ThreatResponse(**record)


@router.get("/threats", response_model=List[ThreatResponse])
async def list_threats(request: Request) -> List[ThreatResponse]:
    try:
        with request.app.state.driver.session() as session:
            records = knowledge_repo.list_threats(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ThreatResponse(**r) for r in records]


@router.post("/search/threats", response_model=List[ThreatHit])
async def search_threats(req: ThreatSearchRequest, request: Request) -> List[ThreatHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    try:
        with request.app.state.driver.session() as session:
            hits = knowledge_repo.search_threats(session, query_vec, req.limit)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ThreatHit(**h) for h in hits]


# ---------------------------------------------------------------------------
# Asset endpoints
# ---------------------------------------------------------------------------


@router.post("/assets", response_model=AssetResponse)
async def upsert_asset(req: AssetCreate, request: Request) -> AssetResponse:
    if req.exposure and req.exposure not in ASSET_EXPOSURES:
        raise HTTPException(400, f"Invalid exposure: {req.exposure}. Must be one of: {sorted(ASSET_EXPOSURES)}")
    if req.data_classification and req.data_classification not in ASSET_DATA_CLASSIFICATIONS:
        raise HTTPException(400, f"Invalid data_classification: {req.data_classification}. Must be one of: {sorted(ASSET_DATA_CLASSIFICATIONS)}")
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.upsert_asset(session, req, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return AssetResponse(**record)


@router.get("/assets/{id}", response_model=AssetResponse)
async def get_asset(id: str, request: Request) -> AssetResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_asset(session, asset_id=id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"Asset '{id}' not found")
    return AssetResponse(**record)


@router.get("/assets", response_model=List[AssetResponse])
async def list_assets(request: Request) -> List[AssetResponse]:
    try:
        with request.app.state.driver.session() as session:
            records = knowledge_repo.list_assets(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [AssetResponse(**r) for r in records]


# ---------------------------------------------------------------------------
# Edge endpoints: IDENTIFIES, MAPPED_TO_TECHNIQUE, TARGETS
# ---------------------------------------------------------------------------


@router.post("/identifies", response_model=IdentifiesResponse)
async def create_identifies(req: IdentifiesCreate, request: Request) -> IdentifiesResponse:
    if req.severity not in IDENTIFIES_SEVERITIES:
        raise HTTPException(400, f"Invalid severity: {req.severity}. Must be one of: {sorted(IDENTIFIES_SEVERITIES)}")
    if req.confidence not in IDENTIFIES_CONFIDENCES:
        raise HTTPException(400, f"Invalid confidence: {req.confidence}. Must be one of: {sorted(IDENTIFIES_CONFIDENCES)}")
    if req.trend not in IDENTIFIES_TRENDS:
        raise HTTPException(400, f"Invalid trend: {req.trend}. Must be one of: {sorted(IDENTIFIES_TRENDS)}")
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_identifies_edge(
                session,
                req.threat_report_id,
                req.threat_id,
                req.severity,
                req.confidence,
                req.trend,
                req.source_terminology,
                now,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="ThreatReport or Threat node not found")
    return IdentifiesResponse(**record)


@router.post("/mapped-to-technique", response_model=MappedToTechniqueResponse)
async def create_mapped_to_technique(req: MappedToTechniqueCreate, request: Request) -> MappedToTechniqueResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_mapped_to_technique_edge(session, req.threat_id, req.framework_id, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Threat or Framework node not found")
    return MappedToTechniqueResponse(**record)


@router.post("/targets", response_model=TargetsResponse)
async def create_targets(req: TargetsCreate, request: Request) -> TargetsResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_targets_edge(session, req.threat_id, req.asset_id, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Threat or Asset node not found")
    return TargetsResponse(**record)


# ---------------------------------------------------------------------------
# Traversal endpoints
# ---------------------------------------------------------------------------


@router.get("/threats/{id}/reports", response_model=List[ThreatReportWithEdge])
async def list_threat_reports_for_threat(id: str, request: Request) -> List[ThreatReportWithEdge]:
    try:
        with request.app.state.driver.session() as session:
            records = knowledge_repo.list_threat_reports_for_threat(session, id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ThreatReportWithEdge(**r) for r in records]


@router.get("/threat-reports/{id}/threats", response_model=List[ThreatWithSeverity])
async def list_threats_for_report(id: str, request: Request) -> List[ThreatWithSeverity]:
    try:
        with request.app.state.driver.session() as session:
            records = knowledge_repo.list_threats_for_report(session, id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [ThreatWithSeverity(**r) for r in records]


# ---------------------------------------------------------------------------
# Threat merge endpoint (WP-138b)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# WP-113 — BusinessAttribute endpoints
# ---------------------------------------------------------------------------


@router.post("/business-attributes", response_model=BusinessAttributeResponse, status_code=201)
async def upsert_business_attribute(req: BusinessAttributeCreate, request: Request) -> BusinessAttributeResponse:
    if req.status == "deprecated":
        if not req.superseded_by:
            raise HTTPException(
                status_code=400,
                detail="superseded_by is required when status is 'deprecated'",
            )
    text = req.description or req.name
    embedding = get_embedding(text, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            if req.status == "deprecated":
                ref = knowledge_repo.get_business_attribute(session, req.superseded_by)
                if ref is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"superseded_by '{req.superseded_by}' does not resolve to an existing BusinessAttribute",
                    )
            record = knowledge_repo.upsert_business_attribute(session, req, embedding, now)
    except HTTPException:
        raise
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return BusinessAttributeResponse(**record)


@router.get("/business-attributes/{ba_id}", response_model=BusinessAttributeResponse)
async def get_business_attribute(ba_id: str, request: Request) -> BusinessAttributeResponse:
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.get_business_attribute(session, ba_id)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"BusinessAttribute '{ba_id}' not found")
    return BusinessAttributeResponse(**record)


@router.get("/business-attributes", response_model=List[BusinessAttributeResponse])
async def list_business_attributes(
    request: Request,
    include_deprecated: bool = False,
    tier: Optional[str] = None,
    group: Optional[str] = None,
) -> List[BusinessAttributeResponse]:
    try:
        with request.app.state.driver.session() as session:
            records = knowledge_repo.list_business_attributes(
                session,
                include_deprecated=include_deprecated,
                tier=tier,
                group=group,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [BusinessAttributeResponse(**r) for r in records]


@router.post("/influence", response_model=InfluenceResponse, status_code=201)
async def create_influence(req: InfluenceCreate, request: Request) -> InfluenceResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_influence_edge(
                session,
                source_id=req.source_id,
                target_id=req.target_id,
                polarity=req.polarity,
                severity=req.severity,
                rationale=req.rationale,
                status=req.status,
                now=now,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Source or target node not found")
    return InfluenceResponse(**record)


@router.post("/contains", response_model=ContainsResponse, status_code=201)
async def create_contains(req: ContainsCreate, request: Request) -> ContainsResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            record = knowledge_repo.create_contains_edge(
                session,
                parent_id=req.parent_id,
                child_id=req.child_id,
                rationale=req.rationale,
                now=now,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Parent or child node not found")
    return ContainsResponse(**record)


# ---------------------------------------------------------------------------
# Threat merge endpoint (WP-138b)
# ---------------------------------------------------------------------------


@router.post("/threats/{threat_id}/merge", response_model=ThreatMergeResponse)
async def merge_threat(
    threat_id: str, req: ThreatMergeRequest, request: Request
) -> ThreatMergeResponse:
    """Merge source Threat into target Threat.

    Rewires all IDENTIFIES (ThreatReport→source) and MAPPED_TO_TECHNIQUE
    (source→Framework) edges to the target, then archives the source.
    Existing target edges from the same ThreatReport are preserved unchanged
    (ON CREATE only — no overwrite of target's assessment properties).

    Returns HTTP 400 if source == target.
    Returns HTTP 404 if either node is missing or already archived.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    if threat_id == req.target_id:
        raise HTTPException(status_code=400, detail="Source and target must differ")
    try:
        with request.app.state.driver.session() as session:
            result = knowledge_repo.merge_threat(session, threat_id, req.target_id)
            # ADR-001: memory_repo import must be local, never at module level
            from memory_service import memory_repo
            memory_repo.append_operation_log(session, {
                "operation": "merge_threat",
                "memory_id": threat_id,
                "source_id": threat_id,
                "target_id": req.target_id,
                "ran_at": now,
                "identifies_rewired": result["identifies_rewired"],
                "techniques_rewired": result["techniques_rewired"],
            })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ThreatMergeResponse(**result)
