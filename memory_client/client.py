# memory_client/client.py
from typing import Optional
import httpx


class MemoryClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._http = httpx.Client(base_url=base_url, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MemoryClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def add_memory(
        self,
        text: str,
        type: str,
        agent_id: str,
        *,
        tags: list[str] | None = None,
        importance: int = 3,
        project_id: Optional[str] = None,
        person_ids: list[str] | None = None,
        strand_ids: list[str] | None = None,
        related_ids: Optional[list[str]] = None,
    ) -> str:
        """POST /memory. Returns memory_id string."""
        body: dict = {
            "text": text,
            "type": type,
            "agent_id": agent_id,
            "tags": tags or [],
            "importance": importance,
            "person_ids": person_ids or [],
            "strand_ids": strand_ids or [],
        }
        if project_id is not None:
            body["project_id"] = project_id
        if related_ids is not None:
            body["related_ids"] = related_ids
        response = self._http.post("/memory", json=body)
        response.raise_for_status()
        return response.json()["memory_id"]

    def search_memory(
        self,
        query: str,
        *,
        tags: Optional[list[str]] = None,
        agent_ids: Optional[list[str]] = None,
        project_ids: Optional[list[str]] = None,
        limit: int = 10,
        max_hops: int = 1,
    ) -> list[dict]:
        """POST /memory/search. Returns list of MemoryHit dicts."""
        body: dict = {
            "query": query,
            "limit": limit,
            "max_hops": max_hops,
        }
        if tags is not None:
            body["tags"] = tags
        if agent_ids is not None:
            body["agent_ids"] = agent_ids
        if project_ids is not None:
            body["project_ids"] = project_ids
        response = self._http.post("/memory/search", json=body)
        response.raise_for_status()
        return response.json()["memories"]

    def wake_up(self, *, limit: int = 20, topic: str | None = None) -> list[dict]:
        """GET /memory/wake-up. Returns list of memory dicts for session start."""
        params: dict = {"limit": limit}
        if topic is not None:
            params["topic"] = topic
        response = self._http.get("/memory/wake-up", params=params)
        response.raise_for_status()
        return response.json()["memories"]

    def list_strands(self) -> list[dict]:
        """GET /strands. Returns list of strand dicts with id, name, description, category."""
        response = self._http.get("/strands")
        response.raise_for_status()
        return response.json()["strands"]

    def get_graph(
        self,
        *,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> dict:
        """GET /memory/graph. Returns {nodes, edges} dict."""
        params: dict = {}
        if project_id is not None:
            params["project_id"] = project_id
        if agent_id is not None:
            params["agent_id"] = agent_id
        if tag is not None:
            params["tag"] = tag
        response = self._http.get("/memory/graph", params=params)
        response.raise_for_status()
        return response.json()
