# memory_service/main.py

from contextlib import asynccontextmanager
from enum import Enum
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    memgraph_user: str = ""
    memgraph_password: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    embedding_model: str = "all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # WP-002: initialise Memgraph driver / connection pool here
    # WP-003: load embedding model here (once, not per-request)
    yield
    # WP-002: close Memgraph driver here


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


# --- Placeholders for v1 endpoints (Phase 4 will implement them properly) ---


class AddMemoryRequest(BaseModel):
    text: str
    type: MemoryType
    tags: List[str] = []
    agent_id: str
    project_id: Optional[str] = None
    person_ids: List[str] = []
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    related_ids: Optional[List[str]] = None


class AddMemoryResponse(BaseModel):
    memory_id: str


@app.post("/memory", response_model=AddMemoryResponse)
async def add_memory(req: AddMemoryRequest) -> AddMemoryResponse:
    # TODO: Implement:
    #  - local embedding generation
    #  - Memgraph node + edge creation
    raise NotImplementedError("add_memory endpoint not implemented yet")


class SearchMemoryRequest(BaseModel):
    query: str
    tags: Optional[List[str]] = None
    agent_ids: Optional[List[str]] = None
    project_ids: Optional[List[str]] = None
    limit: int = Field(default=10, ge=1, le=100)
    max_hops: int = Field(default=1, ge=0, le=3)


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
async def search_memory(req: SearchMemoryRequest) -> SearchMemoryResponse:
    # TODO: Implement:
    #  - compute query embedding
    #  - Memgraph vector search + graph expansion
    raise NotImplementedError("search_memory endpoint not implemented yet")


class GraphNode(BaseModel):
    id: str
    label: str
    type: str
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
) -> GraphResponse:
    # TODO: Implement a query against Memgraph to return a filtered subgraph
    raise NotImplementedError("get_graph endpoint not implemented yet")
