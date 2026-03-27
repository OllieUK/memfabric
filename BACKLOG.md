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
| 1 | R1 | WP-038 | Memory lifecycle operations — update, merge, archive | H | H | 1.0 | WP-037 ✅ | First-class memory manipulation: PATCH, merge, archive, restore. Becoming essential as duplicate and stale memories accumulate. Required before WP-047. See detail below. |
| 2 | R1 | WP-047 | Near-duplicate detection for memory review | H | M | 1.5 | WP-038 | Surface semantically similar memories (cosine similarity above configurable threshold) so they can be reviewed and merged via WP-038 merge endpoint. Feeds into short-rest/long-rest cleanup loop. See detail below. |
| 3 | R1 | WP-039 | Ephemeral test-memory handling — TTL, tagging, cleanup | H | M | 1.5 | WP-038 | Prevent test artefacts polluting live context. See detail below. |
| 4 | R1 | WP-012 | Pin dependency versions in requirements.txt | M | L | 2.0 | — | Use `>=x,<y` bounds. Stability/reproducibility prerequisite — do before declaring a stable first release. |
| 5 | R1 | WP-013 | Pin Docker image tags (no `latest`) | M | L | 2.0 | WP-012 | Replace `latest` tags with specific versions. Do after WP-012. |
| 6 | R1 | WP-045 | Make local startup deterministic offline | M | L | 2.0 | — | Fix misleading Memgraph healthcheck and add a documented/scripted API startup path that works with cached embeddings offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`). Prevent false “memory service unreachable” failures at session start. |
| 7 | R1 | WP-034 | Add version/build hash to `/health` response | M | L | 2.0 | — | Detect stale or mismatched service instances at mandatory session startup. Promoted from low value because startup operability is part of the core working loop. Batch with WP-035/036. |
| 8 | R2 | WP-006 | Wire `GET /memory/graph` | M | M | 1.0 | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 9 | R2 | WP-035 | Return `strand_ids` in `add-memory` API response | L | L | 1.0 | — | Reduce friction when chaining related memories. Batch with WP-034/036. |
| 10 | R2 | WP-036 | Document `### Relevant to today` suppression in COMPANION.md | L | L | 1.0 | — | Avoid companion confusion on small DBs. Batch with WP-034/035. Not covered by the three-tier memory model addition (2026-03-22) — still needed for wake-up output behaviour on sparse graphs. |
| 11 | R2 | WP-043 | Inline effective_strength sort in search | L | L | 1.0 | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as the current proxy. |
| 12 | R2 | WP-025 | Extract shared CLI error handler | L | L | 1.0 | — | 4+ identical `except httpx.*` blocks in `cli.py`. Extract once. |
| 13 | R2 | WP-026 | `MemoryType` mirror in `memory_client` | L | L | 1.0 | WP-007 ✅ | Mirror enum so callers get IDE completion without cross-package import. |
| 14 | R2 | WP-023 | Extract `get_session` context manager for 503 handling | L | L | 1.0 | WP-029 ✅ | `try/with driver.session()/except ServiceUnavailable→503` copy-pasted across all endpoints. Do after WP-029 (adds more endpoints). |
| 15 | R2 | WP-020 | UNWIND for person/strand/related_ids writes | L | L | 1.0 | WP-004 ✅ | Replace per-item `session.run()` loops in `add_memory` with UNWIND queries. Add `related_ids` max-length cap (e.g. 20). |
| 16 | R2 | WP-021 | Non-blocking embedding in async endpoints | L | L | 1.0 | WP-004 ✅, WP-005 ✅ | `get_embedding()` blocks the event loop. Wrap with `run_in_executor` when concurrent usage becomes a problem. |
| 17 | R2 | WP-024 | `cleanup_nodes` support multiple ids per label | L | L | 1.0 | — | Change `extra_ids: dict[str, str]` to `dict[str, str \| list[str]]` for multi-node cleanup in tests. |
| 18 | R2 | WP-017 | Embedding cache eviction / size cap | L | L | 1.0 | WP-003 ✅ | `EMBEDDING_CACHE_DIR` grows without bound. Add LRU eviction or max-entry cap. |
| 19 | R2 | WP-019 | Expose vector index `capacity` as config | L | L | 1.0 | WP-016 ✅ | `capacity: 1000` hardcoded in `init_schema.py`. Add to `Settings`. |
| 20 | R2 | WP-014 | Docker resource limits | L | L | 1.0 | — | Add `mem_limit`/`cpus` to docker-compose. |
| 21 | R2 | WP-049 | Wake-up companion + conversant anchoring | H | M | 1.5 | — | Wake-up should always surface anchor memories for the Companion (Mara) identity and for the specific person the calling agent is conversing with, in addition to prominent + topic-relevant memories. See detail below. |
| 22 | R2 | WP-050 | Domain knowledge store | H | H | 1.0 | WP-041 | Store subject-area knowledge (e.g. cybersecurity) as a distinct layer from episodic memory. The fabric must anchor pointers to domain knowledge stores so agents can discover and retrieve them. See detail below. |
| 23 | R2 | WP-041 | Subject/object schema on Memory nodes | H | H | 1.0 | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| 24 | R3 | WP-042 | Self-contained `memory_client` packaging | L | L | 1.0 | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. Re-scored from medium value because it is packaging polish rather than core product capability. |
| 25 | R3 | WP-008 | LLMClient abstraction | M | M | 1.0 | WP-007 ✅ | `LLMClient.ask(system, prompt, model)` wrappers for Claude/OpenAI/Ollama. |
| 26 | R3 | WP-009 | Headless agent framework | M | H | 0.67 | WP-008 | `BaseAgent` using `memory_client` + `LLMClient`; scheduled/event-driven tasks. |
| 27 | R3 | WP-010 | Remote/mobile access | L | H | 0.33 | WP-009 | Tailscale/VPS hosting + TLS + API key auth. |
| 28 | R3 | WP-011 | Custom graph-cloud UI | L | H | 0.33 | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |

> **Note:** old backlog items once grouped under `v2+` are now part of the same continuous backlog with `Release` assignments.
> Old v2+ WP-034 and WP-035 were renumbered WP-041 and WP-042 to avoid collision with the current WP-034/035/036 items.

---

## Detail Specs

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
