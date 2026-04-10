# Graph-Memory Fabric — Completed Work Packages

Chronological record of delivered WPs, retrospectives, and the Retrospective Log.

---

### WP-126 — PostToolUse observer hook for automatic memory capture ✅

> **Completed 2026-04-10.**

- `hooks/post_tool_use.py`: PostToolUse hook script — captures Write, Edit, significant Bash (output ≥10 chars), and WebFetch events as `observation` memories with `files_modified`/`files_read` provenance, `importance=2`, strand `strand-session-activity`
- `scripts/seed_strands.py`: added `strand-session-activity` strand (Companion Domain)
- `.claude/settings.json`: PostToolUse hook registered
- `tests/test_wp126_post_tool_use_hook.py`: full test suite — unit tests (Groups A–D) + integration tests
- Depends on WP-127 ✅ (files_modified/files_read schema already delivered)

**Retrospective:** `observation` type, `files_modified`, `files_read` all pre-existed from WP-127 — hook implementation was purely additive. Three pure functions (`parse_payload`, `is_substantive`, `build_memory_params`) make the filtering logic independently testable without mocking I/O. Hook must always exit 0 to avoid blocking the primary Claude Code session.

---

### WP-132 — Cross-framework INFORMS edges for ISO 22301, ISO 27005, DIN SPEC 14027 ✅

> **Completed 2026-04-10.**

- `scripts/create_new_framework_informs.py`: 9 framework pairs bridged via embedding similarity at threshold 0.55
- 36,785 INFORMS edges created: ISO 27005→ISO 27001 (8,189), ISO 27005→NIST CSF (2,999), ISO 27005→COBIT (1,681), ISO 22301→ISO 27001 (6,074), ISO 22301→NIST CSF (571), ISO 22301→COBIT (3,192), DIN SPEC 14027→ISO 27001 (7,349), DIN SPEC 14027→ISO 22301 (4,205), DIN SPEC 14027→NIST CSF (2,525)
- DIN SPEC 14027→COBIT deliberately excluded (scope too different)
- Average similarity across all pairs: 0.597–0.628; 0 errors

**Retrospective:** Script was already purpose-built for WP-132 (`create_new_framework_informs.py`). Dry-run + histogram review confirmed 0.55 threshold appropriate — distributions clearly bimodal with natural falloff before threshold. ISO 22301→NIST CSF produced the fewest edges (571) as expected: BCM vocabulary maps more weakly to NIST CSF than to ISO 27001/COBIT. No code changes required; WP-132 was pure data work.

---

## WP-039 — Ephemeral test-memory handling

**Completed:** 2026-04-09.

**Delivered:**
- `Memory.ephemeral: bool` property (default `false`) stored on node in Memgraph; set via `POST /memory` with `"ephemeral": true`
- `POST /memory/search` and `GET /memory/wake-up` exclude ephemeral memories by default via `IS NULL OR = false` guard
- `find_duplicate_memory` and `find_near_duplicates` exclude ephemeral memories from dedup lookups
- `POST /memory/maintenance/purge-ephemeral` — bulk hard-deletes all ephemeral memories, returns `{"deleted": N}`
- `memory purge-ephemeral` CLI command; `memory_purge_ephemeral` MCP tool
- `MemoryClient.add_memory` gains `ephemeral=True` kwarg; new `purge_ephemeral()` method
- 13 unit tests + 5 integration tests passing (I6 requires service rebuilt from new code — documented skip)
- Integration test sweep: 10 test files updated with `ephemeral=True` on test writes; 7 files that write-then-search correctly remain non-ephemeral (they rely on `cleanup_nodes` fixture, as they must find the memory they just wrote)

**Retrospective:** Scope was well-defined and the design was clean to implement — the `IS NULL OR = false` guard pattern applied consistently across repo, search, wake-up, and dedup with no surprises. The integration test sweep required judgment on which tests could and could not use `ephemeral=True` (write-then-search tests cannot); documenting that decision explicitly prevented scope creep. Two items deferred to backlog: `get_memory_for_update` missing ephemeral filter (WP-120, acceptable for v1) and the 7 non-ephemeral test files that rely on `cleanup_nodes` (WP-121). The high-urgency driver (16 test artefact memories polluting the live graph) is now eliminated for the majority of integration test writes.

---

## WP-118 — `DELETE /memory/{id}` hard-delete endpoint

**Completed:** 2026-04-09.

**Delivered:**
- `memory_repo.delete_memory(session, memory_id)` — two-query Cypher pattern (existence check + `DETACH DELETE`); no status filter; raises `ValueError` if not found
- `DELETE /memory/{memory_id}` FastAPI route — 204 on success, 404 on missing, 503 on Memgraph down; operation log entry appended
- `MemoryClient.delete_memory(memory_id)` — returns `None` on 204
- `memory delete <id>` CLI command — prints `Deleted <8-char prefix>`; exits 1 on error; no confirmation prompt
- `memory_delete` MCP tool — plain-text confirmation; module docstring updated
- 14 tests (8 unit + 6 integration) in `tests/test_wp118_hard_delete.py`; all passing against live stack

**Retrospective:** Textbook WP — clear scope, clean implementation, no surprises. The Memgraph `DETACH DELETE` / no-RETURN-clause constraint was handled correctly up-front. Two-stage review caught one real issue (hardcoded 404 detail string vs `str(exc)`) and two documentation gaps; all fixed before merge. Now unblocks WP-039 (ephemeral test-memory cleanup).

---

## WP-119 — Built-in maintenance scheduler + maintenance observability

**Completed:** 2026-04-08. *(Delivered without a pre-written WP — added retroactively.)*

### Maintenance scheduler (`memory_service/scheduler.py`)

- New asyncio background task launched inside the FastAPI lifespan — no external cron or systemd timers required
- **Short-rest**: runs every `SHORT_REST_INTERVAL_HOURS` (default 6h); interval-based
- **Long-rest**: runs at `LONG_REST_UTC_HOUR` UTC (default 03:00) if ≥ `LONG_REST_MIN_INTERVAL_HOURS` have elapsed (default 20h); also runs immediately on startup if ≥ `LONG_REST_OVERDUE_HOURS` have elapsed (default 27h) — this is the "service was down at 03:00, run ASAP on restart" path
- Scheduler task is cancelled cleanly on FastAPI shutdown via `asyncio.CancelledError`
- Kill switch: `SCHEDULER_ENABLED=false` reverts to external timer approach
- Six new settings in `Settings`: `scheduler_enabled`, `scheduler_poll_interval_seconds`, `short_rest_interval_hours`, `long_rest_utc_hour`, `long_rest_min_interval_hours`, `long_rest_overdue_hours`

### Index capacity monitoring (added to `long_rest`)

- Step 5 added to `long_rest`: counts all Memory nodes with an embedding (including archived — Memgraph HNSW indexes by node existence, not status) and reports `embedded_memory_count`, `index_capacity`, `index_utilisation_pct`, `index_near_capacity` (flag at ≥80%)
- `memory_index_capacity` now passed through to `long_rest` from settings
- Scheduler logs a `WARNING` when the index is near capacity, referencing WP-116 (embedding migration) as the resolution path
- `LongRestResponse` extended with four new fields; CLI and MCP tool output updated

### Near-duplicate wiring into maintenance

- `long_rest` now runs `find_near_duplicates` as step 6 (after edge rediscovery, so newly linked pairs are immediately evaluated)
- Returns `near_duplicate_count` and `near_duplicate_candidates` (top N preview) in response, maintenance log, CLI output, and MCP summary
- `maintenance_stats` (health endpoint) also reports `near_duplicate_count` so the dedup queue is visible without running a full long-rest
- Scheduler logs near-duplicate count after each long-rest

**Retrospective:** All three improvements were implemented ad-hoc during a maintenance review session triggered by discovering 16 test artefact memories polluting the near-duplicate queue. The scheduler in particular should have been a formal WP — it touches the service lifespan, adds new settings, and changes operational behaviour. Future work: WP-039 (ephemeral test-memory handling), WP-117 (autonomous dedup auto-merge threshold), WP-118 (hard-delete endpoint).

---

## WP-112 — SP 800-53 Rev 5 ATT&CK bridge ingestion

**Completed:** 2026-04-07.

- Downloaded three source files: NIST OSCAL SP 800-53 Rev 5 catalog (10 MB), CTID `attack-control-framework-mappings` STIX bundle (2.1 MB + 3.4 MB controls file), NIST OLIR SP 800-53 ↔ CSF 2.0 crosswalk (740 records, converted from xlsx)
- Wrote `scripts/ingest_sp800_53.py`: parses 324 base controls (20 families) from OSCAL, creates `Framework` nodes (`level=control`, `domain=federal`) under root `sp800-53-r5` via `POST /knowledge/frameworks`; enhancements (e.g. AC-2(1)) excluded by design
- Wrote `scripts/ingest_sp800_53_attack_mappings.py`: three-way STIX join (CTID controls.json stix_id→control_id, CTID mappings.json relationships, enterprise-attack-17.0.json technique stix_ids); enhancement controls stripped to base (`AC-2(1)` → `AC-2`) to maximise MITIGATES coverage; created **4,920 MITIGATES edges** (SP800-53 → ATT&CK technique/sub-technique) via batched UNWIND
- Wrote `scripts/ingest_sp800_53_csf_crosswalk.py`: parses NIST OLIR flat-list crosswalk; normalises zero-padded IDs (`"AC-01"` → `"AC-1"`) and strips enhancements; created **719 INFORMS edges** (SP800-53 → NIST CSF 2.0 subcategory, `source='nist-olir-sp800-53-csf2'`)
- Extended `scripts/create_cross_framework_informs.py` with `--sp800-53` flag: runs SP 800-53 controls against ISO 27001 at threshold 0.55; created **1,173 INFORMS edges** (`source='embedding-similarity'`)
- **34 unit tests + 16 integration tests, all green (50/50)**; traversal-path test confirms `ATT&CK ←[MITIGATES]← SP800-53 →[INFORMS]→ NIST CSF` multi-hop is live

