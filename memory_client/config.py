from pydantic_settings import BaseSettings, SettingsConfigDict


class ClientSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    agent_id: str = "claude-code"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = ClientSettings()
