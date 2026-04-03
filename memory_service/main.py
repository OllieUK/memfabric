# memory_service/main.py

import subprocess
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import List, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from neo4j.exceptions import ServiceUnavailable
from pydantic import BaseModel, Field, model_validator

from memory_service import memory_repo
from memory_service.config import get_driver, settings
from memory_service.embeddings import get_embedding, get_embedding_dimension



def _get_build_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        return result.stdout.strip()[:7]
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


try:
    _SERVICE_VERSION = _pkg_version("graph-memory-fabric")
except PackageNotFoundError:
    _SERVICE_VERSION = "unknown"

_BUILD_HASH = _get_build_hash()


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
    version: str = _SERVICE_VERSION
    build: str = _BUILD_HASH


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
    control_ids: List[str] = []
    doc_ids: List[str] = []
    control_relationship_type: Optional[Literal["context", "evidence", "gap"]] = None
    org_id: Optional[str] = None

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
    deduplicated: bool = False
    strand_ids: List[str] = []


@app.post("/memory", response_model=AddMemoryResponse)
async def add_memory(req: AddMemoryRequest, request: Request) -> AddMemoryResponse:
    embedding = get_embedding(req.text)
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            existing_id = memory_repo.find_duplicate_memory(
                session,
                req.fact,
                embedding,
                settings.memory_dedup_threshold,
            )
            if existing_id is not None:
                memory_repo.reinforce_memory(
                    session,
                    existing_id,
                    strength_increment=settings.explicit_strength_increment,
                    edge_increment=settings.edge_explicit_increment,
                    co_recalled_ids=[],
                    now_iso=now,
                    consolidated_decay_rate=settings.memory_consolidated_decay_rate,
                )
                # NOTE: control_ids/doc_ids silently ignored on dedup path — same behaviour
                # as strand_ids. The existing memory is reinforced, not a new one created.
                return AddMemoryResponse(memory_id=existing_id, deduplicated=True)
            memory_id = str(uuid.uuid4())
            memory_repo.add_memory(
                session, req, memory_id, embedding, now,
                decay_rate=settings.memory_initial_decay_rate,
                initial_strength_factor=settings.initial_strength_factor,
                importance_floor_factor=settings.importance_floor_factor,
            )
            if settings.enable_knowledge_layer and (req.control_ids or req.doc_ids):
                from memory_service import knowledge_bridge
                if req.control_ids:
                    missing = knowledge_bridge.validate_controls(session, req.control_ids)
                    if missing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unknown control_ids: {missing}",
                        )
                if req.doc_ids:
                    missing = knowledge_bridge.validate_documents(session, req.doc_ids)
                    if missing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unknown doc_ids: {missing}",
                        )
                if req.control_ids:
                    knowledge_bridge.link_controls(
                        session, memory_id, req.control_ids,
                        req.control_relationship_type, req.org_id,
                    )
                knowledge_bridge.link_documents(session, memory_id, req.doc_ids)
            return AddMemoryResponse(memory_id=memory_id, strand_ids=req.strand_ids)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc


class SearchMemoryRequest(BaseModel):
    query: str
    tags: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    project_ids: Optional[List[str]] = None
    person_ids: Optional[List[str]] = None
    limit: int = Field(default=10, ge=1, le=100)
    max_hops: int = Field(default=1, ge=0, le=3)
    traversal_direction: Literal["none", "causes", "effects", "both"] = "none"
    min_importance: Optional[int] = Field(default=None, ge=1, le=5)
    min_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    neighbour_cap: int = Field(default=3, ge=0, le=10)


class AssociatedMemoryHit(BaseModel):
    id: str
    text: str
    type: MemoryType
    importance: Optional[int] = None
    edge_weight: float


class MemoryHit(BaseModel):
    id: str
    text: str
    type: MemoryType
    tags: List[str]
    importance: Optional[int] = None
    score: Optional[float] = None
    strand_ids: List[str] = []
    neighbours: List[str] = []
    associated: List[AssociatedMemoryHit] = []
    controls: List[dict] = []
    documents: List[dict] = []


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
            results = memory_repo.search_memories(session, req, query_embedding, settings.search_neighbour_cap)
            primary_ids = {r["id"] for r in results}
            # Disable associated expansion for person-anchored path (no score, ABOUT edges only)
            cap = req.neighbour_cap if not req.person_ids else 0
            associated_map = memory_repo.fetch_associated(
                session, list(primary_ids), cap, primary_ids
            )
            hydration = {}
            if settings.enable_knowledge_layer and primary_ids:
                from memory_service import knowledge_bridge
                hydration = knowledge_bridge.hydrate_controls_and_documents(
                    session, list(primary_ids)
                )
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc

    memory_ids = list(primary_ids)
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
                score=r.get("score"),
                strand_ids=r["strand_ids"],
                neighbours=r["neighbours"],
                associated=[
                    AssociatedMemoryHit(**a)
                    for a in associated_map.get(r["id"], [])
                ],
                controls=hydration.get(r["id"], {}).get("controls", []),
                documents=hydration.get(r["id"], {}).get("documents", []),
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