**Retrospective:** The CTID file was a STIX 2.1 bundle (not the flat JSON assumed in the plan), requiring a two-file join with the companion controls.json. The NIST OLIR crosswalk used zero-padded IDs (`"AC-01"`) inconsistent with OSCAL (`"ac-1"`) — the mismatch reduced initial edge count from 725 to 164 until normalisation was added. Both issues were caught by the verify-before-claiming-done discipline: running the edge count query after each script revealed silent MATCH failures rather than wrong assertions. The `source_name` field in CTID controls changed between releases (`"NIST_SP-800-53_rev5"` vs `"NIST 800-53 Revision 5"`); the script accepts both via a set. OSCAL base catalog has 324 controls (not the ~1,100 estimated in the spec — enhancements live in separate profile catalogs). WP-107 (cluster analysis) dependency on WP-112 is now satisfied.

---

## WP-111 — M-Series ATT&CK mitigations ingestion

**Completed:** 2026-04-07.

- Wrote `scripts/ingest_attack_mitigations.py`: parses 44 active `course-of-action` STIX objects from the enterprise ATT&CK v17 bundle, creates `Framework` nodes (`level=mitigation`, `domain=enterprise`) under the ATT&CK root via `POST /knowledge/frameworks`, and writes 1421 `MITIGATES` edges (M-Series → technique/sub-technique) directly via neo4j driver using batched `UNWIND` Cypher (1421 pairs → 3 batches of 500)
- Extended `scripts/create_cross_framework_informs.py` with `--m-series` flag: fetches M-Series nodes and runs embedding similarity against ISO 27001, NIST CSF 2.0, and COBIT 2019; produced 371 `INFORMS` edges (144 ISO, 163 NIST, 64 COBIT) at threshold 0.55
- **12 unit tests + 11 integration tests, all green (23/23)**; integration tests confirmed against live Memgraph + FastAPI stack

**Retrospective:** The `mitreattack-python` library's `get_objects_by_type("relationship")` returns all relationship types in one call — filtering for `relationship_type == "mitigates"` is straightforward but requires building a `{stix_id: node_id}` lookup dict during the mitigation parse pass to resolve STIX UUIDs to graph node IDs. MITIGATES edge writes were initially coded one-per-pair (N+1 pattern); simplify review caught this and the fix to batched `UNWIND` was applied before commit. M-Series descriptions are defensive-control vocabulary and cos-sim significantly better than raw ATT&CK technique descriptions — the 371 INFORMS edges at threshold 0.55 confirm the vocabulary alignment hypothesis from the design. New backlog item WP-115 added to refactor the COBIT→ISO/NIST copy-paste blocks to use the loop pattern introduced in this WP.

---

## WP-106 — MITRE ATT&CK Enterprise ingestion

**Completed:** 2026-04-07.

- Extended `FrameworkCreate`/`FrameworkResponse`/`FrameworkHit` with `external_id` (e.g. `T1566.001`, `TA0001`) and `domain` (e.g. `enterprise`) fields; persisted in `upsert_framework` Cypher and returned by `get_framework` and `search_frameworks`
- Added `POST /knowledge/mitigates` endpoint (Control→Framework `MITIGATES` edge, idempotent); activates the `MITIGATES` edge type defined in ADR-002
- Added `POST /knowledge/informs` endpoint (Framework→Control `INFORMS` edge, idempotent); complement to the direct-Cypher INFORMS creation in WP-105
- Added `create_mitigates_edge` and `create_informs_edge` to `knowledge_repo.py`
- Downloaded ATT&CK Enterprise v17.0 STIX bundle to `data/frameworks/enterprise-attack-17.0.json`
- Wrote `scripts/ingest_attack.py` using `mitreattack-python` library; ingests 694 nodes: 1 root + 14 tactics + 211 techniques + 468 sub-techniques; idempotent (all writes via API MERGE); 34 extra CONTAINS edges for multi-tactic techniques
- Installed `mitreattack-python==5.4.4` (brings `stix2`, `deepdiff`, `pandas` and supporting deps)
- **12 unit tests + 15 integration tests, all green (27/27)**

**Retrospective:** The `mitreattack-python` library significantly simplified ingestion — `get_tactics()`, `get_techniques()`, and `get_parent_technique_of_subtechnique()` handle all STIX relationship traversal. The `get_parent_technique_of_subtechnique()` API returns a list of `{"object": <stix2 obj>, "relationships": [...]}` dicts (not raw STIX objects) — worth noting for future STIX queries. Sub-technique parent IDs are more simply derived by `rsplit(".", 1)[0]` on the external ID (T1566.001 → T1566) rather than via the API. 34 techniques span multiple tactics in Enterprise v17 — multi-parent CONTAINS edges are correctly handled via the existing MERGE-based API. Pre-existing failures in WP-099/WP-105 integration tests (unrelated: `name` field renamed to `title`, and 4-dim test embeddings conflicting with 384-dim vector index) were left as-is.

---

## WP-099 — Knowledge layer schema correction: `:Framework` hierarchy, `body` field, retire `:Control`

**Completed:** 2026-04-04.

- Extended `FrameworkCreate`/`FrameworkResponse` with `level` (default `"framework"`), `body` (optional, embedded when present), `parent_id` (creates `CONTAINS` edge on write)
- Updated `upsert_framework` and `get_framework` in `knowledge_repo.py` to persist and return `level`/`body`; creates `CONTAINS` edge when `parent_id` provided
- Added `search_frameworks` (vector search on `framework_embedding_idx`), `create_supports_edge_framework` (Chunk→Framework), `get_chunks_for_framework` to `knowledge_repo.py`
- Removed `POST /knowledge/controls`, `GET /knowledge/controls/{id}`, `POST /knowledge/search/controls` from `knowledge_routes.py` — these were misused for external standard hierarchy nodes
- Removed trace-up/trace-down/gap-analysis/coverage endpoints (deferred to future org control tree WPs)
- Added `POST /knowledge/search/frameworks` endpoint; renamed `GET /controls/{id}/chunks` → `GET /frameworks/{id}/chunks`
- Updated `POST /knowledge/chunk/supports` to use `framework_id` (was `control_id`)
- Replaced `ctrl_embedding_idx` on `:Control` with `framework_embedding_idx` on `:Framework` in `init_knowledge_schema.py`; removed `:Control(id)` from `KNOWLEDGE_CONSTRAINTS`
- Renamed `ctrl_index_capacity` → `framework_index_capacity` in `config.py` and `.env.example`
- Updated `migrate_embeddings.py`: replaced `Control` with `Framework` in `EMBEDDABLE_LABELS`; `_reconstruct_text` for Framework uses `body` only (nodes without body are skipped)
- Rewrote `load_iso27001_chunks.py`: all ISO 27001 hierarchy nodes now loaded as `:Framework` with `level`/`body`/`parent_id`; SUPPORTS payloads use `framework_id`
- Added `framework = "Framework"` to `NodeLabel` enum in `main.py`
- Updated `dump_db.py`/`restore_db.py` edge allowlists: replaced `HAS_CONTROL` with `CONTAINS`
- **21 unit tests, all green**; 5 integration tests added (require live stack)

**Retrospective:** The subagent for Task 1 removed model classes without removing the route handlers that referenced them, causing an import error. Fixed inline before proceeding with later tasks. Tasks 4, 5, 6 were independent and ran in parallel successfully. The `search_frameworks` Cypher originally used a non-existent `f.framework_root_id` property for filtering — corrected to omit the filter in MVP (the filter parameter is accepted but unused).

---

## WP-076 — InfoSec knowledge layer: integration and separation tests

**Completed:** 2026-04-03. Merged via `feature/knowledge-layer` (commit `d9b78d0`).

- Folded WP-024: `cleanup_nodes` in `tests/conftest.py` extended to accept `dict[str, str | list[str]]` — backward-compatible
- Added `knowledge_client` fixture to `conftest.py` (module-scoped, reloads app with `ENABLE_KNOWLEDGE_LAYER=true`) — eliminates duplication across all knowledge-layer test files
- Created `tests/test_wp076_separation.py`: autouse module-scoped `separation_data` fixture seeds 20 Controls + 50 Chunks + 5 Memory nodes; 3 integration tests assert zero cross-layer leakage in search; 1 static AST import-audit test enforces ADR-001 at all times
- Created `tests/test_wp076_integration.py`: 38 integration tests across `TestKnowledgeSchemaIntegration` (4), `TestKnowledgeWriteIntegration` (13), `TestKnowledgeSearchIntegration` (7), `TestCrossLayerIntegration` (14)
- Updated `tests/test_wp075_traceability.py`: appended `TestTraceabilityIntegration` with 11 integration tests for all four traceability endpoints including org-scoped filtering, knowledge-only mode, and gap-analysis classification
- **52 integration tests + 33 unit tests, all green** against live Memgraph + FastAPI stack

**Retrospective:** Fixture-scope bugs were the dominant failure mode: (1) a session-scoped fixture cannot request a module-scoped one — `separation_data` had to be demoted to module scope; (2) a fixture inside a class body cannot exceed `scope="class"` — `seed_search_data` had to be extracted to module level; (3) the `SearchMemoryResponse` wrapper (`{"memories": [...]}`) was not unwrapped in one test assertion. The dedup-collision issue (missing control validation silently skipped on dedup path) required cleaning sentinel memories by fact prefix before each test run. The `knowledge_client` fixture duplication (3 independent copies across test files) was caught by the code quality review and consolidated into conftest.py.

---

## WP-075 — InfoSec knowledge layer: SABSA bidirectional traceability

**Completed:** 2026-04-03. On `feature/knowledge-layer`.

