# WP-102: Housekeeping — URL rename, 503 guards, test fixes, WP-096 numbering

**Date:** 2026-04-05
**Status:** Ready for implementation

## Summary

Four small housekeeping items left over from WP-097 and earlier work: rename a
route for URL consistency, add 503 guards to all knowledge route handlers, fix
pre-existing test failures in test_wp073_ingest.py that reference a
non-existent repo function, and resolve a WP-096 ID collision in BACKLOG.md.

---

## Item 1 — URL rename: `/knowledge/chunk/supports` → `/knowledge/chunks/supports`

### Analysis

- `knowledge_routes.py` line 467: `@router.post("/chunk/supports", ...)` — uses
  singular `chunk`, inconsistent with all other routes (`/chunks`, `/controls`,
  `/frameworks`, `/documents`, `/norms`).
- Two scripts reference the old URL:
  - `scripts/ingest_document.py` line 100
  - `scripts/build_inspector_notebook.py` line 416
- `tests/test_wp073_ingest.py` lines 296 and 382 assert against the string
  `/knowledge/chunk/supports` in the call list; these must be updated to
  `/knowledge/chunks/supports`.
- This is a **breaking API change**. No external callers documented beyond the
  two scripts and the test file.

### Approach

1. In `knowledge_routes.py` change `@router.post("/chunk/supports", ...)` to
   `@router.post("/chunks/supports", ...)`.
2. In `scripts/ingest_document.py` change the URL constant.
3. In `scripts/build_inspector_notebook.py` change the URL constant.
4. In `tests/test_wp073_ingest.py` update both string assertions
   (`/knowledge/chunk/supports` → `/knowledge/chunks/supports`).

No changes to handler logic, Pydantic models, or repo functions.

---

## Item 2 — 503 guards on all knowledge route handlers

### Analysis

`knowledge_routes.py` has 15 handler functions; none wraps
`driver.session()` in a `try/except ServiceUnavailable`. The established pattern
in `main.py` is:

```python
from neo4j.exceptions import ServiceUnavailable
...
try:
    with request.app.state.driver.session() as session:
        ...
except ServiceUnavailable as exc:
    raise HTTPException(status_code=503, detail="Memgraph unavailable") from exc
```

This is already recorded as WP-023 in the backlog
("Extract `get_session` context manager for 503 handling"). This WP implements
the guard without the extraction refactor (which remains low-priority). The full
extraction can happen in a later WP once the guard is proven correct everywhere.

WP-023 notes that extraction should use a context manager. For WP-102 we will
add the try/except inline to each handler, matching the pattern in `main.py`
exactly. This keeps the diff mechanical and reviewable without touching
unrelated refactor scope.

### Handlers requiring the guard (all 15 in knowledge_routes.py)

| Handler | Route |
|---------|-------|
| `upsert_framework` | POST /frameworks |
| `get_framework` | GET /frameworks/{id} |
| `upsert_norm` | POST /norms |
| `get_norm` | GET /norms/{id} |
| `upsert_document` | POST /documents |
| `get_document` | GET /documents/{id} |
| `upsert_chunk` | POST /chunks |
| `get_chunk` | GET /chunks/{id} |
| `search_chunks` | POST /search/chunks |
| `search_frameworks` | POST /search/frameworks |
| `list_norms` | GET /norms |
| `list_documents` | GET /documents |
| `list_incomplete_jurisdictions` | GET /incomplete-jurisdictions |
| `create_supports` | POST /chunks/supports (after Item 1 rename) |
| `get_chunks_for_framework` | GET /frameworks/{id}/chunks |
| `upsert_control` | POST /controls |
| `get_control` | GET /controls/{id} |
| `search_controls` | POST /search/controls |
| `get_chunks_for_control` | GET /controls/{id}/chunks |
| `trace_up` | GET /controls/{id}/trace-up |
| `trace_down` | GET /controls/{id}/trace-down |
| `attribute_coverage` | GET /attributes/{id}/coverage |
| `gap_analysis` | POST /gap-analysis |

Note: `upsert_framework` makes two separate `driver.session()` calls (once for
the MERGE, once to set the embedding). Both must be inside the same try block.

### Approach

1. Add `from neo4j.exceptions import ServiceUnavailable` to
   `knowledge_routes.py` imports.
2. Wrap each handler's body (from the first `with request.app.state.driver.session()`
   to the final `return`) in `try: ... except ServiceUnavailable as exc: raise
   HTTPException(status_code=503, detail="Memgraph unavailable") from exc`.
3. For `upsert_framework` specifically, both session blocks sit inside the same
   handler; wrap the entire function body from the first `with` to the final
   `return FrameworkResponse(...)` in a single try/except so the embedding SET
   call is also covered.

---

## Item 3 — Fix WP-073 test failures

### Analysis

`tests/test_wp073_ingest.py` has six tests that fail at import-time or
execution-time because they reference symbols that do not exist in the current
codebase:

**Three repo-level unit tests (lines 141–180) call:**
```python
knowledge_repo.create_supports_edge(session, chunk_id, control_id, ...)
```
This function does not exist. The function that exists is
`create_supports_edge_framework(session, chunk_id, framework_id, ...)`.