class MaintenanceStatus(BaseModel):
    short_rest_overdue: bool
    long_rest_overdue: bool
    short_rest_days_ago: Optional[float] = None
    long_rest_days_ago: Optional[float] = None
    recommended_action: Optional[str] = None


def _compute_maintenance_status(
    last_short_rest_at: Optional[str],
    last_long_rest_at: Optional[str],
    now_iso: str,
    short_rest_recency_days: int,
    long_rest_recency_days: int,
) -> dict:
    """Compute structured maintenance status for the wake-up response.

    Returns a dict matching MaintenanceStatus fields.
    recommended_action is None when no action is needed.
    """
    now = memory_repo._parse_iso(now_iso)

    def _days_since(ts: Optional[str]) -> Optional[float]:
        if ts is None:
            return None
        try:
            return (now - memory_repo._parse_iso(ts)).total_seconds() / 86400.0
        except (ValueError, TypeError):
            return None

    short_days = _days_since(last_short_rest_at)
    long_days = _days_since(last_long_rest_at)

    short_overdue = short_days is None or short_days > short_rest_recency_days
    long_overdue = long_days is None or long_days > long_rest_recency_days

    if last_long_rest_at is None:
        action = "long-rest has never run — run `memory long-rest` before this session"
    elif last_short_rest_at is None:
        action = "short-rest has never run — run `memory short-rest`"
    elif short_overdue and long_overdue:
        action = "both short-rest and long-rest are overdue — run `memory long-rest` (covers both)"
    elif long_overdue:
        action = f"long-rest is overdue ({long_days:.0f}d) — run `memory long-rest`"
    elif short_overdue:
        action = f"short-rest is overdue ({short_days:.0f}d) — run `memory short-rest`"
    else:
        action = None

    return {
        "short_rest_overdue": short_overdue,
        "long_rest_overdue": long_overdue,
        "short_rest_days_ago": round(short_days, 1) if short_days is not None else None,
        "long_rest_days_ago": round(long_days, 1) if long_days is not None else None,
        "recommended_action": action,
    }


class WakeUpResponse(BaseModel):
    memories: List[WakeUpMemoryItem]          # core (importance-ranked)
    topic_memories: List[WakeUpMemoryItem]    # topic-only; empty when no --topic
    maintenance_status: MaintenanceStatus


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
    maintenance_status_data = {
        "short_rest_overdue": False,
        "long_rest_overdue": False,
        "short_rest_days_ago": None,
        "long_rest_days_ago": None,
        "recommended_action": None,
    }
    try:
        with request.app.state.driver.session() as maint_session:
            ts = memory_repo.get_system_timestamps(maint_session)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        maintenance_status_data = _compute_maintenance_status(
            last_short_rest_at=ts.get("last_short_rest_at"),
            last_long_rest_at=ts.get("last_long_rest_at"),
            now_iso=now_iso,
            short_rest_recency_days=settings.short_rest_recency_days,
            long_rest_recency_days=settings.long_rest_recency_days,
        )
    except Exception:
        pass  # best-effort; never surface maintenance errors to wake-up

    return WakeUpResponse(
        memories=[WakeUpMemoryItem(**r) for r in result["core"]],
        topic_memories=[WakeUpMemoryItem(**r) for r in result["topic"]],
        maintenance_status=MaintenanceStatus(**maintenance_status_data),
    )