- Added `trace_up`, `trace_down`, `attribute_coverage`, `gap_analysis` repo functions to `knowledge_repo.py`
- Added `get_business_attribute` and `list_controls` helper functions (extracted during simplify to eliminate inline duplicate queries)
- Added 11 Pydantic models and 4 route handlers to `knowledge_routes.py`: `GET /knowledge/controls/{id}/trace-up`, `GET /knowledge/controls/{id}/trace-down` (with `org_id` query param), `GET /knowledge/attributes/{id}/coverage`, `POST /knowledge/gap-analysis`
- `trace_down` uses OPTIONAL MATCH throughout — fully functional with zero Memory nodes (ADR-001 knowledge-only mode)
- `MemoryRef.relationship_type` typed as `Literal["context", "evidence", "gap"]` matching existing codebase convention
- 32 unit tests, all green; integration tests run in WP-076
- Simplify fixes: removed `get_control()` pre-check from `trace_down` (MATCH detects not-found); extracted `get_business_attribute()` and `list_controls()` helpers; fixed `result is None` branch in `trace_down` to return `None` (not empty dict)

**Retrospective:** The `MATCH (c:Control {id: $id}) OPTIONAL MATCH ...` pattern for not-found detection is more efficient than a pre-check query — one round-trip instead of two. Simplify review caught the redundant pre-check and two inline queries that should have been helpers. Clearing all 32 tests required one fix post-simplify: the `result is None` fallback in `trace_down` was returning an empty dict instead of `None`.

---

## WP-074 — InfoSec knowledge layer: CLI, MCP tools, and ETL

**Completed:** 2026-04-03. On `feature/knowledge-layer`.

- Added `enable_knowledge_layer: bool = False` to `MCPSettings` in `mcp_server/config.py`
- Added 7 `MemoryClient` methods: `search_controls`, `search_chunks`, `list_norms`, `list_documents`, `get_incomplete_jurisdictions`, `get_control`, `get_norm`
- Added 5 feature-flag-gated MCP tools in `mcp_server/server.py` inside `if settings.enable_knowledge_layer:` block: `knowledge_search_controls`, `knowledge_search_chunks`, `knowledge_list_norms`, `knowledge_get_control`, `knowledge_get_norm`
- Added `knowledge` Typer sub-app to CLI with 5 subcommands: `search-controls`, `search-chunks`, `list-norms`, `list-documents`, `review-supports` (stub)
- Created `scripts/ingest_framework.py`: YAML-validated bulk ETL; upserts Framework → Controls → Norms → Documents → Chunks → Jurisdictions → BusinessAttributes; idempotent (409 = "already existed"); `--dry-run` stops after validation
- Created `data/frameworks/`: `nist-csf-2.0.yaml` (15 controls), `iso-27001-2022.yaml` (11 controls), `jurisdictions.yaml` (10), `business-attributes.yaml` (8 SABSA attributes)
- Added `pyyaml` to `pyproject.toml` dependencies; created `KNOWLEDGE_LAYER.md` (429-line operational runbook)
- 15 unit tests, all green; integration tests run in WP-076

**Retrospective:** Parallel Group A → Group B → Group C agent dispatch worked cleanly — zero file conflicts across 6 agents. The `if settings.enable_knowledge_layer:` conditional wrapping `@mcp.tool` function definitions (not just decorators) is the correct FastMCP pattern for feature-flagged tools registered at import time. `review-supports` intentionally stubbed — full implementation deferred to WP-075.

---

## WP-073 — InfoSec knowledge layer: document ingestion pipeline

**Completed:** 2026-04-03. On `feature/knowledge-layer`.

- Added `create_supports_edge` and `get_chunks_for_control` to `knowledge_repo.py` — SUPPORTS edge (Chunk→Control) with `confidence` and `status`
- Added `SupportsCreate`/`SupportsResponse`/`ChunkWithSupports` Pydantic models + `POST /knowledge/chunk/supports` + `GET /knowledge/controls/{id}/chunks` routes
- Added 6 ingest config settings to `config.py` and `.env.example`: `ingest_chunk_size`, `ingest_chunk_overlap`, `ingest_min_chunk_chars`, `ingest_auto_supports`, `ingest_auto_supports_threshold`, `ingest_chunk_review_mode`
- Created `scripts/chunkers.py`: `chunk_markdown` (heading-aware, heading prepended into text) + `chunk_pdf` (pdfplumber, overlapping char windows); infinite-loop guard on `overlap >= chunk_size`
- Created `scripts/ingest_document.py`: HTTP-only ingest CLI; PDF + Markdown; UUIDs per chunk; review mode (default on) + auto-SUPPORTS mode with threshold
- Added `pdfplumber` to `pyproject.toml` dependencies
- 26 unit tests (13 ingest + 13 chunkers), all green; integration tests run in WP-076

**Retrospective:** Through-`main()` test pattern (patch `sys.argv` + `httpx.Client` + `IngestSettings`) is robust for CLI script tests. Quality review caught: infinite loop in `chunk_pdf` when `overlap >= chunk_size` (fixed), missing confidence range validation (fixed via `Field(ge=0.0, le=1.0)`), four ingest tests reimplementing production logic inline instead of calling `main()` (replaced). Two minor items deferred: M2 (singular URL inconsistency → WP-097), M4 (H1 heading handling → WP-097).

---

## WP-072 — InfoSec knowledge layer: cross-layer Memory edges

**Completed:** 2026-04-03. On `feature/knowledge-layer`.

- Created `memory_service/knowledge_bridge.py` (ADR-001 Guardrail 3 — sole cross-layer import module): 8 functions covering `validate_controls`, `validate_documents`, `link_controls`, `link_documents`, `replace_control_edges`, `replace_doc_edges`, `rewire_cross_layer_edges`, `hydrate_controls_and_documents`
- Extended `AddMemoryRequest`, `UpdateMemoryRequest` with `control_ids`, `doc_ids`, `control_relationship_type`, `org_id`; extended `MemoryHit` with `controls`, `documents`
- Wired bridge into `add_memory`, `update_memory`, `merge_memory`, `search_memory` — all guarded by `settings.enable_knowledge_layer`
- Extended `memory_client/client.py` and `mcp_server/server.py` with all 4 new params
- 14 bridge unit tests + 5 model tests + 12 route tests = 31 tests, all green; integration tests run in WP-076

**Retrospective:** Two-wave approach (bridge module first, route wiring second) worked well. Quality review caught bridge-only PATCH not returning 404 for non-existent memory (fixed). Simplify review caught missing `if req.doc_ids:` guard. `_BRIDGE_FIELDS` as module-level constant is the correct pattern. Lazy `from memory_service import knowledge_bridge` inside route handlers is intentional to avoid pytest collection order issues.

---

## WP-071 — InfoSec knowledge layer: search API

**Completed:** 2026-04-03. On `feature/knowledge-layer`.

- Added 5 repo functions to `knowledge_repo.py`: `search_controls` (vector, `ctrl_embedding_idx`), `search_chunks` (vector, `chunk_embedding_idx`), `list_norms`, `list_documents`, `list_incomplete_jurisdictions`
- Added 4 Pydantic models + 5 route handlers to `knowledge_routes.py`: `POST /knowledge/search/controls`, `POST /knowledge/search/chunks`, `GET /knowledge/norms`, `GET /knowledge/documents`, `GET /knowledge/incomplete-jurisdictions`
- 17 unit tests, all green; integration tests run in WP-076

**Retrospective:** Parallel task dispatch (repo + routes simultaneously) worked cleanly — no file conflicts. Quality review surfaced missing `TestListDocuments` Group A tests (fixed) and absence of `ServiceUnavailable` guard across all 13 `knowledge_routes.py` handlers (logged to WP-023).

---

## WP-070 — InfoSec knowledge layer: write API

**Completed:** 2026-04-03. Commit `a1c1148` on `feature/knowledge-layer`.

- Created `memory_service/knowledge_repo.py`: upsert/get for Framework, Control, Norm, Document, Chunk with MERGE ON CREATE SET; optional CONTAINS/IMPLEMENTS/SOURCED_FROM/HAS_CHUNK/HAS_NEXT edges
- Created `memory_service/knowledge_routes.py`: FastAPI router (`/knowledge` prefix) with 10 endpoints; embeddings via `KNOWLEDGE_EMBEDDING_MODEL`; Document carries no embedding (chunks hold vectors)
- `memory_service/main.py`: conditional `app.include_router(knowledge_router)` when `ENABLE_KNOWLEDGE_LAYER=true`
- `scripts/init_knowledge_schema.py`: added missing `("Framework", "id")` uniqueness constraint
- 24 unit tests (13 repo + 11 route), all green; integration tests run in WP-076

**Retrospective:** Key discovery: FastAPI test fixture must reload `memory_service.config` + `memory_service.main` with `ENABLE_KNOWLEDGE_LAYER=true` AND patch `get_driver` before `TestClient` context starts — otherwise the module-level conditional doesn't register knowledge routes. Pattern captured in `test_wp070.py::app_client` fixture for reuse. Scope intentionally narrowed vs. original BACKLOG spec (no jurisdiction scoping in this WP, no MAPPED_TO cross-framework edges) — deferred to later WPs.

---

## WP-077 — Extract schema-init utils + fix embeddings multi-model routing

**Completed:** 2026-04-03. Commit `ac1a506` on `feature/knowledge-layer`.

- Created `scripts/schema_utils.py` with shared `create_constraint()` + `get_embedding_dimension()`
- `init_schema.py` and `init_knowledge_schema.py` now import from `scripts.schema_utils` (no duplication)
- `memory_service/embeddings.py`: added `_model_cache: dict[str, SentenceTransformer]`, `_load_model_by_name()`, and optional `model_name` parameter throughout `get_model`/`get_embedding`/`get_embedding_dimension`/`_cache_key`
- `scripts/migrate_embeddings.py`: both `get_embedding()` call sites now pass `model_name=model_name`
- 11 unit tests, all green; no integration tests (pure Python, no Memgraph)

**Retrospective:** Three simplify wins: (1) `ClientError` import was missing from both init scripts after extraction — runtime `NameError` averted; (2) `_load_model` and `_load_model_by_name` had duplicate offline-setup blocks — extracted to `_make_st_kwargs()`; (3) `_cache_key` ternary simplified. Background agents cannot write files or run Bash in this environment — established as the in-session implementation pattern for all WPs on this branch.

---

## WP-047 — Near-duplicate detection for memory review

**Completed:** 2026-04-02

