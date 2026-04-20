from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    api_key: str | None = None  # API_KEY env var — forwarded as Authorization: Bearer header
    agent_id: str = "claude-code"
    enable_knowledge_layer: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = MCPSettings()