**Three route-level tests (lines 38–87) test the route against a mock
that patches `knowledge_repo.get_control` and `knowledge_repo.create_supports_edge`.**
The actual route handler calls `get_framework` + `create_supports_edge_framework`;
the mocks patch the wrong functions and the model no longer has a `control_id`
field (it uses `framework_id`). These tests will fail with 422 (schema
mismatch) and/or mock assertion errors.

**Recommendation: Option (b) — update the tests to match current code.**

ADR-002 says SUPPORTS can target Framework OR Control. However:
- `create_supports_edge_framework` exists and is tested by the existing passing
  tests further down the file (the `get_chunks_for_control` and
  `get_chunks_for_framework` tests pass).
- `create_supports_edge` (Chunk→Control) does not exist. Implementing it is a
  separate capability, not a housekeeping fix.
- Chunk→Control SUPPORTS is already supported implicitly via
  `get_chunks_for_control` (which queries the graph) but the route currently
  only accepts `framework_id` as target.

Option (a) — adding `create_supports_edge_control` and a dual-target route —
is a genuine feature extension that warrants its own WP. Adding it under
WP-102 housekeeping would grow the scope beyond what is reasonable for this WP.

The tests in question were written for a design that was not fully implemented.
They should be corrected to match the current code (Chunk→Framework only) and
a new WP should be opened for Chunk→Control SUPPORTS when it is needed.

### Approach

Update the six failing tests in `tests/test_wp073_ingest.py`:

**Route-level tests (3):**
- `test_create_supports_returns_200`: change `control_id` → `framework_id` in
  request JSON, update mock to patch `get_framework` not `get_control`, update
  mock to patch `create_supports_edge_framework` not `create_supports_edge`,
  update response assertion from `data["control_id"]` to `data["framework_id"]`.
- `test_create_supports_missing_chunk_404`: change to use `framework_id` in
  body; patch `get_framework` not `get_control`.
- `test_create_supports_missing_control_404`: rename to
  `test_create_supports_missing_framework_404`; use `framework_id` in body;
  patch `get_framework` returning None.

**Repo-level unit tests (2):**
- `test_create_supports_edge_calls_session_run`: rename to
  `test_create_supports_edge_framework_calls_session_run`; call
  `knowledge_repo.create_supports_edge_framework(session, chunk_id,
  framework_id, confidence, raw_score, status, now)` with correct signature
  (7 positional args, not 5); update assertions to check `framework_id` not
  `control_id`.
- `test_create_supports_edge_returns_none_when_no_match`: rename to
  `test_create_supports_edge_framework_returns_none_when_no_match`; call
  `create_supports_edge_framework` with correct 7-arg signature.

**Ingest script tests (4 — lines 257–423):**
These test `ingest_document.main()` via mocked HTTP calls. They reference
`/knowledge/chunk/supports` in assertions. After Item 1's URL rename the
production code will call `/knowledge/chunks/supports`; update the assertion
strings in these four tests to match. This was already noted in Item 1 but
is recorded here as part of the test fix scope.

Also: the ingest script tests use `doc_type` in `doc_resp` fixture data (line
264, 308, 349, 393). WP-100 renamed `doc_type` → `policy_level` on Document.
Check if the mock response dict keys need updating.

**New backlog item to create:** WP-103 — Chunk→Control SUPPORTS edge
(implement `create_supports_edge_control`, add `POST /knowledge/chunks/supports`
dual-target support, add CLI command).

---

## Item 4 — WP-096 numbering collision

### Analysis

BACKLOG.md has two rows with ID WP-096:

| Row | ID | Title | Priority |
|-----|----|-------|----------|
| Priority 15 | WP-096 | API authentication (bearer tokens / API keys) | H/M = 1.5 |
| Priority 24 | WP-096 | Generalise `validate_node_ids` and `replace_edges` utilities | L/M = 0.5 |

The authentication WP (priority 15, H/M) was present first — it has a full
detail spec at the bottom of BACKLOG.md. The generalisation WP (priority 24,
L/M) was added during WP-072 simplify review (per the retrospective note at
line 292).

**Recommendation:** Renumber the generalisation WP to WP-103, preserving the
authentication WP as WP-096. WP-103 is the next unused number (WP-097 through
WP-102 are all allocated; a scan of BACKLOG.md shows no WP-103).

Additionally, if the new WP for Chunk→Control SUPPORTS (from Item 3) is
created, it can take WP-104.

### Approach

1. In the backlog priority table, change priority-24 row from `WP-096` to
   `WP-103` and update the title and notes to remove the "WP-096" reference.
2. In the retrospective note at line 292 (`New backlog item WP-096: generalise...`),
   update to `WP-103`.
3. Add a detail spec section for WP-103 describing the generalisation scope.
4. Add WP-104 stub for Chunk→Control SUPPORTS.

---

## Affected Files