- `memory_service/memory_repo.py` — `cosine_similarity(a, b)` stdlib helper; `find_near_duplicates(session, threshold, limit)` queries `RELATED_TO`-connected Memory pairs (active, non-ephemeral, with embeddings), computes cosine similarity in Python, returns pairs above threshold sorted by similarity descending
- `memory_service/config.py` — `near_duplicate_threshold: float = 0.92`, `near_duplicate_limit: int = 20`
- `memory_service/main.py` — `GET /memory/duplicates` endpoint; `DuplicateMemoryRef` + `DuplicatePair` Pydantic models; threshold (0–1) and limit (1–100) query params defaulting to settings values
- `memory_client/client.py` — `find_duplicates(threshold, limit)` method
- `memory_client/cli.py` — `find-duplicates` command with Rich table output
- `mcp_server/server.py` — `memory_find_duplicates` MCP tool
- `scripts/dedup_cleanup.py` — consolidated to reuse `memory_repo.cosine_similarity` instead of duplicate `_cosine_distance` implementation
- `tests/test_wp047_near_duplicates.py` — 5 unit tests (`TestCosineSimilarity`), 4 integration/non-integration tests (`TestDuplicatesEndpoint`), 5 unit tests for client/CLI/MCP wiring

**Bug fix:** Initial implementation used directed `(a)-[:RELATED_TO]->(b)` match; changed to undirected `(a)-[:RELATED_TO]-(b)` with `a.id < b.id` dedup guard — directed match silently missed pairs where auto-link created the edge in B→A direction.

**Retrospective:** Plan was accurate and well-specified. Subagent-driven-development worked well — four tasks executed cleanly with spec + quality review catching: directed vs undirected RELATED_TO match bug (Task 3 implementer), archive response not checked in test (Task 3 code review), Optional type annotations on endpoint params (Task 3 code review), mid-file imports in test file (Task 4 code review), missing `env=` in CLI tests (Task 4 code review). Simplify surfaced duplicate `_cosine_distance` in `scripts/dedup_cleanup.py` which was consolidated. Two efficiency items deferred to WP-095.

---

## WP-053 — Scheduled maintenance orchestration for short-rest and long-rest

**Completed:** 2026-04-02

- `scripts/maintenance_runner.py` — standalone script callable by systemd timers; checks last-run timestamps via `/memory/maintenance/stats` and skips if within `--min-interval-hours`; exits 0 on skip or success, 1 on API error
- `scripts/templates/` — four systemd unit files (`memory-short-rest.{service,timer}`, `memory-long-rest.{service,timer}`); `.service` files use `{{PROJECT_DIR}}` and `{{PYTHON}}` placeholders rendered at install time
- `memory schedule install [--target-dir]` — renders templates into `~/.config/systemd/user` (or custom dir); prints enable instructions
- `memory schedule uninstall [--target-dir]` — removes installed unit files
- `memory schedule status` — calls `/memory/maintenance/stats` and prints last short-rest / long-rest timestamps
- `respx` added as test dependency for HTTP mocking

**Retrospective:** Maintenance API was already complete so this was plumbing only. Plan correctly identified no new FastAPI endpoints were needed. Simplify review caught two fixes: merged separate `.service`/`.timer` template loops into a single pass, and fixed TOCTOU anti-pattern in uninstall (`exists()`+`unlink()` → `try/unlink/except FileNotFoundError`). Also extracted `_DEFAULT_SYSTEMD_DIR` constant and `_OPERATION_TS_KEYS` map. Plan referenced `memory_service.config` — correct import is `memory_client.config`; minor plan bug caught at implementation time.

---

## WP-093 — Agent-optimised search: score, min_score, associated expansion

**Completed:** 2026-04-02

- `POST /memory/search` now returns `score: float | null` on each `MemoryHit` — computed as `1.0 - cosine_distance`, rounded to 4 dp; `null` for person-anchored hits (no vector distance)
- New `min_score: float (0–1)` filter on `SearchMemoryRequest` — only primary hits ≥ threshold returned; ignored when `person_ids` is set; empty list is a valid (non-error) result
- New `neighbour_cap: int (0–10, default 3)` on `SearchMemoryRequest` — for each primary hit, up to N associated `Memory` nodes are returned via outbound `RELATED_TO`/`LEADS_TO` edges ordered by edge weight DESC; primary hits excluded from all `associated` lists; person-anchored path always returns `associated: []`
- `AssociatedMemoryHit` Pydantic model added: `id`, `text`, `type`, `importance`, `edge_weight`
- `fetch_associated()` added to `memory_repo.py` — single UNWIND query for all primary IDs, Python-side cap per source
- `MemoryClient.search_memory()` updated with `min_score` and `neighbour_cap` keyword params (backward compatible)
- MCP surface update deferred (follow-on task)

**Retrospective:** TDD worked well across all four tasks. The main complexity was the `associated` dedup logic — primary hits must be excluded from their own `associated` lists, which interacts with `min_score`. Using `min_score=0.95` in the associated expansion tests was the key insight to keep test semantics clean. `RELATED_TO` edge directionality is asymmetric at ingest time; documented in code rather than fixed (fixing would require undirected matching with different semantics for `LEADS_TO`). Simplify review caught two clean-ups: unnecessary `getattr()` replaced with direct attribute access, double `results` iteration collapsed to single pass.

---

## WP-084 — API health and response polish

**Completed:** 2026-04-02

- `GET /health` now returns `version` (from package metadata via `importlib.metadata`) and `build` (7-char git commit hash, falls back to `"unknown"` if git unavailable); both computed once at import time
- `POST /memory` response now includes `strand_ids: List[str]` — echoes the strand IDs passed in the request for new memories; empty list for deduplicated memories
- `MemoryClient.add_memory()` return type changed from `str` to `dict` with keys `memory_id`, `deduplicated`, `strand_ids`
- `mcp_server.memory_add` return type changed from `str` to `dict` (FastMCP serialises automatically)
- CLI updated to extract `result["memory_id"]` from dict return
- `COMPANION.md` documents `### Relevant to today` suppression on small/sparse graphs

**Retrospective:** Three independent improvements batched correctly — combined effort was Low as predicted. The `MemoryClient.add_memory` return type change required updating all callers (CLI + mocks); these were few but worth verifying carefully. MCP return type initially returned `str(result)` (Python repr) which was caught in code quality review and fixed before merge.

---

## WP-089 — Fix wake-up 2-tuple unpacking after WP-054 3-tuple change

**Completed:** 2026-04-02

- `memory_client/cli.py`: updated `wake-up` command to unpack `(core, topic_memories, _maintenance_status)` — was unpacking 2 values from a 3-tuple since WP-054 added `maintenance_status` to `wake_up_split()`, causing `ValueError: too many values to unpack` on every CLI wake-up call
- `tests/test_wp033_mcp_server.py`: updated 3 mock return values (test_u3, test_u6, test_u7) from 2-tuple to 3-tuple `([memories], [], {})`
- `tests/test_wake_up_close_session.py`: updated `TestWakeUpSplitClient.test_returns_core_and_topic_lists` to unpack 3-tuple
- All 25 unit tests in `test_wp033_mcp_server.py` + `test_wake_up_close_session.py` passing

**Retrospective:** WP-054 correctly updated the MCP server and client but missed the CLI unpacking and three test mocks. Bug surfaced in production (Marabot startup failure) rather than CI. Root cause: no regression run against CLI path in WP-054 DoD.

---

## WP-056 — Process log for lifecycle and maintenance operations

**Completed:** 2026-04-02

- Added `_OPERATION_LOG_CAP = 200`, `get_operation_log(session)`, and `append_operation_log(session, entry)` to `memory_service/memory_repo.py` — parallel to the WP-054 maintenance log pair; stores entries as JSON in `sys.operation_log` on the System singleton node
- Added `OperationLogEntry` and `OperationLogResponse` Pydantic models to `memory_service/main.py`
- Added `GET /memory/operation/log` endpoint returning all operation log entries
- Wired `append_operation_log` into all four lifecycle handlers: `update` (with `fields_updated`), `merge` (with `target_id`), `archive`, and `restore`; added `now` computation to `merge_memory` and `restore_memory` handlers which previously lacked it
- Log is written on success path only — failed operations (ValueError → 404) never produce a log entry
- Added `memory_operation_log()` MCP tool to `mcp_server/server.py` returning plain-text summary (most recent first)
- Added `operation_log()` method to `memory_client/client.py`
- Extracted `make_mock_driver()` helper to `tests/conftest.py` (previously inline in test files)
- Fixed redundant `req.model_dump()` call in `update_memory` handler — captures `requested_fields` before `patch_fields` mutation
- 22 tests: 16 unit + 6 integration against live Memgraph; all passing

**New backlog items:**
- WP-091: Add `agent_id` to lifecycle operation log entries — lifecycle endpoints don't currently accept `agent_id`; deferred to follow-up WP (L value, L effort)

**Retrospective:** The parallel structure between `get_operation_log`/`append_operation_log` and the WP-054 maintenance log pair made the repo layer mechanical. The main judgement call was where to write the log: handler vs. repo function — handler was correct because it separates the log from the repo primitive and ensures failed ops don't log. The simplify pass caught a meaningful redundant `model_dump()` call in the update handler, and the test helper extraction to conftest paid off immediately (used by 6 test classes). One latent concern deferred to BACKLOG: the read-modify-write pattern for `append_operation_log` has a theoretical race condition under concurrent lifecycle ops — accepted for v1 single-agent use.

---

## WP-088 — Graph dedup enforcement and agent-ID attribution

**Completed:** 2026-04-01

