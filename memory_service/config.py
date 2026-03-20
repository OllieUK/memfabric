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
    agent_id: str = "claude-code"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_driver(settings: Settings) -> neo4j.Driver:
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"
    if settings.memgraph_user or settings.memgraph_password:
        auth = (settings.memgraph_user, settings.memgraph_password)
    else:
        auth = None
    return GraphDatabase.driver(uri, auth=auth)


settings = Settings()
