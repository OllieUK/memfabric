import json
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


STARTUP_CONFIG_FILENAME = "startup.json"


class ClientSettings(BaseSettings):
    api_base_url: str = "https://memfabric.carr-it.net:8443"
    api_key: str | None = None  # API_KEY env var — sent as Authorization: Bearer header
    agent_id: str = "claude-code"
    wake_up_scope_profile: str | None = "mara_startup_v2"
    wake_up_global_agent_id: str | None = "mara"
    wake_up_project_id: str | None = None
    wake_up_person_id: str | None = None
    wake_up_global_mara_limit: int | None = None
    wake_up_global_user_limit: int | None = None
    wake_up_project_mara_limit: int | None = None
    wake_up_project_baseline_limit: int | None = None
    wake_up_walk_depth: int | None = None
    wake_up_neighbour_cap: int | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = ClientSettings()


def _load_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def global_startup_config_path() -> Path:
    return Path.home() / ".claude" / STARTUP_CONFIG_FILENAME


def find_project_startup_config_path(start_path: str | Path | None = None) -> Path | None:
    start = Path(start_path or os.getcwd())
    try:
        resolved = start.resolve()
    except OSError:
        resolved = start

    if resolved.is_file():
        resolved = resolved.parent

    candidates = [resolved]
    candidates.extend(resolved.parents)
    for candidate in candidates:
        startup_path = candidate / ".claude" / STARTUP_CONFIG_FILENAME
        if startup_path.exists():
            return startup_path
    return None


def resolve_startup_context(start_path: str | Path | None = None) -> dict:
    global_cfg = _load_json_if_exists(global_startup_config_path())
    project_path = find_project_startup_config_path(start_path)
    project_cfg = _load_json_if_exists(project_path) if project_path else {}

    startup_mode = str(project_cfg.get("startup_mode") or "mara").strip().lower()
    explicit_agent_id = os.environ.get("AGENT_ID")

    context = {
        "startup_mode": startup_mode,
        "global_companion_id": global_cfg.get("companion_id") or settings.wake_up_global_agent_id,
        "global_user_id": global_cfg.get("user_id") or settings.wake_up_person_id,
        "project_id": None,
        "project_persona_id": None,
        "wake_up_topic": None,
        "global_config_path": str(global_startup_config_path()),
        "project_config_path": str(project_path) if project_path else None,
    }

    if startup_mode == "global-only":
        return context

    if project_cfg:
        context["project_id"] = project_cfg.get("project_id")
        context["project_persona_id"] = project_cfg.get("project_persona_id") or explicit_agent_id
        context["wake_up_topic"] = project_cfg.get("wake_up_topic")
        return context

    if settings.wake_up_project_id or explicit_agent_id:
        context["project_id"] = settings.wake_up_project_id or explicit_agent_id
        context["project_persona_id"] = explicit_agent_id or settings.agent_id

    return context
