# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** H = High / M = Medium / L = Low
> **Priority score:** `Value / Effort` using `H=3`, `M=2`, `L=1`
> Completed WPs → [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Currently In Progress

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|
| WP-072 | InfoSec knowledge layer: cross-layer Memory edges | feature/knowledge-layer | H | M | WP-070 ✅, WP-071 ✅ | Plan: docs/plans/wp-072.md ✅ |

### Knowledge layer branch

- **Branch:** `feature/knowledge-layer`
- **Worktree:** `.worktrees/feature-knowledge-layer`
- **WP sequence:** WP-077 → WP-070 → WP-071 → WP-072 → WP-024 → WP-073 → WP-074 → WP-075 → WP-076
- **Rebase protocol:** after each core WP lands on master, run `git fetch origin && git rebase origin/master` from the worktree and force-push with `--force-with-lease`. Never let the branch fall more than 3–4 master commits behind.
- **Merge strategy:** `git merge --no-ff feature/knowledge-layer` once WP-076 passes all integration tests on the live stack.

---

## Prioritised Backlog

> Items ordered as a dependency-safe executable sequence informed by `Priority score`.
> Higher score is better, but `Depends on` always wins for execution order.
> When a lower-score prerequisite unlocks a stronger branch, keep the prerequisite immediately ahead of that branch.
> Within an equal-score block, preserve the existing order unless a newly identified dependency requires a move.
> Add new work packages at the bottom of their equal-score block unless dependency constraints require otherwise.
> `Release` is planning metadata only. The backlog stays continuous and contiguous; release numbers indicate target package, not a separate queue.

| Priority | Release | ID | Title | Value | Effort | Priority score | Depends on | Notes |
|----------|---------|----|-------|-------|--------|----------------|------------|-------|
| 4 | R1 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | 1.5 | WP-038 ✅ | Prevent test artefacts polluting live context. See detail below. |
| 5 | R2 | WP-049 | Wake-up companion + conversant anchoring | H | M | 1.5 | — | Wake-up should always surface anchor memories for the Companion (Mara) identity and for the specific person the calling agent is conversing with, in addition to prominent + topic-relevant memories. See detail below. |
| 6 | R2 | WP-008 | API-based LLM provider abstraction | H | M | 1.5 | WP-007 ✅ | Replace the IDE-tied framing with a runtime `LLMClient` provider layer for Anthropic/OpenAI/Ollama. The goal is to let the fabric and future agents run outside VS Code while keeping provider choice swappable behind one interface. |
| 7 | R2 | WP-009 | Headless agent runtime outside VS Code | H | M | 1.5 | WP-008 | Build `BaseAgent` on top of `memory_client` + `LLMClient` so scheduled/event-driven agents can run without an editor session. This is the execution foundation for all higher-level agents that should share the same fabric. |
| 8 | R2 | WP-085 | **Analytics Phase — Sprint 1:** graph-vs-vector diagnostics, cluster discovery, bridge detection (WP-057 + WP-058 + WP-059) | H | M | 1.5 | WP-029 ✅ | Three tightly related graph-analytics capabilities best built together as a shared diagnostic layer: (1) graph-vs-vector agreement — compare each memory's nearest embedding neighbours with its actual `RELATED_TO`/`LEADS_TO` neighbourhood to surface where the graph lags or overlinks semantic reality; (2) latent cluster discovery — cluster embeddings offline to discover emergent themes and compare them with explicit `Strand` assignments to identify overly broad, missing, or mislabeled strands; (3) bridge-memory detection — identify memories that span otherwise separate embedding clusters or graph communities, surfacing high-leverage cross-domain connectors. All three share the same embedding-space traversal infrastructure and diagnostic output pattern. |
| 9 | R2 | WP-077 | Extract shared schema-init utilities + fix migrate_embeddings model routing | L | L | 1.0 | WP-094 | `create_constraint()` and `get_embedding_dimension()` are copy-pasted identically in `init_schema.py` and `init_knowledge_schema.py`. Extract to `scripts/schema_utils.py`. Additionally: `migrate_embeddings.py` sets `model_name = settings.knowledge_embedding_model` for the staleness filter but then calls `get_embedding()` which is hard-wired to `EMBEDDING_MODEL` via the module-level singleton in `embeddings.py`. Fix requires `embeddings.py` to support multiple model instances, or a separate model-load path in the script. Surfaced in WP-094 simplify review. Must complete before WP-070. |
| 10 | R2 | WP-070 | InfoSec knowledge layer: norms & document write API | H | M | 1.5 | WP-094, WP-077 | FastAPI router (`knowledge_routes.py`) + Cypher (`knowledge_repo.py`). Feature-flagged via `ENABLE_KNOWLEDGE_LAYER`. Upserts Norm/Control/Document/Chunk/BusinessAttribute/Organisation/Jurisdiction. IMPLEMENTS edge (Document→Control), APPLIES_IN/OPERATES_IN jurisdiction scoping, OWNED_BY org scoping, MAPPED_TO cross-framework edges. MERGE+text_hash idempotency. Knowledge embeddings use `KNOWLEDGE_EMBEDDING_MODEL`. Anchor Memory writes on norm ingest. See detail below. |
| 11 | R2 | WP-071 | InfoSec knowledge layer: search API | H | M | 1.5 | WP-070 | Vector search over ctrl_embedding_idx and chunk_embedding_idx using `KNOWLEDGE_EMBEDDING_MODEL`. All endpoints functional with zero Memory nodes (standalone compliance mode per ADR-001). Dual modes: unscoped (generic/public) and org-scoped (jurisdiction-filtered via OPERATES_IN ∩ APPLIES_IN). lang filter; cross-lingual by default. include_universal flag. /knowledge/incomplete-jurisdictions diagnostic endpoint. See detail below. |
| 12 | R2 | WP-072 | InfoSec knowledge layer: cross-layer Memory edges | H | M | 1.5 | WP-070, WP-071 | New `knowledge_bridge.py` — sole module importing from both `memory_repo` and `knowledge_repo` (ADR-001 Guardrail 3). Extend add_memory/update_memory with ABOUT_CONTROL {relationship_type, org_id} and CITES_DOC edges (guarded by feature flag). Critical: merge_memory rewiring. Extend MemoryHit response. See detail below. |
| 13 | R2 | WP-074 | InfoSec knowledge layer: CLI, MCP tools, and ETL | H | M | 1.5 | WP-070, WP-071, WP-072 | knowledge_* MCP tools (registered only when flag is on; narrow, single-purpose, LLM-directed docstrings). CLI commands. MemoryClient extension. ingest_framework.py bulk ETL with YAML validation. YAML data files (NIST CSF, ISO 27001, jurisdictions, business attributes). CLI review tool for SUPPORTS edge validation. KNOWLEDGE_LAYER.md (references ADR-001). See detail below. |
| 14 | R2 | WP-075 | InfoSec knowledge layer: SABSA bidirectional traceability | H | M | 1.5 | WP-072, WP-074 | trace-up (control → attributes → norms), trace-down (control → documents → chunks → evidence/gap memories), attribute coverage, gap analysis. Dual-mode per ADR-001: knowledge-only (no Memory traversal, standalone compliance) and integrated (with Memory evidence). Both generic and org-scoped modes. Three-way reconciliation. See detail below. |
| 15 | R2 | WP-006 | Wire `GET /memory/graph` | M | M | 1.0 | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 16 | R2 | WP-043 | Inline effective_strength sort in search | L | L | 1.0 | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as the current proxy. |
| 17 | R2 | WP-090 | Handle non-ServiceUnavailable exceptions in `find_duplicate_memory` | L | L | 1.0 | WP-088 ✅ | `find_duplicate_memory()` in `memory_repo.py` can raise `CypherError` or other Memgraph-level exceptions (e.g. malformed query, vector index unavailable). These propagate uncaught from the `add_memory` handler, which only catches `ServiceUnavailable`. Options: (a) catch `CypherError` inside `find_duplicate_memory` and return `None` (fail-open), or (b) let it propagate to a new `except CypherError → 500` clause in the handler. Fail-open is safer for availability; fail-closed is safer for data integrity. Surfaced during WP-088 code review. |
| 18 | R2 | WP-095 | `GET /memory/duplicates`: add Cypher-level safety cap + async wrap | L | L | 1.0 | WP-047 ✅ | Surfaced in WP-047 simplify review. (1) Add `LIMIT 50000` to the `find_near_duplicates` Cypher query as a guard against pathologically large `RELATED_TO` edge sets — prevents unbounded Bolt transfer at extreme scale. (2) Wrap `find_near_duplicates` call in `run_in_executor` in the async endpoint if concurrent usage becomes a concern (currently synchronous in async handler). Both are low-priority improvements; do when the store grows beyond ~10k memories or concurrency spikes. |
| 19 | R2 | WP-025 | Extract shared CLI error handler | L | L | 1.0 | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. WP-078 added 2 more (list-projects, create-project) — now 18+ instances. |
| 20 | R2 | WP-026 | `MemoryType` mirror in `memory_client` | L | L | 1.0 | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 21 | R2 | WP-023 | Extract `get_session` context manager for 503 handling | L | L | 1.0 | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints in `main.py` AND all 13 handlers in `knowledge_routes.py` (added WP-070/WP-071 — none have the guard). Do after WP-029 (adds more endpoints). |
| 22 | R2 | WP-020 | UNWIND for person/strand/related_ids writes | L | L | 1.0 | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 23 | R2 | WP-021 | Non-blocking embedding in async endpoints | L | L | 1.0 | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 24 | R2 | WP-024 | `cleanup_nodes` support multiple ids per label | L | L | 1.0 | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. Required by WP-076. |
| 25 | R2 | WP-017 | Embedding cache eviction / size cap | L | L | 1.0 | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 26 | R2 | WP-014 | Docker resource limits | L | L | 1.0 | — | Add `mem_limit`/`cpus` to docker-compose. |
| 27 | R2 | WP-081 | Initialise `activation_count` and `last_activated_at` on auto-linked edges at `add_memory` time | L | L | 1.0 | — | The `add_memory` auto-link path (vector search MERGE at ingest) does not set `activation_count` or `last_activated_at` on newly created `RELATED_TO` edges. All other edge writers (long_rest, short_rest) set these fields on creation. The gap means edge-decay and count queries must defensively `COALESCE` these fields. Surfaced during WP-055. |
| 28 | R2 | WP-041 | Subject/object schema on Memory nodes | H | H | 1.0 | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| 29 | R2 | WP-073 | InfoSec knowledge layer: document ingestion pipeline | H | H | 1.0 | WP-071 | PDF (pdfplumber) + Markdown → Document + Chunk nodes. Chunk embeddings use `KNOWLEDGE_EMBEDDING_MODEL`. Heading-aware chunking; HAS_NEXT edges for context expansion. chunk_review_mode (default on) prevents silent auto-SUPPORTS. Conservative threshold (distance < 0.20) for auto-inference; SUPPORTS edges start status=”auto-inferred”. See detail below. |
| 30 | R2 | WP-076 | InfoSec knowledge layer: integration and separation tests | M | M | 1.0 | WP-094, WP-070–WP-075, WP-024 | Full integration + separation + dual-mode tests. Critical: autouse conftest separation test. Knowledge-only mode tests (all endpoints valid with zero Memory nodes). Feature flag off tests (404 for /knowledge/*, control_ids ignored). Dual-org jurisdiction test. merge_memory rewiring. Import audit (knowledge_bridge.py sole cross-layer import). See detail below. |
| 31 | R2 | WP-086 | **Analytics Phase — Sprint 2:** outlier detection, semantic families, strand cohesion, missing-edge suggestions, centrality scoring, echo-chamber detection, semantic timelines, neighbourhood summarisation (WP-060 + WP-061 + WP-063 + WP-064 + WP-065 + WP-066 + WP-067 + WP-068) | M | H | 1.0 | WP-085, WP-047, WP-028 ✅, WP-029 ✅ | Eight analytics capabilities that form the second layer of the analytics phase, building on the Sprint 1 (WP-085) diagnostic infrastructure. All share the same analytical pattern and output surface: (1) vector outlier and anomaly detection — memories far from any semantic neighbourhood or with poor graph/embedding agreement; (2) semantic family analysis — group related memories into families beyond pairwise duplicate pairs (depends on WP-047); (3) strand cohesion diagnostics — measure how tight or fragmented each strand's embedding cluster is; (4) hybrid missing-edge suggestions — propose `RELATED_TO`/`LEADS_TO` links from embedding similarity, time ordering, and topology (review flow, not auto-linking); (5) hybrid memory centrality scoring — blended rank from graph centrality, embedding density, strength, recall count, reinforcement, and edge activation; (6) semantic gravity-well/echo-chamber detection — detect over-saturated retrieval regions; (7) semantic timelines and concept recurrence — track how neighbourhoods shift, recur, or disappear over time; (8) neighbourhood summarisation — turn local density into narrative labels and review queues. |
| 32 | R2 | WP-091 | Add `agent_id` to lifecycle operation log entries | L | L | 1.0 | WP-056 ✅ | The operation log introduced in WP-056 records `update`, `merge`, `archive`, and `restore` events but omits `agent_id` because the lifecycle endpoints do not currently accept it. Add `agent_id` as an optional field to the four request models (`UpdateMemoryRequest`, `MergeMemoryRequest`, and query params for `archive`/`restore`) and pass it through to `append_operation_log` entries. Enables per-agent traceability on all lifecycle mutations. |
| 33 | R2 | WP-092 | Operation log size audit and rotation strategy | L | L | 1.0 | WP-056 ✅ | Review the real-world size and growth rate of `System.operation_log` under normal usage: measure byte size of the JSON property, estimate how quickly the 200-entry cap is reached, and assess read-modify-write overhead on lifecycle endpoints. Based on findings, decide on a rotation strategy — options include: lowering/tuning the cap per operation type, adding a time-based TTL alongside the count cap (e.g. drop entries older than N days), adding a `DELETE /memory/operation/log` or `POST /memory/operation/log/rotate` endpoint for explicit rotation, or splitting per-operation-type logs. Also review whether the same concern applies to `maintenance_log` (WP-054, currently capped at 100). Outcome: either confirm current approach is sufficient at expected scale, or implement the chosen rotation mechanism. |
| 34 | R3 | WP-042 | Self-contained `memory_client` packaging | L | L | 1.0 | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. Re-scored from medium value because it is packaging polish rather than core product capability. |
| 35 | R3 | WP-062 | Concept-drift analysis over time | M | H | 0.67 | — | Compare recent memories and clusters with older semantic regions to detect identity drift, changing priorities, and narrative rewrites. Treat this as analysis tooling first, not as automatic judgment. |
| 36 | R3 | WP-010 | Remote/mobile access | L | H | 0.33 | WP-009 | Tailscale/VPS hosting + TLS + API key auth. |
| 37 | R3 | WP-011 | Custom graph-cloud UI | L | H | 0.33 | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |

> **Note:** old backlog items once grouped under `v2+` are now part of the same continuous backlog with `Release` assignments.

---

## Detail Specs

> Detail sections are ordered by **WP number** (ascending). Execution order is determined solely by the priority table above.

### WP-038 — Memory lifecycle operations: update, merge, archive

#### Motivation

The fabric can add and search memories but cannot maintain them. Three lifecycle operations are essential:
- **Update** when facts change or wording improves
- **Merge** duplicates without losing provenance or graph continuity
- **Archive** memories that should no longer surface normally but remain historically recoverable

#### Data model additions

| Property | Type | Description |
|----------|------|-------------|
| `status` | str | `active` (default), `archived`, `merged` |
| `superseded_by` | str \| None | UUID of active replacement |
| `archived_at` | datetime \| None | Set on archive |
| `updated_at` | datetime \| None | Set on in-place update |

New edge: `MERGED_INTO` (Memory → Memory)

#### New endpoints

```
PATCH /memory/{id}          — update fact/so_what/tags/importance/person_ids/strand_ids; recomputes embedding
POST  /memory/{id}/merge    — body: {target_id, strategy}; marks source merged, rewires links
POST  /memory/{id}/archive  — sets status=archived, archived_at
POST  /memory/{id}/restore  — returns archived memory to active
```

**Search and wake-up** exclude `status in ('archived', 'merged')` by default.

#### Definition of Success

- [ ] All four endpoints implemented; `active`/`archived`/`merged` status respected in search/wake-up
- [ ] Merge rewires `ABOUT`, `IN_STRAND`, explicit `LEADS_TO`, explicit `RELATED_TO` to target
- [ ] Client + CLI + MCP updated
- [ ] Integration tests cover all status transitions


---

### WP-039 — Ephemeral test-memory handling: TTL, tagging, cleanup

#### Motivation

Integration tests write real memories to the live graph. Without explicit ephemeral semantics, test artefacts accumulate and corrupt companion context. Need: test memories excluded from normal retrieval + auto-cleaned once no longer needed.

#### Design

- `Memory.ephemeral: bool` property (default `false`); set via `POST /memory` with `"ephemeral": true`
- Ephemeral memories excluded from `POST /memory/search` and `GET /memory/wake-up` by default
- `POST /memory/maintenance/purge-ephemeral` — hard-deletes all ephemeral memories
- CLI `memory purge-ephemeral`; MCP `memory_purge_ephemeral`

#### Definition of Success

- [ ] `POST /memory` accepts `ephemeral: true`
- [ ] Search and wake-up exclude ephemeral memories by default
- [ ] `POST /memory/maintenance/purge-ephemeral` returns count deleted
- [ ] Integration tests updated to use `ephemeral: true` for test writes


---

### WP-047 — Duplicate handling at ingest + near-duplicate review

#### Motivation

As the fabric grows, two different duplicate problems emerge:

- exact duplicates, where the same memory is stored again and should reinforce an existing node rather than create a parallel one
- near-duplicates, where semantically similar memories accumulate and should be surfaced for review and possible merge

Today both cases require manual inspection or coincidence during retrieval. This work package clarifies the boundary between them so the write path can avoid true duplicates while still supporting a review-and-merge loop for semantically similar memories via WP-038.

#### Design

- Exact-duplicate handling happens at ingest time on `POST /memory`.
- Exact duplicate = the incoming memory matches an existing active memory after agreed normalization of the canonical memory content.
- When an exact duplicate is detected, do not create a new `Memory` node.
- Instead, treat the event as reinforcement of the existing memory and merge any genuinely new contextual associations from the attempted write onto the surviving node.
- Near-duplicate handling remains a review flow.
- `GET /memory/duplicates?threshold=0.92&limit=20` returns a list of candidate pairs `[{a: {id, text}, b: {id, text}, similarity: float}]` ordered by similarity descending.
- For near-duplicate review, implementation iterates Memory node pairs that already have a `RELATED_TO` edge (semantic proximity pre-filter) and keeps only those whose cosine similarity of stored embeddings exceeds `threshold`.
- Alternatively (if no `RELATED_TO` edge exists yet): run vector index search for each node and check top-k against `threshold`. Use the pre-existing `RELATED_TO` approach first and document the limitation.
- Distinct-but-related memories remain valid new nodes; this package is only about exact-duplicate interception and near-duplicate review.
- `threshold` and `limit` configurable via query param; defaults from `Settings`.
- CLI: `memory find-duplicates [--threshold 0.92] [--limit 20]`
- MCP: `memory_find_duplicates`

#### Definition of Success

- [ ] `POST /memory` no longer creates a second active node for an exact duplicate; it reinforces the existing memory instead
- [ ] Exact-duplicate interception preserves or merges any new non-duplicate context edges onto the surviving node
- [ ] `GET /memory/duplicates` returns correct pairs above threshold, ordered by similarity
- [ ] Result excludes archived and merged memories (status filter from WP-038)
- [ ] CLI and MCP wired
- [ ] Integration test: posting the same memory twice does not create a second node and updates the existing node via reinforcement semantics
- [ ] Integration test: seed two nearly-identical memories, confirm they appear as a pair; seed two unrelated memories, confirm they do not


---

### WP-049 — Wake-up companion + conversant anchoring

#### Motivation

Wake-up currently returns the most prominent memories and (optionally) topic-relevant memories. It has no awareness of who the Companion is or who it is speaking with. This means that identity-critical anchor memories for the Companion (Mara) and person-specific context for the current conversant are left to chance — they only surface if they happen to be high-strength or topic-adjacent. The result is that a freshly started session may have no grounding in Mara's identity or in the relationship with the person being addressed.

#### Design

- Add two new sections to the wake-up response:
  - **Companion anchors** — memories tagged with or `ABOUT` the Companion agent (identified by `AGENT_ID`), ordered by importance and strength. Optionally: a synthesised "You are [CompanionName]" heading derived from the Companion's anchor memories so identity is always explicit.
  - **Conversant anchors** — if `person_id` or `person_name` is passed to wake-up, return memories with an `ABOUT` edge to that Person node, ordered by recency and importance.
- Both sections are additive — they do not replace the existing prominent-memories and topic-relevant sections.
- New optional wake-up parameters: `person_id: str | None`, `companion_anchor_limit: int` (default from `Settings`), `conversant_anchor_limit: int` (default from `Settings`).
- CLI: `memory wake-up [--person-id <id>] [--topic <text>]`
- MCP: `memory_wake_up` — add optional `person_id` parameter.
- Config: `WAKE_UP_COMPANION_ANCHOR_LIMIT` (default 5), `WAKE_UP_CONVERSANT_ANCHOR_LIMIT` (default 10).

#### Definition of Success

- [ ] Wake-up response includes a `companion_anchors` section with Companion identity memories
- [ ] When `person_id` is supplied, response includes a `conversant_anchors` section
- [ ] Both sections respect their configured limits
- [ ] Sections are omitted (not empty arrays) when there are no matching memories, to keep the response clean
- [ ] CLI and MCP updated
- [ ] Integration test: seed Companion anchor memories and a Person with ABOUT memories; confirm they appear in the correct sections


---

### WP-050 — Domain knowledge store

#### Motivation

Episodic memories capture events, decisions, and facts from lived experience. But some knowledge is reference-like — stable, subject-area specific (e.g. cybersecurity techniques, medical terminology, legal frameworks) — and should not compete with episodic memory in normal retrieval. It needs to be stored separately so it does not dilute personal memory context, while still being discoverable by agents that need it. Critically, the fabric itself must contain anchors that make the existence and access path for each knowledge domain knowable without prior context.

#### Design

- Introduce a `KnowledgeNode` label (or a `type: knowledge` flag on Memory, TBD at design time) for domain-specific reference knowledge.
- Each knowledge domain is represented by a `Domain` node (e.g. `id: domain-cybersecurity`, `name: "Cybersecurity"`, `description`).
- Knowledge nodes link to their domain via an `IN_DOMAIN` edge (`KnowledgeNode → Domain`).
- Domain nodes are anchored in the fabric via a `Memory` node of type `insight` that names the domain and describes how to query it (e.g. `fact: "Cybersecurity domain knowledge is stored in the fabric under domain-cybersecurity."`). This anchor memory ensures agents can discover domains via normal memory search.
- `POST /knowledge` — ingest a knowledge node: `{domain_id, title, body, tags[], importance}`. Generates embedding from `title + body`.
- `POST /knowledge/search` — vector search scoped to a domain: `{domain_id, query, limit}`.
- `GET /knowledge/domains` — list all domains with node counts.
- Knowledge nodes are excluded from `POST /memory/search` and `GET /memory/wake-up` by default (separate retrieval path).
- CLI: `memory add-knowledge`, `memory search-knowledge --domain <id>`, `memory list-domains`.
- MCP: `memory_add_knowledge`, `memory_search_knowledge`, `memory_list_domains`.

#### Definition of Success

- [ ] `Domain` nodes and `KnowledgeNode` nodes (or equivalent) can be created and queried independently of episodic Memory nodes
- [ ] `POST /knowledge/search` returns results scoped to the specified domain
- [ ] Each domain has an auto-created anchor Memory so normal search surfaces the domain's existence
- [ ] Knowledge nodes are excluded from episodic memory search and wake-up by default
- [ ] CLI and MCP wired
- [ ] Integration tests: ingest knowledge into two domains; confirm search isolation; confirm anchor memories appear in normal memory search


---

### WP-069 — Cybersecurity knowledge layer: schema, indexes, multilingual model ✅

> **Completed 2026-03-28.** See [CHANGELOG](docs/CHANGELOG.md) for delivery details. Superseded in part by WP-094 (ADR-001 alignment).


---

### WP-078 — Project node CRUD endpoints ✅

> **Completed 2026-04-02.**

- Added `GET /project` (list all named projects) and `POST /project` (upsert by id) endpoints mirroring the `/person` pattern
- Added `ProjectItem`, `ProjectsResponse`, `CreateProjectRequest` Pydantic models
- Added `list_projects()` and `upsert_project()` to `memory_repo.py`
- Added `list_projects()` and `create_project()` to `MemoryClient`
- Added `list-projects` and `create-project` CLI commands
- Added `memory_list_projects` and `memory_create_project` MCP tools
- 25 tests: 15 unit + 10 integration, all passing against live stack

**Retrospective:** Mirror pattern was exactly right — each layer (repo → endpoint → client → CLI → MCP) was straightforward once the Person precedent existed. The two-stage code review process caught: missing `@pytest.mark.integration` marks (Task 3), a fragile `_Adapter` base class (Task 7), missing status assertions in integration tests, and a mid-file stdlib import. Worth the review overhead. Simplify surfaced `try/finally` missing from `TestPostProjectEndpoint` and raw string literals duplicating constants.

---

### WP-087 — Expose `person_ids` in MCP `memory_add` ✅

> **Completed 2026-04-02.**

- Added `person_ids: list[str] | None = None` to `memory_add` signature in `mcp_server/server.py`
- Pass-through `person_ids=person_ids` to `client.add_memory(...)` — identical pattern to WP-052
- Unit test `test_u9_memory_add_passes_person_ids` — mock verifies full kwarg pass-through
- Integration test `test_i7_memory_add_person_ids_creates_about_edges` — live stack confirms ABOUT edges created for both supplied person IDs
- Simplify: replaced raw Cypher cleanup in test with `cleanup_nodes` helper (consistent with `test_i6`)

**Retrospective:** Minimal, clean change. WP-052 pattern made this trivial. Simplify surfaced a test-cleanup inconsistency that was easy to fix. Two-stage review passed with no spec gaps.

---

### WP-077 — Extract schema-init utils + fix embeddings multi-model routing ✅

> **Completed 2026-04-03.** Commit `ac1a506` on `feature/knowledge-layer`.

- Created `scripts/schema_utils.py` with shared `create_constraint()` + `get_embedding_dimension()`
- `init_schema.py` and `init_knowledge_schema.py` now import from `scripts.schema_utils` (no duplication)
- `memory_service/embeddings.py`: added `_model_cache: dict[str, SentenceTransformer]`, `_load_model_by_name()`, and optional `model_name` parameter throughout `get_model`/`get_embedding`/`get_embedding_dimension`/`_cache_key`
- `scripts/migrate_embeddings.py`: both `get_embedding()` call sites now pass `model_name=model_name`
- 11 unit tests, all green; no integration tests (pure Python, no Memgraph)

**Retrospective:** Three /simplify wins caught during verification: (1) `ClientError` import was missing from both init scripts after extraction — runtime `NameError` averted; (2) `_load_model` and `_load_model_by_name` had duplicate offline-setup blocks — extracted to `_make_st_kwargs()`; (3) `_cache_key` ternary simplified to `model_name or _model_name`. Background agents (even with `bypassPermissions`) cannot write files or run Bash in this environment — implementation was done directly in-session. This is now the established pattern for all WPs on this branch.

---

### WP-071 — InfoSec knowledge layer: search API ✅

> **Completed 2026-04-03.** On `feature/knowledge-layer`.

- Added 5 repo functions to `knowledge_repo.py`: `search_controls` (vector, `ctrl_embedding_idx`), `search_chunks` (vector, `chunk_embedding_idx`), `list_norms`, `list_documents`, `list_incomplete_jurisdictions`
- Added 4 Pydantic models + 5 route handlers to `knowledge_routes.py`: `POST /knowledge/search/controls`, `POST /knowledge/search/chunks`, `GET /knowledge/norms`, `GET /knowledge/documents`, `GET /knowledge/incomplete-jurisdictions`
- `docs/plans/wp-071.md` written; 17 unit tests (11 Group A + 8 Group B), all green; integration tests deferred to WP-076
- **Retrospective:** Parallel task dispatch (repo + routes simultaneously) worked cleanly — no file conflicts. Quality review surfaced missing `TestListDocuments` Group A tests (fixed) and absence of `ServiceUnavailable` guard across all 13 `knowledge_routes.py` handlers (logged to WP-023).

---

### WP-070 — InfoSec knowledge layer: write API ✅

> **Completed 2026-04-03.** Commit `a1c1148` on `feature/knowledge-layer`.

- Created `memory_service/knowledge_repo.py`: upsert/get for Framework, Control, Norm, Document, Chunk with correct Cypher (MERGE ON CREATE SET; optional CONTAINS/IMPLEMENTS/SOURCED_FROM/HAS_CHUNK/HAS_NEXT edges)
- Created `memory_service/knowledge_routes.py`: FastAPI router (`/knowledge` prefix) with 10 endpoints; embeddings via `KNOWLEDGE_EMBEDDING_MODEL`; Document carries no embedding (chunks hold vectors)
- `memory_service/main.py`: conditional `app.include_router(knowledge_router)` when `ENABLE_KNOWLEDGE_LAYER=true`
- `scripts/init_knowledge_schema.py`: added missing `("Framework", "id")` uniqueness constraint
- `docs/plans/wp-070.md`: self-contained plan written for future reference
- 24 unit tests (13 repo + 11 route), all green; integration tests deferred to WP-076

**Retrospective:** Implementation straightforward once the plan was written. Key discovery: FastAPI test fixture must reload `memory_service.config` + `memory_service.main` with `ENABLE_KNOWLEDGE_LAYER=true` AND patch `get_driver` before `TestClient` context starts — otherwise the module-level conditional doesn't register knowledge routes (settings singleton is already frozen from previous import). Pattern captured in `test_wp070.py::app_client` fixture for reuse in WP-071. Scope was intentionally narrowed vs. original BACKLOG spec (no jurisdiction scoping, no BusinessAttribute/Organisation endpoints, no MAPPED_TO cross-framework edges) — these are deferred to later WPs as needed.

---

### WP-094 — ADR-001 alignment: rename, feature flag, independent embedding model ✅

> **Completed 2026-04-02.**

- Renamed `cybersec_schemas.py` → `knowledge_schemas.py`, `init_cybersec_schema.py` → `init_knowledge_schema.py`, `tests/test_wp069_cybersec_schema.py` → `tests/test_wp069_knowledge_schema.py`
- Added `knowledge_embedding_model` and `enable_knowledge_layer` to `Settings` (config.py)
- `init_knowledge_schema.py` now uses `KNOWLEDGE_EMBEDDING_MODEL` for vector index dimension
- `migrate_embeddings.py` scoped to knowledge-layer nodes only (Control, Chunk); episodic Memory migration is independent
- `.env.example` documents both new settings
- All WP-069 tests ported and passing under new names

**Retrospective:** Straightforward rename + settings addition. No surprises. ADR-001 guardrails now enforced at the code level, unblocking WP-070–076.

---

### WP-070 — Information Security knowledge layer: norms & document write API

#### Motivation

The knowledge layer needs a write path to ingest norms, controls, cross-framework mappings, documents, and chunks. Keeping it in a dedicated `knowledge_repo.py` + `knowledge_routes.py` avoids touching the 1601-line `memory_repo.py` and makes the separation tangible in code.

#### Design

**New `memory_service/knowledge_repo.py`** — all Cypher for the knowledge layer write path. Zero imports from `memory_repo`.

**New `memory_service/knowledge_routes.py`** — FastAPI router, registered conditionally in `main.py`:
```python
if settings.enable_knowledge_layer:
    from memory_service import knowledge_routes
    app.include_router(knowledge_routes.router)
```
This implements ADR-001 Guardrail 1 (feature-flagged router).

**Write endpoints:**

| Endpoint | Action |
|----------|--------|
| `POST /knowledge/norm` | Upsert Norm; creates optional `APPLIES_IN` edges to Jurisdictions |
| `POST /knowledge/control` | Upsert Control; creates `HAS_CONTROL`, optional `ADDRESSES`, optional `APPLIES_IN` edges |
| `POST /knowledge/control/map` | Create `MAPPED_TO` edge (MERGE'd both directions in one transaction) |
| `POST /knowledge/document` | Upsert Document; creates optional `IMPLEMENTS`, `OWNED_BY` edges |
| `POST /knowledge/chunk` | Upsert Chunk; creates `HAS_CHUNK` edge |
| `POST /knowledge/chunk/supports` | Create `SUPPORTS {confidence, raw_score, status}` edge |
| `POST /knowledge/attribute` | Upsert BusinessAttribute |
| `POST /knowledge/organisation` | Upsert Organisation; creates `OPERATES_IN` edges |
| `POST /knowledge/jurisdiction` | Upsert Jurisdiction (primary key is `code`, not `id`) |
| `GET /knowledge/applicable?org_id=...` | Return Norms/Controls applicable to an org via jurisdiction intersection |

**Embedding:** Knowledge-layer embeddings use `KNOWLEDGE_EMBEDDING_MODEL` (not `EMBEDDING_MODEL`). The embedding service must support loading both models if both layers are active.

**Idempotency:** Control write uses `MERGE ON CREATE SET ... ON MATCH SET` pattern. Overwrite embedding in `ON MATCH` only if `text_hash` has changed. When a Control's text changes, DETACH all existing `auto-inferred` SUPPORTS edges and mark owning Documents for re-ingestion.

**Validation:** Jurisdiction lookups use `MERGE (j:Jurisdiction {code: $code})` — never accept free-text names as primary keys. `CITES_DOC` references validated for Document existence; return HTTP 400 if missing.

**Anchor Memories:** On `POST /knowledge/norm` upsert, write a `Memory` node (type=`insight`, importance=3, tags=`["knowledge-anchor", "infosec"]`) with fact describing the framework and how to query it. This is the discovery mechanism for agents that only call `memory_search`.

#### Files

New: `memory_service/knowledge_repo.py`, `memory_service/knowledge_routes.py`
Modified: `memory_service/main.py`

#### Definition of Success

- [ ] All 10 write endpoints operational; Pydantic request models defined
- [ ] Router only loaded when `ENABLE_KNOWLEDGE_LAYER=true`; API returns 404 for `/knowledge/*` when flag is off
- [ ] Knowledge-layer embeddings use `KNOWLEDGE_EMBEDDING_MODEL`, not `EMBEDDING_MODEL`
- [ ] `knowledge_repo.py` has zero imports from `memory_repo.py`
- [ ] Upsert idempotency: posting the same Norm/Control twice does not create duplicate nodes
- [ ] `text_hash` comparison on Control update: embedding only re-computed when text changes
- [ ] On Control text change: existing `auto-inferred` SUPPORTS edges are detached
- [ ] `MAPPED_TO` MERGE'd bidirectionally in one transaction
- [ ] Anchor Memory created on norm upsert; searchable via `POST /memory/search`
- [ ] `GET /knowledge/applicable` returns jurisdiction-intersection result
- [ ] HTTP 400 returned for `CITES_DOC` referencing nonexistent Document
- [ ] Integration tests: upsert norm + controls + document + org; verify graph structure via Cypher


---

### WP-071 — Information Security knowledge layer: search API

#### Motivation

Reference data needs a search path separate from episodic memory. Knowledge search should not increment recall_count or interact with the decay/reinforcement model — it is a lookup, not a recall signal. All search endpoints are fully functional without any Memory nodes in the graph (ADR-001 dual-mode: standalone compliance use).

#### Design

**New read endpoints (added to `knowledge_routes.py`):**

| Endpoint | Description |
|----------|-------------|
| `POST /knowledge/search/controls` | Vector search over `ctrl_embedding_idx` |
| `POST /knowledge/search/chunks` | Vector search over `chunk_embedding_idx` |
| `GET /knowledge/norms` | List all Norms with metadata |
| `GET /knowledge/documents` | List all Documents; filterable by org_id |
| `GET /knowledge/incomplete-jurisdictions` | Lists Norms and Controls with no `APPLIES_IN` edges |

**Embedding for search queries:** Search queries are embedded using `KNOWLEDGE_EMBEDDING_MODEL` (matching the index model).

**`search_controls` request:** `{query, limit, norm_ids?, tags?, jurisdiction_codes?, applicable_to_org_id?, lang?, include_universal?}`
- `lang` filter is optional; omitting it enables cross-lingual search (multilingual model bridges languages natively)
- If `applicable_to_org_id` is set, restrict using `MATCH` (not `OPTIONAL MATCH`) against org's `OPERATES_IN` jurisdictions — standards with no `APPLIES_IN` edges are excluded unless `include_universal: true`
- Response: `{id, code, title, body, norm_id, lang, tags, distance}`

**`search_chunks` request:** `{query, limit, document_ids?, tags?, org_id?, cross_org?, org_ids?}`
- Without `org_id`: returns only public-scope Chunks (Documents with no `OWNED_BY` edge)
- With `org_id`: returns public + org-private Chunks
- `cross_org: true` requires non-empty `org_ids: List[str]` to be explicit; does not default to all-orgs
- Response: `{id, heading, body, document_id, sequence, tags, distance, control_ids?, org_id?}`

No `recall_count` increment — reference data does not participate in the decay model.

#### Files

Modified: `memory_service/knowledge_repo.py`, `memory_service/knowledge_routes.py`

#### Definition of Success

- [ ] `POST /knowledge/search/controls` returns `Control` nodes, never `Memory` nodes
- [ ] `POST /knowledge/search/chunks` returns `Chunk` nodes, never `Memory` nodes
- [ ] Search queries embedded using `KNOWLEDGE_EMBEDDING_MODEL` (not `EMBEDDING_MODEL`)
- [ ] All search endpoints functional with zero Memory nodes in the graph (standalone mode)
- [ ] `lang` filter narrows results; omitting it returns cross-lingual results
- [ ] `applicable_to_org_id` filter uses `MATCH` (not OPTIONAL MATCH); excludes standards with no `APPLIES_IN` unless `include_universal: true`
- [ ] Org-private Chunks only returned when `org_id` provided; public Chunks returned without `org_id`
- [ ] `GET /knowledge/incomplete-jurisdictions` returns Norms/Controls with no `APPLIES_IN` edges
- [ ] `recall_count` not incremented on knowledge search calls
- [ ] Integration test: search controls returns only controls; search chunks returns only chunks; no cross-contamination


---

### WP-072 — Information Security knowledge layer: cross-layer Memory edges

#### Motivation

Compliance evidence and gap findings naturally arise as Memory nodes (conversations, observations, meeting notes). These should be linkable to specific Controls so gap analysis can surface them. `ABOUT_CONTROL` with `relationship_type` distinguishes "I know about this control" (context), "this memory proves the control is in place" (evidence), and "this memory records a finding against this control" (gap). `org_id` on the edge is the isolation boundary for cross-org queries.

This WP is the bridge between the two paradigms (episodic memory and knowledge/traceability). Per ADR-001 Guardrail 3, cross-layer logic is isolated in a dedicated bridge module.

#### Design

**New `memory_service/knowledge_bridge.py`** — the only module that imports from both `memory_repo` and `knowledge_repo`. Contains:
- Edge creation/deletion for `ABOUT_CONTROL` and `CITES_DOC`
- Validation of Control/Document existence (calls `knowledge_repo` functions)
- `MemoryHit` hydration of controls/documents fields
- `merge_memory` rewiring helpers for cross-layer edges

This bridge module is the explicit, auditable coupling surface between the two layers (ADR-001 Guardrail 3).

**Extend `AddMemoryRequest` and `UpdateMemoryRequest`** in `main.py`:
- `control_ids: List[str] = []`
- `doc_ids: List[str] = []`
- `control_relationship_type: Optional[str] = None` — `"context" | "evidence" | "gap"`
- `org_id: Optional[str] = None` — stored on `ABOUT_CONTROL.org_id`; defaults to agent's org

**These fields are accepted only when `ENABLE_KNOWLEDGE_LAYER=true`.** When the flag is off, passing `control_ids` or `doc_ids` is silently ignored (or returns HTTP 400 — TBD during implementation).

**Bridge module additions** (called from `memory_repo` via the bridge):
- Step 8 in `add_memory`: MERGE `ABOUT_CONTROL {relationship_type, org_id}` edges for explicitly provided `control_ids`
- Step 9 in `add_memory`: validate Document existence, then MERGE `CITES_DOC` edges; return HTTP 400 if Document not found

**Critical: add `ABOUT_CONTROL` and `CITES_DOC` to `merge_memory` rewiring list** — same pattern as existing `ABOUT`/`IN_STRAND` rewiring. Without this, merging two memories orphans cross-layer edges on the tombstone node. This is the highest-severity correctness requirement.

**Extend `update_memory`** to replace `control_ids`/`doc_ids` (delete existing edges, recreate — same pattern as `person_ids` replacement).

**Extend `MemoryHit` response:** add optional `controls: List[dict]` and `documents: List[dict]` fields populated via `OPTIONAL MATCH` in `_SEARCH_QUERY_TEMPLATE`. Non-breaking. Hydration guarded by feature flag — when off, fields are always empty/absent.

**Extend MCP tools** `memory_add` and `memory_update` with `control_ids`, `doc_ids`, `control_relationship_type`, `org_id` parameters.

**Decay/maintenance isolation:** `ABOUT_CONTROL` and `CITES_DOC` edges are never touched by decay, short-rest, or long-rest passes (those passes pattern-match `RELATED_TO|LEADS_TO` by name).

#### Files

New: `memory_service/knowledge_bridge.py`
Modified: `memory_service/main.py`, `memory_service/memory_repo.py`, `mcp_server/server.py`

#### Definition of Success

- [ ] `knowledge_bridge.py` is the only module importing from both `memory_repo` and `knowledge_repo`
- [ ] Cross-layer fields silently ignored (or return 400) when `ENABLE_KNOWLEDGE_LAYER=false`
- [ ] `POST /memory` accepts `control_ids`, `doc_ids`, `control_relationship_type`, `org_id` when flag is on
- [ ] `ABOUT_CONTROL {relationship_type, org_id}` edges created correctly; `org_id` stored on edge
- [ ] `CITES_DOC` edges created; HTTP 400 returned if Document does not exist
- [ ] `merge_memory` correctly rewires `ABOUT_CONTROL` and `CITES_DOC` to target node (not orphaned on source tombstone)
- [ ] `update_memory` replaces `control_ids`/`doc_ids` rather than appending
- [ ] `MemoryHit` response includes `controls` and `documents` fields when edges exist and flag is on
- [ ] MCP `memory_add` and `memory_update` tools expose new parameters
- [ ] Integration test: add memory with `control_ids`; merge into another memory; verify edges on target, none on source
- [ ] Integration test: `CITES_DOC` for missing Document returns HTTP 400
- [ ] Integration test: with flag off, `control_ids` parameter is safely ignored


---

### WP-073 — Document ingestion pipeline: PDF and Markdown → Chunk nodes

#### Motivation

Internal policies and runbooks are not delivered as structured YAML catalogues — they are PDFs and Markdown files. A chunking pipeline is needed to break them into Chunk nodes with embeddings, then optionally link them to matching Controls.

#### Design

**New `scripts/ingest_document.py`** — reads PDF (pdfplumber) or Markdown files.

**Embedding:** Chunk embeddings use `KNOWLEDGE_EMBEDDING_MODEL` (matching the `chunk_embedding_idx` model).

**Chunking strategy:** split on paragraph/section boundaries — `\n\n` or `#`/`##`/`###` headings for Markdown; heading-detection via pdfplumber layout analysis for PDF. Do NOT split on page boundaries or fixed token counts. Store `section_heading` and `section_ref` on each Chunk. Create `HAS_NEXT` edges between consecutive Chunks to enable context-window expansion at retrieval time without re-embedding.

**`chunk_review_mode: bool`** (configurable, default `true`): when enabled, creates Chunk nodes and embeddings but does NOT create any `SUPPORTS` edges. The user reviews chunks first, then separately triggers SUPPORTS inference with `--link-controls`. This prevents silent garbage edges from poorly-structured documents.

When `chunk_review_mode=false`: for each chunk, run vector search over `ctrl_embedding_idx`; create `SUPPORTS {confidence, raw_score, status="auto-inferred"}` if distance < `supports_distance_threshold` (default 0.20).

**Embedding invalidation:** if a Control's `text_hash` changes after re-ingestion, find all `SUPPORTS` edges from Chunks to that Control, revert `status` to `"auto-inferred"`, and flag owning Documents for `--link-controls` re-processing.

**Config** (`.env`/Settings): `chunk_min_length`, `chunk_max_length`, `supports_distance_threshold`, `chunk_review_mode`.

Script calls the `/knowledge/` HTTP API — does not connect to Memgraph directly.

**New dependencies:** `pdfplumber`, `markdown-it-py`

#### Files

New: `scripts/ingest_document.py`
Modified: `requirements.txt`, `memory_service/config.py`

#### Definition of Success

- [ ] Markdown file chunked on heading/paragraph boundaries; each chunk is a `Chunk` node with `heading`, `body`, `section_ref`
- [ ] PDF file chunked using pdfplumber layout analysis; same node structure
- [ ] Chunk embeddings use `KNOWLEDGE_EMBEDDING_MODEL` (not `EMBEDDING_MODEL`)
- [ ] `HAS_NEXT` edges link consecutive chunks within a document
- [ ] `chunk_review_mode=true` (default): no `SUPPORTS` edges created; chunks only
- [ ] `chunk_review_mode=false`: `SUPPORTS` edges created with `status="auto-inferred"` for distance < threshold
- [ ] `--link-controls` flag triggers SUPPORTS inference independently of chunking run
- [ ] Re-ingesting an updated document with changed Control text reverts affected `SUPPORTS` edges to `auto-inferred`
- [ ] Integration test: ingest a sample Markdown file; verify Chunk nodes and `HAS_CHUNK`/`HAS_NEXT` edges; verify no `SUPPORTS` edges in review mode


---

### WP-074 — Information Security knowledge layer: CLI, MCP tools, and ETL

#### Motivation

The knowledge layer API needs to be accessible from the same CLI and MCP surfaces as the personal memory layer. ETL scripts are needed for bulk framework ingestion from structured YAML catalogues. MCP tools must be narrow and single-purpose with LLM-directed docstrings to be useful to agents.

#### Design

**New MCP tools in `mcp_server/server.py`** (≤12 initial tools):

| Tool | Docstring purpose |
|------|-------------------|
| `knowledge_list_applicable_norms(org_id)` | "Returns norms applicable to the specified organisation based on its OPERATES_IN jurisdictions. Call this first to scope any compliance query." |
| `knowledge_search_controls(query, org_id, domain?, limit)` | "Vector search for controls applicable to org_id. Restricts to org's jurisdiction scope automatically." |
| `knowledge_search_chunks(query, org_id, limit)` | "Searches document sections owned by org_id's organisation. Returns evidence and policy text." |
| `knowledge_list_norms()` | "Lists all loaded norms with jurisdiction scope." |
| `knowledge_list_documents(org_id)` | "Lists documents owned by this organisation." |
| `knowledge_add_standard`, `knowledge_add_control`, `knowledge_map_controls`, `knowledge_add_organisation`, `knowledge_add_jurisdiction` | Write tools mirroring the HTTP API |
| `knowledge_review_supports(control_id, limit)` | "Shows auto-inferred Chunk→Control links for human review. Returns chunk text + control text side-by-side." |
| `knowledge_confirm_supports(chunk_id, control_id)` / `knowledge_reject_supports(chunk_id, control_id)` | Human validation of provisional SUPPORTS edges |

MCP tools are only registered when `ENABLE_KNOWLEDGE_LAYER=true`.

**New CLI commands** in `memory_client/cli.py` mirror MCP tools via Typer. CLI also includes `memory ingest-framework` and `memory ingest-document` as top-level commands.

**Extend `memory_client/client.py`** with HTTP client methods for `/knowledge/` endpoints.

**New `scripts/ingest_framework.py`** — bulk ingestion from structured YAML/JSON control catalogue. Reads standards, controls, and cross-mappings; calls API in dependency order (Norm → Controls → MAPPED_TO edges). Reproducible and auditable.

**Seed data files:**
- `scripts/data/nist_csf_controls.yaml` — NIST CSF controls
- `scripts/data/iso27001_controls.yaml` — ISO 27001:2022 controls (no `APPLIES_IN` edges — universal)
- `scripts/data/business_attributes.yaml` — seed catalogue (confidentiality, integrity, availability, accountability, auditability, non-repudiation, etc.)
- `scripts/data/jurisdictions.yaml` — seed list (EU, DE, UK, US, critical-infrastructure, healthcare, payments, financial-services, energy, transport)

YAML schema includes `lang` field. A standard node's default `lang` applies to all controls unless overridden per-control. NIS2 → `"en"`, KRITIS-DG → `"de"`.

**New `docs/KNOWLEDGE_LAYER.md`** — separation invariants, node/edge reference, operational procedures (how to ingest a new framework, re-ingest after control text updates), feature flag documentation, ADR-001 reference.

#### Files

New: `scripts/ingest_framework.py`, `scripts/data/nist_csf_controls.yaml`, `scripts/data/iso27001_controls.yaml`, `scripts/data/business_attributes.yaml`, `scripts/data/jurisdictions.yaml`, `docs/KNOWLEDGE_LAYER.md`
Modified: `mcp_server/server.py`, `memory_client/cli.py`, `memory_client/client.py`

#### Definition of Success

- [ ] All MCP tools defined with LLM-directed docstrings; each tool has exactly one job
- [ ] MCP tools only registered when `ENABLE_KNOWLEDGE_LAYER=true`
- [ ] CLI commands mirror MCP tools; `memory ingest-framework` and `memory ingest-document` operational
- [ ] `ingest_framework.py` ingests NIST CSF and ISO 27001 YAML files successfully against live service
- [ ] YAML schema validates `lang` field; default propagates from Norm to Controls
- [ ] `knowledge_review_supports` returns chunk text + control text side-by-side
- [ ] `knowledge_confirm_supports` / `knowledge_reject_supports` set `status` correctly on the edge
- [ ] `docs/KNOWLEDGE_LAYER.md` documents separation invariants, operational procedures, and references ADR-001
- [ ] Integration test: ingest ISO 27001 via `ingest_framework.py`; verify Norm + Control nodes; verify anchor Memory created


---

### WP-075 — Information Security knowledge layer: SABSA bidirectional traceability

#### Motivation

SABSA requires two-way traceability: every control must be traceable upward to the business attributes it serves, and downward to the evidence that proves it is implemented. Gap analysis must distinguish between declared intent (IMPLEMENTS) and inferred evidence (SUPPORTS) — they are different claims. The three-way reconciliation exposes the asymmetry that is otherwise hidden.

Per ADR-001, traceability endpoints must work in **dual mode**: knowledge-only (no Memory traversal) and integrated (with Memory evidence/gap nodes). The knowledge-only mode supports standalone compliance use.

#### Design

**New read endpoints (added to `knowledge_routes.py`):**

`GET /knowledge/control/{id}/trace-up`
- Which Norm owns it (`HAS_CONTROL`)?
- Which BusinessAttributes does it address (`ADDRESSES`)?
- Which Controls map to it across frameworks (`MAPPED_TO`)?
- Response: `{control, norm, attributes[], mapped_controls[]}`
- **Knowledge-only:** Fully functional without Memory nodes.

`GET /knowledge/control/{id}/trace-down`
- Which Documents declare intent to implement it (`IMPLEMENTS`)?
- Which Chunks contain supporting content (`SUPPORTS`, sorted by confidence)?
- Which Memory nodes are linked as evidence, context, or gap findings (`ABOUT_CONTROL` by `relationship_type`)?
- Response: `{control, documents[], chunks[], evidence[], context[], gaps[]}`
- Parameters: `depth: int = 1`, `limit: int = 20`, `include_archived: bool = false`
- **Knowledge-only:** Returns documents and chunks; `evidence`, `context`, and `gaps` arrays are empty when no Memory nodes exist. Response is still valid and useful.

`GET /knowledge/attribute/{attribute_id}/coverage`
- All Controls that `ADDRESSES` this attribute, grouped by Norm
- For each: count of Documents `IMPLEMENTS` it, count of Chunks `SUPPORTS` it, count of Memory nodes as evidence vs. gap findings
- Response: structured coverage report for compliance dashboards
- **Knowledge-only:** Memory counts are zero; document and chunk counts still provide coverage visibility.

`GET /knowledge/gap-analysis?org_id=...&framework=...&domain=...&attribute_id=...&include_universal=false`
- Controls in scope: `MATCH` (not OPTIONAL MATCH) against `APPLIES_IN` ∩ org's `OPERATES_IN`; `include_universal=false` excludes standards with no `APPLIES_IN` edges by default
- Without `org_id`: generic mode — all loaded frameworks, no jurisdiction filter
- Three-way reconciliation: `implemented_and_supported`, `implemented_not_supported` (declared intent, no chunk evidence), `supported_not_implemented` (chunk evidence, no formal declaration)
- Evidence layer: `ABOUT_CONTROL(relationship_type="evidence", org_id=$org_id)` Memory nodes — uses `OPTIONAL MATCH` so zero evidence memories is valid
- Gap layer: `ABOUT_CONTROL(relationship_type="gap", org_id=$org_id)` Memory nodes — uses `OPTIONAL MATCH`
- Response includes: `scope_snapshot_at`, `mode: "generic" | "org-scoped"`, warning if org's `last_scope_updated_at` is newer than `scope_snapshot_at`
- Response: `{org_id, applicable_norms[], total_controls, implemented_and_supported[], implemented_not_supported[], supported_not_implemented[], evidenced[], gap_findings[], evidence_gaps[]}`
- **Knowledge-only:** `evidenced` and `gap_findings` are empty; three-way reconciliation still works using Documents (IMPLEMENTS) and Chunks (SUPPORTS) only.

**`MAPPED_TO` does not carry jurisdiction.** Gap analysis Cypher must not inherit applicability through `MAPPED_TO` chains.

**New MCP tools:** `knowledge_trace_up`, `knowledge_trace_down`, `knowledge_attribute_coverage`, `knowledge_gap_analysis`. All tools work in both modes (omit `org_id` for generic; provide `org_id` for org-scoped). Tool docstrings explicitly describe both modes.

All endpoints are read-only Cypher traversals in `knowledge_repo.py`. Memory-touching traversals use `OPTIONAL MATCH` and are routed through `knowledge_bridge.py`. No new write operations.

#### Files

Modified: `memory_service/knowledge_repo.py`, `memory_service/knowledge_routes.py`, `memory_service/knowledge_bridge.py`, `mcp_server/server.py`

#### Definition of Success

- [ ] `trace-up` returns correct standard, attributes, and mapped controls for a seeded control
- [ ] `trace-down` returns documents, chunks, and memories grouped by `relationship_type`; respects `limit` and `depth`
- [ ] `trace-down` with zero Memory nodes: returns valid response with empty evidence/context/gaps arrays
- [ ] `include_archived=true` surfaces archived Memory nodes in evidence/gap lists
- [ ] `attribute/coverage` returns correct counts grouped by Norm
- [ ] `attribute/coverage` with zero Memory nodes: memory counts are zero, document/chunk counts correct
- [ ] `gap-analysis` without `org_id`: returns all loaded controls (generic mode)
- [ ] `gap-analysis` with `org_id`: scoped to org's `OPERATES_IN` ∩ `APPLIES_IN`; `include_universal=false` excludes unscoped standards
- [ ] `gap-analysis` with zero Memory nodes: three-way reconciliation works using Documents and Chunks only
- [ ] Three-way reconciliation categories mutually exclusive and exhaustive over applicable controls
- [ ] `MAPPED_TO` traversal does NOT inherit jurisdiction scope
- [ ] Dual-org test: org A (EU) and org B (US) + EU-only standard → gap-analysis for org A returns EU controls; for org B returns zero
- [ ] MCP tools `knowledge_trace_up`, `knowledge_trace_down`, `knowledge_attribute_coverage`, `knowledge_gap_analysis` operational


---

### WP-076 — Information Security knowledge layer: integration and separation tests

#### Motivation

The separation guarantee is an architectural invariant, not a convention. It must be enforced by a test that runs on every test session — not just as part of a WP-076 suite. Any future regression (e.g. a new query accidentally scanning all labels) is caught immediately.

#### Design

**Test files:**

| File | Coverage |
|------|----------|
| `tests/test_wp069_knowledge_schema.py` | Schema smoke: indexes and constraints exist after `init_knowledge_schema.py` |
| `tests/test_wp070_knowledge_write.py` | Upsert Norm, Control, Document, Chunk; confirm edges; idempotency; embedding uses `KNOWLEDGE_EMBEDDING_MODEL` |
| `tests/test_wp071_knowledge_search.py` | Vector search returns correct nodes; anchor Memory written on standard upsert |
| `tests/test_wp072_cross_layer.py` | `ABOUT_CONTROL`/`CITES_DOC` on add/update; `relationship_type` and `org_id` stored; confirmed in MemoryHit; `merge_memory` rewires correctly; `CITES_DOC` for missing Document returns HTTP 400; flag-off behaviour |
| `tests/test_wp075_traceability.py` | trace-up/trace-down/coverage/gap-analysis; dual-org jurisdiction test; generic mode; three-way reconciliation; `include_archived=true` |
| `tests/test_wp076_separation.py` | **autouse conftest fixture**: seed 20+ Controls + 50+ Chunks; call `POST /memory/search`; assert zero knowledge-layer nodes. Seed Memories; call `POST /knowledge/search/controls`; assert zero Memory nodes. Run `long_rest`; assert zero `SUPPORTS.confidence` or `ABOUT_CONTROL` properties modified. |

**Knowledge-only mode tests (ADR-001 dual-mode):**
- All WP-071 search tests pass with zero Memory nodes in the graph
- WP-075 `trace-down` returns valid response with empty evidence/context/gaps when no Memory nodes exist
- WP-075 `gap-analysis` produces valid three-way reconciliation using only Documents and Chunks
- WP-075 `attribute/coverage` returns zero for memory counts but correct document/chunk counts

**Feature flag tests:**
- `/knowledge/*` endpoints return 404 when `ENABLE_KNOWLEDGE_LAYER=false`
- `control_ids`/`doc_ids` on `POST /memory` safely ignored when flag is off
- MCP knowledge tools not registered when flag is off

**Prerequisite:** WP-024 (multi-node cleanup helper) must be resolved or folded into WP-076 before these tests are written. Knowledge-layer tests use test-scoped ID prefixes (`test-{uuid}-`) to avoid cross-test interference on shared `MERGE`'d reference nodes.

**Shared conftest fixtures:**
- `knowledge_seeded_db` — Norm + controls + chunks with `test-{uuid}-` prefix IDs; teardown cleans up
- `dual_org_seeded_db` — two orgs, two jurisdictions, jurisdiction-scoped standards for separation validation

**The separation test is an autouse conftest fixture.** It runs on every test session — any future regression is caught immediately.

#### Files

New: `tests/test_wp069_knowledge_schema.py`, `tests/test_wp070_knowledge_write.py`, `tests/test_wp071_knowledge_search.py`, `tests/test_wp072_cross_layer.py`, `tests/test_wp075_traceability.py`, `tests/test_wp076_separation.py`
Modified: `tests/conftest.py`

#### Definition of Success

- [ ] All six test files pass against live stack
- [ ] `test_wp076_separation.py` is an autouse conftest fixture — runs on every test session
- [ ] Separation test: `POST /memory/search` returns zero Control/Chunk/Norm/Document nodes
- [ ] Separation test: `POST /knowledge/search/controls` returns zero Memory nodes
- [ ] Separation test: `long_rest` run does not modify `SUPPORTS.confidence` or `ABOUT_CONTROL` edges
- [ ] Knowledge-only mode: all search and traceability endpoints produce valid results with zero Memory nodes
- [ ] Feature flag off: `/knowledge/*` returns 404; `control_ids` on `POST /memory` safely ignored
- [ ] Dual-org jurisdiction test: gap-analysis for org A (EU) returns EU controls; for org B (US) returns zero for EU-only standard
- [ ] Generic mode test: gap-analysis without `org_id` returns all loaded controls
- [ ] `merge_memory` rewiring test: `ABOUT_CONTROL`/`CITES_DOC` edges on source node correctly appear on target node after merge
- [ ] `knowledge_bridge.py` is the only module importing from both `memory_repo` and `knowledge_repo` (import audit)


---

### WP-082 — Associative pull-through in search results *(superseded by WP-093)*

> **This WP is superseded.** WP-093 is a strict superset — it implements the associative expansion designed here and adds score exposure and min_score filtering. Retained for reference only.

#### Motivation

Vector search ranks hits by embedding distance. When two memories are semantically related but worded differently — e.g. an original *fact* and a later *observation about that fact* — the observation often scores higher because its text echoes the query more directly. The original fact is silently omitted even though it is strongly linked via a high-weight `RELATED_TO` or `LEADS_TO` edge.

Human recall works differently: the direct match surfaces first, then its strongest associations arrive involuntarily. This WP adds that second step.

#### Design (retained for reference — see WP-093 for adopted design)

- Add an optional `associated_count` parameter to `POST /memory/search` (default: 3, max: 10). When > 0, pull-through is active.
- For each primary hit, run a secondary Cypher pass: follow `RELATED_TO` and `LEADS_TO` edges (both directions) from the matched node, ordered by `weight` descending, limited to `associated_count` results per hit.
- Return these as a hydrated `associated: List[MemoryHit]` field on each `SearchMemoryHit` (not bare IDs — full text/type/tags/importance so callers can use them without a second lookup).
- Exclude from `associated` any node that already appears as a primary hit in the same response (no duplication).
- Activate associated edges in the background recall increment (same path as primary hits), so pull-through reinforces the graph structure.


---

### WP-085 — Analytics Phase Sprint 1: graph-vs-vector diagnostics, cluster discovery, bridge detection

> Consolidates: WP-057, WP-058, WP-059

#### Motivation

As the fabric grows, the explicit graph (`RELATED_TO`/`LEADS_TO` edges) and the embedding space can silently diverge. Sprint 1 of the Analytics Phase builds the core diagnostic layer that checks this agreement, discovers emergent clusters that the Strand taxonomy may not capture, and surfaces bridge memories that serve as high-leverage connectors between otherwise separate domains.

#### Design

**WP-057 — Graph-vs-vector agreement diagnostics**
- For each Memory node, query the vector index for its top-K nearest neighbours (by embedding cosine distance).
- Compare the result set against the node's actual `RELATED_TO`/`LEADS_TO` edges (both directions).
- Produce a per-node agreement score: fraction of vector-top-K that are also graph neighbours.
- Output: list of memories ranked by *disagreement* (low score = graph lags behind or overlinks semantic reality).
- Endpoint: `GET /analytics/graph-vector-agreement?limit=50&threshold=0.85`
- CLI: `memory analytics graph-vector-agreement`

**WP-058 — Latent cluster discovery vs strand membership**
- Cluster all Memory embeddings offline using a configurable algorithm (e.g. HDBSCAN or k-means with silhouette selection).
- For each discovered cluster, report its dominant `Strand` assignments (via `IN_STRAND` edges) and the degree of overlap.
- Flag clusters with high strand fragmentation (many different strands) and strands with low cluster coherence (spread across many clusters).
- Output: cluster membership report + suggested strand splits/merges.
- Endpoint: `GET /analytics/cluster-strand-alignment?min_cluster_size=5`
- CLI: `memory analytics cluster-strand-alignment`

**WP-059 — Bridge-memory detection across semantic regions**
- Identify memories with high *betweenness* in the graph and/or memories that lie between distinct embedding clusters.
- Bridge score = combination of: graph betweenness centrality (via MAGE), embedding-space inter-cluster proximity.
- Output: ranked list of bridge memories with their bridged cluster/strand pairs.
- Endpoint: `GET /analytics/bridge-memories?limit=20`
- CLI: `memory analytics bridge-memories`

All three endpoints share a common analytics router (`memory_service/analytics_routes.py`) and utility module (`memory_service/analytics_utils.py`).

#### Definition of Success

- [ ] `GET /analytics/graph-vector-agreement` returns per-memory agreement scores, ranked by disagreement
- [ ] `GET /analytics/cluster-strand-alignment` clusters embeddings and compares with Strand membership
- [ ] `GET /analytics/bridge-memories` identifies cross-cluster connector memories with bridge scores
- [ ] `analytics_routes.py` and `analytics_utils.py` exist as the shared analytics layer
- [ ] CLI commands operational for all three endpoints
- [ ] Integration tests: seed diverse memories across multiple strands; verify all three endpoints return non-empty results with correct structure


---

### WP-086 — Analytics Phase Sprint 2: outlier detection, semantic families, strand cohesion, missing-edge suggestions, centrality scoring, echo-chamber detection, semantic timelines, neighbourhood summarisation

> Consolidates: WP-060, WP-061, WP-063, WP-064, WP-065, WP-066, WP-067, WP-068

#### Motivation

Sprint 2 extends the analytics layer (built in WP-085) with eight additional capabilities that share the same diagnostic output pattern. Together they provide comprehensive tools for understanding the memory fabric's health, topology, and temporal evolution. They are batched together because each is relatively self-contained once the Sprint 1 infrastructure is in place, and delivering them as a unit avoids eight separate "add one analytics endpoint" WPs drifting out of sequence.

#### Design

**WP-060 — Vector outlier and anomaly detection**
- Identify memories whose embedding distance to all top-K neighbours exceeds a configurable threshold.
- Useful for spotting noise, malformed memories, or genuinely novel information.
- Endpoint: `GET /analytics/outliers?distance_threshold=0.95&limit=20`

**WP-061 — Semantic family analysis** *(depends on WP-047)*
- Group related memories into semantic families beyond pairwise duplicate candidates.
- A family is a connected component in a similarity graph built at a given threshold.
- Support review of repeated framings, adjacent formulations, and candidate summarisation targets.
- Endpoint: `GET /analytics/semantic-families?threshold=0.85&min_size=2`

**WP-063 — Strand cohesion diagnostics**
- Measure how semantically tight or fragmented each strand is (intra-strand embedding variance).
- Flag strands whose members are too dispersed or naturally split into sub-clusters.
- Endpoint: `GET /analytics/strand-cohesion`

**WP-064 — Hybrid missing-edge suggestions**
- Suggest `RELATED_TO` or `LEADS_TO` edges from a combination of embedding similarity, shared context, and time ordering — for node pairs that have no existing edge.
- Returns as a suggestion/review list; does not auto-link.
- Endpoint: `GET /analytics/missing-edges?limit=30`

**WP-065 — Hybrid memory centrality scoring**
- Blended centrality rank: graph degree + betweenness + embedding density + strength + recall count + edge activation.
- Provides a more reliable "core memory" signal than any single metric.
- Endpoint: `GET /analytics/centrality?limit=50`

**WP-066 — Semantic gravity-well / echo-chamber detection**
- Detect embedding regions that are over-saturated: disproportionately dense, self-reinforcing in retrieval, or dominating wake-up output.
- Endpoint: `GET /analytics/echo-chambers?density_threshold=0.8`

**WP-067 — Semantic timelines and concept recurrence**
- Track how semantic neighbourhoods recur, disappear, or shift across time (using `created_at`/`last_used_at`).
- Useful for long-running strands (career, health, relationships) and for identifying topic resurgence.
- Endpoint: `GET /analytics/semantic-timeline?strand_id=<id>&bucket=week`

**WP-068 — Neighbourhood summarisation and semantic labels**
- For each embedding cluster or neighbourhood, produce a short natural-language label derived from the dominant terms/facts.
- Turns semantic density into navigable overview labels and review queues.
- Endpoint: `GET /analytics/neighbourhood-labels?min_cluster_size=5`

All endpoints are added to `analytics_routes.py` (from WP-085). No new routers needed.

#### Definition of Success

- [ ] All eight endpoints operational in `analytics_routes.py`
- [ ] CLI commands for all eight endpoints
- [ ] WP-061 (`semantic-families`) depends on WP-047 duplicate infrastructure being in place
- [ ] Integration tests: each endpoint returns structurally correct results against a seeded live database
- [ ] No existing `POST /memory/search` or wake-up behaviour changed


---

### WP-093 — Agent-optimised search: score exposure, min_score filter, associative expansion

#### Motivation

The companion agent (Mara) runs per-turn memory queries during active conversations against a token-constrained context window. The current `POST /memory/search` has three gaps that force the agent to take all top-N results regardless of relevance:

1. **No score visibility.** Cosine distance is computed internally but stripped from the response. The agent cannot distinguish a tight, high-confidence match from a diffuse scatter of marginal hits.
2. **Flat top-N ignores graph structure.** Vector search returns the N closest nodes by embedding distance. Strongly-linked memories — e.g. the original fact when an observation-about-it scores higher — are silently omitted.
3. **No primary/associated distinction.** An agent prioritising context-window budget needs to know which memories were direct semantic matches versus which arrived via graph expansion.

#### Design

**1. `score` field on `MemoryHit`**

Add `score: float | None` to `MemoryHit`. For vector-search hits: `score = 1.0 - distance` (higher = more similar). For person-anchored hits (no vector distance): `score = null`.

Non-breaking additive change to response schema.

**2. `min_score` on `SearchMemoryRequest`**

Add `min_score: float | None = None` (range 0–1). When set, only memories with `score >= min_score` are returned as primary hits. `limit` is applied after `min_score` filtering — no padding with lower-scoring results. Empty list is valid (not an error). Ignored when `person_ids` is set.

**3. `neighbour_cap` and `associated` on `SearchMemoryRequest` / `MemoryHit`**

Add `neighbour_cap: int = 3` to `SearchMemoryRequest`. For each primary hit, follow its outbound `RELATED_TO` and `LEADS_TO` edges ordered by `weight` descending, fetch and hydrate up to `neighbour_cap` linked Memory nodes, and return them in `associated: list[AssociatedMemoryHit]` on the hit.

`AssociatedMemoryHit` carries: `id`, `text`, `type`, `importance`, `edge_weight` (the `RELATED_TO`/`LEADS_TO` weight). No `score` field (not vector-matched).

Deduplication: a node that appears as a primary hit is excluded from all `associated` lists.

Person-anchored path (`person_ids` set): returns `associated: []`, ignores `min_score`.

**4. `MemoryClient.search_memory()` update**

Accept and pass through `min_score` and `neighbour_cap`. Existing callers that do not set these fields are unaffected (both default to no-op).

**MCP surface update is out of scope** — follow-on task once HTTP layer is stable.

#### Acceptance criteria

- [ ] `POST /memory/search` response includes `score` on all vector-search hits; `null` on person-anchored hits
- [ ] `min_score=0.80` returns only hits with `score >= 0.80`; returns empty list (not an error) when nothing qualifies
- [ ] `neighbour_cap=3` returns up to 3 `associated` entries per hit, ordered by `edge_weight` descending
- [ ] A memory appearing as both a primary hit and a candidate associated entry appears only in the primary list
- [ ] Person-anchored search (`person_ids` set) returns `associated: []` and ignores `min_score`
- [ ] All existing tests pass — callers that omit the new fields see identical behaviour
- [ ] `MemoryClient.search_memory()` accepts and passes through `min_score` and `neighbour_cap`
- [ ] Integration test: seed fact + observation-about-fact with high-weight `RELATED_TO`; search for observation; confirm fact appears in `associated`
- [ ] Integration test: `min_score` set high enough that no results pass — confirm empty list, 200 OK
- [ ] Integration test: primary hit deduplication — confirm a node that is a primary hit does not appear in any `associated` list


---

### WP-094 — ADR-001 alignment: rename, feature flag, independent embedding model

> **Architecture:** See [ADR-001](docs/architecture/ADR-001-knowledge-layer-placement.md) for the full decision record.

#### Motivation

WP-069 delivered the knowledge layer schema under the `cybersec_*` naming convention, with a single shared embedding model and no feature flag. ADR-001 (accepted 2026-04-02) establishes three architectural guardrails that require reworking these deliverables before the remaining knowledge layer WPs (070–076) proceed:

1. **Feature flag** (`ENABLE_KNOWLEDGE_LAYER`, default false) — knowledge routes only load when enabled
2. **Independent embedding model** (`KNOWLEDGE_EMBEDDING_MODEL`) — decouples knowledge and episodic migration timelines
3. **`knowledge_*` naming** — reflects the broader Information Security scope, not just "cybersecurity"

#### Design

**Rename files:**
- `memory_service/cybersec_schemas.py` → `memory_service/knowledge_schemas.py`
- `scripts/init_cybersec_schema.py` → `scripts/init_knowledge_schema.py`
- `tests/test_wp069_cybersec_schema.py` → `tests/test_wp069_knowledge_schema.py`

**Update all internal references** to the old file/module names (imports in `main.py`, any references in config, test conftest, etc.).

**Add `Settings` fields** in `memory_service/config.py`:
- `knowledge_embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"` — independent of `embedding_model`
- `enable_knowledge_layer: bool = False` — feature flag

**Update `init_knowledge_schema.py`** to use `KNOWLEDGE_EMBEDDING_MODEL` for knowledge-layer vector indexes.

**Update `migrate_embeddings.py`:**
- Remove the forced re-embedding of Memory nodes (episodic memory stays on its current model)
- Scope to knowledge-layer nodes only (Control, Chunk), using `KNOWLEDGE_EMBEDDING_MODEL`
- If both models are the same (user chose to unify), it still works — just re-embeds everything with the one model

**Update `.env.example`** with `KNOWLEDGE_EMBEDDING_MODEL` and `ENABLE_KNOWLEDGE_LAYER` entries.

#### Files

Renamed: `memory_service/cybersec_schemas.py` → `memory_service/knowledge_schemas.py`, `scripts/init_cybersec_schema.py` → `scripts/init_knowledge_schema.py`, `tests/test_wp069_cybersec_schema.py` → `tests/test_wp069_knowledge_schema.py`
Modified: `memory_service/config.py`, `memory_service/main.py`, `scripts/migrate_embeddings.py`, `.env.example`

#### Definition of Success

- [ ] All `cybersec_*` files renamed to `knowledge_*`; no references to old names remain
- [ ] `KNOWLEDGE_EMBEDDING_MODEL` setting exists, independent of `EMBEDDING_MODEL`
- [ ] `ENABLE_KNOWLEDGE_LAYER` setting exists, default `false`
- [ ] `init_knowledge_schema.py` uses `KNOWLEDGE_EMBEDDING_MODEL` for index creation
- [ ] `migrate_embeddings.py` scoped to knowledge-layer nodes only; does not touch Memory embeddings
- [ ] `.env.example` documents both new settings
- [ ] Existing WP-069 tests pass under new file names
- [ ] Integration test: verify knowledge schema init uses the knowledge embedding model

