# memory_service/main.py

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import List, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel, Field, model_validator

from memory_service import memory_repo
from memory_service.config import get_driver, settings
from memory_service.embeddings import get_embedding, get_embedding_dimension


@asynccontextmanager
async def lifespan(app: FastAPI):
    driver = get_driver(settings)
    driver.verify_connectivity()
    if settings.embedding_preload_on_startup:
        get_embedding_dimension()
    app.state.driver = driver
    try:
        yield
    finally:
        driver.close()


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
            memory_repo.add_memory(
                session, req, memory_id, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
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


def _do_recall_increment(driver, memory_ids: list[str]) -> None:
    """Background task: fire recall increment for searched memories."""
    try:
        with driver.session() as session:
            memory_repo.recall_increment(
                session,
                memory_ids,
                strength_increment=settings.recall_strength_increment,
                edge_increment=settings.edge_recall_increment,
            )
    except Exception:
        pass  # best-effort; do not surface errors to the search response


@app.post("/memory/search", response_model=SearchMemoryResponse)
async def search_memory(
    req: SearchMemoryRequest, request: Request, background_tasks: BackgroundTasks
) -> SearchMemoryResponse:
    query_embedding = get_embedding(req.query)
    try:
        with request.app.state.driver.session() as session:
            results = memory_repo.search_memories(session, req, query_embedding)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc

    memory_ids = [r["id"] for r in results]
    if memory_ids:
        background_tasks.add_task(_do_recall_increment, request.app.state.driver, memory_ids)

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
    maintenance_warning: Optional[str] = None


@app.get("/memory/wake-up", response_model=WakeUpResponse)
async def wake_up(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    topic: Optional[str] = Query(default=None),
) -> WakeUpResponse:
    # NOTE: wake-up intentionally does NOT call recall_increment.
    # Wake-up is passive context priming, not active recall. Strengthening nodes here
    # would create a feedback loop where frequently-loaded memories self-reinforce
    # regardless of whether they were actually used in the session.
    # Strength signals come from: search (automatic) and explicit reinforce at close-session
    # (companion-driven, for memories that genuinely shaped the session).
    # Do NOT add recall_increment here without revisiting this design decision.
    topic_embedding = get_embedding(topic) if topic else None
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.wake_up(session, limit=limit, topic_embedding=topic_embedding)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc

    # Check maintenance staleness — best-effort, do not fail wake-up if this errors
    maintenance_warning = None
    try:
        with request.app.state.driver.session() as maint_session:
            ts = memory_repo.get_system_timestamps(maint_session)
        last_long = ts.get("last_long_rest_at")
        if last_long is None:
            maintenance_warning = (
                "Note: long-rest has never run — consider running "
                "`memory long-rest` before this session."
            )
        else:
            last_dt = memory_repo._parse_iso(last_long)
            days_ago = (datetime.now(tz=timezone.utc) - last_dt).total_seconds() / 86400.0
            if days_ago > settings.long_rest_recency_days:
                maintenance_warning = (
                    f"Note: long-rest last ran {days_ago:.0f} day(s) ago — "
                    "consider running `memory long-rest` before this session."
                )
    except Exception:
        pass  # best-effort; never surface maintenance errors to wake-up

    return WakeUpResponse(
        memories=[WakeUpMemoryItem(**r) for r in result["core"]],
        topic_memories=[WakeUpMemoryItem(**r) for r in result["topic"]],
        maintenance_warning=maintenance_warning,
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


class DecayPassResponse(BaseModel):
    nodes_updated: int
    edges_updated: int


class WeakEdgeItem(BaseModel):
    source_id: str
    target_id: str
    relation: str
    weight: float
    activation_count: Optional[int] = None


class WeakEdgesResponse(BaseModel):
    edges: List[WeakEdgeItem]


@app.post("/memory/maintenance/decay", response_model=DecayPassResponse)
async def run_decay_pass(request: Request) -> DecayPassResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.decay_pass(session, "", now_iso, settings.min_memory_strength)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return DecayPassResponse(**result)


@app.get("/memory/maintenance/weak-edges", response_model=WeakEdgesResponse)
async def get_weak_edges(request: Request) -> WeakEdgesResponse:
    try:
        with request.app.state.driver.session() as session:
            edges = memory_repo.list_weak_edges(session, settings.edge_prune_threshold)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return WeakEdgesResponse(edges=[WeakEdgeItem(**e) for e in edges])


class ShortRestResponse(BaseModel):
    nodes_decayed: int
    edges_decayed: int
    dry_run: bool


@app.post("/memory/maintenance/short-rest", response_model=ShortRestResponse)
async def short_rest(
    request: Request,
    dry_run: bool = Query(default=False),
) -> ShortRestResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.short_rest(
                session,
                now_iso=now_iso,
                recency_days=settings.short_rest_recency_days,
                min_strength=settings.min_memory_strength,
                edge_modulation_factor=settings.edge_modulation_factor,
                edge_modulation_cap=settings.edge_modulation_cap,
                dry_run=dry_run,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ShortRestResponse(**result)


class LongRestResponse(BaseModel):
    nodes_decayed: int
    edges_decayed: int
    edges_discovered: int
    edges_pruned: int
    dry_run: bool


@app.post("/memory/maintenance/long-rest", response_model=LongRestResponse)
async def long_rest(
    request: Request,
    dry_run: bool = Query(default=False),
    prune: bool = Query(default=False),
) -> LongRestResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.long_rest(
                session,
                now_iso=now_iso,
                min_strength=settings.min_memory_strength,
                edge_modulation_factor=settings.edge_modulation_factor,
                edge_modulation_cap=settings.edge_modulation_cap,
                rediscovery_strength_threshold=settings.rediscovery_strength_threshold,
                edge_hard_prune_floor=settings.edge_hard_prune_floor,
                edge_hard_prune_min_days=settings.edge_hard_prune_min_days,
                edge_decay_rate=settings.edge_decay_rate,
                dry_run=dry_run,
                prune=prune,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return LongRestResponse(**result)


class MaintenanceStatsNodes(BaseModel):
    total: int
    mean_strength: float
    median_strength: float
    below_prune_floor: int
    at_max_strength: int


class MaintenanceStatsEdges(BaseModel):
    total: int
    mean_weight: float
    weak_count: int


class MaintenanceStatsMaintenance(BaseModel):
    last_short_rest_at: Optional[str] = None
    last_long_rest_at: Optional[str] = None
    short_rest_overdue: bool
    long_rest_overdue: bool


class MaintenanceStatsResponse(BaseModel):
    nodes: MaintenanceStatsNodes
    edges: MaintenanceStatsEdges
    maintenance: MaintenanceStatsMaintenance


@app.get("/memory/maintenance/stats", response_model=MaintenanceStatsResponse)
async def maintenance_stats(request: Request) -> MaintenanceStatsResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            result = memory_repo.maintenance_stats(
                session,
                now_iso=now_iso,
                edge_prune_threshold=settings.edge_hard_prune_floor,
                short_rest_recency_days=settings.short_rest_recency_days,
                long_rest_recency_days=settings.long_rest_recency_days,
            )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return MaintenanceStatsResponse(**result)


class ReinforceRequest(BaseModel):
    signal: Literal["explicit"] = "explicit"
    co_recalled_ids: List[str] = []


class ReinforceResponse(BaseModel):
    memory_id: str
    new_strength: float


@app.post("/memory/{memory_id}/reinforce", response_model=ReinforceResponse)
async def reinforce_memory(
    memory_id: str, req: ReinforceRequest, request: Request
) -> ReinforceResponse:
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            new_strength = memory_repo.reinforce_memory(
                session,
                memory_id,
                strength_increment=settings.explicit_strength_increment,
                edge_increment=settings.edge_explicit_increment,
                co_recalled_ids=req.co_recalled_ids,
                now_iso=now_iso,
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ReinforceResponse(memory_id=memory_id, new_strength=new_strength)


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
