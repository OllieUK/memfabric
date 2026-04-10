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
        control_ids: list[str] | None = None,
        doc_ids: list[str] | None = None,
        control_relationship_type: str | None = None,
        org_id: str | None = None,
        ephemeral: bool = False,
        files_modified: list[str] | None = None,
        files_read: list[str] | None = None,
    ) -> dict:
        """POST /memory. Returns dict with memory_id, deduplicated, and strand_ids."""
        body: dict = {
            "fact": fact,
            "type": type,
            "agent_id": agent_id,
            "tags": tags or [],
            "importance": importance,
            "person_ids": person_ids or [],
            "strand_ids": strand_ids or [],
            "ephemeral": ephemeral,
            "files_modified": files_modified or [],
            "files_read": files_read or [],
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
        if control_ids is not None:
            body["control_ids"] = control_ids
        if doc_ids is not None:
            body["doc_ids"] = doc_ids
        if control_relationship_type is not None:
            body["control_relationship_type"] = control_relationship_type
        if org_id is not None:
            body["org_id"] = org_id
        response = self._http.post("/memory", json=body)
        response.raise_for_status()
        return response.json()

    def search_memory(
        self,
        query: str,
        *,
        tags: list[str] | None = None,
        agent_ids: list[str] | None = None,
        project_ids: list[str] | None = None,
        person_ids: list[str] | None = None,
        limit: int = 10,
        max_hops: int = 1,
        traversal_direction: str = "none",
        min_importance: int | None = None,
        min_score: float | None = None,
        neighbour_cap: int | None = None,
        files_modified: list[str] | None = None,
        files_read: list[str] | None = None,
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
        if person_ids is not None:
            body["person_ids"] = person_ids
        if min_importance is not None:
            body["min_importance"] = min_importance
        if min_score is not None:
            body["min_score"] = min_score
        if neighbour_cap is not None:
            body["neighbour_cap"] = neighbour_cap
        if files_modified is not None:
            body["files_modified"] = files_modified
        if files_read is not None:
            body["files_read"] = files_read
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
        self,
        *,
        limit: int = 20,
        topic: str | None = None,
        person_id: str | None = None,
        companion_anchor_limit: int | None = None,
        conversant_anchor_limit: int | None = None,
    ) -> dict:
        """GET /memory/wake-up. Returns the full response dict.

        Keys always present: memories, topic_memories, maintenance_status
        Keys present when populated: companion_anchors, conversant_anchors
        """
        params: dict = {"limit": limit}
        if topic is not None:
            params["topic"] = topic
        if person_id is not None:
            params["person_id"] = person_id
        if companion_anchor_limit is not None:
            params["companion_anchor_limit"] = companion_anchor_limit
        if conversant_anchor_limit is not None:
            params["conversant_anchor_limit"] = conversant_anchor_limit
        response = self._http.get("/memory/wake-up", params=params)
        response.raise_for_status()
        return response.json()

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

    def list_projects(self) -> list[dict]:
        """GET /project. Returns list of project dicts: id, name, description."""
        response = self._http.get("/project")
        response.raise_for_status()
        return response.json()["projects"]

    def create_project(self, project_id: str, name: str, description: str | None = None) -> dict:
        """POST /project. Creates or merges a Project node. Returns project dict."""
        body: dict = {"id": project_id, "name": name}
        if description is not None:
            body["description"] = description
        response = self._http.post("/project", json=body)
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
        control_ids: list[str] | None = None,
        doc_ids: list[str] | None = None,
        control_relationship_type: str | None = None,
        org_id: str | None = None,
        files_modified: list[str] | None = None,
        files_read: list[str] | None = None,
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
        if control_ids is not None:
            body["control_ids"] = control_ids
        if doc_ids is not None:
            body["doc_ids"] = doc_ids
        if control_relationship_type is not None:
            body["control_relationship_type"] = control_relationship_type
        if org_id is not None:
            body["org_id"] = org_id
        if files_modified is not None:
            body["files_modified"] = files_modified
        if files_read is not None:
            body["files_read"] = files_read
        response = self._http.patch(f"/memory/{memory_id}", json=body)
        response.raise_for_status()
        return response.json()

    def get_memories_by_file(
        self,
        path: str,
        role: str = "any",
        limit: int = 20,
    ) -> list[dict]:
        """Return memories tagged with the given file path.

        Args:
            path: File path to match (exact string match).
            role: "modified" checks files_modified only, "read" checks files_read only,
                  "any" checks both.
            limit: Max results (default 20).

        Returns:
            List of memory dicts, each with at minimum id, text, type, importance,
            files_modified, files_read.
        """
        params: dict = {"path": path, "role": role, "limit": limit}
        response = self._http.get("/memory/by-file", params=params)
        response.raise_for_status()
        return response.json()["memories"]

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

    def delete_memory(self, memory_id: str) -> None:
        """DELETE /memory/{id}. Returns None on 204."""
        response = self._http.delete(f"/memory/{memory_id}")
        response.raise_for_status()

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

    def purge_ephemeral(self) -> dict:
        """POST /memory/maintenance/purge-ephemeral. Returns {"deleted": int}."""
        response = self._http.post("/memory/maintenance/purge-ephemeral")
        response.raise_for_status()
        return response.json()

    def maintenance_stats(self) -> dict:
        """GET /memory/maintenance/stats. Returns the health snapshot dict."""
        response = self._http.get("/memory/maintenance/stats")
        response.raise_for_status()
        return response.json()

    def maintenance_log(self) -> list[dict]:
        """GET /memory/maintenance/log. Returns list of audit entry dicts."""
        response = self._http.get("/memory/maintenance/log")
        response.raise_for_status()
        return response.json()["entries"]

    def operation_log(self) -> list[dict]:
        """GET /memory/operation/log. Returns list of operation entry dicts."""
        response = self._http.get("/memory/operation/log")
        response.raise_for_status()
        return response.json()["entries"]

    def find_duplicates(
        self, *, threshold: float | None = None, limit: int | None = None
    ) -> list[dict]:
        """GET /memory/duplicates. Returns near-duplicate pairs."""
        params: dict = {}
        if threshold is not None:
            params["threshold"] = threshold
        if limit is not None:
            params["limit"] = limit
        response = self._http.get("/memory/duplicates", params=params)
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

    def search_controls(
        self,
        query: str,
        *,
        limit: int = 10,
        framework_id: str | None = None,
    ) -> list[dict]:
        """POST /knowledge/search/controls. Returns list of ControlHit dicts."""
        body: dict = {"query": query, "limit": limit}
        if framework_id is not None:
            body["framework_id"] = framework_id
        response = self._http.post("/knowledge/search/controls", json=body)
        response.raise_for_status()
        return response.json()

    def search_chunks(
        self,
        query: str,
        *,
        limit: int = 10,
        doc_id: str | None = None,
    ) -> list[dict]:
        """POST /knowledge/search/chunks. Returns list of ChunkHit dicts."""
        body: dict = {"query": query, "limit": limit}
        if doc_id is not None:
            body["doc_id"] = doc_id
        response = self._http.post("/knowledge/search/chunks", json=body)
        response.raise_for_status()
        return response.json()

    def list_norms(self) -> list[dict]:
        """GET /knowledge/norms. Returns list of NormResponse dicts."""
        response = self._http.get("/knowledge/norms")
        response.raise_for_status()
        return response.json()

    def list_documents(self) -> list[dict]:
        """GET /knowledge/documents. Returns list of DocumentResponse dicts."""
        response = self._http.get("/knowledge/documents")
        response.raise_for_status()
        return response.json()

    def get_incomplete_jurisdictions(self) -> dict:
        """GET /knowledge/incomplete-jurisdictions. Returns diagnostic dict."""
        response = self._http.get("/knowledge/incomplete-jurisdictions")
        response.raise_for_status()
        return response.json()

    def get_control(self, control_id: str) -> dict:
        """GET /knowledge/controls/{control_id}. Returns ControlResponse dict."""
        response = self._http.get(f"/knowledge/controls/{control_id}")
        response.raise_for_status()
        return response.json()

    def get_norm(self, norm_id: str) -> dict:
        """GET /knowledge/norms/{norm_id}. Returns NormResponse dict."""
        response = self._http.get(f"/knowledge/norms/{norm_id}")
        response.raise_for_status()
        return response.json()