class StrandItem(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


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


class ProjectItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class ProjectsResponse(BaseModel):
    projects: List[ProjectItem]


class CreateProjectRequest(BaseModel):
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


@app.get("/project", response_model=ProjectsResponse)
async def list_projects(request: Request) -> ProjectsResponse:
    try:
        with request.app.state.driver.session() as session:
            projects = memory_repo.list_projects(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ProjectsResponse(projects=[ProjectItem(**p) for p in projects])


@app.post("/project", response_model=ProjectItem)
async def create_project(req: CreateProjectRequest, request: Request) -> ProjectItem:
    try:
        with request.app.state.driver.session() as session:
            project = memory_repo.upsert_project(session, req)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ProjectItem(**project)


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
            # Note: edge modulation is intentionally omitted here (factor=0, cap=10 defaults).
            # Use /memory/maintenance/short-rest or /memory/maintenance/long-rest for
            # modulated decay that takes incoming edge weights into account.
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


class MaintenanceLogEntry(BaseModel):
    operation: str
    ran_at: str
    dry_run: bool
    nodes_affected: int
    edges_affected: int
    edges_discovered: int
    edges_pruned: int


class MaintenanceLogResponse(BaseModel):
    entries: List[MaintenanceLogEntry]


@app.get("/memory/maintenance/log", response_model=MaintenanceLogResponse)
async def maintenance_log(request: Request) -> MaintenanceLogResponse:
    try:
        with request.app.state.driver.session() as session:
            entries = memory_repo.get_maintenance_log(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return MaintenanceLogResponse(entries=[MaintenanceLogEntry(**e) for e in entries])


class OperationLogEntry(BaseModel):
    operation: str
    memory_id: str
    ran_at: str
    fields_updated: Optional[List[str]] = None
    target_id: Optional[str] = None


class OperationLogResponse(BaseModel):
    entries: List[OperationLogEntry]


@app.get("/memory/operation/log", response_model=OperationLogResponse)
async def operation_log(request: Request) -> OperationLogResponse:
    try:
        with request.app.state.driver.session() as session:
            entries = memory_repo.get_operation_log(session)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return OperationLogResponse(entries=[OperationLogEntry(**e) for e in entries])


class UpdateMemoryRequest(BaseModel):
    fact: Optional[str] = None
    so_what: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    person_ids: Optional[List[str]] = None
    strand_ids: Optional[List[str]] = None
    control_ids: Optional[List[str]] = None
    doc_ids: Optional[List[str]] = None
    control_relationship_type: Optional[Literal["context", "evidence", "gap"]] = None
    org_id: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateMemoryRequest":
        if all(v is None for v in [
            self.fact, self.so_what, self.tags,
            self.importance, self.person_ids, self.strand_ids,
            self.control_ids, self.doc_ids, self.control_relationship_type, self.org_id,
        ]):
            raise ValueError("At least one field must be provided for update")
        return self


class UpdateMemoryResponse(BaseModel):
    memory_id: str
    updated_at: str


class MergeMemoryRequest(BaseModel):
    target_id: str
    strategy: str = "replace"


class MergeMemoryResponse(BaseModel):
    source_id: str
    target_id: str


class ArchiveMemoryResponse(BaseModel):
    memory_id: str
    archived_at: str


class RestoreMemoryResponse(BaseModel):
    memory_id: str
    status: str = "active"


@app.patch("/memory/{memory_id}", response_model=UpdateMemoryResponse)
async def update_memory(
    memory_id: str, req: UpdateMemoryRequest, request: Request
) -> UpdateMemoryResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    patch_fields = req.model_dump(exclude_none=True)
    requested_fields = list(patch_fields.keys())
    new_embedding = None

    try:
        with request.app.state.driver.session() as session:
            if "fact" in patch_fields or "so_what" in patch_fields:
                # Fetch current node to merge with patch before recomputing embedding
                current = memory_repo.get_memory_for_update(session, memory_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="Memory not found or not active")
                merged_fact = patch_fields.get("fact", current["fact"] or "")
                merged_so_what = patch_fields.get("so_what", current["so_what"])
                merged_text = merged_fact + (" " + merged_so_what if merged_so_what else "")
                patch_fields["text"] = merged_text
                new_embedding = get_embedding(merged_text)
            # Strip bridge fields before passing to repo (repo knows nothing about these)
            _BRIDGE_FIELDS = {"control_ids", "doc_ids", "control_relationship_type", "org_id"}
            bridge_fields = {k: v for k, v in patch_fields.items() if k in _BRIDGE_FIELDS}
            repo_patch = {k: v for k, v in patch_fields.items() if k not in _BRIDGE_FIELDS}
            if not repo_patch:
                current = memory_repo.get_memory_for_update(session, memory_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="Memory not found or not active")
            memory_repo.update_memory(session, memory_id, repo_patch, new_embedding, now)
            if settings.enable_knowledge_layer and bridge_fields:
                from memory_service import knowledge_bridge
                if "control_ids" in bridge_fields:
                    missing = knowledge_bridge.validate_controls(session, bridge_fields["control_ids"])
                    if missing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unknown control_ids: {missing}",
                        )
                    knowledge_bridge.replace_control_edges(
                        session, memory_id,
                        bridge_fields["control_ids"],
                        bridge_fields.get("control_relationship_type"),
                        bridge_fields.get("org_id"),
                    )
                if "doc_ids" in bridge_fields:
                    missing = knowledge_bridge.validate_documents(session, bridge_fields["doc_ids"])
                    if missing:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unknown doc_ids: {missing}",
                        )
                    knowledge_bridge.replace_doc_edges(
                        session, memory_id, bridge_fields["doc_ids"],
                    )
            memory_repo.append_operation_log(session, {
                "operation": "update",
                "memory_id": memory_id,
                "ran_at": now,
                "fields_updated": requested_fields,
            })
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return UpdateMemoryResponse(memory_id=memory_id, updated_at=now)


@app.post("/memory/{memory_id}/merge", response_model=MergeMemoryResponse)
async def merge_memory(
    memory_id: str, req: MergeMemoryRequest, request: Request
) -> MergeMemoryResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    if memory_id == req.target_id:
        raise HTTPException(status_code=400, detail="Source and target must differ")
    try:
        with request.app.state.driver.session() as session:
            memory_repo.merge_memory(
                session,
                memory_id,
                req.target_id,
                req.strategy,
                default_edge_decay_rate=settings.edge_decay_rate,
            )
            if settings.enable_knowledge_layer:
                from memory_service import knowledge_bridge
                knowledge_bridge.rewire_cross_layer_edges(session, memory_id, req.target_id)
            memory_repo.append_operation_log(session, {
                "operation": "merge",
                "memory_id": memory_id,
                "ran_at": now,
                "target_id": req.target_id,
            })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return MergeMemoryResponse(source_id=memory_id, target_id=req.target_id)


@app.post("/memory/{memory_id}/archive", response_model=ArchiveMemoryResponse)
async def archive_memory(
    memory_id: str, request: Request
) -> ArchiveMemoryResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            memory_repo.archive_memory(session, memory_id, now)
            memory_repo.append_operation_log(session, {
                "operation": "archive",
                "memory_id": memory_id,
                "ran_at": now,
            })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ArchiveMemoryResponse(memory_id=memory_id, archived_at=now)


@app.post("/memory/{memory_id}/restore", response_model=RestoreMemoryResponse)
async def restore_memory(
    memory_id: str, request: Request
) -> RestoreMemoryResponse:
    now = datetime.now(tz=timezone.utc).isoformat()
    try:
        with request.app.state.driver.session() as session:
            memory_repo.restore_memory(session, memory_id)
            memory_repo.append_operation_log(session, {
                "operation": "restore",
                "memory_id": memory_id,
                "ran_at": now,
            })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return RestoreMemoryResponse(memory_id=memory_id)


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
                consolidated_decay_rate=settings.memory_consolidated_decay_rate,
            )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return ReinforceResponse(memory_id=memory_id, new_strength=new_strength)


