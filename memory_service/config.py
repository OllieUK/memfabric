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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_driver(settings: Settings) -> neo4j.Driver:
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    if settings.memgraph_user or settings.memgraph_password:
        auth = (settings.memgraph_user, settings.memgraph_password)
    else:
        auth = None
    return GraphDatabase.driver(uri, auth=auth)


settings = Settings()
