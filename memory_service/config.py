# memory_service/config.py

import neo4j
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    memgraph_user: str = ""
    memgraph_password: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_local_files_only: bool = True
    embedding_preload_on_startup: bool = True
    agent_id: str = "claude-code"

    memory_decay_rate: float = 0.01
    initial_strength_factor: float = 0.4
    memory_initial_decay_rate: float = 0.07
    memory_consolidated_decay_rate: float = 0.01
    importance_floor_factor: float = 0.3
    edge_decay_rate: float = 0.005
    recall_strength_increment: float = 0.05
    explicit_strength_increment: float = 0.20
    edge_recall_increment: float = 0.02
    edge_explicit_increment: float = 0.10
    edge_prune_threshold: float = 0.05
    min_memory_strength: float = 0.0
    short_rest_recency_days: int = 7
    long_rest_recency_days: int = 1
    rediscovery_strength_threshold: float = 0.3
    edge_hard_prune_floor: float = 0.01
    edge_hard_prune_min_days: int = 90
    edge_modulation_factor: float = 0.5
    edge_modulation_cap: float = 10.0
    # Prevents response bloat from highly-connected nodes on dense graphs.
    # Per traversal direction; total per hit is at most 3 × this value.
    search_neighbour_cap: int = 50
    memory_index_capacity: int = 5000
    framework_index_capacity: int = 5000
    ctrl_index_capacity: int = 5000
    chunk_index_capacity: int = 10000
    threat_index_capacity: int = 1000
    memory_dedup_threshold: float = 0.05
    near_duplicate_threshold: float = 0.92
    near_duplicate_limit: int = 20
    wake_up_companion_anchor_limit: int = 5           # WAKE_UP_COMPANION_ANCHOR_LIMIT
    wake_up_conversant_anchor_limit: int = 10         # WAKE_UP_CONVERSANT_ANCHOR_LIMIT
    wake_up_default_person_id: str | None = None      # WAKE_UP_DEFAULT_PERSON_ID
    knowledge_embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    enable_knowledge_layer: bool = False

    # Built-in maintenance scheduler
    scheduler_enabled: bool = True
    scheduler_poll_interval_seconds: int = 300          # how often to check (5 min)
    short_rest_interval_hours: int = 6                  # run short-rest every N hours
    long_rest_utc_hour: int = 3                         # target wall-clock hour (UTC)
    long_rest_min_interval_hours: int = 20              # don't double-run within this window
    long_rest_overdue_hours: int = 27                   # run ASAP if missed by this much

    # Document ingestion pipeline (WP-073)
    ingest_chunk_size: int = 2000
    ingest_chunk_overlap: int = 200
    ingest_min_chunk_chars: int = 50
    ingest_auto_supports: bool = False
    ingest_auto_supports_threshold: float = 0.20
    ingest_chunk_review_mode: bool = True

    auto_merge_threshold: float | None = None

    # Authentication (WP-096): valid bearer tokens / API keys.
    # pydantic-settings parses API_KEYS as a JSON array or comma-separated string.
    # Empty = unauthenticated (dev / localhost mode).
    api_keys: frozenset[str] = frozenset()

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def get_driver(settings: Settings) -> neo4j.Driver:
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    if settings.memgraph_user or settings.memgraph_password:
        auth = (settings.memgraph_user, settings.memgraph_password)
    else:
        auth = None
    return GraphDatabase.driver(uri, auth=auth)


settings = Settings()
