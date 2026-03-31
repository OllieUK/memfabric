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
        fact: str,
        type: str,
        agent_id: str,
        *,
        so_what: str | None = None,
        cause_ids: list[str] | None = None,
        effect_ids: list[str] | None = None,
        tags: list[str] | None = None,
        importance: int = 3,
        project_id: str | None = None,
        person_ids: list[str] | None = None,
        strand_ids: list[str] | None = None,
        related_ids: list[str] | None = None,
    ) -> str:
        """POST /memory. Returns memory_id string."""
        body: dict = {
            "fact": fact,
            "type": type,
            "agent_id": agent_id,
            "tags": tags or [],
            "importance": importance,
            "person_ids": person_ids or [],
            "strand_ids": strand_ids or [],
        }
        if so_what is not None:
            body["so_what"] = so_what
        if cause_ids is not None:
            body["cause_ids"] = cause_ids
        if effect_ids is not None:
            body["effect_ids"] = effect_ids
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
        tags: list[str] | None = None,
        agent_ids: list[str] | None = None,
        project_ids: list[str] | None = None,
        limit: int = 10,
        max_hops: int = 1,
        traversal_direction: str = "none",
        min_importance: int | None = None,
    ) -> list[dict]:
        """POST /memory/search. Returns list of MemoryHit dicts."""
        body: dict = {
            "query": query,
            "limit": limit,
            "max_hops": max_hops,
            "traversal_direction": traversal_direction,
        }
        if tags is not None:
            body["tags"] = tags
        if agent_ids is not None:
            body["agent_ids"] = agent_ids
        if project_ids is not None:
            body["project_ids"] = project_ids
        if min_importance is not None:
            body["min_importance"] = min_importance
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

    def wake_up_split(
        self, *, limit: int = 20, topic: str | None = None
    ) -> tuple[list[dict], list[dict]]:
        """GET /memory/wake-up. Returns (core_memories, topic_memories) tuple.

        core_memories: importance-ranked list (always populated if DB has memories)
        topic_memories: topic-only results (empty when no topic provided)
        """
        params: dict = {"limit": limit}
        if topic is not None:
            params["topic"] = topic
        response = self._http.get("/memory/wake-up", params=params)
        response.raise_for_status()
        data = response.json()
        return data["memories"], data.get("topic_memories", [])

    def list_strands(self) -> list[dict]:
        """GET /strands. Returns list of strand dicts with id, name, description, category."""
        response = self._http.get("/strands")
        response.raise_for_status()
        return response.json()["strands"]

    def list_persons(self) -> list[dict]:
        """GET /person. Returns list of person dicts: id, name, description."""
        response = self._http.get("/person")
        response.raise_for_status()
        return response.json()["persons"]

    def create_person(self, person_id: str, name: str, description: str | None = None) -> dict:
        """POST /person. Creates or merges a Person node. Returns person dict."""
        body: dict = {"id": person_id, "name": name}
        if description is not None:
            body["description"] = description
        response = self._http.post("/person", json=body)
        response.raise_for_status()
        return response.json()

    def reinforce_memory(
        self,
        memory_id: str,
        co_recalled_ids: list[str] | None = None,
    ) -> dict:
        """POST /memory/{id}/reinforce. Returns {memory_id, new_strength}."""
        body: dict = {"signal": "explicit"}
        if co_recalled_ids:
            body["co_recalled_ids"] = co_recalled_ids
        response = self._http.post(f"/memory/{memory_id}/reinforce", json=body)
        response.raise_for_status()
        return response.json()

    def update_memory(
        self,
        memory_id: str,
        *,
        fact: str | None = None,
        so_what: str | None = None,
        tags: list[str] | None = None,
        importance: int | None = None,
        person_ids: list[str] | None = None,
        strand_ids: list[str] | None = None,
    ) -> dict:
        """PATCH /memory/{id}. Returns {memory_id, updated_at}."""
        body: dict = {}
        if fact is not None:
            body["fact"] = fact
        if so_what is not None:
            body["so_what"] = so_what
        if tags is not None:
            body["tags"] = tags
        if importance is not None:
            body["importance"] = importance
        if person_ids is not None:
            body["person_ids"] = person_ids
        if strand_ids is not None:
            body["strand_ids"] = strand_ids
        response = self._http.patch(f"/memory/{memory_id}", json=body)
        response.raise_for_status()
        return response.json()

    def merge_memory(self, memory_id: str, target_id: str, strategy: str = "replace") -> dict:
        """POST /memory/{id}/merge. Returns {source_id, target_id}."""
        response = self._http.post(
            f"/memory/{memory_id}/merge",
            json={"target_id": target_id, "strategy": strategy},
        )
        response.raise_for_status()
        return response.json()

    def archive_memory(self, memory_id: str) -> dict:
        """POST /memory/{id}/archive. Returns {memory_id, archived_at}."""
        response = self._http.post(f"/memory/{memory_id}/archive")
        response.raise_for_status()
        return response.json()

    def restore_memory(self, memory_id: str) -> dict:
        """POST /memory/{id}/restore. Returns {memory_id, status}."""
        response = self._http.post(f"/memory/{memory_id}/restore")
        response.raise_for_status()
        return response.json()

    def run_decay(self) -> dict:
        """POST /memory/maintenance/decay. Returns {nodes_updated, edges_updated}."""
        response = self._http.post("/memory/maintenance/decay")
        response.raise_for_status()
        return response.json()

    def get_weak_edges(self) -> list[dict]:
        """GET /memory/maintenance/weak-edges. Returns list of weak edge dicts."""
        response = self._http.get("/memory/maintenance/weak-edges")
        response.raise_for_status()
        return response.json()["edges"]

    def short_rest(self, *, dry_run: bool = False) -> dict:
        """POST /memory/maintenance/short-rest. Returns {nodes_decayed, edges_decayed, dry_run}."""
        params: dict = {}
        if dry_run:
            params["dry_run"] = "true"
        response = self._http.post("/memory/maintenance/short-rest", params=params)
        response.raise_for_status()
        return response.json()

    def long_rest(self, *, dry_run: bool = False, prune: bool = False) -> dict:
        """POST /memory/maintenance/long-rest. Returns {nodes_decayed, edges_decayed, edges_discovered, edges_pruned, dry_run}."""
        params: dict = {}
        if dry_run:
            params["dry_run"] = "true"
        if prune:
            params["prune"] = "true"
        response = self._http.post("/memory/maintenance/long-rest", params=params)
        response.raise_for_status()
        return response.json()

    def maintenance_stats(self) -> dict:
        """GET /memory/maintenance/stats. Returns the health snapshot dict."""
        response = self._http.get("/memory/maintenance/stats")
        response.raise_for_status()
        return response.json()

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