class DuplicateMemoryRef(BaseModel):
    id: str
    text: str


class DuplicatePair(BaseModel):
    a: DuplicateMemoryRef
    b: DuplicateMemoryRef
    similarity: float


@app.get("/memory/duplicates", response_model=List[DuplicatePair])
async def find_duplicates(
    request: Request,
    threshold: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    limit: Optional[int] = Query(default=None, ge=1, le=100),
) -> List[DuplicatePair]:
    effective_threshold = threshold if threshold is not None else settings.near_duplicate_threshold
    effective_limit = limit if limit is not None else settings.near_duplicate_limit
    try:
        with request.app.state.driver.session() as session:
            pairs = memory_repo.find_near_duplicates(session, effective_threshold, effective_limit)
    except ServiceUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
    return [DuplicatePair(**p) for p in pairs]


class NodeLabel(str, Enum):
    memory = "Memory"
    strand = "Strand"
    agent = "Agent"
    person = "Person"
    project = "Project"
    standard = "Standard"
    control = "Control"
    document = "Document"
    chunk = "Chunk"
    business_attribute = "BusinessAttribute"
    organisation = "Organisation"
    jurisdiction = "Jurisdiction"


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


# Knowledge layer router — only registered when ENABLE_KNOWLEDGE_LAYER=true
if settings.enable_knowledge_layer:
    from memory_service.knowledge_routes import router as knowledge_router
    app.include_router(knowledge_router)
