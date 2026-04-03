# memory_service/knowledge_routes.py
#
# FastAPI router for the /knowledge endpoints.
# Registered in main.py only when ENABLE_KNOWLEDGE_LAYER=true.
#
# ADR-001: this file must NOT import from memory_repo. All cross-layer
# logic lives in knowledge_bridge.py.

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from memory_service import knowledge_repo
from memory_service.config import settings
from memory_service.embeddings import get_embedding

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FrameworkCreate(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    description: Optional[str] = None


class FrameworkResponse(BaseModel):
    id: str
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    created_at: str


class ControlCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework_id: str
    parent_id: Optional[str] = None  # if set, creates CONTAINS edge parent→this


class ControlResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework_id: str
    created_at: str


class NormCreate(BaseModel):
    id: str
    name: str
    text: str                           # requirement text; used for embedding
    status: str = "draft"              # draft | active | deprecated
    effective_date: Optional[str] = None
    control_id: Optional[str] = None  # if set, creates IMPLEMENTS edge norm→control
    doc_id: Optional[str] = None      # if set, creates SOURCED_FROM edge norm→doc


class NormResponse(BaseModel):
    id: str
    name: str
    text: str
    status: str
    effective_date: Optional[str] = None
    created_at: str


class DocumentCreate(BaseModel):
    id: str
    title: str
    doc_type: str                       # policy | procedure | standard | guideline
    source_url: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    doc_type: str
    source_url: Optional[str] = None
    created_at: str


class ChunkCreate(BaseModel):
    id: str
    text: str                           # chunk content; used for embedding
    sequence: int
    doc_id: str                         # parent document; creates HAS_CHUNK edge
    prev_chunk_id: Optional[str] = None  # if set, creates HAS_NEXT edge prev→this


class ChunkResponse(BaseModel):
    id: str
    text: str
    sequence: int
    doc_id: str
    created_at: str


# ---------------------------------------------------------------------------
# Search request/response models
# ---------------------------------------------------------------------------


class ControlSearchRequest(BaseModel):
    query: str
    limit: int = 10
    framework_id: Optional[str] = None


class ChunkSearchRequest(BaseModel):
    query: str
    limit: int = 10
    doc_id: Optional[str] = None


class ControlHit(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    framework_id: str
    created_at: str
    distance: float


class ChunkHit(BaseModel):
    id: str
    text: str
    sequence: int
    doc_id: str
    created_at: str
    distance: float


class SupportsCreate(BaseModel):
    chunk_id: str
    control_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: str = "auto-inferred"


class SupportsResponse(BaseModel):
    chunk_id: str
    control_id: str
    confidence: float
    status: str
    created_at: str


class ChunkWithSupports(BaseModel):
    id: str
    text: str
    sequence: int
    doc_id: str
    created_at: str
    confidence: float
    status: str


# ---------------------------------------------------------------------------
# Framework endpoints
# ---------------------------------------------------------------------------


@router.post("/frameworks", response_model=FrameworkResponse)
async def upsert_framework(req: FrameworkCreate, request: Request) -> FrameworkResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        record = knowledge_repo.upsert_framework(session, req, now)
    return FrameworkResponse(**record)


@router.get("/frameworks/{framework_id}", response_model=FrameworkResponse)
async def get_framework(framework_id: str, request: Request) -> FrameworkResponse:
    with request.app.state.driver.session() as session:
        record = knowledge_repo.get_framework(session, framework_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Framework '{framework_id}' not found")
    return FrameworkResponse(**record)


# ---------------------------------------------------------------------------
# Control endpoints
# ---------------------------------------------------------------------------


@router.post("/controls", response_model=ControlResponse)
async def upsert_control(req: ControlCreate, request: Request) -> ControlResponse:
    embedding = get_embedding(req.name, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        record = knowledge_repo.upsert_control(session, req, embedding, now)
    return ControlResponse(**record)


@router.get("/controls/{control_id}", response_model=ControlResponse)
async def get_control(control_id: str, request: Request) -> ControlResponse:
    with request.app.state.driver.session() as session:
        record = knowledge_repo.get_control(session, control_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Control '{control_id}' not found")
    return ControlResponse(**record)


# ---------------------------------------------------------------------------
# Norm endpoints
# ---------------------------------------------------------------------------


@router.post("/norms", response_model=NormResponse)
async def upsert_norm(req: NormCreate, request: Request) -> NormResponse:
    embedding = get_embedding(req.text, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        record = knowledge_repo.upsert_norm(session, req, embedding, now)
    return NormResponse(**record)


@router.get("/norms/{norm_id}", response_model=NormResponse)
async def get_norm(norm_id: str, request: Request) -> NormResponse:
    with request.app.state.driver.session() as session:
        record = knowledge_repo.get_norm(session, norm_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Norm '{norm_id}' not found")
    return NormResponse(**record)


# ---------------------------------------------------------------------------
# Document endpoints
# ---------------------------------------------------------------------------


@router.post("/documents", response_model=DocumentResponse)
async def upsert_document(req: DocumentCreate, request: Request) -> DocumentResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        record = knowledge_repo.upsert_document(session, req, now)
    return DocumentResponse(**record)


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, request: Request) -> DocumentResponse:
    with request.app.state.driver.session() as session:
        record = knowledge_repo.get_document(session, doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return DocumentResponse(**record)


# ---------------------------------------------------------------------------
# Chunk endpoints
# ---------------------------------------------------------------------------


@router.post("/chunks", response_model=ChunkResponse)
async def upsert_chunk(req: ChunkCreate, request: Request) -> ChunkResponse:
    embedding = get_embedding(req.text, model_name=settings.knowledge_embedding_model)
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        record = knowledge_repo.upsert_chunk(session, req, embedding, now)
    return ChunkResponse(**record)


@router.get("/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(chunk_id: str, request: Request) -> ChunkResponse:
    with request.app.state.driver.session() as session:
        record = knowledge_repo.get_chunk(session, chunk_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Chunk '{chunk_id}' not found")
    return ChunkResponse(**record)


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------


@router.post("/search/controls", response_model=List[ControlHit])
async def search_controls(req: ControlSearchRequest, request: Request) -> List[ControlHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    with request.app.state.driver.session() as session:
        hits = knowledge_repo.search_controls(session, query_vec, req.limit, req.framework_id)
    return [ControlHit(**h) for h in hits]


@router.post("/search/chunks", response_model=List[ChunkHit])
async def search_chunks(req: ChunkSearchRequest, request: Request) -> List[ChunkHit]:
    query_vec = get_embedding(req.query, model_name=settings.knowledge_embedding_model)
    with request.app.state.driver.session() as session:
        hits = knowledge_repo.search_chunks(session, query_vec, req.limit, req.doc_id)
    return [ChunkHit(**h) for h in hits]


# ---------------------------------------------------------------------------
# Catalogue list endpoints
# ---------------------------------------------------------------------------


@router.get("/norms", response_model=List[NormResponse])
async def list_norms(request: Request) -> List[NormResponse]:
    with request.app.state.driver.session() as session:
        norms = knowledge_repo.list_norms(session)
    return [NormResponse(**n) for n in norms]


@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(request: Request) -> List[DocumentResponse]:
    with request.app.state.driver.session() as session:
        docs = knowledge_repo.list_documents(session)
    return [DocumentResponse(**d) for d in docs]


# ---------------------------------------------------------------------------
# Diagnostic endpoints
# ---------------------------------------------------------------------------


@router.get("/incomplete-jurisdictions")
async def list_incomplete_jurisdictions(request: Request) -> dict:
    with request.app.state.driver.session() as session:
        result = knowledge_repo.list_incomplete_jurisdictions(session)
    return result


# ---------------------------------------------------------------------------
# SUPPORTS edge endpoints
# ---------------------------------------------------------------------------


@router.post("/chunk/supports", response_model=SupportsResponse)
async def create_supports(req: SupportsCreate, request: Request) -> SupportsResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    with request.app.state.driver.session() as session:
        if knowledge_repo.get_chunk(session, req.chunk_id) is None:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {req.chunk_id}")
        if knowledge_repo.get_control(session, req.control_id) is None:
            raise HTTPException(status_code=404, detail=f"Control not found: {req.control_id}")
        record = knowledge_repo.create_supports_edge(
            session, req.chunk_id, req.control_id, req.confidence, req.status, now
        )
    if record is None:
        raise HTTPException(status_code=404, detail="Chunk or Control not found")
    return SupportsResponse(**record)


@router.get("/controls/{control_id}/chunks", response_model=List[ChunkWithSupports])
async def get_chunks_for_control(control_id: str, request: Request) -> List[ChunkWithSupports]:
    with request.app.state.driver.session() as session:
        if knowledge_repo.get_control(session, control_id) is None:
            raise HTTPException(status_code=404, detail=f"Control not found: {control_id}")
        chunks = knowledge_repo.get_chunks_for_control(session, control_id)
    return [ChunkWithSupports(**c) for c in chunks]