| File | Change |
|------|--------|
| `memory_service/knowledge_routes.py` | Rename route URL (Item 1); add ServiceUnavailable import and try/except to all handlers (Item 2) |
| `scripts/ingest_document.py` | Update URL string (Item 1) |
| `scripts/build_inspector_notebook.py` | Update URL string (Item 1) |
| `tests/test_wp073_ingest.py` | Fix 6 failing tests (Item 3); update URL assertions in 4 ingest tests (Item 1) |
| `BACKLOG.md` | Renumber duplicate WP-096 → WP-103 (Item 4); add WP-103 and WP-104 stubs |

---

## Cypher Patterns

No new Cypher. No changes to `knowledge_repo.py`.

---

## Test Plan

### Unit Tests

**`tests/test_wp073_ingest.py` (Item 3 fix — all existing, corrected)**

| Test | What it verifies |
|------|-----------------|
| `test_create_supports_returns_200` (updated) | Route returns 200 with `framework_id` field; mocks `get_framework` + `create_supports_edge_framework` |
| `test_create_supports_missing_chunk_404` (updated) | 404 when chunk not found; uses `framework_id` body |
| `test_create_supports_missing_framework_404` (renamed + updated) | 404 when framework not found |
| `test_create_supports_edge_framework_calls_session_run` (renamed + updated) | Repo function calls session.run once with correct kwargs |
| `test_create_supports_edge_framework_returns_none_when_no_match` (renamed + updated) | Returns None when session returns no record |

**New unit test file: `tests/test_wp102_housekeeping.py`**

| Test | What it verifies |
|------|-----------------|
| `test_chunks_supports_route_url` | `POST /knowledge/chunks/supports` returns 200 (not 404 for unknown path) via TestClient with mocked driver; confirms the old URL `/knowledge/chunk/supports` returns 404 |
| `test_503_on_service_unavailable_framework` | `POST /knowledge/frameworks` with a driver that raises `ServiceUnavailable` returns HTTP 503 |
| `test_503_on_service_unavailable_chunks` | `POST /knowledge/chunks` with a driver that raises `ServiceUnavailable` returns HTTP 503 |
| `test_503_on_service_unavailable_supports` | `POST /knowledge/chunks/supports` with a driver that raises `ServiceUnavailable` returns HTTP 503 |
| `test_503_on_service_unavailable_trace_up` | `GET /knowledge/controls/x/trace-up` with driver raising `ServiceUnavailable` returns 503 |

### Integration Tests (require live stack)

**File: `tests/test_wp102_integration.py`**

All tests in this file require live Memgraph + running FastAPI service.
Mark each with `@pytest.mark.integration`.

| Test | What it verifies |
|------|-----------------|
| `test_chunks_supports_url_live` | `POST /knowledge/chunks/supports` accepted by live service with valid chunk+framework; old URL `/knowledge/chunk/supports` returns 404 or 405 |
| `test_503_not_triggered_when_db_healthy` | All guarded knowledge routes return non-503 responses when Memgraph is healthy (smoke check) |

### Acceptance Criteria

1. `pytest tests/test_wp073_ingest.py` passes with zero failures (currently 6 fail).
2. `pytest tests/test_wp102_housekeeping.py` passes with zero failures.
3. `GET http://localhost:8000/knowledge/chunk/supports` (old singular URL) does not exist (404 or 405).
4. `POST http://localhost:8000/knowledge/chunks/supports` (new plural URL) responds correctly.
5. When Memgraph is stopped and any knowledge route is called, the response is HTTP 503 with body `{"detail": "Memgraph unavailable"}` — not a 500 traceback.
6. BACKLOG.md contains exactly one `WP-096` entry (API auth) and one `WP-103` entry (generalise utilities).
7. `pytest -x` runs cleanly across all test files.

---

## Risks / Open Questions

1. **`upsert_framework` double session block.** The handler opens two `session()` calls — one for the MERGE, one for the embedding SET. Wrapping both in a single `try` is correct but the implementer must verify the indentation carefully to avoid missing the second block.

2. **Ingest script `doc_type` vs `policy_level` in mock data.** `tests/test_wp073_ingest.py` lines 264, 308, 349, 393 use `doc_type` in mock HTTP response dicts. WP-100 renamed this field to `policy_level` on the Document node, but these are mocked HTTP responses (not live calls) so the key names only matter if the ingest script reads that field from the response. Implementer should check `scripts/ingest_document.py` to see whether it reads `doc_type` from the POST response; if so, update the mock response keys.

3. **WP-023 vs WP-102 overlap.** WP-023 calls for extracting a `get_session` context manager. This WP deliberately does not do that extraction — it only adds the inline try/except. WP-023 should remain in the backlog. The implementer should add a note to WP-023's backlog entry confirming it is still open (the 503 guard is now present; the extraction is still desirable for DRY reasons).

4. **WP-097 URL reference in detail spec.** The WP-097 detail spec in BACKLOG.md mentions `POST /knowledge/chunk/supports` (singular). Update that reference to plural when making the backlog edits.

5. **`build_inspector_notebook.py` URL reference.** This file is in `scripts/` and is not imported by the running service, so the rename is not urgent from a runtime perspective. However it should be kept consistent to avoid confusion.