- Added `memory_dedup_threshold: float = 0.05` to `Settings` in `memory_service/config.py`
- Added `find_duplicate_memory(session, fact, embedding, threshold) -> str | None` to `memory_service/memory_repo.py` — two-stage check: exact case-insensitive `fact` match first, then vector similarity via `vector_search.search`; excludes merged/archived nodes
- Extended `AddMemoryResponse` with `deduplicated: bool = False` (backward-compatible)
- Updated `POST /memory` handler: generates embedding before dedup check; on hit reinforces canonical and returns early with `deduplicated=True`; UUID generation moved after dedup check to avoid scoping issues
- Made `agent_id` a required positional parameter in MCP `memory_add` tool (`mcp_server/server.py`) — removed `or settings.agent_id` silent fallback
- Created `scripts/dedup_cleanup.py` — one-time batch script: finds exact and semantic duplicate groups using union-find + cosine distance (stdlib `math`), merges each group into canonical node (oldest `created_at`; tie-break: highest `importance`), reinforces canonical once per group; supports `--dry-run` and `--similarity-threshold` flags
- Updated `tests/test_add_memory.py::TestPostMemoryFactSoWhat` to UUID-suffix fact strings (pre-existing fragility exposed by the dedup gate)
- Updated `tests/test_wp033_mcp_server.py` to pass explicit `agent_id` (old fallback test updated to test new required behaviour)
- 17 new tests (11 unit, 6 integration); 135 integration tests passing; 0 new regressions

**New backlog items from /simplify:**
- WP-089: Fix 3 pre-existing failing tests in `test_wp033_mcp_server.py` (test_u3, test_u6, test_u7) — `memory_wake_up` mock expects 2-tuple but `wake_up_split` now returns 3-tuple (M value, L effort)
- WP-090: Handle non-`ServiceUnavailable` exceptions in `find_duplicate_memory` (e.g. MAGE not loaded) — currently propagates as 500 instead of 503 (L value, L effort)

**Retrospective:** The dedup gate immediately exposed a latent fragility: several integration tests in `test_add_memory.py` used well-known fact strings ("Oliver has ADHD.") that matched live DB data. UUID-suffixing is the correct fix. The pre-write semantic dedup threshold (0.05) works well with `all-MiniLM-L6-v2` but needed empirical phrase selection for the integration test — the plan's suggested phrases were too distant with UUID suffixes. The `WITH node, distance` Cypher fix (missed in initial implementation, caught by code review) validates the value of the `WITH`-before-`WHERE` codebase pattern. Requiring explicit `agent_id` in the MCP tool is a breaking change that will immediately surface any callers that were relying on the silent fallback — this is the intended effect.

---

## WP-054 — Maintenance audit trail and startup escalation loop

**Completed:** 2026-04-01

- Added `get_maintenance_log(session) -> list` and `append_maintenance_log(session, entry)` to `memory_service/memory_repo.py` — stores JSON audit entries on the `System` node (`maintenance_log` property, capped at 100)
- Wired `append_maintenance_log` into `short_rest()` and `long_rest()` — entries written on real runs only (not dry-run)
- Added `GET /memory/maintenance/log` endpoint, `MaintenanceLogEntry` and `MaintenanceLogResponse` Pydantic models to `memory_service/main.py`
- Replaced `maintenance_warning: Optional[str]` on `WakeUpResponse` with `maintenance_status: MaintenanceStatus` — structured object with `short_rest_overdue`, `long_rest_overdue`, `short_rest_days_ago`, `long_rest_days_ago`, `recommended_action`; checks both maintenance types (previously only long-rest)
- Added `_compute_maintenance_status()` pure helper in `main.py` with priority-ordered `recommended_action` logic
- Added `maintenance_log()` to `memory_client/client.py`; updated `wake_up_split()` return to 3-tuple including `maintenance_status`
- Updated `memory_wake_up` MCP tool to surface maintenance alert block prominently at top of briefing when action is needed; added `memory_maintenance_log` MCP tool
- Updated stale WP-040 tests that checked for the old `maintenance_warning` field
- 29 unit tests + 4 integration tests (live stack), all passing

**Retrospective:** Replacing the single string `maintenance_warning` with a structured `MaintenanceStatus` object was the right call — it lets the MCP surface a clear actionable prompt rather than a passive note, and it exposes both short-rest and long-rest overdue state (the old implementation only checked long-rest). The JSON-on-System-node approach for the audit log keeps the schema minimal (no new node type), which fits v1 constraints well. Watch for: if the audit log needs richer queries (filter by operation type, date range), a dedicated `Operation` node would be warranted — WP-056 is already planned for this.

---

## WP-052 — Expose `person_ids` in MCP `memory_update`

**Completed:** 2026-04-01

- Added `person_ids: list[str] | None = None` parameter to `memory_update` MCP tool in `mcp_server/server.py`
- Updated tool docstring to clarify that `person_ids` is a full replacement (existing ABOUT edges are removed and recreated)
- Threaded `person_ids` through to the underlying `MemoryClient.update_memory()` call which already supported the parameter
- Added unit test U8 to `tests/test_wp033_mcp_server.py`: verifies the parameter is passed through to the client correctly via mock
- Added integration test I6 to `tests/test_wp033_mcp_server.py`: creates a memory linked to one person, updates via MCP to link to a different person, verifies old link is gone and new link is present via HTTP search filter
- All 8 unit tests and 6 integration tests passing

**Retrospective:** Minimal change — single parameter addition to an existing tool; HTTP API, repo layer, and Python client already handled `person_ids` correctly. The implementation surface was straightforward once the pattern was identified. The test plan validated that HTTP PATCH, Python client, and MCP tool all needed to expose the same parameter for true parity, and all three now do.

---

## WP-045 — Make Local Startup Deterministic Offline

**Completed:** 2026-04-01

