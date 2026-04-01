# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** H = High / M = Medium / L = Low
> **Priority score:** `Value / Effort` using `H=3`, `M=2`, `L=1`
> Completed WPs → [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Currently In Progress

| ID | Title | Phase | Value | Effort | Depends on | Notes |
|----|-------|-------|-------|--------|------------|-------|

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
| 1 | R1 | WP-056 | Process log for lifecycle and maintenance operations | M | L | 2.0 | WP-038 ✅, WP-040 ✅ | Add explicit process/event logging for operations like update, merge, archive, restore, short-rest, and long-rest. The goal is traceability beyond node/edge timestamps: who/what ran it, when, what changed, and the outcome summary. Could be a dedicated `Operation` node/edge model, append-only event log, or both. |
| 2 | R1 | WP-084 | API health and response polish (WP-034 + WP-035 + WP-036) | M | L | 2.0 | — | Batch of three small improvements best done together: (1) add version/build hash to `/health` response to detect stale service instances at startup; (2) return `strand_ids` in `add-memory` API response to reduce friction when chaining related memories; (3) document `### Relevant to today` suppression in `COMPANION.md` for small/sparse DBs so wake-up output is not confusing. Combined effort is still Low. |
| 3 | R1 | WP-078 | Project node CRUD endpoints | M | L | 2.0 | — | Add `GET /project` (list) and `POST /project` (upsert) endpoints mirroring the existing `/person` pattern. Add `name` and `description` properties to Project nodes (currently only `id` is stored). Extend MCP with a `memory_create_project` tool. Makes project management a first-class operation rather than a side effect of `add_memory`. |
| 4 | R1 | WP-087 | Expose `person_ids` in MCP `memory_add` | M | L | 2.0 | WP-052 ✅ | The MCP `memory_add` tool does not expose `person_ids`, meaning memories cannot be linked to people at creation time via the MCP surface. The HTTP API and Python client both support it. One-parameter addition to the MCP wrapper + unit test (mock) + integration test (live stack, verify ABOUT edge created). Identical pattern to WP-052. |
| 5 | R1 | WP-089 | Fix pre-existing wake-up mock failures in test_wp033_mcp_server.py | M | L | 2.0 | WP-088 ✅ | Three tests (test_u3, test_u6, test_u7) in `tests/test_wp033_mcp_server.py` fail because they mock `wake_up_split.return_value` as a 2-tuple, but `wake_up_split()` now returns a 3-tuple (fact memories, topic memories, maintenance_status — added in WP-054). Update mock return values to 3-tuples. Surfaced during WP-088 regression run. |
| 5 | R1 | WP-053 | Scheduled maintenance orchestration for short-rest and long-rest | H | M | 1.5 | WP-040 ✅ | Move maintenance from manual CLI usage to real routine care. Add a scheduler or documented host-level automation path that runs `short-rest` on a frequent cadence and `long-rest` on a slower cadence, with safe defaults, dry-run support for rollout, and clear operational docs. |
| 6 | R1 | WP-047 | Near-duplicate detection for memory review | H | M | 1.5 | WP-038 ✅ | Surface semantically similar memories (cosine similarity above configurable threshold) so they can be reviewed and merged via WP-038 merge endpoint. Feeds into short-rest/long-rest cleanup loop. See detail below. |
| 7 | R1 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | 1.5 | WP-038 ✅ | Prevent test artefacts polluting live context. See detail below. |
| 8 | R2 | WP-049 | Wake-up companion + conversant anchoring | H | M | 1.5 | — | Wake-up should always surface anchor memories for the Companion (Mara) identity and for the specific person the calling agent is conversing with, in addition to prominent + topic-relevant memories. See detail below. |
| 9 | R2 | WP-008 | API-based LLM provider abstraction | H | M | 1.5 | WP-007 ✅ | Replace the IDE-tied framing with a runtime `LLMClient` provider layer for Anthropic/OpenAI/Ollama. The goal is to let the fabric and future agents run outside VS Code while keeping provider choice swappable behind one interface. |
| 10 | R2 | WP-009 | Headless agent runtime outside VS Code | H | M | 1.5 | WP-008 | Build `BaseAgent` on top of `memory_client` + `LLMClient` so scheduled/event-driven agents can run without an editor session. This is the execution foundation for all higher-level agents that should share the same fabric. |
| 11 | R2 | WP-085 | **Analytics Phase — Sprint 1:** graph-vs-vector diagnostics, cluster discovery, bridge detection (WP-057 + WP-058 + WP-059) | H | M | 1.5 | WP-029 ✅ | Three tightly related graph-analytics capabilities best built together as a shared diagnostic layer: (1) graph-vs-vector agreement — compare each memory's nearest embedding neighbours with its actual `RELATED_TO`/`LEADS_TO` neighbourhood to surface where the graph lags or overlinks semantic reality; (2) latent cluster discovery — cluster embeddings offline to discover emergent themes and compare them with explicit `Strand` assignments to identify overly broad, missing, or mislabeled strands; (3) bridge-memory detection — identify memories that span otherwise separate embedding clusters or graph communities, surfacing high-leverage cross-domain connectors. All three share the same embedding-space traversal infrastructure and diagnostic output pattern. |
| 12 | R2 | WP-006 | Wire `GET /memory/graph` | M | M | 1.0 | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 13 | R2 | WP-043 | Inline effective_strength sort in search | L | L | 1.0 | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as the current proxy. |
| 14 | R2 | WP-090 | Handle non-ServiceUnavailable exceptions in `find_duplicate_memory` | L | L | 1.0 | WP-088 ✅ | `find_duplicate_memory()` in `memory_repo.py` can raise `CypherError` or other Memgraph-level exceptions (e.g. malformed query, vector index unavailable). These propagate uncaught from the `add_memory` handler, which only catches `ServiceUnavailable`. Options: (a) catch `CypherError` inside `find_duplicate_memory` and return `None` (fail-open), or (b) let it propagate to a new `except CypherError → 500` clause in the handler. Fail-open is safer for availability; fail-closed is safer for data integrity. Surfaced during WP-088 code review. |
| 15 | R2 | WP-025 | Extract shared CLI error handler | L | L | 1.0 | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. |
| 15 | R2 | WP-026 | `MemoryType` mirror in `memory_client` | L | L | 1.0 | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 16 | R2 | WP-023 | Extract `get_session` context manager for 503 handling | L | L | 1.0 | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints. Do after WP-029 (adds more endpoints). |
| 17 | R2 | WP-020 | UNWIND for person/strand/related_ids writes | L | L | 1.0 | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 18 | R2 | WP-021 | Non-blocking embedding in async endpoints | L | L | 1.0 | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 19 | R2 | WP-024 | `cleanup_nodes` support multiple ids per label | L | L | 1.0 | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. Required by WP-076. |
| 20 | R2 | WP-017 | Embedding cache eviction / size cap | L | L | 1.0 | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 21 | R2 | WP-014 | Docker resource limits | L | L | 1.0 | — | Add `mem_limit`/`cpus` to docker-compose. |
| 22 | R2 | WP-081 | Initialise `activation_count` and `last_activated_at` on auto-linked edges at `add_memory` time | L | L | 1.0 | — | The `add_memory` auto-link path (vector search MERGE at ingest) does not set `activation_count` or `last_activated_at` on newly created `RELATED_TO` edges. All other edge writers (long_rest, short_rest) set these fields on creation. The gap means edge-decay and count queries must defensively `COALESCE` these fields. Surfaced during WP-055. |
| 23 | R2 | WP-082 | Associative pull-through in search results | M | M | 1.0 | WP-029 ✅ | For each vector-search hit, follow its strongest `RELATED_TO` and `LEADS_TO` edges (by `weight` descending) and return the top-K linked memories as a hydrated `associated` list alongside the primary hit. Mirrors human associative recall: the direct match surfaces first, then its strongest connections arrive involuntarily. Fixes cases where the most-recent *observation about a fact* scores highest in vector search while the original linked *fact* is silently omitted. See detail below. |
| 24 | R2 | WP-041 | Subject/object schema on Memory nodes | H | H | 1.0 | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| 25 | R2 | WP-077 | Extract shared schema-init utilities | L | L | 1.0 | WP-069 | `create_constraint()` and `get_embedding_dimension()` are copy-pasted identically in `init_schema.py` and `init_cybersec_schema.py`. Extract to `scripts/schema_utils.py`. Found in WP-069 /simplify review. Best done before WP-070 builds further on these scripts. |
| 26 | R2 | WP-070 | Cybersecurity knowledge layer: standards & document write API | H | M | 1.5 | WP-069 | FastAPI router (`cybersec_routes.py`) + Cypher (`cybersec_repo.py`). Upserts Standard/Control/Document/Chunk/BusinessAttribute/Organisation/Jurisdiction. IMPLEMENTS edge (Document→Control), APPLIES_IN/OPERATES_IN jurisdiction scoping, OWNED_BY org scoping, MAPPED_TO cross-framework edges. MERGE+text_hash idempotency. Anchor Memory writes on standard ingest. See detail below. |
| 27 | R2 | WP-071 | Cybersecurity knowledge layer: search API | H | M | 1.5 | WP-070 | Vector search over ctrl_embedding_idx and chunk_embedding_idx. Dual modes: unscoped (generic/public, no org required) and org-scoped (jurisdiction-filtered via OPERATES_IN ∩ APPLIES_IN). lang filter for language-specific queries; cross-lingual by default. include_universal flag for globally-applicable standards. /knowledge/incomplete-jurisdictions diagnostic endpoint. See detail below. |
| 28 | R2 | WP-072 | Cybersecurity knowledge layer: cross-layer Memory edges | H | M | 1.5 | WP-070, WP-071 | Extend add_memory/update_memory with ABOUT_CONTROL {relationship_type, org_id} and CITES_DOC edges. Critical: add ABOUT_CONTROL/CITES_DOC to merge_memory rewiring to prevent edge orphaning on merge. Extend MemoryHit response. Extend MCP memory_add/memory_update. See detail below. |
| 29 | R2 | WP-074 | Cybersecurity knowledge layer: CLI, MCP tools, and ETL | H | M | 1.5 | WP-070, WP-071, WP-072 | knowledge_* MCP tools (narrow, single-purpose, LLM-directed docstrings). CLI commands. MemoryClient extension. ingest_framework.py bulk ETL with YAML validation. YAML data files (NIST CSF, ISO 27001, jurisdictions, business attributes). CLI review tool for SUPPORTS edge validation. CYBERSEC_LAYER.md. See detail below. |
| 30 | R2 | WP-075 | Cybersecurity knowledge layer: SABSA bidirectional traceability | H | M | 1.5 | WP-072, WP-074 | trace-up (control → attributes → standards), trace-down (control → documents → chunks → evidence/gap memories), attribute coverage (BAP-style scorecard), gap analysis. Both generic and org-scoped modes. Three-way reconciliation: implemented+supported / implemented-not-supported / supported-not-implemented. include_archived flag for historical evidence. See detail below. |
| 31 | R2 | WP-073 | Cybersecurity knowledge layer: document ingestion pipeline | H | H | 1.0 | WP-071 | PDF (pdfplumber) + Markdown → Document + Chunk nodes. Heading-aware chunking; HAS_NEXT edges for context expansion. chunk_review_mode (default on) prevents silent auto-SUPPORTS. Conservative threshold (distance < 0.20) for auto-inference; SUPPORTS edges start status=”auto-inferred”. Embedding invalidation on control re-embed. See detail below. |
| 32 | R2 | WP-076 | Cybersecurity knowledge layer: integration and separation tests | M | M | 1.0 | WP-069–WP-075, WP-024 | Full integration + separation tests. Critical: autouse conftest separation test (POST /memory/search never returns knowledge-layer nodes; runs every session). Dual-org jurisdiction test. merge_memory ABOUT_CONTROL rewiring test. long_rest non-interference test. Prerequisite: WP-024. See detail below. |
| 34 | R2 | WP-086 | **Analytics Phase — Sprint 2:** outlier detection, semantic families, strand cohesion, missing-edge suggestions, centrality scoring, echo-chamber detection, semantic timelines, neighbourhood summarisation (WP-060 + WP-061 + WP-063 + WP-064 + WP-065 + WP-066 + WP-067 + WP-068) | M | H | 1.0 | WP-085, WP-047, WP-028 ✅, WP-029 ✅ | Eight analytics capabilities that form the second layer of the analytics phase, building on the Sprint 1 (WP-085) diagnostic infrastructure. All share the same analytical pattern and output surface: (1) vector outlier and anomaly detection — memories far from any semantic neighbourhood or with poor graph/embedding agreement; (2) semantic family analysis — group related memories into families beyond pairwise duplicate pairs (depends on WP-047); (3) strand cohesion diagnostics — measure how tight or fragmented each strand's embedding cluster is; (4) hybrid missing-edge suggestions — propose `RELATED_TO`/`LEADS_TO` links from embedding similarity, time ordering, and topology (review flow, not auto-linking); (5) hybrid memory centrality scoring — blended rank from graph centrality, embedding density, strength, recall count, reinforcement, and edge activation; (6) semantic gravity-well/echo-chamber detection — detect over-saturated retrieval regions; (7) semantic timelines and concept recurrence — track how neighbourhoods shift, recur, or disappear over time; (8) neighbourhood summarisation — turn local density into narrative labels and review queues. |
| 35 | R3 | WP-042 | Self-contained `memory_client` packaging | L | L | 1.0 | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. Re-scored from medium value because it is packaging polish rather than core product capability. |
| 36 | R3 | WP-062 | Concept-drift analysis over time | M | H | 0.67 | — | Compare recent memories and clusters with older semantic regions to detect identity drift, changing priorities, and narrative rewrites. Treat this as analysis tooling first, not as automatic judgment. |
| 37 | R3 | WP-010 | Remote/mobile access | L | H | 0.33 | WP-009 | Tailscale/VPS hosting + TLS + API key auth. |
| 38 | R3 | WP-011 | Custom graph-cloud UI | L | H | 0.33 | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |

> **Note:** old backlog items once grouped under `v2+` are now part of the same continuous backlog with `Release` assignments.

---

## Detail Specs

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

### WP-082 — Associative pull-through in search results

#### Motivation

Vector search ranks hits by embedding distance. When two memories are semantically related but worded differently — e.g. an original *fact* and a later *observation about that fact* — the observation often scores higher because its text echoes the query more directly. The original fact is silently omitted even though it is strongly linked via a high-weight `RELATED_TO` or `LEADS_TO` edge.

Human recall works differently: the direct match surfaces first, then its strongest associations arrive involuntarily. This WP adds that second step.

#### Design

- Add an optional `associated_count` parameter to `POST /memory/search` (default: 3, max: 10). When > 0, pull-through is active.
- For each primary hit, run a secondary Cypher pass: follow `RELATED_TO` and `LEADS_TO` edges (both directions) from the matched node, ordered by `weight` descending, limited to `associated_count` results per hit.
- Return these as a hydrated `associated: List[MemoryHit]` field on each `SearchMemoryHit` (not bare IDs — full text/type/tags/importance so callers can use them without a second lookup).
- Exclude from `associated` any node that already appears as a primary hit in the same response (no duplication).
- Activate associated edges in the background recall increment (same path as primary hits), so pull-through reinforces the graph structure.
- Add `associated_count` to `SearchMemoryRequest`; update `MemoryHit` / `SearchMemoryResponse` schemas; update MCP `memory_search` tool.
- The existing `neighbours` field (bare IDs) remains for backwards compatibility; `associated` is the new hydrated version.

#### Definition of Success

- [ ] `POST /memory/search` with `associated_count > 0` returns hydrated `associated` nodes for each hit
- [ ] Associated nodes are ordered by edge `weight` descending
- [ ] A node already present as a primary hit does not appear in any `associated` list
- [ ] Background recall increment activates edges to associated nodes
- [ ] `associated_count = 0` (or omitted) produces identical response to current behaviour
- [ ] MCP `memory_search` exposes `associated_count` parameter
- [ ] Integration test: seed a fact + an observation-about-the-fact with a high-weight `RELATED_TO` edge; search for the observation; confirm the fact appears in `associated`
- [ ] Integration test: search with `associated_count=0`; confirm `associated` is empty for all hits

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

### WP-069 — Cybersecurity knowledge layer: schema, indexes, multilingual model

#### Motivation

Adding ISO 27001, NIST CSF, NIS2, and KRITIS controls as searchable reference data requires a separate schema layer. Using the same `Memory` label would contaminate episodic memory retrieval — `mem_embedding_idx ON :Memory(embedding)` is label-scoped, so knowledge-layer nodes with their own labels are structurally invisible to all existing wake-up, search, and decay queries. No filtering or `layer` property is needed: the label IS the layer.

Multilingual support is required from the start: ISO 27001 is in English; KRITIS-DG is in German. Cross-lingual semantic search is needed to link them. Switching to `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, same as current `all-MiniLM-L6-v2`) enables this as a near-drop-in replacement.

#### Design

**New node labels and their key properties:**

| Label | Key properties |
|-------|---------------|
| `Standard` | `id` (namespaced: `"ISO27001:2022"`), `name`, `publisher`, `version`, `effective_date`, `last_updated_at`, `lang` |
| `Control` | `id` (`"{standard_id}:{code}"`), `standard_id`, `code`, `title`, `body`, `domain`, `sabsa_layer?`, `standard_version`, `lang`, `text_hash` (SHA-256 of code+title+body), `embedding_model_name`, `tags[]`, `embedding` |
| `Document` | `id`, `title`, `doc_type`, `policy_level?`, `source`, `version`, `lang`, `last_updated_at`, `tags[]` |
| `Chunk` | `id` (`"{doc_id}:{version}:{sequence}"`), `document_id`, `document_version`, `sequence`, `heading`, `body`, `section_ref`, `lang`, `embedding_model_name`, `tags[]`, `embedding` |
| `BusinessAttribute` | `id` (kebab-case), `name`, `domain`, `description` |
| `Organisation` | `id`, `name`, `type` (`"employer" \| "client" \| "regulatory-body" \| "standards-body"`), `description`, `last_scope_updated_at` |
| `Jurisdiction` | `code` (primary key, ISO 3166-1 alpha-2 or defined sectoral enum), `name`, `type` (`"geographic" \| "sectoral"`), `notes` |

**New vector indexes:**
- `ctrl_embedding_idx ON :Control(embedding)` — cosine, 384-dim, capacity from `ctrl_index_capacity` setting
- `chunk_embedding_idx ON :Chunk(embedding)` — cosine, 384-dim, capacity from `chunk_index_capacity` setting
- `mem_embedding_idx` capacity bumped to 5000 (folds in WP-019)

**New `Settings` fields** in `memory_service/config.py`: `ctrl_index_capacity: int = 5000`, `chunk_index_capacity: int = 10000`, `memory_index_capacity: int = 5000`

**Post-creation validation:** after creating each vector index, read back `SHOW INDEX INFO` and assert label and property match expectations. Generalise `get_existing_index_dimension()` into `validate_vector_index(session, index_name, expected_label, expected_property)` called for each index. Fail loudly on mismatch.

**New script: `scripts/init_cybersec_schema.py`** — idempotent, separate from `init_schema.py` so deployments without the knowledge layer never run it. Creates uniqueness constraints for all new node types, creates vector indexes, validates them.

**New script: `scripts/migrate_embeddings.py`** — re-embeds all nodes in all three indexes after model switch. Idempotent: skips nodes where `embedding_model_name` already matches the current `EMBEDDING_MODEL` setting. Run once after switching to the multilingual model.

**New `memory_service/cybersec_schemas.py`** — defines `SABSA_LAYERS` and `CONTROL_DOMAINS` as validated enum sets shared by routes and ETL validation. Normalises to lowercase on write.

**Extend `NodeLabel` enum** in `memory_service/main.py` with `Standard`, `Control`, `Document`, `Chunk`, `BusinessAttribute`, `Organisation`, `Jurisdiction`.

**Update `dump_db.py` / `restore_db.py`** edge-type allowlist to include: `HAS_CONTROL`, `MAPPED_TO`, `SUPPORTS`, `HAS_CHUNK`, `IMPLEMENTS`, `ADDRESSES`, `OWNED_BY`, `APPLIES_IN`, `OPERATES_IN`, `ABOUT_CONTROL`, `CITES_DOC`.

#### Files

New: `scripts/init_cybersec_schema.py`, `memory_service/cybersec_schemas.py`, `scripts/migrate_embeddings.py`
Modified: `memory_service/config.py`, `memory_service/main.py`, `scripts/dump_db.py`, `scripts/restore_db.py`

#### Definition of Success

- [ ] `init_cybersec_schema.py` runs idempotently; creates all constraints and indexes; validates label/property after creation
- [ ] `ctrl_embedding_idx` and `chunk_embedding_idx` exist with correct label and dimension
- [ ] `mem_embedding_idx` capacity is 5000
- [ ] `NodeLabel` enum includes all 7 new labels
- [ ] `dump_db.py` / `restore_db.py` include all new edge types in their allowlists
- [ ] `migrate_embeddings.py` re-embeds all nodes with stale `embedding_model_name`; skips up-to-date nodes; idempotent
- [ ] Integration test: run schema init twice; assert no errors and no duplicate constraints/indexes
- [ ] Integration test: existing `POST /memory/search` returns zero knowledge-layer nodes (separation baseline)

---

### WP-070 — Cybersecurity knowledge layer: standards & document write API

#### Motivation

The knowledge layer needs a write path to ingest standards, controls, cross-framework mappings, documents, and chunks. Keeping it in a dedicated `cybersec_repo.py` + `cybersec_routes.py` avoids touching the 1341-line `memory_repo.py` and makes the separation tangible in code.

#### Design

**New `memory_service/cybersec_repo.py`** — all Cypher for the knowledge layer write path.

**New `memory_service/cybersec_routes.py`** — FastAPI router, registered via `app.include_router(cybersec_router)` in `main.py`.

**Write endpoints:**

| Endpoint | Action |
|----------|--------|
| `POST /knowledge/standard` | Upsert Standard; creates optional `APPLIES_IN` edges to Jurisdictions |
| `POST /knowledge/control` | Upsert Control; creates `HAS_CONTROL`, optional `ADDRESSES`, optional `APPLIES_IN` edges |
| `POST /knowledge/control/map` | Create `MAPPED_TO` edge (MERGE'd both directions in one transaction) |
| `POST /knowledge/document` | Upsert Document; creates optional `IMPLEMENTS`, `OWNED_BY` edges |
| `POST /knowledge/chunk` | Upsert Chunk; creates `HAS_CHUNK` edge |
| `POST /knowledge/chunk/supports` | Create `SUPPORTS {confidence, raw_score, status}` edge |
| `POST /knowledge/attribute` | Upsert BusinessAttribute |
| `POST /knowledge/organisation` | Upsert Organisation; creates `OPERATES_IN` edges |
| `POST /knowledge/jurisdiction` | Upsert Jurisdiction (primary key is `code`, not `id`) |
| `GET /knowledge/applicable?org_id=...` | Return Standards/Controls applicable to an org via jurisdiction intersection |

**Idempotency:** Control write uses `MERGE ON CREATE SET ... ON MATCH SET` pattern. Overwrite embedding in `ON MATCH` only if `text_hash` has changed. When a Control's text changes, DETACH all existing `auto-inferred` SUPPORTS edges and mark owning Documents for re-ingestion.

**Validation:** Jurisdiction lookups use `MERGE (j:Jurisdiction {code: $code})` — never accept free-text names as primary keys. `CITES_DOC` references validated for Document existence; return HTTP 400 if missing.

**Anchor Memories:** On `POST /knowledge/standard` upsert, write a `Memory` node (type=`insight`, importance=3, tags=`["cybersec", "knowledge-anchor"]`) with fact describing the framework and how to query it. This is the discovery mechanism for agents that only call `memory_search`.

#### Files

New: `memory_service/cybersec_repo.py`, `memory_service/cybersec_routes.py`
Modified: `memory_service/main.py`

#### Definition of Success

- [ ] All 10 write endpoints operational; Pydantic request models defined
- [ ] Upsert idempotency: posting the same Standard/Control twice does not create duplicate nodes
- [ ] `text_hash` comparison on Control update: embedding only re-computed when text changes
- [ ] On Control text change: existing `auto-inferred` SUPPORTS edges are detached
- [ ] `MAPPED_TO` MERGE'd bidirectionally in one transaction
- [ ] Anchor Memory created on standard upsert; searchable via `POST /memory/search`
- [ ] `GET /knowledge/applicable` returns jurisdiction-intersection result
- [ ] HTTP 400 returned for `CITES_DOC` referencing nonexistent Document
- [ ] Integration tests: upsert standard + controls + document + org; verify graph structure via Cypher

---

### WP-071 — Cybersecurity knowledge layer: search API

#### Motivation

Reference data needs a search path separate from episodic memory. Knowledge search should not increment recall_count or interact with the decay/reinforcement model — it is a lookup, not a recall signal.

#### Design

**New read endpoints (added to `cybersec_routes.py`):**

| Endpoint | Description |
|----------|-------------|
| `POST /knowledge/search/controls` | Vector search over `ctrl_embedding_idx` |
| `POST /knowledge/search/chunks` | Vector search over `chunk_embedding_idx` |
| `GET /knowledge/standards` | List all Standards with metadata |
| `GET /knowledge/documents` | List all Documents; filterable by org_id |
| `GET /knowledge/incomplete-jurisdictions` | Lists Standards and Controls with no `APPLIES_IN` edges |

**`search_controls` request:** `{query, limit, standard_ids?, tags?, jurisdiction_codes?, applicable_to_org_id?, lang?, include_universal?}`
- `lang` filter is optional; omitting it enables cross-lingual search (multilingual model bridges languages natively)
- If `applicable_to_org_id` is set, restrict using `MATCH` (not `OPTIONAL MATCH`) against org's `OPERATES_IN` jurisdictions — standards with no `APPLIES_IN` edges are excluded unless `include_universal: true`
- Response: `{id, code, title, body, standard_id, lang, tags, distance}`

**`search_chunks` request:** `{query, limit, document_ids?, tags?, org_id?, cross_org?, org_ids?}`
- Without `org_id`: returns only public-scope Chunks (Documents with no `OWNED_BY` edge)
- With `org_id`: returns public + org-private Chunks
- `cross_org: true` requires non-empty `org_ids: List[str]` to be explicit; does not default to all-orgs
- Response: `{id, heading, body, document_id, sequence, tags, distance, control_ids?, org_id?}`

No `recall_count` increment — reference data does not participate in the decay model.

#### Files

Modified: `memory_service/cybersec_repo.py`, `memory_service/cybersec_routes.py`

#### Definition of Success

- [ ] `POST /knowledge/search/controls` returns `Control` nodes, never `Memory` nodes
- [ ] `POST /knowledge/search/chunks` returns `Chunk` nodes, never `Memory` nodes
- [ ] `lang` filter narrows results; omitting it returns cross-lingual results
- [ ] `applicable_to_org_id` filter uses `MATCH` (not OPTIONAL MATCH); excludes standards with no `APPLIES_IN` unless `include_universal: true`
- [ ] Org-private Chunks only returned when `org_id` provided; public Chunks returned without `org_id`
- [ ] `GET /knowledge/incomplete-jurisdictions` returns Standards/Controls with no `APPLIES_IN` edges
- [ ] `recall_count` not incremented on knowledge search calls
- [ ] Integration test: search controls returns only controls; search chunks returns only chunks; no cross-contamination

---

### WP-072 — Cybersecurity knowledge layer: cross-layer Memory edges

#### Motivation

Compliance evidence and gap findings naturally arise as Memory nodes (conversations, observations, meeting notes). These should be linkable to specific Controls so gap analysis can surface them. `ABOUT_CONTROL` with `relationship_type` distinguishes "I know about this control" (context), "this memory proves the control is in place" (evidence), and "this memory records a finding against this control" (gap). `org_id` on the edge is the isolation boundary for cross-org queries.

#### Design

**Extend `AddMemoryRequest` and `UpdateMemoryRequest`** in `main.py`:
- `control_ids: List[str] = []`
- `doc_ids: List[str] = []`
- `control_relationship_type: Optional[str] = None` — `"context" | "evidence" | "gap"`
- `org_id: Optional[str] = None` — stored on `ABOUT_CONTROL.org_id`; defaults to agent's org

**`memory_repo.py` additions** (only personal-layer file touched):
- Step 8 in `add_memory`: MERGE `ABOUT_CONTROL {relationship_type, org_id}` edges for explicitly provided `control_ids`
- Step 9 in `add_memory`: validate Document existence, then MERGE `CITES_DOC` edges; return HTTP 400 if Document not found

**Critical: add `ABOUT_CONTROL` and `CITES_DOC` to `merge_memory` rewiring list** — same pattern as existing `ABOUT`/`IN_STRAND` rewiring. Without this, merging two memories orphans cross-layer edges on the tombstone node. This is the highest-severity correctness requirement.

**Extend `update_memory`** to replace `control_ids`/`doc_ids` (delete existing edges, recreate — same pattern as `person_ids` replacement).

**Extend `MemoryHit` response:** add optional `controls: List[dict]` and `documents: List[dict]` fields populated via `OPTIONAL MATCH` in `_SEARCH_QUERY_TEMPLATE`. Non-breaking.

**Extend MCP tools** `memory_add` and `memory_update` with `control_ids`, `doc_ids`, `control_relationship_type`, `org_id` parameters.

**Decay/maintenance isolation:** `ABOUT_CONTROL` and `CITES_DOC` edges are never touched by decay, short-rest, or long-rest passes (those passes pattern-match `RELATED_TO|LEADS_TO` by name).

#### Files

Modified: `memory_service/main.py`, `memory_service/memory_repo.py`, `mcp_server/server.py`

#### Definition of Success

- [ ] `POST /memory` accepts `control_ids`, `doc_ids`, `control_relationship_type`, `org_id`
- [ ] `ABOUT_CONTROL {relationship_type, org_id}` edges created correctly; `org_id` stored on edge
- [ ] `CITES_DOC` edges created; HTTP 400 returned if Document does not exist
- [ ] `merge_memory` correctly rewires `ABOUT_CONTROL` and `CITES_DOC` to target node (not orphaned on source tombstone)
- [ ] `update_memory` replaces `control_ids`/`doc_ids` rather than appending
- [ ] `MemoryHit` response includes `controls` and `documents` fields when edges exist
- [ ] MCP `memory_add` and `memory_update` tools expose new parameters
- [ ] Integration test: add memory with `control_ids`; merge into another memory; verify edges on target, none on source
- [ ] Integration test: `CITES_DOC` for missing Document returns HTTP 400

---

### WP-073 — Document ingestion pipeline: PDF and Markdown → Chunk nodes

#### Motivation

Internal policies and runbooks are not delivered as structured YAML catalogues — they are PDFs and Markdown files. A chunking pipeline is needed to break them into Chunk nodes with embeddings, then optionally link them to matching Controls.

#### Design

**New `scripts/ingest_document.py`** — reads PDF (pdfplumber) or Markdown files.

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
- [ ] `HAS_NEXT` edges link consecutive chunks within a document
- [ ] `chunk_review_mode=true` (default): no `SUPPORTS` edges created; chunks only
- [ ] `chunk_review_mode=false`: `SUPPORTS` edges created with `status="auto-inferred"` for distance < threshold
- [ ] `--link-controls` flag triggers SUPPORTS inference independently of chunking run
- [ ] Re-ingesting an updated document with changed Control text reverts affected `SUPPORTS` edges to `auto-inferred`
- [ ] Integration test: ingest a sample Markdown file; verify Chunk nodes and `HAS_CHUNK`/`HAS_NEXT` edges; verify no `SUPPORTS` edges in review mode

---

### WP-074 — Cybersecurity knowledge layer: CLI, MCP tools, and ETL

#### Motivation

The knowledge layer API needs to be accessible from the same CLI and MCP surfaces as the personal memory layer. ETL scripts are needed for bulk framework ingestion from structured YAML catalogues. MCP tools must be narrow and single-purpose with LLM-directed docstrings to be useful to agents.

#### Design

**New MCP tools in `mcp_server/server.py`** (≤12 initial tools):

| Tool | Docstring purpose |
|------|-------------------|
| `knowledge_list_applicable_standards(org_id)` | "Returns standards applicable to the specified organisation based on its OPERATES_IN jurisdictions. Call this first to scope any compliance query." |
| `knowledge_search_controls(query, org_id, domain?, limit)` | "Vector search for controls applicable to org_id. Restricts to org's jurisdiction scope automatically." |
| `knowledge_search_chunks(query, org_id, limit)` | "Searches document sections owned by org_id's organisation. Returns evidence and policy text." |
| `knowledge_list_standards()` | "Lists all loaded standards with jurisdiction scope." |
| `knowledge_list_documents(org_id)` | "Lists documents owned by this organisation." |
| `knowledge_add_standard`, `knowledge_add_control`, `knowledge_map_controls`, `knowledge_add_organisation`, `knowledge_add_jurisdiction` | Write tools mirroring the HTTP API |
| `knowledge_review_supports(control_id, limit)` | "Shows auto-inferred Chunk→Control links for human review. Returns chunk text + control text side-by-side." |
| `knowledge_confirm_supports(chunk_id, control_id)` / `knowledge_reject_supports(chunk_id, control_id)` | Human validation of provisional SUPPORTS edges |

**New CLI commands** in `memory_client/cli.py` mirror MCP tools via Typer. CLI also includes `memory ingest-framework` and `memory ingest-document` as top-level commands.

**Extend `memory_client/client.py`** with HTTP client methods for `/knowledge/` endpoints.

**New `scripts/ingest_framework.py`** — bulk ingestion from structured YAML/JSON control catalogue. Reads standards, controls, and cross-mappings; calls API in dependency order (Standard → Controls → MAPPED_TO edges). Reproducible and auditable.

**Seed data files:**
- `scripts/data/nist_csf_controls.yaml` — NIST CSF controls
- `scripts/data/iso27001_controls.yaml` — ISO 27001:2022 controls (no `APPLIES_IN` edges — universal)
- `scripts/data/business_attributes.yaml` — seed catalogue (confidentiality, integrity, availability, accountability, auditability, non-repudiation, etc.)
- `scripts/data/jurisdictions.yaml` — seed list (EU, DE, UK, US, critical-infrastructure, healthcare, payments, financial-services, energy, transport)

YAML schema includes `lang` field. A standard node's default `lang` applies to all controls unless overridden per-control. NIS2 → `"en"`, KRITIS-DG → `"de"`.

**New `docs/CYBERSEC_LAYER.md`** — separation invariants, node/edge reference, operational procedures (how to ingest a new framework, re-ingest after control text updates).

#### Files

New: `scripts/ingest_framework.py`, `scripts/data/nist_csf_controls.yaml`, `scripts/data/iso27001_controls.yaml`, `scripts/data/business_attributes.yaml`, `scripts/data/jurisdictions.yaml`, `docs/CYBERSEC_LAYER.md`
Modified: `mcp_server/server.py`, `memory_client/cli.py`, `memory_client/client.py`

#### Definition of Success

- [ ] All MCP tools defined with LLM-directed docstrings; each tool has exactly one job
- [ ] CLI commands mirror MCP tools; `memory ingest-framework` and `memory ingest-document` operational
- [ ] `ingest_framework.py` ingests NIST CSF and ISO 27001 YAML files successfully against live service
- [ ] YAML schema validates `lang` field; default propagates from Standard to Controls
- [ ] `knowledge_review_supports` returns chunk text + control text side-by-side
- [ ] `knowledge_confirm_supports` / `knowledge_reject_supports` set `status` correctly on the edge
- [ ] `docs/CYBERSEC_LAYER.md` documents separation invariants and operational procedures
- [ ] Integration test: ingest ISO 27001 via `ingest_framework.py`; verify Standard + Control nodes; verify anchor Memory created

---

### WP-075 — Cybersecurity knowledge layer: SABSA bidirectional traceability

#### Motivation

SABSA requires two-way traceability: every control must be traceable upward to the business attributes it serves, and downward to the evidence that proves it is implemented. Gap analysis must distinguish between declared intent (IMPLEMENTS) and inferred evidence (SUPPORTS) — they are different claims. The three-way reconciliation exposes the asymmetry that is otherwise hidden.

#### Design

**New read endpoints (added to `cybersec_routes.py`):**

`GET /knowledge/control/{id}/trace-up`
- Which Standard owns it (`HAS_CONTROL`)?
- Which BusinessAttributes does it address (`ADDRESSES`)?
- Which Controls map to it across frameworks (`MAPPED_TO`)?
- Response: `{control, standard, attributes[], mapped_controls[]}`

`GET /knowledge/control/{id}/trace-down`
- Which Documents declare intent to implement it (`IMPLEMENTS`)?
- Which Chunks contain supporting content (`SUPPORTS`, sorted by confidence)?
- Which Memory nodes are linked as evidence, context, or gap findings (`ABOUT_CONTROL` by `relationship_type`)?
- Response: `{control, documents[], chunks[], evidence[], context[], gaps[]}`
- Parameters: `depth: int = 1`, `limit: int = 20`, `include_archived: bool = false`

`GET /knowledge/attribute/{attribute_id}/coverage`
- All Controls that `ADDRESSES` this attribute, grouped by Standard
- For each: count of Documents `IMPLEMENTS` it, count of Chunks `SUPPORTS` it, count of Memory nodes as evidence vs. gap findings
- Response: structured coverage report for compliance dashboards

`GET /knowledge/gap-analysis?org_id=...&framework=...&domain=...&attribute_id=...&include_universal=false`
- Controls in scope: `MATCH` (not OPTIONAL MATCH) against `APPLIES_IN` ∩ org's `OPERATES_IN`; `include_universal=false` excludes standards with no `APPLIES_IN` edges by default
- Without `org_id`: generic mode — all loaded frameworks, no jurisdiction filter
- Three-way reconciliation: `implemented_and_supported`, `implemented_not_supported` (declared intent, no chunk evidence), `supported_not_implemented` (chunk evidence, no formal declaration)
- Evidence layer: `ABOUT_CONTROL(relationship_type="evidence", org_id=$org_id)` Memory nodes
- Gap layer: `ABOUT_CONTROL(relationship_type="gap", org_id=$org_id)` Memory nodes
- Response includes: `scope_snapshot_at`, `mode: "generic" | "org-scoped"`, warning if org's `last_scope_updated_at` is newer than `scope_snapshot_at`
- Response: `{org_id, applicable_standards[], total_controls, implemented_and_supported[], implemented_not_supported[], supported_not_implemented[], evidenced[], gap_findings[], evidence_gaps[]}`

**`MAPPED_TO` does not carry jurisdiction.** Gap analysis Cypher must not inherit applicability through `MAPPED_TO` chains.

**New MCP tools:** `knowledge_trace_up`, `knowledge_trace_down`, `knowledge_attribute_coverage`, `knowledge_gap_analysis`. All tools work in both modes (omit `org_id` for generic; provide `org_id` for org-scoped). Tool docstrings explicitly describe both modes.

All endpoints are read-only Cypher traversals in `cybersec_repo.py`. No new write operations.

#### Files

Modified: `memory_service/cybersec_repo.py`, `memory_service/cybersec_routes.py`, `mcp_server/server.py`

#### Definition of Success

- [ ] `trace-up` returns correct standard, attributes, and mapped controls for a seeded control
- [ ] `trace-down` returns documents, chunks, and memories grouped by `relationship_type`; respects `limit` and `depth`
- [ ] `include_archived=true` surfaces archived Memory nodes in evidence/gap lists
- [ ] `attribute/coverage` returns correct counts grouped by Standard
- [ ] `gap-analysis` without `org_id`: returns all loaded controls (generic mode)
- [ ] `gap-analysis` with `org_id`: scoped to org's `OPERATES_IN` ∩ `APPLIES_IN`; `include_universal=false` excludes unscoped standards
- [ ] Three-way reconciliation categories mutually exclusive and exhaustive over applicable controls
- [ ] `MAPPED_TO` traversal does NOT inherit jurisdiction scope
- [ ] Dual-org test: org A (EU) and org B (US) + EU-only standard → gap-analysis for org A returns EU controls; for org B returns zero
- [ ] MCP tools `knowledge_trace_up`, `knowledge_trace_down`, `knowledge_attribute_coverage`, `knowledge_gap_analysis` operational

---

### WP-076 — Cybersecurity knowledge layer: integration and separation tests

#### Motivation

The separation guarantee is an architectural invariant, not a convention. It must be enforced by a test that runs on every test session — not just as part of a WP-076 suite. Any future regression (e.g. a new query accidentally scanning all labels) is caught immediately.

#### Design

**Test files:**

| File | Coverage |
|------|----------|
| `tests/test_wp069_cybersec_schema.py` | Schema smoke: indexes and constraints exist after `init_cybersec_schema.py` |
| `tests/test_wp070_cybersec_write.py` | Upsert Standard, Control, Document, Chunk; confirm edges; idempotency |
| `tests/test_wp071_cybersec_search.py` | Vector search returns correct nodes; anchor Memory written on standard upsert |
| `tests/test_wp072_cross_layer.py` | `ABOUT_CONTROL`/`CITES_DOC` on add/update; `relationship_type` and `org_id` stored; confirmed in MemoryHit; `merge_memory` rewires correctly; `CITES_DOC` for missing Document returns HTTP 400 |
| `tests/test_wp075_traceability.py` | trace-up/trace-down/coverage/gap-analysis; dual-org jurisdiction test; generic mode; three-way reconciliation; `include_archived=true` |
| `tests/test_wp076_separation.py` | **autouse conftest fixture**: seed 20+ Controls + 50+ Chunks; call `POST /memory/search`; assert zero knowledge-layer nodes. Seed Memories; call `POST /knowledge/search/controls`; assert zero Memory nodes. Run `long_rest`; assert zero `SUPPORTS.confidence` or `ABOUT_CONTROL` properties modified. |

**Prerequisite:** WP-024 (multi-node cleanup helper) must be resolved or folded into WP-076 before these tests are written. Knowledge-layer tests use test-scoped ID prefixes (`test-{uuid}-`) to avoid cross-test interference on shared `MERGE`'d reference nodes.

**Shared conftest fixtures:**
- `cybersec_seeded_db` — Standard + controls + chunks with `test-{uuid}-` prefix IDs; teardown cleans up
- `dual_org_seeded_db` — two orgs, two jurisdictions, jurisdiction-scoped standards for separation validation

**The separation test is an autouse conftest fixture.** It runs on every test session — any future regression is caught immediately.

#### Files

New: `tests/test_wp069_cybersec_schema.py`, `tests/test_wp070_cybersec_write.py`, `tests/test_wp071_cybersec_search.py`, `tests/test_wp072_cross_layer.py`, `tests/test_wp075_traceability.py`, `tests/test_wp076_separation.py`
Modified: `tests/conftest.py`

#### Definition of Success

- [ ] All six test files pass against live stack
- [ ] `test_wp076_separation.py` is an autouse conftest fixture — runs on every test session
- [ ] Separation test: `POST /memory/search` returns zero Control/Chunk/Standard/Document nodes
- [ ] Separation test: `POST /knowledge/search/controls` returns zero Memory nodes
- [ ] Separation test: `long_rest` run does not modify `SUPPORTS.confidence` or `ABOUT_CONTROL` edges
- [ ] Dual-org jurisdiction test: gap-analysis for org A (EU) returns EU controls; for org B (US) returns zero for EU-only standard
- [ ] Generic mode test: gap-analysis without `org_id` returns all loaded controls
- [ ] `merge_memory` rewiring test: `ABOUT_CONTROL`/`CITES_DOC` edges on source node correctly appear on target node after merge
