# memory_service/main.py

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel, Field, model_validator

from memory_service import memory_repo
from memory_service.config import get_driver, settings
from memory_service.embeddings import get_embedding


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.driver = get_driver(settings)
    yield
    app.state.driver.close()


app = FastAPI(
    title="Graph Memory Service",
    description="Local graph + vector memory API backed by Memgraph",
    version="0.1.0",
    lifespan=lifespan,
)


class MemoryType(str, Enum):
    fact = "fact"
    decision = "decision"
    insight = "insight"
    todo = "todo"
    event = "event"
    observation = "observation"


class HealthResponse(BaseModel):
    status: str = "ok"


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse()


class AddMemoryRequest(BaseModel):
    fact: Optional[str] = None   # populated by validator; None means "not yet provided"
    so_what: Optional[str] = None
    text: Optional[str] = None   # deprecated alias for fact
    type: MemoryType
    tags: List[str] = []
    agent_id: str
    project_id: Optional[str] = None
    person_ids: List[str] = []
    strand_ids: List[str] = []
    importance: int = Field(default=3, ge=1, le=5)
    related_ids: Optional[List[str]] = None
    cause_ids: List[str] = []
    effect_ids: List[str] = []

    @model_validator(mode="before")
    @classmethod
    def resolve_fact_and_text(cls, values: dict) -> dict:
        fact = values.get("fact")
        text = values.get("text")
        if fact is None and text is None:
            raise ValueError("Either 'fact' or 'text' must be provided")
        if fact is None and text is not None:
            values["fact"] = text
        # Derive text from fact + so_what
        resolved_fact = values["fact"]  # guaranteed non-None by guard above
        so_what = values.get("so_what")
        values["text"] = resolved_fact + (" " + so_what if so_what else "")
        return values


class AddMemoryResponse(BaseModel):
    memory_id: str


@app.post("/memory", response_model=AddMemoryResponse)
async def add_memory(req: AddMemoryRequest, request: Request) -> AddMemoryResponse:
    embedding = get_embedding(req.text)
    memory_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            memory_repo.add_memory(session, req, memory_id, embedding, now)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return AddMemoryResponse(memory_id=memory_id)


class SearchMemoryRequest(BaseModel):
    query: str
    tags: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    project_ids: Optional[List[str]] = None
    limit: int = Field(default=10, ge=1, le=100)
    max_hops: int = Field(default=1, ge=0, le=3)
    traversal_direction: Literal["none", "causes", "effects", "both"] = "none"


class MemoryHit(BaseModel):
    id: str
    text: str
    type: MemoryType
    tags: List[str]
    importance: Optional[int] = None
    neighbours: List[str] = []


class SearchMemoryResponse(BaseModel):
    memories: List[MemoryHit]


@app.post("/memory/search", response_model=SearchMemoryResponse)
async def search_memory(req: SearchMemoryRequest, request: Request) -> SearchMemoryResponse:
    query_embedding = get_embedding(req.query)
    try:
        with request.app.state.driver.session() as session:
            results = memory_repo.search_memories(session, req, query_embedding)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return SearchMemoryResponse(
        memories=[
            MemoryHit(
                id=r["id"],
                text=r["text"],
                type=r["type"],
                tags=r["tags"],
                importance=r["importance"],
                neighbours=r["neighbours"],
            )
            for r in results
        ]
    )


class WakeUpMemoryItem(BaseModel):
    id: str
    text: str
    type: MemoryType
    tags: List[str]
    importance: Optional[int] = None
    created_at: Optional[str] = None
    strand_id: Optional[str] = None


class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]          # core (importance-ranked)
    topic_memories: List[WakeUpMemoryItem]    # topic-only; empty when no --topic


@app.get("/memory/wake-up", response_model=WakeUpResponse)
async def wake_up(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
) -> WakeUpResponse:
    topic_embedding = get_embedding(topic) if topic else None
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.wake_up(session, limit=limit, topic_embedding=topic_embedding)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return WakeUpResponse(
        memories=[WakeUpMemoryItem(**r) for r in result["core"]],
        topic_memories=[WakeUpMemoryItem(**r) for r in result["topic"]],
    )


class StrandItem(BaseModel):
    id: str
    name: str
    description: str
    category: str


class StrandsResponse(BaseModel):
    strands: List[StrandItem]


class PersonItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class PersonsResponse(BaseModel):
    persons: List[PersonItem]


class CreatePersonRequest(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


@app.get("/strands", response_model=StrandsResponse)
async def list_strands(request: Request) -> StrandsResponse:
    try:
        with request.app.state.driver.session() as session:
            strands = memory_repo.list_strands(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return StrandsResponse(strands=[StrandItem(**s) for s in strands])


@app.get("/person", response_model=PersonsResponse)
async def list_persons(request: Request) -> PersonsResponse:
    try:
        with request.app.state.driver.session() as session:
            persons = memory_repo.list_persons(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return PersonsResponse(persons=[PersonItem(**p) for p in persons])


@app.post("/person", response_model=PersonItem)
async def create_person(req: CreatePersonRequest, request: Request) -> PersonItem:
    try:
        with request.app.state.driver.session() as session:
            person = memory_repo.upsert_person(session, req)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return PersonItem(**person)


class NodeLabel(str, Enum):
    memory = "Memory"
    strand = "Strand"
    agent = "Agent"
    person = "Person"
    project = "Project"


class GraphNode(BaseModel):
    id: str
    label: NodeLabel
    type: Optional[MemoryType] = None  # only present for Memory nodes
    tags: List[str] = []


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: str
    weight: Optional[float] = None


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


@app.get("/memory/graph", response_model=GraphResponse)
async def get_graph(
    project_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    tag: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> GraphResponse:
    # TODO: Implement a query against Memgraph to return a filtered subgraph
    raise NotImplementedError("get_graph endpoint not implemented yet")