- Replaced the TCP-only bash healthcheck (`exec 3<>/dev/tcp`) in `docker-compose.yml` with a Python `socket.create_connection` check; increased `start_period` to 30s and `retries` to 10 for more robust cold-start behaviour
- Added `wait_for_memgraph()` to `scripts/start-local-stack.sh` — polls `docker inspect` until the container is `healthy` before launching uvicorn; configurable timeout via `MEMGRAPH_WAIT_TIMEOUT` (default 60s); uses `return 1` (not `exit 1`) for composability with `set -e`
- Documented `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `EMBEDDING_PRELOAD_ON_STARTUP`, and `MEMORY_SERVICE_RELOAD` in `.env.example` with accurate comments; added context comment on `EMBEDDING_LOCAL_FILES_ONLY` as the primary offline control

**Retrospective:** Purely operational — no API or schema changes. The code review surfaced that `exit 1` inside a bash function bypasses trap handlers and the unused `sys` import in the healthcheck one-liner was dead code. Both caught pre-merge. The `.env.example` comment for `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` initially misrepresented the control flow (the embeddings module derives these from `EMBEDDING_LOCAL_FILES_ONLY`, not the other way around) — code review caught it. Good signal that doc changes need the same review rigour as code.

---

## WP-083 — `person_ids` filter on `POST /memory/search`

**Completed:** 2026-03-31

- Added `person_ids: Optional[List[str]] = None` to `SearchMemoryRequest` in `memory_service/main.py`
- Extended `_SEARCH_QUERY_TEMPLATE` in `memory_service/memory_repo.py` with `OPTIONAL MATCH (m)-[:ABOUT]->(per:Person)` / `WHERE ($person_ids IS NULL OR per.id IN $person_ids)` — identical pattern to existing `project_ids` filter
- Propagated `person_ids` through `MemoryClient.search_memory` in `memory_client/client.py`
- Exposed `person_ids` in MCP `memory_search` tool in `mcp_server/server.py` with docstring explaining semantics
- Added `TestPersonIdsFilter` (4 integration tests) to `tests/test_search_memory.py`: single-person filter, multi-person OR, backward-compat with omitted filter, composition with `tags`
- All 31 search tests passing

**Retrospective:** The `project_ids` filter was an exact template for this change — implementation was mechanical once the pattern was identified. TDD caught a Pydantic silent-drop behaviour (unknown fields aren't rejected by default) which meant tests initially showed 2 passing instead of all failing; the correct TDD-red signal was 2 assertion failures on the filter-dependent tests. The `getattr` defensive guard introduced during implementation was caught in code review and replaced with direct attribute access — consistent with all adjacent params.

---

## WP-012 + WP-013 — Pin Dependency and Docker Image Versions (2026-03-31)

- Added `<next_major` upper bounds to all three `requirements.txt` files (`memory_service`, `memory_client`, `mcp_server`); original lower bounds preserved
- Replaced `memgraph/memgraph-mage:latest` and `memgraph/lab:latest` with `3.9.0` in `docker-compose.yml`
- `pip check` shows no new conflicts introduced (pre-existing `pygobject`/`docling-core` warnings unchanged)

**Retrospective:** Purely mechanical config change. The installed versions at time of pinning are: fastapi 0.135.1, uvicorn 0.42.0, neo4j 6.1.0, sentence-transformers 5.3.0, pydantic 2.12.5, fastmcp 3.1.1, memgraph 3.9.0. When any package crosses its ceiling, bump intentionally after reviewing the changelog.

---

## WP-055 — Fix Long-Rest Edge Discovery Reporting Mismatch (2026-03-31)

- Replaced per-node `count(r)` accumulation in the live rediscovery path of `long_rest()` with a single post-loop Cypher count query: `MATCH ()-[r:RELATED_TO]->() WHERE r.last_activated_at = $now_iso AND r.activation_count = 0 RETURN count(r)`
- `edges_discovered` now equals the count of edges verifiable in the graph by timestamp + activation_count, eliminating the mismatch observed on 2026-03-27 (reported 8, graph had 15)
- Dry-run path unchanged: continues accumulating `would_discover` per-node as a forward-looking estimate
- Added `test_long_rest_edges_discovered_matches_graph` integration test to `TestLongRest`

**Retrospective:** Straightforward single-query replacement. The post-loop count pattern is more trustworthy than per-MERGE accumulation for any future maintenance operations that write edges in bulk.

---

## WP-080 — Server-side `min_importance` filter on memory search

**Completed:** 2026-03-31

- Added `min_importance: Optional[int]` (range 1–5) to `SearchMemoryRequest` in `memory_service/main.py`
- Added `AND ($min_importance IS NULL OR m.importance >= $min_importance)` to `_SEARCH_QUERY_TEMPLATE` in `memory_service/memory_repo.py`
- Passed `min_importance` through `search_memories()` to the Cypher query
- Added `min_importance: int | None = None` keyword parameter to `MemoryClient.search_memory()` in `memory_client/client.py`
- 5 integration tests added to `tests/test_search_memory.py` (`TestSearchMinImportance`)
- When omitted, behaviour is unchanged (no filtering applied)

**Retrospective:** Straightforward parameter threading. Consider extending the same pattern to `min_strength` if callers need decay-aware filtering server-side.

---

## WP-079 — Importance recalibration pass

**Date:** 2026-03-28

- Reviewed all active memories at `importance >= 4` against the blast-radius-of-absence definition introduced in `memory_client/COMPANION.md`
- Recalibrated `145` of the `174` reviewed memories by updating `importance` only; no memory text or graph structure changed
- One additional active `importance=4` memory discovered outside the initial export was downgraded during verification, for `146` total live updates
- High-priority pool reduced from `174` memories (`58` fives, `116` fours) to `52` (`13` fives, `39` fours)
- Final active-memory distribution after the pass: `13` at `5`, `39` at `4`, `174` at `3`, `26` at `2`, `3` at `1`
- Surviving `5` memories are now concentrated on hard boundaries, startup / HITL protocol, Mara identity anchors, Umbrella safety cues, and primary-relationship constraints
- Surviving `4` memories are now concentrated on live project constraints, current job-search rules, material communication guidance, and high-impact personal calibration such as ADHD support needs
- Added a data-pass plan and verification note at `docs/superpowers/plans/2026-03-28-wp-079-importance-recalibration.md`

**Retrospective:** The main risk was not under-correcting single memories but preserving whole inflated categories. Reviewing by blast radius rather than emotional salience cleaned this up quickly: relationship texture, biography, project history, and ritual detail mostly belong at `3`, not `4` or `5`. The one extra `importance=4` memory found during verification is a good reminder that future recalibration tooling should query live data again immediately before mutation, not rely only on a single export snapshot.

---

## WP-069 — Cybersecurity knowledge layer: schema, indexes, multilingual model

**Date:** 2026-03-28

- New `scripts/init_cybersec_schema.py` — idempotent Memgraph setup for the knowledge layer: 7 uniqueness constraints (`Standard.id`, `Control.id`, `Document.id`, `Chunk.id`, `BusinessAttribute.id`, `Organisation.id`, `Jurisdiction.code`), two vector indexes (`ctrl_embedding_idx ON :Control(embedding)`, `chunk_embedding_idx ON :Chunk(embedding)`), post-creation validation via `SHOW INDEX INFO`, legacy capacity advisory for `mem_embedding_idx`
- New `memory_service/cybersec_schemas.py` — shared enum-like frozensets: `SABSA_LAYERS`, `CONTROL_DOMAINS`, `CONTROL_RELATIONSHIP_TYPES`, `DOCUMENT_POLICY_LEVELS`, `JURISDICTION_TYPES`, `ORGANISATION_TYPES`
- New `scripts/migrate_embeddings.py` — one-time re-embedding migration for `Memory`, `Control`, and `Chunk` nodes after switching `EMBEDDING_MODEL`; idempotent (skips nodes where `embedding_model_name` already matches); `--dry-run` and `--batch-size` flags
- `memory_service/config.py` — added `memory_index_capacity: int = 5000`, `ctrl_index_capacity: int = 5000`, `chunk_index_capacity: int = 10000`
- `memory_service/main.py` — `NodeLabel` enum extended with 7 knowledge-layer labels: `Standard`, `Control`, `Document`, `Chunk`, `BusinessAttribute`, `Organisation`, `Jurisdiction`
- `scripts/init_schema.py` — fixed `SHOW INDEX INFO` column name (`"index type"` with space); `create_vector_index` now accepts configurable `capacity` parameter; `mem_embedding_idx` capacity defaults to `settings.memory_index_capacity` (5000)
- `scripts/dump_db.py` — edge query broadened from `:Memory`-scoped `RELATED_TO|LEADS_TO` to label-agnostic `WHERE type(r) IN [...]` covering all 13 edge types including the knowledge layer
- `scripts/restore_db.py` — `ALLOWED_EDGE_TYPES` frozenset expanded to all 13 edge types; hoisted to module level (was inside loop)
- WP-019 closed (superseded): `ctrl_index_capacity` and `chunk_index_capacity` config fields, plus `mem_embedding_idx` capacity bump to 5000, fold in WP-019's scope
- 12 unit tests + 4 integration tests in `tests/test_wp069_cybersec_schema.py`

**Retrospective:** Memgraph's `SHOW INDEX INFO` and `SHOW CONSTRAINT INFO` use space-containing column names (`"index type"`, `"constraint type"`, `"properties"` as list) not the simple `"type"` or `"property"` names you'd expect. All record lookups need `.get("index type") or .get("type")` fallback chains. Deferred to WP-077: `create_constraint()` and `get_embedding_dimension()` are duplicated identically between `init_schema.py` and `init_cybersec_schema.py` — worth extracting to `scripts/schema_utils.py` once there are three init scripts.

---

## WP-051 — Fix merge rewiring dedup for weighted relationships

**Date:** 2026-03-28

- `merge_memory()` previously used `MERGE (tgt)-[:IN_STRAND {weight: ...}]->(s)` and `MERGE (tgt)-[:RELATED_TO {weight: ...}]->(rel)` — because Memgraph matches the entire pattern including inline properties, these created duplicate parallel edges when the target already had the same topological edge with a different weight
- Fixed by switching to topology-only MERGE (`MERGE (tgt)-[existing:IN_STRAND]->(s)`) with `ON CREATE SET` / `ON MATCH SET` to populate or reconcile properties
- IN_STRAND reconciliation: `weight = max(existing, source)`
- RELATED_TO reconciliation: `weight = max`, `activation_count = sum`, `last_activated_at = more recent`, `decay_rate = min` (lower rate = more consolidated)
- Dropped internal-only `now_iso` parameter from `merge_memory()`; generated unconditionally inside the function
- Moved `count_edges` and `get_edge_props` helpers to `tests/conftest.py` alongside existing graph inspection helpers
- 5 new integration tests: IN_STRAND dedup (target wins, source wins), RELATED_TO full property reconciliation, sparse edge with missing properties, pure rewire

**Retrospective:** Memgraph does not support `min()` as a scalar function in Cypher. The first attempt used `min(existing.weight, 1.0)` for a weight cap — dead code in any case since weights are bounded 0–1. Removed on `/simplify` review. The topology-only MERGE pattern (MERGE then SET) is the right approach for any edge carrying properties that may be written from multiple sources.

---

## WP-038 — Memory lifecycle operations: update, merge, archive, restore

**Date:** 2026-03-27

- Added `status: 'active'` to all new Memory nodes at creation; search and wake-up now filter `WHERE (m.status IS NULL OR m.status = 'active')` for backwards compatibility with pre-WP-038 nodes
- `PATCH /memory/{id}`: in-place update of fact, so_what, tags, importance, person_ids, strand_ids; recomputes embedding when text content changes; person_ids/strand_ids are full replacements
- `POST /memory/{id}/merge`: rewires ABOUT, IN_STRAND, LEADS_TO (both directions), RELATED_TO (both directions) from source to target; creates MERGED_INTO tombstone edge; sets `source.status='merged'`, `source.superseded_by=target_id`
- `POST /memory/{id}/archive`: sets `status='archived'`, `archived_at`; excluded from search and wake-up
- `POST /memory/{id}/restore`: returns archived memory to active, clears `archived_at`; merged memories cannot be restored
- `get_memory_for_update` repo helper fetches current fact/so_what for merge-then-recompute pattern; PATCH endpoint uses single session for both read and write
- Client, CLI, and MCP updated with `update_memory`, `merge_memory`, `archive_memory`, `restore_memory`
- New `tests/test_wp038_lifecycle.py`: 14 unit tests (Pydantic validation, Cypher filter assertions, HTTP client/CLI wire-up) + 21 integration tests covering all status transitions, edge rewiring, and exclusion from search/wake-up

**Retrospective:** /simplify caught three issues post-implementation: a redundant existence check in `update_memory` (the endpoint already validates via `get_memory_for_update`), two separate DB sessions in the PATCH endpoint that could be one, and a dead `now` parameter in `merge_memory` that was accepted but never used. All fixed before commit.

---

## WP-022 — Cap neighbour count in search results

**Date:** 2026-03-27

- Added `search_neighbour_cap: int = 50` to `Settings` (config.py) and `.env.example`; prevents response bloat from highly-connected nodes on dense graphs
- `search_memories` in `memory_repo.py` now requires a `neighbour_cap: int` argument; each `collect(DISTINCT x.id)` Cypher expression carries `[..{neighbour_cap}]` so the database slices before serialisation
- `main.py` call site passes `settings.search_neighbour_cap`
- New `tests/test_wp022_neighbour_cap.py`: 4 unit tests (Cypher string assertions) + 3 integration tests; uses `monkeypatch` for settings override

**Retrospective:** Integration tests initially failed because `add_memory` auto-creates `RELATED_TO` edges, making exact neighbour counts unpredictable. Fixed by using `max_hops=0` to isolate LEADS_TO traversal and switching the below-cap test to assert `>=` rather than exact equality.

---

## WP-048 — Two-speed decay + importance floor to protect core memories

**Date:** 2026-03-26

- Added 4 new config fields: `initial_strength_factor` (0.4), `memory_initial_decay_rate` (0.07), `memory_consolidated_decay_rate` (0.01), `importance_floor_factor` (0.3)
- `add_memory`: initial strength = `initial_strength_factor * importance/5` (was `importance/5`); decay rate = `memory_initial_decay_rate` (fast); `min_strength` = `importance_floor_factor * importance/5` stored on node
- `reinforce_memory`: first reinforcement switches `decay_rate` to `memory_consolidated_decay_rate` using pre-increment count check via WITH clause
- `decay_pass` + `short_rest`: read per-node `min_strength` as decay floor; fall back to global `min_memory_strength` for nodes without the property
- Updated `tests/test_wp029_reinforcement.py` for new initial-strength expectations
- New `tests/test_wp048_two_speed_decay.py`: 8 unit tests + 8 integration tests covering all acceptance criteria

**Retrospective:** The Memgraph evaluation-order nuance in the consolidation Cypher (needing a `WITH` to capture pre-increment `reinforcement_count`) was the only implementation surprise. Per-node `min_strength` fallback for pre-existing memories requires no migration — `coalesce` handles it cleanly.

---

## WP-046 — Deduplicate search and wake-up results

**Date:** 2026-03-26

- Added `WITH DISTINCT` to `_SEARCH_QUERY_TEMPLATE` so primary search hits are deduplicated before multi-hop OPTIONAL MATCH traversal fan-out
- Added `WITH DISTINCT` to both core and topic queries in `wake_up` to guard against duplicate rows from multi-strand OPTIONAL MATCH joins
- Regression tests in `tests/test_wp046_dedup.py`: diamond-topology neighbour dedup, primary results dedup, wake-up topic dedup
- All 3 dedup tests pass; no regression in 22 existing search tests

**Retrospective:** Fix was surgical — one `DISTINCT` keyword in each of three Cypher queries. The diamond-topology test correctly documents the expected invariant even though it passed before the fix (sparse graph); it will catch regressions on a denser graph.

---

## WP-044 — Fix broken 503 + connect-error tests

**Date:** 2026-03-25

- `test_returns_503_when_db_down` (×2): moved mock-driver assignment inside `TestClient` context so lifespan no longer overwrites it; removed `test_driver` fixture dep (no live DB needed)
- `test_connect_error_exits_nonzero` (×2): replaced env-redirect approach (ignored by pydantic-settings at import time) with `respx.mock` + `side_effect=httpx.ConnectError`, matching existing pattern in `test_wake_up_close_session.py`
- All 4 tests now exercise the intended failure paths; 121 passing (was 119), no regressions

**Retrospective:** Root causes were well-documented in the backlog — execution was straightforward once the patterns were clear. The `test_driver` fixture dependency on the 503 tests was an easy miss (tests looked like integration tests but were really unit tests).

---

## WP-040 — Memory maintenance orchestration: Short Rest & Long Rest

**Date:** 2026-03-22

- 7 new Settings fields: `short_rest_recency_days`, `long_rest_recency_days`, `rediscovery_strength_threshold`, `edge_hard_prune_floor`, `edge_hard_prune_min_days`, `edge_modulation_factor`, `edge_modulation_cap`
- `System` singleton node created by `init_schema.py` (MERGE, idempotent); stores `last_short_rest_at` / `last_long_rest_at`
- `_apply_decay_modulated()` — edge-modulated decay: `effective_rate = base_rate / min(1 + factor * incoming_weight_sum, cap)` — well-connected nodes decay slower (elaborative encoding)
- `decay_pass()` extended with `node_ids`, `edge_modulation_factor`, `edge_modulation_cap`, `dry_run` kwargs; UNWIND writes gated on `if not dry_run`; incoming edge weights fetched via `OPTIONAL MATCH`
- `short_rest()` — scoped decay: Python-side recency filtering (`recall_count > 0 OR last_used_at within recency window`); updates `last_short_rest_at`
- `long_rest()` — 4-step: full decay_pass + per-node vector rediscovery + prune candidates + system node update
- `maintenance_stats()` — node/edge health snapshot + overdue flags vs. `short_rest_recency_days` / `long_rest_recency_days`
- `POST /memory/maintenance/short-rest[?dry_run=true]` / `POST /memory/maintenance/long-rest[?dry_run=true][&prune=true]` / `GET /memory/maintenance/stats` — all registered before `POST /memory/{memory_id}/reinforce` (route ordering)
- `GET /memory/wake-up` extended: `maintenance_warning` field surfaced when `last_long_rest_at` is stale (best-effort, never fails wake-up)
- `MemoryClient.short_rest()`, `.long_rest()`, `.maintenance_stats()` + CLI `memory short-rest`, `memory long-rest`, `memory status`
- MCP `memory_short_rest`, `memory_long_rest`, `memory_maintenance_stats` tools
- `scripts/dump_db.py` + `scripts/restore_db.py` — pre-maintenance snapshot + MERGE-based restore with edge-type allowlist
- 23 new tests (unit + integration); 220 passing; 4 pre-existing failures unchanged
- **Key finding:** `edge_modulation_cap` default of `1.0` makes modulation inert — plan review caught and corrected to `10.0` before implementation. Division-by-zero guard (`max(..., 1e-9)`) added to `_apply_decay_modulated`. Plan review also caught WHERE clause operator precedence bug in `short_rest` Cypher.

**Retrospective:** Three plan-review catches before a line of code was written saved at least one full debug cycle each. Quality review on Task 7 (CLI) surfaced output-placement inconsistency (`console.print` outside try block) and a false-positive dry-run test — both fixed before Task 10. Subagent-driven development worked cleanly across 10 tasks with no regressions. The per-node rediscovery loop in `long_rest` is O(k) vector queries — noted as a known scalability limit for large graphs; deferred to v2.

---

## WP-029 — Memory + edge reinforcement (strength, decay, Hebbian activation)

**Date:** 2026-03-22

- 8 new Settings fields (`memory_decay_rate`, `edge_decay_rate`, `recall_strength_increment`, `explicit_strength_increment`, `edge_recall_increment`, `edge_explicit_increment`, `edge_prune_threshold`, `min_memory_strength`)
- Memory nodes created with `strength = importance / 5.0`, `recall_count=0`, `reinforcement_count=0`, `last_reinforced_at`, `decay_rate`
- `recall_increment()` — non-blocking background task fires after every search; increments node strength (capped 1.0) and activates `RELATED_TO|LEADS_TO` edges within result set
- `decay_pass()` — Python-side computation (Memgraph does not support `duration.between()` on datetime types); fetches nodes/edges, applies `strength * exp(-rate * days)`, writes back via UNWIND
- `reinforce_memory()` — explicit signal; updates `last_reinforced_at`, increments `reinforcement_count`, Hebbian UNWIND×UNWIND over co-recalled edges
- `POST /memory/maintenance/decay` and `GET /memory/maintenance/weak-edges` registered before `POST /memory/{memory_id}/reinforce` (FastAPI route ordering critical)
- `memory reinforce-memory`, `memory run-decay` CLI commands; `memory_reinforce`, `memory_run_decay` MCP tools
- `scripts/migrate_reinforcement_defaults.py`: backfills pre-existing nodes/edges; ran against live DB (0 nodes, 123 edges updated)
- **Key finding:** Memgraph does not support `duration.between()` on datetime types — Python-side decay computation required. Cypher `localDateTime()` rejects `+00:00` suffix — `strftime("%Y-%m-%dT%H:%M:%S")` required for any Cypher date arithmetic.

**Retrospective:** Route ordering catch (Task 4 before Task 5) was the highest-risk item — the plan review caught it preemptively and the shadow test `test_decay_pass_not_shadowed_by_reinforce_route` confirms it at runtime. Memgraph `duration.between()` incompatibility required Python-side decay (2-round-trip design); functionally equivalent. Subagent-driven development with spec+quality review per task caught no regressions across 8 tasks.

---

## WP-037 — Person nodes + `ABOUT` edges

**Date:** 2026-03-21

- `PersonItem`, `PersonsResponse`, `CreatePersonRequest` Pydantic models added; `GET /person` and `POST /person` endpoints (MERGE + SET upsert semantics)
- `list_persons()` and `upsert_person()` added to `memory_repo.py`; `upsert_person` guards `result.single()` with RuntimeError on unexpected None
- `MemoryClient.list_persons()` and `MemoryClient.create_person()` added to `memory_client/client.py`
- CLI `list-persons` (Rich table) and `create-person` (positional id + `--name` + `--description`) added to `memory_client/cli.py`
- MCP `memory_list_persons` and `memory_create_person` tools added to `mcp_server/server.py`
- `scripts/migrate_person_nodes.py`: JSON-line stdin/stdout, `--dry-run`, `--pre-created-persons`, `coalesce` name heuristic preserves explicit names
- `scripts/__init__.py` created for package resolution under pytest
- **Key finding:** `person_ids`, `ABOUT` edge creation (step 3 in `add_memory`), and `Person` schema constraint were already implemented — WP-037 added the management endpoints and migration only
- 59 new tests (32 unit, 27 integration); 175 total passing; 4 pre-existing failures unchanged

**Retrospective:** Parallel subagent dispatch (Tasks 6–7 and 8–9 in parallel; 10–11 and 12–13 in parallel) shaved significant wall-clock time. Review-loop quality gate caught the `result.single()` None guard in Task 3 — caught before integration tests ran. Tasks 12–13 required `scripts/__init__.py` for dotted imports under pytest — not in the original plan but a 1-line fix.

---

## WP-028 — Causal graph: `fact`/`so_what` fields + `LEADS_TO` edge

**Date:** 2026-03-21

- `AddMemoryRequest` split into `fact` + `so_what`; `text` deprecated as alias via `model_validator(mode="before")`; `text` derived as `fact + " " + so_what` and used for embeddings
- `cause_ids`/`effect_ids` on `AddMemoryRequest`; steps 6 & 7 in `memory_repo.add_memory()` create `LEADS_TO` edges using `OPTIONAL MATCH + WHERE IS NOT NULL + MERGE` (missing UUIDs silently skipped)
- `traversal_direction` on `SearchMemoryRequest` (`none|causes|effects|both`); `search_memories()` builds LEADS_TO clauses independently of `max_hops`; `hop_depth = max(hops, 1)` ensures traversal even when `max_hops=0`
- `memory_client/client.py`, `cli.py`, `mcp_server/server.py` all updated; `close-session` scaffolds updated to use `fact=`/`so_what=` and include causal link step
- `scripts/migrate_fact_so_what.py`: JSON-line stdin/stdout protocol, `--dry-run`, idempotent (WHERE m.fact IS NULL, always fetches from SKIP 0)
- 6 unit tests + 9 integration tests; 117 passing, 3 pre-existing mock failures

**Retrospective:** Three rounds of plan review were needed — each caught real bugs: Pydantic v2 `Optional[str] = None` vs `str = ""` sentinel, migration pagination bug (SKIP 0 not offset), vacuous test assertions. Two-stage review (spec then quality) paid off — quality review caught the `not fact` vs `is None` issue which was a genuine correctness hazard.

---

## WP-033 — MCP server + Claude Code/Desktop wiring

**Date:** 2026-03-21

- FastMCP-based server in `mcp_server/` exposing 5 tools via STDIO: `memory_add`, `memory_search`, `memory_wake_up`, `memory_list_strands`, `memory_close_session`
- `pyproject.toml` consolidated (removed `setup.cfg`), `memory-mcp` entry point registered
- `.mcp.json` created at repo root for Claude Code auto-discovery
- `WIRING.md` fully updated: Claude Code MCP + CLI wiring, Claude Desktop entry-point + fallback configs
- `COMPANION.md` updated: MCP tools as preferred path, CLI as fallback
- 7 unit tests + 5 integration tests all passing

**Retrospective:** FastMCP decorator syntax is clean; fresh-client-per-call pattern safe for concurrent requests; plain-text briefing assembly avoids Rich dependency in server; `.mcp.json` auto-discovery in Claude Code works out of the box. Setup.cfg/pyproject.toml conflict required removing setup.cfg and using `--no-build-isolation` for editable installs in this environment.

---

## WP-032 — End-to-end companion validation

**Date:** 2026-03-21

- Ran full companion validation session against live stack; all five criteria passed
- Identified and resolved a pre-existing service-restart issue (stale uvicorn process) causing strand_id to be absent from wake-up API responses
- Created `docs/wp-032-validation-evidence.md` with PASS/FAIL evidence, gap analysis, and three new backlog items (WP-034, WP-035, WP-036)

**Retrospective:** The audit against the spec (Section 4.2) before starting WP-032 caught two deviations from WP-030: grouping by tag instead of strand_id, and missing the topic section. The stale-service bug (no `--reload` on uvicorn start) was invisible from the CLI — argues for a version hash in `/health` (WP-034).

---

## WP-031 — `memory_client` companion package: COMPANION.md + WIRING.md + docs

**Date:** 2026-03-21

- Created `memory_client/COMPANION.md` — full session protocol: wake-up, add-memory, close-session; type/importance reference; minimal session pattern
- Created `memory_client/WIRING.md` — Claude Code wiring (active), Claude Desktop + MCP placeholder (WP-033), generic HTTP/Python fallback
- Created `docs/companion-integration.md` — high-level overview, current capability status table, quick-start snippet

**Retrospective:** Pure docs WP — fast to execute.

---

## WP-030 — `memory wake-up` + `memory close-session` CLI commands

**Date:** 2026-03-21

- Added `wake_up(session, limit, topic_embedding)` to `memory_repo.py`: importance-ranked query merged with optional vector search, deduplicated, capped at limit; extracted `_record_to_memory_dict()` helper
- Added `WakeUpMemoryItem`, `WakeUpResponse` Pydantic models and `GET /memory/wake-up` endpoint with `Query()` params
- Added `MemoryClient.wake_up()` to `memory_client/client.py`
- Added `memory wake-up` and `memory close-session` CLI commands to `memory_client/cli.py`
- Created `tests/test_wake_up_close_session.py`: 15 tests (12 unit, 3 integration); all passing

**Retrospective:** `/simplify` caught a two-HTTP-call design flaw in the CLI (server already handles merge server-side). `Field()` vs `Query()` for FastAPI query params is a subtle footgun — always use `Query()` in endpoint function signatures.

---

## WP-027 — `memory list-strands` CLI command

**Date:** 2026-03-21

- Fixed all 20 strand descriptions in `scripts/seed_strands.py` to use "the user"/"the Companion" language convention
- Added `list_strands(session)` to `memory_repo.py`, `StrandItem`/`StrandsResponse` models and `GET /strands` endpoint
- Added `MemoryClient.list_strands()` and `memory list-strands` CLI command (grouped by category)
- Created `tests/test_list_strands.py`: 15 tests all passing

**Retrospective:** `/simplify` identified CLI error handler duplication at 4 copies — WP-025 trigger condition met.

---

## WP-015 — In-session LLM workflow patterns

**Date:** 2026-03-20

- Created `docs/workflows/` with five workflow files and index README: `contextual-recall.md`, `summarise-session.md`, `propose-todos.md`, `refine-edges.md`, `strand-maintenance.md`

**Retrospective:** Workflow docs must be validated against the actual API response schema — `created_at` not returned by search API; caught and fixed before commit.

---

## WP-007 — memory_client.py + Typer CLI

**Date:** 2026-03-20

- Created `memory_client/` package: `config.py`, `client.py` (`MemoryClient` httpx wrapper), `cli.py` (Typer `add-memory`, `search-memory`, `dump-graph`)
- Created `pyproject.toml` + `setup.cfg` for editable install and `memory` entry point
- Created `tests/test_cli.py`: 17 unit tests using `typer.testing.CliRunner` + `respx` mocks

---

## WP-005 — Wire POST /memory/search

**Date:** 2026-03-20

- Added `_SEARCH_QUERY_TEMPLATE` and `search_memories()` to `memory_repo.py`: single Cypher query combining vector search, tag/agent/project filters, and optional neighbour expansion
- Implemented `search_memory` endpoint in `main.py`
- Created `tests/test_search_memory.py`: 18 tests across 8 classes

---

## WP-004 — Wire POST /memory

**Date:** 2026-03-20

- Created `memory_service/memory_repo.py`: `add_memory()` — Agent+Memory+PRODUCED_BY in one round-trip; Project/Person/Strand upserts; auto + explicit RELATED_TO
- Updated `main.py` with driver lifecycle, `strand_ids`, `importance` validation, 503 handling
- Updated `tests/conftest.py`: `test_driver`, `client` fixtures; shared graph helpers (`node_exists`, `edge_exists`, `get_memory_node`, `cleanup_nodes`)
- Created `tests/test_add_memory.py`: 14 integration tests

---

## WP-016 — Shared config module

**Date:** 2026-03-20

- Created `memory_service/config.py`: canonical `Settings`, `get_driver()`, module-level `settings` singleton
- Removed duplicate `Settings`/`get_driver()` from `main.py`, `init_schema.py`, `smoke_test.py`

---

## WP-018 — Vector index dimension from model at runtime

**Date:** 2026-03-20

- Added `get_embedding_dimension()` and `get_existing_index_dimension()` to `init_schema.py`; detects dimension mismatch before create with actionable error message
- Updated `tests/test_embeddings.py` to use model-reported dimension instead of hardcoded 384

---

## WP-002 — Memgraph schema + vector index

**Date:** 2026-03-20

- Created `scripts/init_schema.py`: uniqueness constraints on all node labels + cosine vector index on `Memory(embedding)`. Idempotent.
- Created `scripts/smoke_test.py`: insert → vector search → assert → cleanup

---

## WP-003 — Local embeddings module

**Date:** 2026-03-20

- Created `memory_service/embeddings.py`: `get_embedding(text) -> list[float]`; model loaded once at import; optional on-disk cache via `EMBEDDING_CACHE_DIR`
- Created `tests/test_embeddings.py`: 4 tests (shape, determinism, distinct texts, cache)

---

## WP-001 — Project framework + Phase 1 scaffold

**Date:** 2026-03-20

- Created `.gitignore`, `.env`, `.env.example`, `docker-compose.yml` env passthrough
- Created `memory_service/requirements.txt`, `memory_service/main.py` with `Settings`
- Created `CLAUDE.md`, `BACKLOG.md`, `README.md`
- Initialised git repo

---

## Retrospective Log

### WP-001
- **What went well:** Existing partial scaffold was correct and required only additive changes.
- **Deferred:** WP-012 (pin dep versions), WP-013 (pin Docker image tags), WP-014 (Docker resource limits).

### WP-002 + WP-003
- **What went well:** Parallel agent dispatch conflict-free.
- **What to improve:** `Settings`/`get_driver()` ended up triplicated — future WPs adding scripts should import from shared module from the start.
- **Deferred:** WP-016 (shared config), WP-017 (cache eviction), WP-018 (vector dimension from model).

### WP-016 + WP-018
- **What went well:** Parallel dispatch conflict-free — each agent owned different files.
- **What to improve:** WP-016 agent left stale `get_driver()` with undefined names in `init_schema.py`. Agents should import-check after editing.
- **Deferred:** WP-019 (expose `capacity` as config).

### WP-005
- **What went well:** Single-query design clean. Parallel dispatch for code + tests conflict-free.
- **What to improve:** Graph expansion tests used `if hit is not None:` guards — silently skipping assertions. Always assert the hit is found first.
- **Deferred:** WP-022 (cap unbounded collect), WP-023 (extract 503 context manager), WP-024 (cleanup_nodes multi-id).

### WP-004
- **What went well:** Plan agent resolved all design questions upfront. Parallel agents conflict-free.
- **What to improve:** Agents should verify their own imports after editing (redundant/stale imports found during simplify).
- **Deferred:** WP-020 (UNWIND for N+1 loops), WP-021 (non-blocking embedding).

### MVP Live Demo (2026-03-20)
- **Memgraph 3.8 compatibility fixes required:** (1) vector index DDL syntax changed; (2) `EXISTS{}` subqueries not supported inside `WITH ... WHERE` — replaced with `OPTIONAL MATCH` + scalar filter; (3) `ORDER BY distance` after `collect()` aggregation requires `distance` in `RETURN` clause. Also: empty `MEMGRAPH_USER=` env var caused startup crash — removed explicit `environment:` block from docker-compose.

### WP-015
- **What went well:** Three parallel review agents caught all significant issues.
- **What to improve:** Workflow docs should be validated against actual API response schema, not just CLI option names.
- **Deferred:** WP-027 (list-strands command).

### WP-007
- **What went well:** Clean package separation; `respx` mocking kept tests self-contained.
- **What to improve:** `setup.cfg` needed due to old setuptools — editable installs should be validated as part of DoS.
- **Deferred:** WP-025 (shared CLI error handler), WP-026 (`MemoryType` mirror in client).
