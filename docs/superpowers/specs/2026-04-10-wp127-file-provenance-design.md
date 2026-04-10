# WP-127 — `files_modified` and `files_read` Properties on Memory Nodes

**Date:** 2026-04-10  
**Status:** Approved — ready for implementation planning  
**Depends on:** —  
**Gates:** WP-126 (PostToolUse observer hook), WP-128 (tiered search)

---

## Motivation

There is currently no way to ask the fabric "what do I know about changes to `memory_repo.py`?" File provenance as first-class list properties on Memory nodes enables:

- **Pre-edit context injection:** load relevant memories before touching a file
- **Decision archaeology:** reconstruct the history of decisions around a specific module
- **WP-126 foundation:** the observer hook writes these properties automatically on capture

This WP delivers the schema and API surface. WP-126 writes the properties; they can also be set manually via `POST /memory` and `PATCH /memory/{id}`.

---

## Data Model

Two new optional list properties on `Memory` nodes in Memgraph:

| Property | Type | Default | Semantics |
|---|---|---|---|
| `files_modified` | `list[str]` | `[]` | Paths of files written/edited when this memory was captured |
| `files_read` | `list[str]` | `[]` | Paths of files read when this memory was captured |

Memgraph supports list properties natively. Paths are stored as-given (no normalisation) — callers are responsible for consistent path format. Relative paths relative to the project root are the recommended convention (e.g. `memory_service/memory_repo.py`, not absolute paths).

---

## API Changes

### `POST /memory` — AddMemoryRequest

Add to `AddMemoryRequest`:

```python
files_modified: Optional[List[str]] = None
files_read: Optional[List[str]] = None
```

Persisted in Step 1 of `memory_repo.add_memory` Cypher as list properties on the `Memory` node. `None` is stored as `[]` (empty list) — consistent with `tags`.

### `PATCH /memory/{id}` — UpdateMemoryRequest

Add to `UpdateMemoryRequest`:

```python
files_modified: Optional[List[str]] = None
files_read: Optional[List[str]] = None
```

`update_memory` in `memory_repo.py` treats these as full replacements (same pattern as `tags`). `None` means "do not update this field". Update the `at_least_one_field` validator to include both new fields.

### `POST /memory/search` — SearchMemoryRequest

Add to `SearchMemoryRequest`:

```python
files_modified: Optional[List[str]] = None  # any-of match
files_read: Optional[List[str]] = None       # any-of match
```

Each non-None filter appends a WHERE predicate:

```cypher
ANY(f IN m.files_modified WHERE f IN $files_modified)
ANY(f IN m.files_read WHERE f IN $files_read)
```

Both predicates are ANDed with any existing filters. A memory must satisfy all provided filters.

### `GET /memory/by-file` — new endpoint

```
GET /memory/by-file?path=<path>&role=modified|read|any
```

Pure file-scoped retrieval — no embedding query, no semantic scoring.

| Param | Type | Default | Description |
|---|---|---|---|
| `path` | `str` | required | File path to match (exact string match against list elements) |
| `role` | `str` | `any` | `modified` checks `files_modified` only; `read` checks `files_read` only; `any` checks both |
| `limit` | `int` | `20` | Max results |

Returns `List[MemoryHit]`, sorted by `importance DESC, created_at DESC`. Only active (non-archived, non-merged) memories are returned.

Cypher pattern for `role=any`:

```cypher
MATCH (m:Memory)
WHERE m.status = 'active'
  AND (ANY(f IN m.files_modified WHERE f = $path)
    OR ANY(f IN m.files_read WHERE f = $path))
RETURN m ORDER BY m.importance DESC, m.created_at DESC LIMIT $limit
```

### `MemoryHit` — extend response shape

Add to `MemoryHit`:

```python
files_modified: List[str] = []
files_read: List[str] = []
```

These are populated from the Memory node in the search result Cypher. Consumers can inspect provenance directly from search results.

---

## Client Changes

`memory_client/client.py`:

- `add_memory()` — pass `files_modified` and `files_read` through to the request body
- `update_memory()` — same
- New method `get_memories_by_file(path: str, role: str = "any", limit: int = 20) -> list[dict]`

---

## Out of Scope

- Automatic file provenance capture (WP-126)
- Full-text / prefix search within file paths — exact match only
- Path normalisation or canonicalisation — caller's responsibility
- Indexing file path lists for performance (acceptable at current scale; revisit if corpus grows beyond ~50k memories)

---

## Tests

### Unit

1. `AddMemoryRequest` with `files_modified=["memory_repo.py"]` serialises to JSON with the field present
2. `UpdateMemoryRequest` with only `files_modified=["foo.py"]` passes the `at_least_one_field` validator
3. `SearchMemoryRequest` with `files_modified=["foo.py"]` produces a Cypher WHERE clause containing `ANY(f IN m.files_modified WHERE f IN $files_modified)`
4. `MemoryHit` with `files_modified=["a.py"]` serialises and deserialises correctly

### Integration (live Memgraph + running FastAPI service required)

1. Add a memory with `files_modified=["memory_repo.py"]` via `POST /memory`
2. Call `GET /memory/by-file?path=memory_repo.py&role=modified` — assert the memory is returned
3. Call `GET /memory/by-file?path=memory_repo.py&role=read` — assert the memory is NOT returned
4. Call `GET /memory/by-file?path=memory_repo.py&role=any` — assert it IS returned
5. Add a memory with `files_read=["memory_repo.py"]`, repeat role checks
6. Call `POST /memory/search` with `files_modified=["memory_repo.py"]` — assert filtered results contain only memories with that path in `files_modified`

### Acceptance Criteria

- `GET /memory/by-file?path=memory_repo.py` returns memories tagged with that file
- `POST /memory/search` with file filter returns only memories matching the filter
- `MemoryHit` in search results includes `files_modified` and `files_read`
- `files_modified` and `files_read` are settable via both `POST /memory` and `PATCH /memory/{id}`
