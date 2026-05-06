# Graph-Memory Fabric – Feature Backlog

> **Value:** H = High / M = Medium / L = Low
> **Effort:** H = High / M = Medium / L = Low
> **Priority score:** `Value / Effort` using `H=5`, `M=3`, `L=1`
> Completed WPs → [docs/CHANGELOG.md](docs/CHANGELOG.md)

---

## Currently In Progress

| ID | Title | Started |
|----|-------|---------|
| _none_ | | |

---

## Prioritised Backlog

> Items ordered as a dependency-safe executable sequence informed by `Priority score`.
> Higher score is better, but `Depends on` always wins for execution order.
> When a lower-score prerequisite unlocks a stronger branch, keep the prerequisite immediately ahead of that branch.
> Within an equal-score block, preserve the existing order unless a newly identified dependency requires a move.
> Add new work packages at the bottom of their equal-score block unless dependency constraints require otherwise.
> `Release` is planning metadata only. The backlog stays continuous and contiguous; release numbers indicate target package, not a separate queue.

| Order | Release | ID | Title | Value | Effort | Priority score | Depends on | Notes |
|-------|---------|-----|-------|-------|--------|----------------|------------|-------|
| 1 | R2 | WP-113 | Security architecture layer: SABSA, precepts, and business attributes | H | H | 1.0 | WP-107 ✅ | Activate the strategic threat-to-business path from ADR-002. Three components: (1) Seed SABSA Business Attribute Profile as `BusinessAttribute` nodes (customer trust, regulatory standing, operational continuity, competitive advantage, brand reputation, etc.) — SABSA is the primary driver of this layer. (2) Seed universal `Precept` nodes derived from cross-framework convergence (the obligations that ISO 27001, NIST CSF, COBIT, and SP 800-53 all independently demand). Wire `REQUIRES` from Norms, `ADDRESSES` from Controls, `FULFILS` from Precepts to BusinessAttributes. (3) Consider ingestion of additional architectural frameworks that feed the precept model: SABSA conceptual layer, C2M2 capability dimensions, Zero Trust (NIST SP 800-207), CIS Controls v8, TOGAF security architecture domain. Unlocks the board-level query: "Which business attributes face the most active threats?" via Threat → JEOPARDISES → Precept → FULFILS → BusinessAttribute. |
| 3 | R2 | WP-085 | **Analytics Phase — Sprint 1:** graph-vs-vector diagnostics, cluster discovery, bridge detection (WP-057 + WP-058 + WP-059) | M | M | 1.0 | WP-029 ✅ | Three tightly related graph-analytics capabilities best built together as a shared diagnostic layer: (1) graph-vs-vector agreement — compare each memory's nearest embedding neighbours with its actual `RELATED_TO`/`LEADS_TO` neighbourhood to surface where the graph lags or overlinks semantic reality; (2) latent cluster discovery — cluster embeddings offline to discover emergent themes and compare them with explicit `Strand` assignments to identify overly broad, missing, or mislabeled strands; (3) bridge-memory detection — identify memories that span otherwise separate embedding clusters or graph communities, surfacing high-leverage cross-domain connectors. All three share the same embedding-space traversal infrastructure and diagnostic output pattern. |
| 3 | R2 | WP-006 | Wire `GET /memory/graph` | M | M | 1.0 | WP-028 ✅, WP-029 ✅ | Filtered subgraph export: project/agent/tag/since/until params; returns `{nodes, edges}`. |
| 4 | R2 | WP-116 | Migrate episodic Memory embeddings to `paraphrase-multilingual-MiniLM-L12-v2` | M | M | 1.0 | WP-094 ✅ | WP-094 gave the knowledge layer its own `KNOWLEDGE_EMBEDDING_MODEL` (`paraphrase-multilingual-MiniLM-L12-v2`) but deliberately left episodic Memory nodes on `all-MiniLM-L6-v2`. Migrating Memory nodes to the same multilingual model enables cross-lingual episodic search, aligns the two embedding spaces (closer cos-sim between memory and knowledge layer nodes), and removes a class of subtle retrieval errors when searching in non-English. Migration requires: (1) Drop and recreate `mem_embedding_idx` at the new model's dimension (768 vs 384 for MiniLM-L6-v2; confirm exact dim for paraphrase-multilingual). (2) Re-embed all Memory nodes in batches via `scripts/migrate_embeddings.py` (already exists for the knowledge layer migration). (3) Update `EMBEDDING_MODEL` default in `.env.example`. (4) Run long-rest after migration to rebuild RELATED_TO edges against the new vector space. See detail below. |
| 5 | R2 | WP-128 | Tiered search MCP tool (compact index + selective detail fetch) | M | M | 1.0 | ✅ WP-127 | Add GET /memory/search/index (compact result set: id, fact excerpt, importance, strength) and POST /memory/batch (full MemoryResponse for selected IDs). Update MCP tool descriptions to document the two-step scan-then-fetch pattern. Reduces token cost on every search that doesn't need full detail. See detail below. |
| 6 | R2 | WP-125 | Weighted hop-traversal for wake-up anchor sections | M | M | 1.0 | WP-049 ✅ | Extend `wake_up()` companion_anchors and conversant_anchors beyond direct `ABOUT` edges. After retrieving direct ABOUT-linked memories, expand one additional hop via `RELATED_TO` edges, scoring candidates as `importance × strength × edge_weight^hop`. Direct ABOUT hits (hop=0) score at full value; 1-hop neighbours are weighted by the edge's Hebbian activation weight, so only strongly co-activated memories survive. Config: `WAKE_UP_COMPANION_ANCHOR_HOPS` (default 1), `WAKE_UP_CONVERSANT_ANCHOR_HOPS` (default 2). Rationale: conversant section benefits from deeper context about the person (e.g. project memory RELATED_TO a habit memory ABOUT Oliver) while companion (agent identity) stays shallower. Cross-section dedup already in place; hop-scored ordering integrates naturally into the existing priority chain. Marabot equivalent: `wakeup_max_hops` / `_query_person` — but implemented here via direct Cypher rather than a list-position proxy. |
| 7 | R2 | WP-139 | CLI and API shared-infrastructure DRY pass | M | M | 1.0 | — | Supersedes WP-023, WP-025, WP-026, WP-020, WP-021. Bundles five individually-scoped cleanup WPs targeting the same infrastructure spine (`main.py`, `knowledge_routes.py`, `cli.py`, `memory_repo.add_memory`) into a single focused DRY pass. See detail below. |
| 8 | R2 | WP-137 | German-language CTI extraction support for BSI Lagebericht | M | M | 1.0 | WP-108 ✅ | The BSI IT-Sicherheitslage report is German-language; `extract_cti_threats.py` currently yields 0 threats because all `BEHAVIOR_INDICATORS` and `TECHNIQUE_KEYWORDS` are English. The `paraphrase-multilingual-MiniLM-L12-v2` embedding model already handles German natively, so embeddings and deduplication will work correctly once sentences are extracted — the gap is solely in the extraction gate. **Option analysis:** **(1) Extend keyword/verb lists (lowest effort):** Add German behaviour-verb equivalents to `BEHAVIOR_INDICATORS` (e.g. "verwendet", "eingesetzt", "ausgeführt", "verschlüsselt") and German keyword→ATT&CK mappings to `TECHNIQUE_KEYWORDS` (many terms are loanwords: "ransomware"→T1486, "phishing"→T1566 already work; add "anmeldedaten"→T1003, "seitwärtsbewegung"→T1021, etc.). Single-pass pipeline preserved. Brittle: misses conjugations and paraphrases; requires ongoing manual curation for each new German report. **(2) Offline pre-translation via `argostranslate` (clean separation):** Translate extracted PDF text from `de→en` before the existing pipeline runs it. `argostranslate` runs fully offline (~100 MB model). `extract_cti_threats.py` stays English-only; translation is a composable pre-processing flag (`--translate-from de`). Downside: translation quality affects extraction accuracy; adds model download to setup. **(3) spaCy German NER + verb extraction (more robust extraction gate):** Use `spaCy` with `de_core_news_sm` to extract sentences containing action verbs, replacing the hand-curated `BEHAVIOR_INDICATORS` list. Handles conjugations automatically. TECHNIQUE_KEYWORDS mapping still needs German terms, but the behaviour-indicator gate becomes language-agnostic. Higher setup cost; adds spaCy as a dependency. **(4) Language detection + routing (polyglot architecture):** Add `langdetect` or `lingua` to detect language per-page, then route through a language-specific extractor module. Makes the pipeline polyglot by design — future French/Dutch/Japanese reports require only a new extractor, not a fork of the main script. Best long-term architecture if more non-English reports are anticipated. **(5) Offline LLM extraction via Ollama (highest effort, most robust):** Run a local model (e.g. `mistral`, `llama3`) as a pre-processor that produces structured `{sentence, techniques[]}` JSON directly from each page. Handles language, paraphrase, and technique mapping in one pass. Consistent with the "no external LLM API calls" constraint. Highest setup cost; slowest at ingest time. **Recommended path:** Option 2 (argostranslate) for a quick win on the BSI report; Option 4 (language detection + routing) as the target architecture if additional non-English reports are added. Surfaced during live ingestion run (0 threats from BSI report — 364 German-language sentences extracted but none passed the English extraction gate). |
| 10 | R2 | WP-134 | BSI Lagebericht 2025 ingestion as threat intelligence document | M | M | 1.0 | ✅ WP-108, WP-113 | Ingest the BSI Lagebericht 2025 ("Die Lage der IT-Sicherheit in Deutschland 2025") as a ThreatReport document into the knowledge layer. The report is web-first (no single download PDF); primary URL: `https://medien.bsi.bund.de/lagebericht/`. Approach: (1) fetch the report's HTML pages via `ingest_document.py` or a custom web-scraping script, chunking by section; (2) create a `ThreatReport` document node and `Threat` nodes for named threat actor groups and attack categories mentioned; (3) wire `JEOPARDISES` edges from Threats to relevant Precept nodes (WP-113) and `MAPPED_TO_TECHNIQUE` edges to ATT&CK nodes where technique IDs are cited. The 8-page PDF handout (`/lagebericht/Lagebericht2025_Achtseiter.pdf`) can serve as a starting point for key statistics and threat categories before tackling full web ingestion. German language — multilingual embedding model handles this natively. |
| 11 | R2 | WP-114 | D3FEND defensive technique ingestion | M | M | 1.0 | WP-108 ✅ | Ingest MITRE D3FEND (~500 defensive techniques) from OWL/JSON-LD ontology. Create Framework nodes (level=defensive-technique) under a D3FEND root. Create `d3f:counters` edges as MITIGATES edges D3FEND → ATT&CK. Run embedding similarity to ISO/NIST/COBIT/SP800-53 for INFORMS edges (D3FEND vocabulary is defensive/technical — closer to SP 800-53 controls than to governance frameworks). D3FEND adds a second defensive pathway alongside M-Series for SOC-level traversal; primarily valuable once the threat intelligence model (WP-108) is operational. D3FEND also carries its own informative references to SP 800-53 and NIST CSF which may be used as an alternative to embedding similarity. |
| 12 | R2 | WP-140 | WP-049 code-review follow-ups | L | L | 1.0 | ✅ WP-049 | Supersedes WP-122, WP-123, WP-124. Bundles three deferred code-review items from WP-049 (endpoint ordering assertions, empty ABOUT-edge unit tests, `.env.example` docs for WAKE_UP limits) into one WP. See detail below. |
| 13 | R2 | WP-141 | Ingest script hygiene | L | L | 1.0 | ✅ WP-108, ✅ WP-073 | Supersedes WP-135, WP-136, WP-097. Bundles three small improvements to `scripts/` surfaced from WP-108 and WP-073 simplify reviews (shared `ApiSettings` base class, optional `embedding` field on `ThreatCreate`, H1 heading support in `chunk_markdown`). See detail below. |
| 14 | R2 | WP-042 | Self-contained `memory_client` packaging | L | L | 1.0 | WP-031 ✅ | Move `pyproject.toml` into `memory_client/` for independent install. Re-scored from medium value because it is packaging polish rather than core product capability. |
| 15 | R2 | WP-130 | Concept tags on Memory nodes | L | L | 1.0 | — | Add `concepts[]` array property alongside `tags[]` to capture epistemic role of a memory (gotcha, pattern, trade_off, decision_rationale, how_it_works, why_it_exists, what_changed, problem_solution, open_question). Enables queries like "all gotchas about Memgraph" independently of subject tags. See detail below. |
| 16 | R2 | WP-090 | Handle non-ServiceUnavailable exceptions in `find_duplicate_memory` | L | L | 1.0 | WP-088 ✅ | `find_duplicate_memory()` in `memory_repo.py` can raise `CypherError` or other Memgraph-level exceptions (e.g. malformed query, vector index unavailable). These propagate uncaught from the `add_memory` handler, which only catches `ServiceUnavailable`. Options: (a) catch `CypherError` inside `find_duplicate_memory` and return `None` (fail-open), or (b) let it propagate to a new `except CypherError → 500` clause in the handler. Fail-open is safer for availability; fail-closed is safer for data integrity. Surfaced during WP-088 code review. |
| 17 | R2 | WP-095 | `GET /memory/duplicates`: add Cypher-level safety cap + async wrap | L | L | 1.0 | WP-047 ✅ | Surfaced in WP-047 simplify review. (1) Add `LIMIT 50000` to the `find_near_duplicates` Cypher query as a guard against pathologically large `RELATED_TO` edge sets — prevents unbounded Bolt transfer at extreme scale. (2) Wrap `find_near_duplicates` call in `run_in_executor` in the async endpoint if concurrent usage becomes a concern (currently synchronous in async handler). Both are low-priority improvements; do when the store grows beyond ~10k memories or concurrency spikes. |
| 18 | R2 | WP-138b | Apply calibrated dedup threshold to existing Threat corpus | L | L | 1.0 | ✅ WP-138 | One-off merge pass: run find_duplicates against all 364 existing Threat nodes at threshold 0.28 (calibrated in WP-138); merge pairs above threshold via existing merge endpoint; preserves IDENTIFIES edge provenance. Unblocks uniform corpus state — the current graph has all pre-WP-138 threats ingested at the old 0.15 default, so new threats will dedup correctly but old pairs remain split. |
| 19 | R2 | WP-043 | Inline effective_strength sort in search | L | L | 1.0 | WP-029 ✅ | Add Cypher inline decay formula as search sort key. Currently deferred — stored strength post-decay-pass used as the current proxy. |
| 20 | R2 | WP-091 | Add `agent_id` to lifecycle operation log entries | L | L | 1.0 | WP-056 ✅ | The operation log introduced in WP-056 records `update`, `merge`, `archive`, and `restore` events but omits `agent_id` because the lifecycle endpoints do not currently accept it. Add `agent_id` as an optional field to the four request models (`UpdateMemoryRequest`, `MergeMemoryRequest`, and query params for `archive`/`restore`) and pass it through to `append_operation_log` entries. Enables per-agent traceability on all lifecycle mutations. |
| 21 | R2 | WP-092 | Operation log size audit and rotation strategy | L | L | 1.0 | WP-056 ✅ | Review the real-world size and growth rate of `System.operation_log` under normal usage: measure byte size of the JSON property, estimate how quickly the 200-entry cap is reached, and assess read-modify-write overhead on lifecycle endpoints. Based on findings, decide on a rotation strategy — options include: lowering/tuning the cap per operation type, adding a time-based TTL alongside the count cap (e.g. drop entries older than N days), adding a `DELETE /memory/operation/log` or `POST /memory/operation/log/rotate` endpoint for explicit rotation, or splitting per-operation-type logs. Also review whether the same concern applies to `maintenance_log` (WP-054, currently capped at 100). Outcome: either confirm current approach is sufficient at expected scale, or implement the chosen rotation mechanism. |
| 22 | R2 | WP-121 | 7 integration test files leave non-ephemeral artefacts on cleanup failure | L | L | 1.0 | WP-039 ✅ | Deferred from WP-039 integration test sweep. Seven test files write memories that cannot use `ephemeral=True` because they write-then-search (the search must find the memory they just wrote, so it cannot be excluded from retrieval). These tests rely on the `cleanup_nodes` fixture for cleanup. If `cleanup_nodes` fails or is skipped, artefacts remain in the live graph. Mitigation options: (1) add a post-test Cypher assertion that no tagged test nodes remain, raising clearly if cleanup was incomplete; (2) introduce a test-scoped `purge_ephemeral`-style fixture that sweeps by `agent_id=test-agent` after each session; (3) document as accepted risk since `cleanup_nodes` is reliable in practice. |
| 23 | R2 | WP-SEC-ZWJ | ZWJ / zero-width character bypass in content filter | L | L | 1.0 | WP-SEC-2 ✅ | Zero-width joiner (U+200D), zero-width non-joiner (U+200C), and zero-width space (U+200B) can split banned literals across character boundaries (e.g. `<sy\u200Dstem>`), bypassing `contains_injection()`. Low-urgency given no evidence of live exploitation, but the bypass is well-known. Fix: strip all zero-width characters from text before checking `_INJECTION_LITERALS`, or add the ZWJ/ZWNJ/ZWS codepoints to the Unicode detection loop in `contains_injection()`. |
| 24 | R2 | WP-133 | BSI Grundschutzkatalog ingestion | M | H | 0.6 | WP-132 ✅ | Ingest the BSI IT-Grundschutz Kompendium (available at `scripts/bsi-standard-2003_en_pdf.pdf` in the standards folder) as Framework nodes. BSI Grundschutz is Germany's federal standard for baseline IT security — structured as building blocks (Bausteine) covering infrastructure, organisation, and technical components. Expected strong embedding overlap with ISO 27001 Annex A controls (BSI aligns to ISO 27001 by design) and COBIT. The Kompendium is published in both German and English; ingest the English version for best cos-sim against existing English-language framework embeddings. The `Elementare_Gefaehrdungen.pdf` (elementary threats catalogue) is a companion document — ingest alongside as ThreatReport or separate Framework with JEOPARDISES edges to Grundschutz controls. |
| 25 | R2 | WP-041 | Subject/object schema on Memory nodes | M | H | 0.6 | WP-028 ✅ | Add explicit `subject` and `object` fields. Required before multi-user or shared-memory scenarios. Avoid hard-coded subject assumptions in ingestion APIs. |
| 26 | R2 | WP-008 | API-based LLM provider abstraction | L | M | 0.33 | WP-007 ✅ | Replace the IDE-tied framing with a runtime `LLMClient` provider layer for Anthropic/OpenAI/Ollama. The goal is to let the fabric and future agents run outside VS Code while keeping provider choice swappable behind one interface. |
| 27 | R2 | WP-009 | Headless agent runtime outside VS Code | L | M | 0.33 | WP-008 | Build `BaseAgent` on top of `memory_client` + `LLMClient` so scheduled/event-driven agents can run without an editor session. This is the execution foundation for all higher-level agents that should share the same fabric. |
| 28 | R2 | WP-103 | Generalise `validate_node_ids` and `replace_edges` utilities | L | M | 0.33 | WP-072 ✅ | Simplify review (WP-072) found that `validate_controls`/`validate_documents` in `knowledge_bridge.py` are structurally identical (UNWIND + OPTIONAL MATCH null-filter), and `replace_control_edges`/`replace_doc_edges` duplicate the person/strand replace pattern in `memory_repo.update_memory`. Extract (1) `validate_node_ids(session, ids, label)` generic validator and (2) `replace_edges(session, memory_id, target_ids, edge_type, target_label, edge_properties)` generic replacer. Low priority — all current callers are correct; this is a maintenance-reducing refactor. (Renumbered from WP-096 in WP-102 to resolve ID collision.) |
| 29 | R2 | WP-098 | Excel cross-standard mapping importer | L | M | 0.33 | — | Design a parser for Excel files mapping controls across frameworks (e.g. ISO 27001 ↔ NIST CSF). Format TBD — pending inspection of a real mapping file. Build once a real mapping spreadsheet is available. |
| 30 | R2 | WP-131 | Retrieval feedback signal and observation ROI tracking | L | M | 0.33 | WP-126 ✅ | Add POST /memory/{id}/feedback endpoint (signal: retrieved/used/irrelevant), retrieval_count and last_retrieved_at properties on Memory nodes (auto-incremented by search), observation_tokens property for ROI tracking (set by WP-126 hook), and GET /memory/feedback/stats aggregate endpoint. Foundation for future reinforcement learning on retrieval quality. See detail below. |
| 31 | R2 | WP-145 | CalDAV ↔ Fabric bi-directional task sync | M | M | 1.0 | WP-143 ✅ | `tools/sync_caldav.py` — syncs first-order Task nodes (project tasks + external tasks) between Nextcloud CalDAV and the Fabric. WPs (`source_ref=*:WP-*`) stay in Fabric only. Inbound: completed VTODOs → fabric `done`; new VTODOs → new Task nodes; `X-FABRIC-TASK-ID` property links VTODO to fabric UUID. Outbound: first-order Task nodes without a matching VTODO get pushed. CHANGELOG write-back: on inbound completion, appends entry to project-specific `CHANGELOG.md`. See detail below. |
| 32 | R2 | WP-146 | Windows Task Scheduler entry for CalDAV sync | L | L | 1.0 | WP-145 ✅ | WSL cron only fires while the WSL instance is active. A Windows Task Scheduler entry calling `wsl -e bash -c "python3 /home/oliver/projects/graph-memory-fabric/tools/sync_caldav.py"` ensures sync survives Windows restarts without requiring an open terminal. Trigger: on logon + every 4 hours. |
| 33 | R2 | WP-147 | Strand health diagnostics and thin-strand capture prompts | L | L | 1.0 | — | Surface under-populated strands and generate structured capture prompts for the thin ones. Motivation: the fabric holds rich decision/protocol/project context but several Core Life Domain strands (`strand-core-health`, `strand-core-leisure-play`, `strand-core-finances`, `strand-core-house-home`, etc.) are sparse — the graph knows Oliver's trajectory but not his Tuesday. This creates a retrieval gap: wake-up returns authoritative context but Mara cannot make conversation feel lived-in. **Deliverables:** (1) `GET /strand/health` endpoint — for each strand: memory count, mean strength, mean importance, last-written-at, a `health` enum (`healthy` ≥10 memories, `thin` 3–9, `empty` 0–2). (2) `GET /strand/{id}/capture-prompts` — returns 3–5 open questions tailored to the strand's description and category, derived from the strand description + any existing CURIOSITY THREAD memories in that strand. Prompts are generated from the strand's own content (no LLM call — template-based with strand-aware variable substitution). (3) Update `memory_client/COMPANION.md` to document the `CURIOSITY THREAD` pattern as a first-class memory type: when to write one, how to tag it, and how capture-prompts should reference it. See detail below. |
| 33 | R3 | WP-010 | Remote/mobile access | L | H | 0.2 | WP-009, WP-096 ✅ | Tailscale/VPS hosting + TLS. Auth handled by WP-096. |
| 32 | R3 | WP-011 | Custom graph-cloud UI | L | H | 0.2 | WP-006 | React + D3.js/vis-network consuming `GET /memory/graph`. |
| 33 | R2 | WP-086 | **Analytics Phase — Sprint 2:** outlier detection, semantic families, strand cohesion, missing-edge suggestions, centrality scoring, echo-chamber detection, semantic timelines, neighbourhood summarisation (WP-060 + WP-061 + WP-063 + WP-064 + WP-065 + WP-066 + WP-067 + WP-068) | L | H | 0.2 | WP-085, WP-047 ✅, WP-028 ✅, WP-029 ✅ | Eight analytics capabilities that form the second layer of the analytics phase, building on the Sprint 1 (WP-085) diagnostic infrastructure. All share the same analytical pattern and output surface: (1) vector outlier and anomaly detection — memories far from any semantic neighbourhood or with poor graph/embedding agreement; (2) semantic family analysis — group related memories into families beyond pairwise duplicate pairs (depends on WP-047); (3) strand cohesion diagnostics — measure how tight or fragmented each strand's embedding cluster is; (4) hybrid missing-edge suggestions — propose `RELATED_TO`/`LEADS_TO` links from embedding similarity, time ordering, and topology (review flow, not auto-linking); (5) hybrid memory centrality scoring — blended rank from graph centrality, embedding density, strength, recall count, reinforcement, and edge activation; (6) semantic gravity-well/echo-chamber detection — detect over-saturated retrieval regions; (7) semantic timelines and concept recurrence — track how neighbourhoods shift, recur, or disappear over time; (8) neighbourhood summarisation — turn local density into narrative labels and review queues. |
| 34 | R3 | WP-062 | Concept-drift analysis over time | L | H | 0.2 | — | Compare recent memories and clusters with older semantic regions to detect identity drift, changing priorities, and narrative rewrites. Treat this as analysis tooling first, not as automatic judgment. |
> **Note:** old backlog items once grouped under `v2+` are now part of the same continuous backlog with `Release` assignments.

---

## Ambient Chores

> Items here carry no Order-ID. Pick them up opportunistically when an active WP touches the same file, or during a `/simplify` pass. This section is not a queue.

| WP | Title | Surface area | When to apply |
|----|-------|-------------|---------------|
| ~~WP-014~~ | ~~Docker resource limits~~ | ~~`docker-compose.yml`~~ | ✅ Applied in WP-144 (`mem_limit`, `cpus`, `pids_limit` on `api` and `caddy` services) |
| WP-017 | Embedding cache eviction / size cap | `memory_service/` embedding utilities | When embedding perf or disk usage becomes a concern |
| WP-024 | `cleanup_nodes` multi-id support | `tests/conftest.py` | Verify whether already done in WP-076; delete if complete |
| WP-081 | Initialise `activation_count` and `last_activated_at` on auto-linked edges | `memory_repo.add_memory` | When next touching `add_memory` write path |
| WP-115 | Refactor COBIT→ISO/NIST blocks to loop | `scripts/create_cross_framework_informs.py` | When next touching that script |
| WP-120 | `get_memory_for_update` ephemeral filter | `memory_repo.get_memory_for_update` | Before ephemeral semantics are extended to prod use |
| WP-SEC-R15b | Add SHA-256 pin verification to `ingest_attack_mitigations.py` | `scripts/ingest_attack_mitigations.py` | When next touching that script (same pattern as WP-SEC-R15 in `ingest_attack.py`) |
| WP-151 | Update WP-105 integration test scaffolding for SSE-aware MCP HTTP transport | `tests/test_wp105_*.py`, `_mcp_call` helper | Surfaced 2026-04-29 in WP-150 implementation. Current FastMCP HTTP transport requires `Accept: application/json, text/event-stream` and frames responses as Server-Sent Events. Existing WP-105 integration tests use the older single-`Accept` JSON-only pattern and would fail against the live build. WP-150 added an SSE-aware variant locally; this WP back-fills the WP-105 tests with the same helper. Pick up next time a WP touches the MCP HTTP transport. |
| WP-152 | Re-evaluate `make_list_coercer` factory in `mcp_server/_coercion.py` | `mcp_server/_coercion.py` | Surfaced 2026-04-29 in WP-150 `/simplify` review. The factory is unused in production (all current MCP list params are `list[str]`). Has a slight smell — post-processes `_coerce_str_list` output to undo the bare-string wrap when the inner type isn't `str`. Re-evaluate after 6 months: if no `list[int]`/`list[dict]` MCP parameter materialised, delete the factory under YAGNI; if one did, decide whether to keep it generic or specialise. |
| WP-155 | Cross-module FastMCP `StreamableHTTPSessionManager` test infra fragility | `tests/conftest.py`, `tests/test_wp1*` | Surfaced 2026-05-06 in WP-153 implementation. The conftest `client` fixture is function-scoped, so each integration test re-enters the FastAPI lifespan; FastMCP's `StreamableHTTPSessionManager.run()` raises `RuntimeError: can only be called once per instance` on the second entry. Each WP-153 file passes alone but two together fail in one pytest invocation. Worked around with module-scoped TestClient fixtures in WP-153 tests. Root-cause fix is either (a) make `StreamableHTTPSessionManager.run()` idempotent or (b) promote conftest `client` to session scope (audit other tests for app.state mutation first). |
| WP-156 | `hooks/stop.py` registration uses absolute path | `.claude/settings.json` | Surfaced 2026-05-06 in WP-154. Stop hook command is `python3 /home/oliver/projects/graph-memory-fabric/hooks/stop.py` — correct on this machine, but breaks any sandbox or alternate clone path (caused the parallel session's confusion that led to commit `5e73526`). Convert to project-relative path or use a `${CLAUDE_PROJECT_DIR}`-style anchor if Claude Code's hook system supports it. Touch when next editing `.claude/settings.json`. |
| WP-157 | CLAUDE.md rule 75 ("always commit from Git Bash on Windows") is stale | `CLAUDE.md` | Surfaced 2026-05-06 in WP-154 implementation. Rule was added because WSL exec of `op-ssh-sign.exe` fails with `MZ: not found`. The current toolchain has `op-ssh-sign-wsl.exe` (a WSL-aware shim) configured as `gpg.ssh.program`, plus a 1Password SSH agent socket bridged into WSL at `~/.1p-agent.sock`. Verified: WSL commits produce valid 1Password-backed signatures without the prompt issue described in the rule. Update the rule to allow WSL commits when the WSL shim is configured. |
| WP-158 | `git verify-commit` fails with `Sig: B` due to missing allowed_signers entries | `~/.config/git/allowed_signers` | Surfaced 2026-05-06. `git config gpg.ssh.allowedSignersFile` points at `/home/oliver/.config/git/allowed_signers`, but the file lacks the `<email> <key>` mapping needed to upgrade `Sig: B` (good signature, untrusted signer) to `Sig: G` (good and trusted). Fix is one line per author identity. Trivial config polish; no blocker. |
| WP-159 | Bake embedding model into image at Dockerfile build time | `Dockerfile`, `docker-compose.yml` | Surfaced 2026-05-06 during WP-153/154 homeserver deploy. The image relies on the `hf_cache` named volume being pre-populated with `all-MiniLM-L6-v2` weights; the `:ro` mount means the running container can't repopulate. When the volume is lost or project-renamed (volume name follows `<project>_<volume>` convention), the api fails at startup with `LocalEntryNotFoundError`. Fix: add `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"` after pip install in the Dockerfile so the model lives in an image layer. Trade-off: adds ~150 MB to image size and ~30 s to build time. Worth it: removes a class of operational dependency between volume lifecycle and image lifecycle. |
| WP-160 | Surface git SHA via `/health` endpoint | `Dockerfile`, `docker-compose.yml`, `memory_service/main.py` | Surfaced 2026-05-06. The `/health` endpoint already reserves a `build` field but never populates it (always returns `unknown`). One-line `curl /health` should answer "what code is live" — avoids three-round-trip diagnostics every deploy. Implementation: Dockerfile `ARG GIT_SHA=unknown` → `ENV BUILD_SHA="${GIT_SHA}"`, compose `build.args.GIT_SHA: "${GIT_SHA:-dev}"`, deploy script `export GIT_SHA=$(git rev-parse HEAD)` before build, and `main.py:/health` reads `os.environ.get("BUILD_SHA")` for the build field. |
| WP-161 | `claude-diag` wrapper points at wrong compose project after deploy rename | `scripts/homeserver/claude-diag` (deployed as `/usr/local/bin/claude-diag`) | Surfaced 2026-05-06 in WP-153 deploy. Wrapper hardcodes `COMPOSE_DIR=/opt/stacks/deploy/memfabric` and `SERVICE=memfabric-api`, but the rebuilt stack runs under compose project name `graph-memory-fabric` (image `graph-memory-fabric-memfabric-api:latest`, volume `graph-memory-fabric_hf_cache`). All `claude-diag` subcommands now report "service memfabric-api is not running" even when it is. Resolution options: (a) update wrapper's `COMPOSE_DIR` and `SERVICE` to match the new project name, or (b) standardise the project name across deploy paths (set `COMPOSE_PROJECT_NAME=memfabric` explicitly in the homeserver's env). Option (b) is preferable — the legacy `memfabric_*` named volumes still exist on disk and would resume being attached, restoring continuity. |
| WP-162 | `claude-diag logs` subcommand is silent when container not running | `scripts/homeserver/claude-diag` | Surfaced 2026-05-06. Other diag subcommands (`mcp-probe`, `inspect-main`) print `service "memfabric-api" is not running` when the container is absent; `logs` returns empty. Inconsistent — diagnoses are easier to interpret if the wrapper consistently reports container state. Trivial fix: prepend an existence check in `cmd_logs` that prints the not-running message and exits 0 before attempting the `compose logs` call. |
| WP-163 | Developer experience and deploy discipline hardening | `docker-compose.override.yml`, `tests/conftest.py`, `Makefile` (new), `docs/operations/deploy.md` (new) | Surfaced 2026-05-06 from accumulated fragmentation observed during WP-153/154 deploy. Five sub-items: (1) update `docker-compose.override.yml` template to match current base service names (`memfabric-api`, not `api`) and publish localhost ports for db/api/lab — caught only because Step 2 of the WP-153 deploy needed local integration tests; the override had been silently broken since WP-144. (2) Promote conftest's `client` fixture to bypass WP-096 auth automatically (monkeypatch `api_keys=[]` once at session scope). Currently every integration test author has to remember to `_set_keys(monkeypatch, [])` per test — also affects `test_wp046_dedup.py` and others which now fail against an auth-enabled local stack. Audit existing tests for `app.state` mutation impact before promoting scope. Subsumes part of WP-155's root-cause fix. (3) Add `make stack-up`, `make stack-down`, `make smoke` targets wrapping the correct `docker compose` invocation including `--env-file` so developers don't have to remember it; mirror the homeserver's `dcumf` alias contract. (4) Write `docs/operations/deploy.md` documenting the canonical homeserver deploy sequence including the explicit `docker compose build` step (dropping it reuses stale images — a real bug we hit), the `dcumf` alias, and the volume-name continuity check (`docker volume ls | grep hf_cache` to detect compose-project-name churn before deploys break). (5) Add a pre-commit check or deploy-doc warning that catches `docker compose up -d` without `--build` for code-only changes. |
| WP-164 | Verification protocol for remote-Claude review branches | `CLAUDE.md`, `docs/operations/remote-review.md` (new), optional GitHub Action | Surfaced 2026-05-06 from WP-153/154 work and the parallel session's `5e73526` "fix" that was actually a regression. Branches authored by remote-Claude sessions (pattern: `claude/review-*` or `claude/*-<random>`) may contain sandbox-specific assumptions (absolute paths matching `/home/user/...`, hook registrations naive of host's global hooks, tests broken by behavioural changes the same commit introduces). Codify a verification checklist: (1) any absolute paths in commits must match the host filesystem layout per `claude_baseline_manifest.json`, (2) any new hook registrations must be checked against `~/.claude/settings.json` for collision before merge, (3) any tests changed by the commit must be run locally to confirm they still pass with the new behaviour, (4) any settings.json edits must be reviewed for self-modification implications. Optional follow-up: add a GitHub Action that diffs absolute paths in incoming PRs against an allow-listed pattern set, surfacing sandbox-style paths (`/home/user/...`) automatically. The `5e73526` commit on master is the canonical example — it was committed directly to master to "fix" the parallel session's missing file, but the real fix was sandbox-vs-host alignment, not a master-side commit. |
| WP-165 | MCP server registration silently fails when `MEMFABRIC_API_KEY` env var is absent at Claude Code startup | `.mcp.json`, session-start hook, `docs/operations/` | Surfaced 2026-05-06 + 2026-05-06 (resume). The project's `.mcp.json` uses `"Authorization": "Bearer ${MEMFABRIC_API_KEY}"` which Claude Code substitutes from the env var at startup. If the var isn't in Claude Code's process environment (e.g. exported only in a child shell, or missing entirely), substitution produces `Bearer ` (empty), the `/mcp/` endpoint returns 401, the MCP server is marked "Failed to connect" by Claude Code, and the entire `mcp__memory__*` tool surface is unavailable for the session — even though the fabric itself is healthy and reachable via direct HTTP. Affected two consecutive sessions on 2026-05-06: prevented writing close-session memories via MCP and forced a fall-back to direct REST calls with the bearer from `~/.memfabric/token`. Resolution options: (1) session-start hook check that warns when `claude mcp list` shows `memory: ✗ Failed to connect`, (2) Claude Code feature request for token-file-based auth in `.mcp.json` schema (avoids env-var substitution entirely; the token already lives at the canonical path `~/.memfabric/token` per the Mara baseline contract), (3) document explicit `export MEMFABRIC_API_KEY=$(cat ~/.memfabric/token)` step in the project's session-start docs as a workaround. Option 2 is the cleanest long-term fix; option 1 + 3 are an immediate mitigation pair. |
| WP-166 | Memgraph backup hardening — off-host, restore-tested, dedicated user, alerting | `scripts/homeserver/backup-nightly.sh`, `docs/operations/backup.md`, new infra | Surfaced 2026-05-06 from the volume-orphaning near-miss. A minimum-viable nightly backup is in place (Layer 1: local JSON dump + volume tarball, 14-day retention, runs as user `oliver`). The proper version covers the gaps documented in `docs/operations/backup.md`: (1) **off-host replication** — rsync or restic the daily artefacts to a separate machine on the LAN (laptop, NAS, second host); (2) **restore-test discipline** — periodic automated restore-from-backup into a throwaway Memgraph instance to verify backups are actually usable; (3) **dedicated stack-user** — backup currently runs as user `oliver` for ergonomic reasons; should be a dedicated user with read-only access to source dirs and write-only access to backup dirs, similar to `claude-diag` discipline; (4) **cold / off-site storage** — encrypted upload to Backblaze B2/S3 for ransomware and physical-loss defence; (5) **alerting on failure** — currently silent failures land in `backup.log`; want at least an email or push notification on any non-zero exit. Optionally also: tiered retention (7 daily + 4 weekly + 12 monthly) instead of flat 14-day; integration with the existing `dump_db.py` / `restore_db.py` pair to make sure they keep working as the schema evolves; a `make backup` target as a developer-facing shortcut. |

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

> **Completed 2026-04-09.** Commits `7de5b23`→`40426c0` on `master`.

#### Definition of Success

- [x] Wake-up response includes a `companion_anchors` section with Companion identity memories
- [x] When `person_id` is supplied, response includes a `conversant_anchors` section
- [x] Both sections respect their configured limits
- [x] Sections are omitted (not empty arrays) when there are no matching memories, to keep the response clean
- [x] CLI and MCP updated
- [x] Integration test: seed Companion anchor memories and a Person with ABOUT memories; confirm they appear in the correct sections

**Retrospective:** Design required an extra brainstorming round to resolve Agent/Person node duality for companion identification. Chose label-agnostic ABOUT traversal (`MATCH (m)-[:ABOUT]->(n) WHERE n.id = $agent_id`) — clean, forward-looking, and additive. The `wake_up_split` dict-return change was the most wide-ranging mechanical change (5 caller sites + 3 pre-existing broken mocks fixed), but straightforward. Seeding script linked 39 existing identity memories to the `claude-code` node, making the feature immediately live. Follow-up items WP-122/WP-123/WP-124 deferred to backlog.

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

> **Completed 2026-04-03.** See `docs/CHANGELOG.md` for full retrospective. Commit `ac1a506` on `feature/knowledge-layer`.

- Created `scripts/schema_utils.py` with shared `create_constraint()` + `get_embedding_dimension()`
- `init_schema.py` and `init_knowledge_schema.py` now import from `scripts.schema_utils` (no duplication)
- `memory_service/embeddings.py`: added `_model_cache: dict[str, SentenceTransformer]`, `_load_model_by_name()`, and optional `model_name` parameter throughout `get_model`/`get_embedding`/`get_embedding_dimension`/`_cache_key`
- `scripts/migrate_embeddings.py`: both `get_embedding()` call sites now pass `model_name=model_name`
- 11 unit tests, all green; no integration tests (pure Python, no Memgraph)

**Retrospective:** Three /simplify wins caught during verification: (1) `ClientError` import was missing from both init scripts after extraction — runtime `NameError` averted; (2) `_load_model` and `_load_model_by_name` had duplicate offline-setup blocks — extracted to `_make_st_kwargs()`; (3) `_cache_key` ternary simplified to `model_name or _model_name`. Background agents (even with `bypassPermissions`) cannot write files or run Bash in this environment — implementation was done directly in-session. This is now the established pattern for all WPs on this branch.

---

### WP-072 — InfoSec knowledge layer: cross-layer Memory edges ✅

> **Completed 2026-04-03.** Merged via `feature/knowledge-layer` (commit `d9b78d0`). See `docs/CHANGELOG.md` for full retrospective.

- Created `memory_service/knowledge_bridge.py` (ADR-001 Guardrail 3 — sole cross-layer import module): 8 functions covering `validate_controls`, `validate_documents`, `link_controls`, `link_documents`, `replace_control_edges`, `replace_doc_edges`, `rewire_cross_layer_edges`, `hydrate_controls_and_documents`
- Extended `AddMemoryRequest`, `UpdateMemoryRequest` with `control_ids`, `doc_ids`, `control_relationship_type: Literal["context","evidence","gap"]`, `org_id`; extended `MemoryHit` with `controls: List[dict]`, `documents: List[dict]`
- Wired bridge into `add_memory` (validate + link), `update_memory` (bridge-field stripping + replace), `merge_memory` (rewire), `search_memory` (hydrate) — all guarded by `settings.enable_knowledge_layer`
- Extended `memory_client/client.py` and `mcp_server/server.py` `memory_add`/`memory_update` tools with all 4 new params
- 14 bridge unit tests + 5 model tests + 12 route tests = 31 tests, all green; integration tests deferred to WP-076
- Simplify fixes: added `if req.doc_ids:` guard on `link_documents` call; promoted `_BRIDGE_FIELDS` to module level
- New backlog item WP-103 (renumbered from WP-096 in WP-102): generalise `validate_node_ids` + `replace_edges` utilities (low priority)

**Retrospective:** Two-wave approach (bridge module first, route wiring second) worked well — Wave 1 was fully reviewable in isolation before Wave 2 added route complexity. Quality review caught bridge-only PATCH not returning 404 for non-existent memory (fixed before merge). Simplify review caught missing `if req.doc_ids:` guard. `_BRIDGE_FIELDS` as module-level constant is the correct pattern. Lazy `from memory_service import knowledge_bridge` inside route handlers is intentional to avoid pytest collection order issues.

---

### WP-076 — InfoSec knowledge layer: integration and separation tests ✅

> **Completed 2026-04-03.** Merged via `feature/knowledge-layer` (commit `d9b78d0`). See `docs/CHANGELOG.md` for full retrospective.

- Folded WP-024: `cleanup_nodes` in `tests/conftest.py` extended to accept `dict[str, str | list[str]]` — backward-compatible
- Added `knowledge_client` fixture to `conftest.py` (module-scoped, reloads app with `ENABLE_KNOWLEDGE_LAYER=true`) — eliminates duplication across all knowledge-layer test files
- Created `tests/test_wp076_separation.py`: autouse module-scoped `separation_data` fixture seeds 20 Controls + 50 Chunks + 5 Memory nodes; 3 integration tests assert zero cross-layer leakage in search; 1 static AST import-audit test enforces ADR-001 at all times
- Created `tests/test_wp076_integration.py`: 38 integration tests across `TestKnowledgeSchemaIntegration` (4), `TestKnowledgeWriteIntegration` (13), `TestKnowledgeSearchIntegration` (7), `TestCrossLayerIntegration` (14)
- Updated `tests/test_wp075_traceability.py`: appended `TestTraceabilityIntegration` with 11 integration tests for all four traceability endpoints including org-scoped filtering, knowledge-only mode, and gap-analysis classification
- **52 integration tests + 33 unit tests, all green** against live Memgraph + FastAPI stack

**Retrospective:** Fixture-scope bugs were the dominant failure mode: (1) a session-scoped fixture cannot request a module-scoped one — `separation_data` had to be demoted to module scope; (2) a fixture inside a class body cannot exceed `scope="class"` — `seed_search_data` had to be extracted to module level; (3) the `SearchMemoryResponse` wrapper (`{"memories": [...]}`) was not unwrapped in one test assertion. The dedup-collision issue (missing control validation silently skipped on dedup path) required cleaning sentinel memories by fact prefix before each test run. The `knowledge_client` fixture duplication (3 independent copies across test files) was caught by the code quality review and consolidated into conftest.py.

---

### WP-075 — InfoSec knowledge layer: SABSA bidirectional traceability ✅

> **Completed 2026-04-03.** Merged via `feature/knowledge-layer` (commit `d9b78d0`). See `docs/CHANGELOG.md` for full retrospective.

- Added `trace_up`, `trace_down`, `attribute_coverage`, `gap_analysis` repo functions to `knowledge_repo.py`
- Added `get_business_attribute` and `list_controls` helper functions (extracted during simplify to eliminate inline duplicate queries)
- Added 11 Pydantic models and 4 route handlers to `knowledge_routes.py`: `GET /knowledge/controls/{id}/trace-up`, `GET /knowledge/controls/{id}/trace-down` (with `org_id` query param), `GET /knowledge/attributes/{id}/coverage`, `POST /knowledge/gap-analysis`
- `trace_down` uses OPTIONAL MATCH throughout — fully functional with zero Memory nodes (ADR-001 knowledge-only mode)
- `MemoryRef.relationship_type` typed as `Literal["context", "evidence", "gap"]` matching existing codebase convention
- `trace_down` not-found detection via MATCH failure (`.single()` returns None) — eliminates redundant pre-check round-trip
- 32 unit tests, all green; integration tests deferred to WP-076
- Simplify fixes: removed `get_control()` pre-check from `trace_down` (MATCH detects not-found); extracted `get_business_attribute()` and `list_controls()` helpers; fixed `result is None` branch in `trace_down` to return `None` (not empty dict)

**Retrospective:** The `MATCH (c:Control {id: $id}) OPTIONAL MATCH ...` pattern for not-found detection is more efficient than a pre-check query — one round-trip instead of two. The simplify review caught the redundant pre-check and two inline queries that should have been helpers. Clearing all 32 tests required one additional fix post-simplify: the `result is None` fallback in `trace_down` was returning an empty dict instead of `None`, which had been the correct pre-simplify behaviour but broke after the pre-check was removed.

---

### WP-074 — InfoSec knowledge layer: CLI, MCP tools, and ETL ✅

> **Completed 2026-04-03.** Merged via `feature/knowledge-layer` (commit `d9b78d0`). See `docs/CHANGELOG.md` for full retrospective.

- Added `enable_knowledge_layer: bool = False` to `MCPSettings` in `mcp_server/config.py`
- Added 7 `MemoryClient` methods: `search_controls`, `search_chunks`, `list_norms`, `list_documents`, `get_incomplete_jurisdictions`, `get_control`, `get_norm`
- Added 5 feature-flag-gated MCP tools in `mcp_server/server.py` inside `if settings.enable_knowledge_layer:` block: `knowledge_search_controls`, `knowledge_search_chunks`, `knowledge_list_norms`, `knowledge_get_control`, `knowledge_get_norm`
- Added `knowledge` Typer sub-app to CLI with 5 subcommands: `search-controls`, `search-chunks`, `list-norms`, `list-documents`, `review-supports` (stub)
- Created `scripts/ingest_framework.py`: YAML-validated bulk ETL; upserts Framework → Controls → Norms → Documents → Chunks → Jurisdictions → BusinessAttributes; idempotent (409 = "already existed"); `--dry-run` stops after validation
- Created `data/frameworks/`: `nist-csf-2.0.yaml` (15 controls), `iso-27001-2022.yaml` (11 controls), `jurisdictions.yaml` (10), `business-attributes.yaml` (8 SABSA attributes)
- Added `pyyaml` to `pyproject.toml` dependencies
- Created `KNOWLEDGE_LAYER.md`: 429-line operational runbook covering separation invariants, node/edge reference, ingest procedures, embedding model guidance, and ADR references
- 15 unit tests, all green; integration tests deferred to WP-076
- Simplify fixes: removed 5 redundant `Console()` instantiations (use module-level); simplified `review-supports` stub message (removed implementation details and unused param); normalised Jurisdictions/BusinessAttributes error-counting to `if s != "error"` pattern
- Deferred: WP-025 updated to cover 4 new knowledge CLI commands (missing `HTTPStatusError` handling + extract shared handler)

**Retrospective:** Parallel Group A → Group B → Group C agent dispatch worked cleanly — zero file conflicts across 6 agents. The `if settings.enable_knowledge_layer:` conditional wrapping `@mcp.tool` function definitions (not just decorators) is the correct FastMCP pattern for feature-flagged tools registered at import time. `review-supports` intentionally stubbed — full implementation deferred to WP-075 when the SUPPORTS status update endpoint is available.

---

### WP-073 — InfoSec knowledge layer: document ingestion pipeline ✅

> **Completed 2026-04-03.** Merged via `feature/knowledge-layer` (commit `d9b78d0`). See `docs/CHANGELOG.md` for full retrospective.

- Added `create_supports_edge` and `get_chunks_for_control` to `knowledge_repo.py` — SUPPORTS edge (Chunk→Control) with `confidence` and `status`; returns ordered by confidence DESC
- Added `SupportsCreate`/`SupportsResponse`/`ChunkWithSupports` Pydantic models + `POST /knowledge/chunk/supports` + `GET /knowledge/controls/{id}/chunks` routes to `knowledge_routes.py`; `confidence` range-validated via `Field(ge=0.0, le=1.0)`
- Added 6 ingest config settings to `config.py` and `.env.example`: `ingest_chunk_size`, `ingest_chunk_overlap`, `ingest_min_chunk_chars`, `ingest_auto_supports`, `ingest_auto_supports_threshold`, `ingest_chunk_review_mode`
- Created `scripts/chunkers.py`: `chunk_markdown` (heading-aware, heading prepended into text) + `chunk_pdf` (pdfplumber, overlapping char windows); infinite-loop guard on `overlap >= chunk_size`
- Created `scripts/ingest_document.py`: HTTP-only ingest CLI; PDF + Markdown; UUIDs per chunk; review mode (default on) + auto-SUPPORTS mode with threshold; `[WARN]` messages on HTTP failure (not silent)
- Added `pdfplumber` to `pyproject.toml` dependencies; `fpdf2` to `dev` extras
- 26 unit tests (13 ingest + 13 chunkers), all green; integration tests deferred to WP-076
- Deferred minor items: M2 (`chunk/supports` singular URL), M4 (H1 heading handling in `chunk_markdown`)

**Retrospective:** Through-`main()` test pattern (patch `sys.argv` + `httpx.Client` + `IngestSettings`) is robust for CLI script tests — avoids false positives from inline logic reimplementation. Quality review (`simplify`) caught: (C1) infinite loop in `chunk_pdf` when `overlap >= chunk_size` (fixed), (I1) missing confidence range validation (fixed via `Field(ge=0.0, le=1.0)`), (I2) four ingest tests reimplementing production logic inline instead of calling `main()` (replaced). M1 (silent HTTPError suppression) fixed inline. Two minor items deferred to backlog.

---

### WP-071 — InfoSec knowledge layer: search API ✅

> **Completed 2026-04-03.** Merged via `feature/knowledge-layer` (commit `d9b78d0`). See `docs/CHANGELOG.md` for full retrospective.

- Added 5 repo functions to `knowledge_repo.py`: `search_controls` (vector, `ctrl_embedding_idx`), `search_chunks` (vector, `chunk_embedding_idx`), `list_norms`, `list_documents`, `list_incomplete_jurisdictions`
- Added 4 Pydantic models + 5 route handlers to `knowledge_routes.py`: `POST /knowledge/search/controls`, `POST /knowledge/search/chunks`, `GET /knowledge/norms`, `GET /knowledge/documents`, `GET /knowledge/incomplete-jurisdictions`
- `docs/plans/wp-071.md` written; 17 unit tests (11 Group A + 8 Group B), all green; integration tests deferred to WP-076
- **Retrospective:** Parallel task dispatch (repo + routes simultaneously) worked cleanly — no file conflicts. Quality review surfaced missing `TestListDocuments` Group A tests (fixed) and absence of `ServiceUnavailable` guard across all 13 `knowledge_routes.py` handlers (logged to WP-023).

---

### WP-070 — InfoSec knowledge layer: write API ✅

> **Completed 2026-04-03.** Commit `a1c1148` on `feature/knowledge-layer`. See `docs/CHANGELOG.md` for full retrospective.

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

### WP-093 — Agent-optimised search: score exposure, min_score filter, associative expansion *(person-path scoring semantics superseded by WP-149)*

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

Person-anchored path (`person_ids` set): returns `associated: []`, ignores `min_score`. *(WP-149 supersedes: `min_score` is now applied on the person-anchored path too; score is numeric, not null.)*

**4. `MemoryClient.search_memory()` update**

Accept and pass through `min_score` and `neighbour_cap`. Existing callers that do not set these fields are unaffected (both default to no-op).

**MCP surface update is out of scope** — follow-on task once HTTP layer is stable.

#### Acceptance criteria

- [ ] `POST /memory/search` response includes `score` on all vector-search hits; `null` on person-anchored hits *(superseded by WP-149: person-anchored hits now also carry a numeric score)*
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

### WP-096 — API authentication (bearer tokens / API keys)

#### Motivation

The service currently has no authentication layer — any process that can reach `localhost:8000` can read and write memories. Safe external exposure (Tailscale, VPS, mobile access) requires that every request be authenticated. This WP adds a lightweight, stateless auth layer that supports both human users (via a pre-shared bearer token / API key) and multiple independent agents (via per-agent keys), without introducing a user-account database or session state.

#### Design

**Authentication scheme:** `Authorization: Bearer <token>` header (primary) with `X-API-Key: <token>` as a fallback alias. Both are equivalent; a single check function handles both.

**Key storage:** one or more valid tokens stored in `.env` as `API_KEYS` (comma-separated). Loaded at startup via `pydantic-settings`. No database, no key rotation endpoint in v1. Adding a new key requires a service restart.

**FastAPI implementation:** a `verify_api_key` async dependency function injected via `Depends()` into the router. Applied globally via `app.include_router(..., dependencies=[Depends(verify_api_key)])` or at the app level, so no individual route handler needs to change. Returns `401 Unauthorized` with `WWW-Authenticate: Bearer` on failure.

**Exemptions:** `GET /health` remains unauthenticated (used by uptime monitors and Docker health checks).

**`memory_client` / CLI update:** add `API_KEY` env var support to `MemoryClient` so the Python client and CLI can authenticate automatically.

**MCP server update:** pass `API_KEY` through the MCP server env so `memory-mcp` can authenticate.

#### Files

- `memory_service/auth.py` — new: `verify_api_key` dependency
- `memory_service/config.py` — add `api_keys: list[str]` setting
- `memory_service/main.py` — apply auth dependency globally; exempt `/health`
- `memory_client/client.py` — add `api_key` param, inject as `Authorization` header
- `memory_client/cli.py` — read `API_KEY` from env, pass to client
- `.env.example` — document `API_KEYS` variable
- `tests/test_wp096_auth.py` — unit + integration tests

#### Definition of Success

- [ ] All endpoints except `GET /health` return `401` when no valid token is provided
- [ ] A valid `Authorization: Bearer <token>` is accepted on all protected endpoints
- [ ] A valid `X-API-Key: <token>` is accepted as an alternative
- [ ] Multiple keys in `API_KEYS` all work independently (supports per-agent keys)
- [ ] `GET /health` remains unauthenticated
- [ ] `MemoryClient` reads `API_KEY` from env and sends it automatically
- [ ] MCP server passes `API_KEY` through to the service
- [ ] Unit tests: 401 with missing/invalid token, 200 with valid token
- [ ] Integration tests: run against live stack with `API_KEYS` set in `.env`
- [ ] `.env.example` documents `API_KEYS`

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

---

### WP-099 — Knowledge layer schema correction: `:Framework` hierarchy, `body` field, retire `:Control`

> **Architecture:** See [ADR-002](docs/architecture/ADR-002-knowledge-layer-graph-model.md) — all framework hierarchy nodes are `:Framework` with `level` + `body`.

#### Motivation

ADR-002 specifies that `:Framework` is the node type for the entire framework hierarchy — from the top-level standard down to individual clauses and Annex A controls. Each node carries a `level` property (e.g. `framework/category/section/clause`) and a `body` field containing the requirement text. The WP-070–076 implementation diverges from this: it uses `:Control` nodes (without `body`) for sub-framework items, and `:Framework` only for the top-level standard node.

This is blocking correct ISO 27001 loading and will cause confusion for any downstream analytics, traceability, or gap analysis that traverses the hierarchy.

#### Design

**Node label change:** All nodes currently created as `:Control` via `POST /knowledge/controls` should instead be `:Framework` nodes. The `:Control` label is reserved (per ADR-002) for the organisation's internal security architecture — not for nodes in an external standard's hierarchy.

**New fields on `:Framework`:**
- `level: str` — position in hierarchy: `framework` | `category` | `section` | `clause` | `sub-clause` (exact vocabulary depends on the standard; stored as-is)
- `body: str | None` — the full requirement text. Optional — section headers have no body.
- `parent_id: str | None` — if set, creates `CONTAINS` edge from parent `:Framework` to this node

**API changes:**
- `POST /knowledge/frameworks` — add `level`, `body`, `parent_id` to `FrameworkCreate`; `level` defaults to `"framework"` for backward compatibility
- `GET /knowledge/frameworks/{id}` — add `level`, `body` to `FrameworkResponse`
- **Remove** `POST /knowledge/controls`, `GET /knowledge/controls/{id}`, `GET /knowledge/search/controls` — or redirect to framework equivalents
- `POST /knowledge/search/frameworks` — new endpoint (replaces controls search), searches `:Framework` nodes by embedding on `body`
- `POST /knowledge/chunks/supports` — `control_id` field renamed to `framework_id` (done in WP-100/WP-102)

**Schema / index changes:**
- `init_knowledge_schema.py`: replace `ctrl_embedding_idx ON :Control(embedding)` with `framework_embedding_idx ON :Framework(embedding)` — note `:Framework` nodes without `body` have no embedding and are excluded from the index
- Drop uniqueness constraint on `:Control(id)`; add/verify `UNIQUE :Framework(id)` (likely already exists)

**Migration:**
- Delete all existing `:Control` nodes and reload via updated loader scripts
- `load_iso27001_chunks.py`: use `POST /knowledge/frameworks` with `parent_id` and `body` for all hierarchy nodes; drop all `POST /knowledge/controls` calls
- `SUPPORTS` edges: `chunk_id → framework_id` (rename field in `SupportsCreate`)

#### Acceptance criteria

- [ ] `POST /knowledge/frameworks` accepts `level`, `body`, `parent_id`; creates `CONTAINS` edge when `parent_id` set
- [ ] `GET /knowledge/frameworks/{id}` returns `level` and `body`
- [ ] Vector search on framework `body` text works via new search endpoint
- [ ] No `:Control` nodes in the graph after migration
- [ ] ISO 27001 full load (137 entries) produces correct `:Framework` hierarchy, `body` populated on all leaf nodes, `CONTAINS` tree navigable from root
- [ ] `SUPPORTS` edges link `:Chunk` → `:Framework` correctly
- [ ] `init_knowledge_schema.py` creates `framework_embedding_idx` not `ctrl_embedding_idx`
- [ ] All existing knowledge layer integration tests updated and passing



---

### WP-127 — File provenance on Memory nodes

Completed 2026-04-10. Added files_modified and files_read list properties to Memory nodes. Exposed through AddMemoryRequest, UpdateMemoryRequest (optional), SearchMemoryRequest (filter), and MemoryHit (response). New GET /memory/by-file endpoint for path-based lookup with role=modified|read|any. _build_file_filter_clause helper inserts AND predicates into search query templates. memory_client.search_memory(), add_memory(), update_memory(), and get_memories_by_file() all extended. 28 tests (23 unit + 5 integration against live stack), all passing.

Retrospective: integration test caught a real gap — search_memory() in the client was not updated alongside the other client methods. Running integration tests via the client (not raw HTTP) is what surfaced it. The person-path branch of search_memories also needed a dedicated test — the main branch alone gives false confidence.

---

### WP-129 — SessionStart context injection hook ✅

**Completed 2026-04-10.** Extracted `format_wake_up()` from `cli.py` into `memory_client/formatting.py` (plain=True builds plain strings directly for hook consumers, plain=False builds Rich markup for CLI). `hooks/session_start.py` calls `wake_up_split` + `format_wake_up` and prints plain text to stdout. Registered in `.claude/settings.json` using the correct nested hook schema. CLI output unchanged. 20 tests passing. Hook verified against live service.

**Retrospective:** Extracting the formatter first made the hook trivial (~35 lines). The plain=True flag was the key design decision — keeps one renderer for two consumers without branching logic. The nested hook schema (`{"hooks": [{"type": "command", "command": "..."}]}`) differs from what the plan originally specified — always verify Claude Code hook registration format against the actual schema validator.

---

### WP-104 — COBIT 2019 ingestion ✅

> **Completed 2026-04-07.** Commit `e6e1e61` on `master`.

- `scripts/inspect_cobit2019.py`: Excel extractor — reads Objectives, Objectives-Practices, Activities sheets with merged-cell forward-fill; synthesises 5 domain nodes from objective ID prefixes; outputs parent-before-child YAML
- `scripts/cobit2019_inspection.yaml`: 1,479 entries (1 framework + 5 domains + 40 objectives + 231 practices + 1,202 activities), each objective includes a separate `purpose` field and `body` formatted as `{desc}\n\nPurpose: {purpose}`
- `scripts/load_cobit2019_chunks.py`: YAML → `POST /knowledge/frameworks` loader; no cross-reference edges (deferred to WP-105)
- Verified: 1,479 Framework nodes, 1,478 CONTAINS edges, 1,479 embeddings — all green

**Retrospective:** Smooth execution. Activity regex capture group was the one implementation bug caught in review (regex had no capture group — counter fallback ran unconditionally). Purpose Statement separation was caught during YAML human review and fixed before load. OLIR cross-references deferred to WP-105: CSF 1.1→2.0 version gap makes the mapping unreliable as a primary source; embedding similarity is the correct approach.

---

### WP-105 — Cross-framework INFORMS edges (COBIT ↔ ISO 27001 / NIST CSF 2.0) ✅

> **Completed 2026-04-07.** Commit `5af6ac3` on `master`.

- `scripts/create_cross_framework_informs.py`: fetches Framework node embeddings from Memgraph, computes pairwise cosine similarity via numpy bulk matrix multiply, creates INFORMS edges above threshold via MERGE (idempotent, preserves existing source property)
- `tests/test_wp105_cross_framework_informs.py`: 5 unit tests + 3 integration tests
- Threshold **0.55** chosen to match density of existing NIST→ISO official reference edges (2.2% vs 3.4%); calibration confirmed p50 of known-good pairs is 0.49 so 0.55 captures the higher-confidence half
- Results: 737 COBIT→ISO + 745 COBIT→NIST = **1,482 new INFORMS edges**; 1,879 total INFORMS edges in graph
- Coverage: 31/40 COBIT objectives and 178/231 practices connected; 9 unconnected objectives all BAI domain (corroborates ISACA journal finding that BAI aligns weakly to ISO 27001)
- OLIR (CSF 1.1 → COBIT) not used — CSF 1.1/2.0 version gap makes it unreliable as primary source

**Retrospective:** Calibrate mode against existing NIST→ISO xref edges was essential — revealed the default 0.55 threshold is already stricter than half the official NIST reference mappings (p50=0.49). BAI domain gap confirms published ISACA research. Deferred to BACKLOG: double similarity computation in main() (performance), compute_histogram linear scan, histogram boundary bin artefact.

**Deferred to BACKLOG:**
- Double similarity computation in `main()` — similarity matrix recomputed twice per framework pair (performance, not correctness). Low priority.
- `compute_histogram` linear scan — use `np.histogram` for large matrices. Low priority.
- Histogram `high=1.0+bin_width` creates spurious 1.00–1.05 bin. Low priority.

---

### WP-107 — Cross-framework cluster analysis ✅

> **Completed 2026-04-09.** Commit `fdc29f1` on `master`.

- `scripts/analyse_cross_framework_clusters.py`: standalone analysis script — MAGE `community_detection.get_subgraph` for Louvain communities, `betweenness_centrality.get` for bridge detection, scikit-learn k-means + silhouette sweep for embedding clusters, `--write` flag for write-back to Framework nodes
- `tests/test_wp107_cluster_analysis.py`: 16 unit tests + 6 integration tests, all green
- Results: 3273 Framework nodes analysed, 6 Louvain communities, 20 k-means clusters, 3277 nodes annotated with `louvain_community_id`, `embedding_cluster_id`, `betweenness_centrality`
- Cross-framework mixing confirmed: governance frameworks (ISO 27001, SP 800-53, NIST CSF, COBIT) form shared communities; ATT&CK techniques cluster separately (expected — distinct vocabulary)
- MAGE procedure names discovered: `community_detection.get_subgraph` (not `algo.louvain`), `betweenness_centrality.get` (not `algo.betweenness_centrality`)

**Retrospective:** MAGE procedure naming differed from documentation — fallback pattern proved essential. ISO 27001 node prefix (`iso-27001-2022`) differed from `_FRAMEWORK_PREFIX_MAP` key (`iso27001`) — caught during live run, fixed immediately. Silhouette sweep at k=8..30 across 3273 nodes was slow (~minutes); `--k` flag added to allow forcing. 6 Louvain communities is fewer than expected but semantically correct: governance frameworks cluster together while ATT&CK forms its own community. Framework embedding index confirmed as 384-dim (not 768 as assumed in plan) — relevant for WP-116.

---

### WP-109 — ISO 22301 Business Continuity ingestion ✅

> **Completed 2026-04-09.**

- `scripts/inspect_iso22301.py`: PDF extractor (30-page standard); 62 clauses, 147 normative statements extracted to `scripts/iso22301_inspection.yaml`
- `scripts/load_iso22301_chunks.py`: framework loader; 293 nodes upserted under `iso-22301-2019` root
- Fills the BCM/resilience gap identified in WP-107 cluster analysis (COBIT RC coverage weakest of all NIST CSF functions)
- Cross-framework INFORMS edges completed in WP-132 ✅

**Retrospective:** Standard follows same Clause 4–10 structure as ISO 27001/27005 — extraction script was a clean adaptation. Annex is informative only (no normative controls to extract).

---

### WP-110 — ISO 27005 Risk Management ingestion ✅

> **Completed 2026-04-09.**

- YAML already available: `scripts/iso27005_inspection.yaml` (3011 lines, produced in a prior session)
- `scripts/load_iso27005_chunks.py`: framework loader; 315 nodes upserted under `iso-27005-2022` root
- Fills the risk vocabulary gap between COBIT governance language and NIST CSF GV.RM subcategories
- Cross-framework INFORMS edges completed in WP-132 ✅

**Retrospective:** Statement type classification required mapping `" should "` → `"informative"` (not `"guidance"`) to match the API's `STATEMENT_TYPES` frozenset. ISO 27005 uses "should" throughout as a guidance document rather than a requirements standard.

---

### WP — DIN SPEC 14027:2026-04 Corporate Security ingestion ✅

> **Completed 2026-04-09.** (Ingested as part of session work; no WP number assigned — treated as extension of WP-109/110 ingestion sprint.)

- `scripts/inspect_din14027.py`: PDF extractor (202 pages, German); normative clauses 1–20 (pages 12–45, 0-indexed); 87 clauses, 233 statements extracted to `scripts/din14027_inspection.yaml`
- `scripts/load_din14027_chunks.py`: framework loader; 321 nodes upserted under `din-spec-14027-2026` root
- German-language content — handled natively by `paraphrase-multilingual-MiniLM-L12-v2` embedding model
- Annex A (normative tabular requirements matrix) not extracted — too complex for line-based extraction; deferred
- Cross-framework INFORMS edges completed in WP-132 ✅

**Retrospective:** Two-sided PDF layout (recto/verso x0 shift) required per-page baseline normalisation. NFD-decomposed characters in German (ü, ä, ö) required NFC normalisation in the loader for `" soll "` / `" muss "` keyword matching.

---

### WP-108 — Threat report ingestion and cluster validation ✅

> **Completed 2026-04-09.**

- `ThreatReport`, `Threat`, `Asset` node types added to knowledge layer per ADR-002
- 15 new API endpoints: CRUD for ThreatReport/Threat/Asset, IDENTIFIES/MAPPED_TO_TECHNIQUE/TARGETS edges, vector search, traversal queries
- `threat_embedding_idx` (384-dim, cosine) created in Memgraph
- `scripts/extract_cti_threats.py`: fully automated CTI extraction pipeline — PDF → `pdfplumber.extract_words()` → sentence split → `CTIReportParser` (behaviour verb + ATT&CK keyword detection) → embedding dedup → Threat/IDENTIFIES/MAPPED_TO_TECHNIQUE writes
- `scripts/ingest_all_threat_reports.py`: orchestration for 6 reports (Verizon DBIR 2025, Cloudflare 2026, ENISA ETL 2025, BSI Lagebericht, Microsoft DDR 2025, Mandiant M-Trends 2026)
- `scripts/seed_assets.py` + `data/threats/assets.yaml`: 4 universal Asset reference nodes (IT/OT/IoT/IT-OT-integration)
- `scripts/validate_threat_clusters.py`: cluster coherence analysis — top threats by report coverage, ATT&CK coverage, unmitigated technique gaps
- `scripts/pdf_utils.py`: extracted shared `words_to_lines`/`line_text` helpers (previously duplicated across 6 inspect scripts)
- 45 tests: 38 unit + 7 integration, all passing
- New backlog items surfaced: WP-135 (shared ApiSettings), WP-136 (optional embedding passthrough on ThreatCreate)

**Retrospective:** Fully automated extraction approach (keyword→ATT&CK + embedding dedup) worked well — no manual YAML curation required. The `@field_validator` on `AssetCreate` caused a 422 vs 400 inconsistency caught by integration tests; resolved by updating the test to expect 422 (semantically correct — Pydantic fires before the route handler). The `/simplify` pass surfaced six copies of `words_to_lines`/`line_text` across inspect scripts — extracted to `pdf_utils.py` as the highest-value fix.

**WP-138 calibration note (2026-04-11):** Re-calibrated `--dedup-threshold` from 0.15 to **0.28** based on self-similarity analysis of the 364-threat corpus (`scripts/calibrate_threat_dedup.py`). Method: pairwise cosine distances over `Threat.embedding` (paraphrase-multilingual-MiniLM-L12-v2, 384-dim). The planned ATT&CK tag-overlap classifier was found invalid at validation — within/between distributions fully overlapped (within.p90=0.72, between.p10=0.49), and manual inspection confirmed pairs classified as "within" were semantically unrelated (F2 pre-mortem failure confirmed). Pivoted to cross-report nearest-neighbour analysis: for each Threat, its nearest neighbour from a *different* ThreatReport. This correctly surfaces dedup candidates. Cross-report NN distances start at 0.189 with a natural gap around 0.25–0.28; 0.28 chosen after simulating at 0.25 (8 merges, mostly within-report noise), 0.28 (15 merges, all genuine paraphrases on manual inspection), and 0.30 (18 merges, includes false positives). Pair-rerun simulation on Verizon+ENISA predicted 15 merges at 0.28 vs. 0 at 0.15 (baseline was 0 — the 7 "deduplicated" in WP-108 were same-sentence duplicates within a single report, not cross-report). OCR noise heuristic (`_ocr_noise_heuristic`) flagged ~51% of the corpus — over-aggressive for real threat sentences containing statistics; used as a diagnostic flag only, not a filter in the chosen threshold. The existing 364 Threat nodes retain their original graph shape; WP-138b will optionally apply a merge pass under the new default. Re-run `scripts/calibrate_threat_dedup.py --verify` after any new report ingestion or embedding-model change; drift >0.03 triggers re-calibration.

---

### WP-138 — Calibrate threat deduplication threshold ✅

**Completed 2026-04-11.**

- New `scripts/calibrate_threat_dedup.py`: calibration spike with `--histogram`, `--pair-rerun`, `--recommend`, `--verify`, `--sample-for-review` subcommands; `--json` flag for machine-readable output; `--exclude-noise` and `--technique-mode` options
- New `tests/test_wp138_threat_dedup_calibration.py`: 11 unit tests (8 parametrised `classify_pairs` cases, 3 `_auto_recommend` cases, order-invariance test, OCR heuristic test) + 3 `@pytest.mark.integration` subprocess tests; all passing
- `scripts/extract_cti_threats.py`: default `--dedup-threshold` raised from 0.15 to 0.28; calibration comment added referencing embedding model and WP-138
- `BACKLOG.md`: WP-108 retrospective extended with calibration note; WP-138b added to prioritised table
- Methodology note: ATT&CK tag-overlap classifier was found invalid at validation (within/between distributions fully overlapping, F2 pre-mortem failure confirmed). Pivoted to cross-report nearest-neighbour analysis which correctly identified dedup candidates at 0.189–0.26 cosine distance. Chosen threshold 0.28 validated by `--pair-rerun` simulation (15 merges vs. 0 at baseline, all genuine paraphrases on manual inspection).
- `ingest_all_threat_reports.py` unchanged — inherits new default via argparse automatically

**Retrospective:** The F2 pre-mortem failure mode (tag-overlap classifier invalid) fired exactly as predicted and was caught early via the `--sample-for-review` subcommand before any threshold was committed. The cross-report NN pivot was not planned but resolved the calibration problem cleanly. OCR noise heuristic proved over-aggressive (~51% flag rate); left as a diagnostic tool only and not used as a filter. Spike scope held cleanly — no schema changes, no new endpoints, no external dependencies.

---

### WP-SEC-R15 — STIX SHA-256 verification in `scripts/ingest_attack.py` ✅

**Completed 2026-04-11.** R2-tier hardening item from the post-WP-SEC-3 threat analysis.

- Added `_verify_stix_sha256(path: Path, skip: bool = False) -> None` helper: reads `data/frameworks/attack-stix-pins.json`, looks up the expected SHA-256 by filename, computes `hashlib.sha256(path.read_bytes()).hexdigest()`, exits with a clear error message on mismatch or missing pin.
- `_resolve_stix_path()` now calls `_verify_stix_sha256()` in all three branches: user-supplied file (if pinned), cached default path, and fresh download.
- Added `--skip-sha256-check` CLI flag for emergency bypass (prints warning to stderr).
- TODO comment at old line 336 replaced with the actual verification call.
- 9 tests in `tests/test_wp_sec_r15_stix_verification.py`: clean pass, mismatch exit, missing pin exit, malformed pin file, skip warning, cached-path verification, tampered cache exit, download verification, skip flag bypass. All passing.
- Ambient chore deferred: `scripts/ingest_attack_mitigations.py` lacks the same SHA-256 check — add to Ambient Chores when next touching that script.

**Retrospective:** The implementer's edits existed only in context and were never persisted to disk — caught immediately by the verifier's Gate 1 (import test). The Group C deploy-checklist functioned exactly as intended: failed fast on a missing symbol, no false PASS. The `sys.modules` stub pattern for `mitreattack` (system Python lacks it) is now an established pattern for this test suite.

---

### WP-SEC-R10 / WP-SEC-R12 — `.claude/settings.json` permissions hardening ✅

**Completed 2026-04-11.** Two R2-tier hardening items from the post-WP-SEC-3 threat analysis.

- **R10 (destructive git to ask-tier):** 11 patterns added to `permissions.ask`: `git push --force*`, `git push --force-with-lease*`, `git push -f*`, `git reset --hard*`, `git clean -f*`, `git branch -D *`, `git branch -d *`, `git checkout .*`, `git checkout -- *`, `git restore .*`, `git restore --source*`. These were previously covered by the blanket `Bash(git *)` allow rule; the new ask entries override it (deny→ask→allow precedence confirmed in Phase 0 probe P0.2).
- **R12 (supply-chain installs to ask-tier):** 11 patterns added: `wget*`, `uv pip install*`, `uv add*`, `npm install*`, `npm i *`, `yarn add*`, `pnpm add*`, `cargo install*`, `go install*`, `gem install*`, `brew install*`. `pip install *` was already in ask. Curl-pipe-to-shell (`curl * | sh`) is not achievable via prefix matching (P0.3 confirmed) — curl and wget individually gated in ask-tier breaks the attack chain at the first command.
- Both WPs applied in a single Edit call. 8 structural tests in `tests/test_wp_sec_r_settings.py`: all passing. `jq empty` confirms valid JSON.

**Retrospective:** Phase 0 probe P0.3 was essential — it ruled out four curl/wget pipe patterns that the original plan included but which cannot be matched by Claude Code's prefix-only Bash pattern syntax. Documented as a known gap. The Phase 0 investment (5 probes) prevented three categories of late-stage implementation failure.

---

### WP-SEC-R1 / WP-SEC-R3R4 / WP-SEC-R5 — `hooks/_filters.py` hardening ✅

**Completed 2026-04-11.** Three R2-tier hardening items from the post-WP-SEC-3 threat analysis, applied in a single sprint pass.

- **R1 (NFKC + bypass detection):** `contains_injection()` now applies `unicodedata.normalize("NFKC", text)`, strips zero-width characters (U+00AD, U+200B–D, U+FEFF), and collapses whitespace runs before the literal scan. A pre-computed `_INJECTION_LITERALS_DENSE` module constant strips all whitespace, NBSP (U+00A0), and hyphens from each literal at load time; `contains_injection()` also builds a dense form of the input and compares in that space. This closes space-insertion (`<system - reminder>`), soft-hyphen (`<system­reminder>`), and NBSP bypass vectors without mutating the original text.
- **R3R4 (extended redaction):** `_REDACT_PATTERNS` extended with: AWS AKIA/ASIA access keys, Slack xox tokens, Stripe sk_live/rk_live, GitLab glpat, GitHub fine-grained PATs, PEM private key headers, HTTP basic auth URLs, JSON KV form (`"password": "value"`), YAML KV form (`password: value`), CLI flag form (`--password value`). Minimum 8-char value anchoring prevents false positives on short dev tokens. Corpus regression test runs all new patterns against `data/frameworks/**/*.yaml` — zero redactions on clean framework text.
- **R5 (sensitive-path globs):** `_SENSITIVE_FILENAME_GLOBS` extended with 13 entries (`.netrc`, `.pgpass`, `.my.cnf`, `*.p12`, `*.pfx`, `*.jks`, `*.keystore`, `*.gpg`, `secring.*`, `logins.json`, `cookies.sqlite`, `login data`, `*.kdbx`). `_SENSITIVE_PATH_GLOBS` extended with 6 entries (`*/.aws/*`, `*/.kube/*`, `*/.gnupg/*`, `*/.mozilla/firefox/*/logins.json`, `*/Chrome/*/Login Data`, `*/keyrings/*`).
- 31 tests in `tests/test_wp_sec_r_filters.py`: 8 injection bypass tests, 13 redaction pattern tests, 8 sensitive-path tests, 2 corpus regression tests. All passing.

**Retrospective:** The dense-form check was the key design insight — NFKC normalisation alone is insufficient for space-inserted tags because the hyphen in `<system-reminder>` is preserved as-is in the normalised text. Pre-computing `_INJECTION_LITERALS_DENSE` at module load (not per-call) was caught by `/simplify` and fixed before commit. Corpus regression tests confirmed zero false positives on the live framework YAML corpus, which was the highest-risk concern (F2.1/F2.2 from the pre-mortem).

---

### WP-111 — M-Series ATT&CK mitigations ingestion

#### Motivation

MITRE ATT&CK Enterprise includes 43 `course-of-action` mitigation objects (M-XXXX) alongside the techniques. These describe high-level countermeasures in defensive language ("Restrict use of privileged accounts", "Use MFA") — vocabulary that is semantically much closer to ISO/NIST/COBIT controls than raw ATT&CK technique descriptions. The STIX bundle already downloaded at `data/frameworks/enterprise-attack-17.0.json` contains both the mitigation objects and the `mitigates` relationships linking them to specific techniques. This WP requires no new data sources.

Creating M-Series nodes and their MITIGATES edges to ATT&CK techniques provides:
1. The first edges that connect ATT&CK to the rest of the graph (via embedding similarity to ISO/NIST/COBIT)
2. A human-readable intermediate layer between adversary techniques and compliance controls
3. Infrastructure for WP-112's SP 800-53 bridge and WP-108's threat report ingestion

#### Scope

- Parse `course-of-action` STIX objects from `enterprise-attack-17.0.json`
- Create `Framework` nodes: `attack-enterprise.M1017`, etc. with `level=mitigation`, `domain=enterprise`, `external_id=M1017`
- Create `CONTAINS` edges from the ATT&CK root node (`attack-enterprise-v17`) to each mitigation node
- Parse `relationship` STIX objects where `relationship_type == "mitigates"` — create `MITIGATES` edges: M-Series node → ATT&CK technique node
- Run embedding similarity (reuse `create_cross_framework_informs.py` logic) between M-Series nodes and ISO/NIST/COBIT Framework nodes to create `INFORMS` edges
- Use same 0.55 threshold as WP-105; calibrate against known M-Series → control overlaps if possible

#### Out of scope

- D3FEND (WP-114)
- SP 800-53 (WP-112)
- Any Threat or ThreatReport nodes (WP-108)

#### Data sources

- `data/frameworks/enterprise-attack-17.0.json` — already present (downloaded in WP-106)
- No additional downloads required

---

### WP-112 — SP 800-53 Rev 5 ATT&CK bridge ingestion

#### Motivation

After WP-111, ATT&CK techniques are connected to M-Series mitigation nodes. But M-Series nodes (43 total) only bridge ATT&CK to the rest of the graph via embedding similarity — there is no authoritative structured path from ATT&CK techniques to ISO/NIST/COBIT controls. NIST SP 800-53 Rev 5 provides that bridge:

- CTID (`center-for-threat-informed-defense/attack-control-framework-mappings`) publishes a machine-readable mapping of SP 800-53 Rev 5 controls → ATT&CK techniques with `MITIGATES` semantics
- NIST publishes a SP 800-53 ↔ CSF 2.0 crosswalk as part of the OLIR/Informative References programme

Combined, these produce the traversal path:
```
ATT&CK technique ←[MITIGATES]← SP800-53 control →[INFORMS]→ NIST CSF subcategory →[INFORMS]→ ISO 27001 clause
```

SP 800-53 is "traversal glue" — it does not need to be a primary browsable surface; it just needs to exist so multi-hop queries can traverse it.

#### Scope

- Download NIST SP 800-53 Rev 5 OSCAL JSON from `usnistgov/oscal-content` (public GitHub, ~2MB)
- Ingest ~1,100 base controls as Framework nodes: `sp800-53r5.AC-1`, `sp800-53r5.AC-2`, etc. with `level=control`, `external_id=AC-1`
- Do NOT ingest enhancement statements as separate nodes (keep granularity manageable)
- Download CTID `attack-control-framework-mappings` for SP 800-53 Rev 5 (JSON, public GitHub)
- Create `MITIGATES` edges: SP800-53 node → ATT&CK technique node (from CTID mappings)
- Download/use NIST SP800-53 ↔ CSF 2.0 crosswalk (NIST OLIR programme, CSV/JSON)
- Create `INFORMS` edges: SP800-53 node → NIST CSF 2.0 subcategory node (from NIST crosswalk)
- Run embedding similarity between SP 800-53 nodes and ISO 27001 nodes for additional `INFORMS` edges (supplementing the structured crosswalk)

#### Out of scope

- SP 800-53 enhancement statements (too granular — base controls only)
- SP 800-53 as a Norm/compliance object (treat as Framework only in this WP)
- SP 800-53 → COBIT direct mapping (allow graph traversal to handle this)

#### Data sources

- NIST OSCAL content: `https://github.com/usnistgov/oscal-content` (public)
- CTID mappings: `https://github.com/center-for-threat-informed-defense/attack-control-framework-mappings` (public)
- NIST OLIR SP800-53/CSF crosswalk: NIST website (public)

---

### WP-113 — Security architecture layer: SABSA, precepts, and business attributes

#### Motivation

ADR-002 defines a strategic threat-to-business traversal path:

```
Threat → [JEOPARDISES] → Precept → [FULFILS] → BusinessAttribute
```

This path enables the board-level question: *"Which business objectives face the most active threats?"* — traversable without descending into the control tree. Neither `Precept` nodes nor `BusinessAttribute` nodes exist yet.

`BusinessAttribute` nodes are grounded in the SABSA (Sherwood Applied Business Security Architecture) Business Attribute Profile — the canonical set of security-relevant business outcomes. SABSA is the architectural framework that ADR-002's node model was designed around. WP-113 should be approached with SABSA as the primary lens, then broadened to include other architectural frameworks that feed the precept/attribute model.

#### Scope

**Component 1 — SABSA Business Attribute Profile:**
- Seed canonical SABSA Business Attribute nodes: confidentiality, integrity, availability, accountability, assurance, reliability, safety, and the higher-order business attributes they compose (customer trust, regulatory standing, operational continuity, competitive advantage, brand reputation)
- Wire SABSA's conceptual security architecture as a Framework (the six SABSA layers: contextual, conceptual, logical, physical, component, operational) if text is available and adds value
- Create `FULFILS` edges: universal Precepts → Business Attributes

**Component 2 — Universal Precept seeding:**
- Derive ~30–50 universal Precept nodes from cross-framework convergence: obligations that ISO 27001, NIST CSF, COBIT 2019, and SP 800-53 all independently demand (access control, data protection, audit/logging, incident response, risk assessment, supply chain security, etc.)
- Wire `REQUIRES` edges from existing Norm nodes (ISO 27001 as a Norm if mandated) to Precepts
- Wire `ADDRESSES` edges from top-level Control nodes to Precepts (requires Control tree to have content — may be seeded manually or from an org's control framework)

**Component 3 — Additional architectural frameworks (assess fit, ingest selectively):**
- **C2M2 (Cybersecurity Capability Maturity Model):** 10 domains with maturity-level descriptors. Useful for capability gap analysis alongside compliance gap analysis. Assess whether ingesting as Framework nodes adds value vs treating as metadata on Control nodes.
- **CIS Controls v8:** 18 controls with implementation groups (IG1/IG2/IG3). Highly practical. Strong overlap with SP 800-53 and NIST CSF — likely to produce dense INFORMS edges. May serve as a better "glue" between ATT&CK and governance frameworks than SP 800-53 for some use cases.
- **Zero Trust Architecture (NIST SP 800-207):** Principles rather than controls — more suitable as Precept-level content than as Framework nodes.
- **TOGAF Security Architecture domain:** Relevant for enterprise architecture alignment. Lower priority unless a TOGAF-aligned org context is added.

#### Out of scope

- Full SABSA methodology ingestion (the full SABSA framework is proprietary and lengthy)
- Org-specific Control tree population (this WP seeds universal/reference content only)
- `JEOPARDISES` edges (Threat → Precept) — these belong in WP-108 once Threat nodes exist

---

### WP-114 — D3FEND defensive technique ingestion

#### Motivation

MITRE D3FEND is a knowledge graph of cybersecurity countermeasures (~500 defensive techniques) published as an OWL ontology. It complements ATT&CK by describing *how to defend* at a technical level. D3FEND's `d3f:counters` relationships link each defensive technique to the ATT&CK offensive techniques it counters.

After WP-108 (threat reports) activates the full threat intelligence model, D3FEND adds a second, more granular defensive pathway alongside M-Series for SOC-level analysis. D3FEND's own informative references also map to SP 800-53 and NIST CSF, providing alternative non-embedding bridge paths.

#### Scope

- Download D3FEND ontology JSON-LD from `https://d3fend.mitre.org/ontologies/d3fend.json` (public)
- Create a D3FEND root Framework node + hierarchy (Harden, Detect, Isolate, Deceive, Evict, Model)
- Create ~500 Framework nodes (level=defensive-technique) with `external_id=D3-XXX`, `domain=enterprise`
- Create `MITIGATES` edges: D3FEND technique → ATT&CK technique (from `d3f:counters` relationships)
- Use D3FEND's own SP 800-53/NIST CSF informative references for structured `INFORMS` edges where available (prefer structured over embedding for known mappings)
- Run embedding similarity for remaining gaps against ISO/NIST/COBIT/SP800-53

#### Out of scope

- D3FEND Digital Artifacts (the `d3f:DigitalArtifact` taxonomy) — relevant for future Asset modelling but out of scope here
- D3FEND ICS/OT coverage (focus on enterprise)

---

### WP-116 — Migrate episodic Memory embeddings to `paraphrase-multilingual-MiniLM-L12-v2`

#### Motivation

WP-094 introduced `KNOWLEDGE_EMBEDDING_MODEL` (defaulting to `paraphrase-multilingual-MiniLM-L12-v2`) for the knowledge layer, deliberately leaving episodic Memory nodes on `all-MiniLM-L6-v2`. The two-model split was the right short-term call — it decoupled migration timelines — but the long-term cost is:

- Cross-lingual episodic search fails silently (e.g. a memory stored in English is not retrieved by a Welsh query)
- The two embedding spaces differ in dimension (384 vs 768) and metric geometry, making cross-layer cosine similarity between Memory and Control/Chunk nodes unreliable
- `long_rest` edge rediscovery uses the episodic index; non-English content creates systematic gaps

Migrating episodic Memory nodes to the multilingual model closes all three gaps.

#### Scope

1. **Confirm model dimension**: load `paraphrase-multilingual-MiniLM-L12-v2` via `get_embedding_dimension()` and verify (expected 768; confirm before proceeding)
2. **Drop and recreate `mem_embedding_idx`**: the index cannot be resized in-place — must drop (`DROP VECTOR INDEX mem_embedding_idx`) and recreate at the new dimension via `init_schema.py`. Update `MEMORY_INDEX_CAPACITY` default in `.env.example` if needed (768-dim vectors consume more memory per slot)
3. **Re-embed all Memory nodes**: extend or reuse `scripts/migrate_embeddings.py` to re-embed Memory nodes in batches using `EMBEDDING_MODEL`. The script already handles knowledge-layer nodes; add a `--memory` flag
4. **Update `.env.example`**: change `EMBEDDING_MODEL` default to `paraphrase-multilingual-MiniLM-L12-v2`
5. **Run `long_rest`** after migration to rebuild `RELATED_TO` edges using the new vector space (old edges were computed under the 384-dim geometry and will have incorrect weights)
6. **Integration tests**: verify `mem_embedding_idx` dimension matches the new model; verify search returns results for a non-English query against an English memory

#### Out of scope

- Cross-layer vector joins between Memory and Control/Chunk nodes (that would require a separate WP; this WP only aligns the index dimensions as a prerequisite)
- Changing `KNOWLEDGE_EMBEDDING_MODEL` (it already uses the multilingual model)

---

### WP-117 — Autonomous dedup: define auto-merge threshold and wire into long_rest

#### Motivation

The near-duplicate review queue is now surfaced on every long_rest run, but acting on it still requires a human to call the merge endpoint. This is the wrong default for a system that is meant to maintain itself autonomously — the dedup queue will grow between sessions and only shrink when a human happens to check.

If the fabric is to function as a genuine agent companion with its own agency, it must be capable of self-maintenance: consolidating redundant memories without waiting for human intervention. The threshold question is the critical design decision — get it wrong and the system silently discards information it should have kept.

#### Design decisions required

1. **Threshold validation**: Before choosing an auto-merge threshold, sample the current corpus at multiple thresholds (0.95, 0.97, 0.99) and manually inspect the pairs at each level. The goal is to identify the floor above which both members of a pair are genuinely the same memory expressed in different words — not merely topically similar. Document findings as a decision record.

2. **Merge semantics**: Auto-merge must preserve provenance. The canonical node (higher importance, or older if equal) absorbs the other: its `fact` is kept, the merged node's `strand_ids`, `tags`, `person_ids`, `related_ids`, and `RELATED_TO`/`LEADS_TO` edges are transferred, and the discarded node is archived (not deleted) with a `merged_into` pointer. This is identical to the existing manual merge path — WP-117 simply calls it programmatically.

3. **Opt-in default**: `AUTO_MERGE_THRESHOLD` defaults to `None` (disabled) so the feature is safe to deploy before the threshold is validated. Operators enable it explicitly.

#### Scope

- Add `auto_merge_threshold: Optional[float] = None` to `Settings`
- Add an auto-merge step to `long_rest` (after near-duplicate review, step 7): for each pair above `auto_merge_threshold`, call the existing merge logic; record each merge in the maintenance log with `operation=auto_merge`, both node IDs, similarity score, and the surviving node ID
- Add `auto_merged_count` to the `long_rest` return dict, CLI output, and MCP summary
- Integration test: seed two near-identical memories, run long_rest with `auto_merge_threshold=0.97`, assert one is archived with `merged_into` set

#### Out of scope

- Changing the existing manual merge endpoint or its semantics
- Auto-merge for the knowledge layer (Control/Chunk deduplication is a separate concern)

---

### WP-126 — PostToolUse observer hook for automatic memory capture

#### Motivation

Memory capture in the current system requires the model or the user to explicitly call `memory add`. In practice this is inconsistently done — significant decisions, file edits, and discoveries are lost simply because the discipline to write them is absent. claude-mem's shadow observer pattern solves this by wiring a `PostToolUse` hook that automatically captures tool activity without requiring any in-session action from the model.

We can adopt the zero-friction capture idea without the full shadow-agent complexity: a lightweight hook script that fires after each tool use, detects meaningful events (file writes, file edits, significant bash commands), and POSTs a structured observation memory to the service. The result enters our graph with embeddings, strand membership, and decay — rather than a flat SQLite table — so all existing retrieval and analytics capabilities apply to it.

#### Scope

- Add a new optional memory `type` value: `observation` (alongside existing `fact`, `decision`, `insight`, `todo`, `event`)
- Add two optional array properties to the `Memory` node schema: `files_modified: list[str]` and `files_read: list[str]`, stored as Memgraph list properties
- Write a hook script `hooks/post_tool_use.py` that:
  - Receives the Claude Code `PostToolUse` hook payload (tool name, input, output, session metadata) on stdin as JSON
  - Filters out ephemeral/trivial calls: `Read` tool calls on files already read this session, empty `Bash` outputs, search results with no matches
  - For substantive events (file writes via `Write`/`Edit`, significant `Bash` commands, `WebFetch` that returned content), constructs a compact `fact` string and POSTs to `POST /memory` with `type=observation`, `files_modified`/`files_read` populated, `importance=2`, `agent_id` from env, and a `strand_ids` hint from a configurable default strand (e.g. `strand-core-health` or a new `strand-session-activity`)
  - On failure (service unreachable), logs to stderr and exits 0 (hook must not block the primary session)
- Register the hook in `.claude/settings.json` (or document the registration step for users)
- Add `GET /memory/search?files_modified=<path>` filter support — extend the search Cypher query to accept an optional `files_modified` filter param that matches memories where the path appears in the `files_modified` list property
- Unit test: hook script correctly parses `Write` tool payload and constructs the expected memory POST body
- Integration test: POST a memory with `files_modified=["memory_repo.py"]`, then call `GET /memory/search?files_modified=memory_repo.py` and assert the memory is returned

#### Out of scope

- A full shadow Claude subprocess (as used by claude-mem) — the lightweight hook is the target for this WP
- Automatic strand inference from file paths (can be a follow-on WP)
- Hook registration automation (document manual step; automate in a follow-on)

---

### WP-127 — `files_modified` and `files_read` properties on Memory nodes

#### Motivation

There is currently no way to ask the fabric "what do I know about changes to `memory_repo.py`?" or "what have I read about `knowledge_routes.py`?". Adding file provenance as first-class properties on Memory nodes enables file-scoped retrieval — valuable for pre-edit context injection (load relevant memories before touching a file) and for reconstructing the history of decisions around a specific module.

This WP delivers the schema and API surface for file provenance. WP-126 (the observer hook) writes the properties automatically; they can also be set manually via the existing `POST /memory` and `PATCH /memory/{id}` endpoints.

#### Scope

- Add `files_modified: Optional[list[str]] = None` and `files_read: Optional[list[str]] = None` to `AddMemoryRequest` and `UpdateMemoryRequest` Pydantic models
- Persist both fields to the `Memory` node in Memgraph as list properties (Memgraph supports list properties natively)
- Include both fields in `MemoryResponse`
- Add optional `files_modified` and `files_read` query params to `POST /memory/search` (the structured search body) — each filters to memories where the given path appears anywhere in the respective list property
- Add a dedicated `GET /memory/by-file?path=<path>&role=modified|read|any` endpoint that returns memories filtered by file path without requiring a semantic query
- Update `memory_client/client.py` to pass the new fields through `add_memory()` and `update_memory()`
- Unit tests: `AddMemoryRequest` serialises `files_modified` correctly; search filter Cypher is correct for list-contains predicate
- Integration test: add a memory with `files_modified=["memory_repo.py"]`, call `GET /memory/by-file?path=memory_repo.py`, assert it is returned

#### Out of scope

- Automatic file provenance capture (that is WP-126)
- Full-text search within file paths (exact match and prefix match are sufficient)

---

### WP-128 — Tiered search MCP tool (compact index + selective detail fetch)

#### Motivation

The current `POST /memory/search` endpoint returns full memory text for every result. When used via MCP, this floods the context window with detail that the model often does not need — it may only need to scan titles and importance scores to decide which 2–3 memories are actually relevant. claude-mem's three-layer search pattern (`search → timeline → get_observations`) achieves ~10x token savings by separating the index scan from detail retrieval.

Adding a tiered search surface lets agents scan cheaply and fetch selectively, reducing token cost on every search that doesn't need full detail.

#### Scope

- Add `GET /memory/search/index` endpoint: accepts the same filter params as `POST /memory/search` plus a `q` text query param; returns a compact list of matches with fields `id`, `fact` (first 80 chars), `type`, `importance`, `strength`, `strand_ids`, `created_at` only — no `so_what`, no `tags` detail, no embedding
- Add `POST /memory/batch` endpoint: accepts `{"ids": ["uuid1", "uuid2", ...]}` (max 50); returns full `MemoryResponse` objects for each ID
- Update MCP tool definitions to document the two-step pattern: use `search_index` to get candidate IDs, then `get_memories` with selected IDs to retrieve full detail
- Update `memory_client/client.py` with `search_index()` and `get_memories_batch()` methods
- Unit tests: `search_index` returns only the compact field set; `batch` correctly retrieves multiple memories by ID
- Integration test: add 5 memories, call `search_index`, verify response is compact; call `batch` with 3 of the IDs, verify full detail returned

#### Out of scope

- Changes to the existing `POST /memory/search` endpoint (stays as-is for backwards compatibility)
- A three-stage `timeline` intermediate step (the compact index + batch fetch is sufficient for our graph model, where `RELATED_TO` traversal already provides neighbourhood context)

---

### WP-130 — Concept tags on Memory nodes

#### Motivation

Free-form `tags[]` on memories capture topic labels but not the *epistemic role* of a memory — whether it is a gotcha to avoid, a pattern to follow, a trade-off rationale, or an explanation of why something works. claude-mem's concept taxonomy (`how-it-works`, `why-it-exists`, `what-changed`, `problem-solution`, `gotcha`, `pattern`, `trade-off`) makes this distinction explicit and filterable.

Adding a `concepts[]` array alongside `tags[]` lets agents search for "all gotchas about Memgraph" or "all patterns for Cypher queries" independently of subject-matter tags.

#### Scope

- Define a `MemoryConcept` enum in the service: `how_it_works`, `why_it_exists`, `what_changed`, `problem_solution`, `gotcha`, `pattern`, `trade_off`, `decision_rationale`, `open_question` (9 values — drop claude-mem's `facts` and `narrative` which are structural, not epistemic)
- Add `concepts: Optional[list[MemoryConcept]] = None` to `AddMemoryRequest`, `UpdateMemoryRequest`, and `MemoryResponse`
- Persist `concepts` as a list property on `Memory` nodes
- Add optional `concepts` filter to `POST /memory/search` (any-of matching: memory is included if it has at least one of the requested concept types)
- Mirror `MemoryConcept` in `memory_client`
- Unit test: `AddMemoryRequest` with `concepts=["gotcha"]` serialises correctly; search with `concepts=["gotcha", "pattern"]` generates correct Cypher `ANY(c IN m.concepts WHERE c IN [...])` predicate
- Integration test: add a memory with `concepts=["gotcha"]`, search with `concepts=["gotcha"]`, assert it is returned; search with `concepts=["pattern"]`, assert it is not

#### Out of scope

- Automatic concept inference from memory text (LLM-free constraint; concepts are set by the writing agent)
- Concept-based analytics (would be a follow-on analytics WP)

---

### WP-131 — Retrieval feedback signal and observation ROI tracking

#### Motivation

The fabric currently has no signal for whether a memory was actually useful when retrieved. Decay and reinforcement are driven by explicit recall events, but there is no passive signal from the retrieval path itself. claude-mem's `observation_feedback` table and `relevance_count` column lay the groundwork for Thompson Sampling — tracking which memories are retrieved and acted upon. While full Thompson Sampling is out of scope, the feedback signal is worth adding as the foundation for future reinforcement learning on retrieval quality.

Additionally, tracking the token cost of producing observation memories (from WP-126's hook) provides a simple ROI metric: did this automatically captured observation ever get retrieved? This is the same `discovery_tokens` concept from claude-mem, adapted to our graph model.

#### Scope

- Add a `POST /memory/{id}/feedback` endpoint accepting `{"signal": "retrieved" | "used" | "irrelevant", "session_id": str, "agent_id": str}` — appends the signal to a `retrieval_feedback` list property on the Memory node (capped at 50 entries, same ring-buffer pattern as `operation_log`)
- Add `retrieval_count` (int, default 0) and `last_retrieved_at` (datetime) properties to Memory nodes; increment both whenever `GET /memory/{id}` or `POST /memory/search` returns the memory (existing search path)
- Add `observation_tokens` optional int property to Memory nodes — set by the hook script (WP-126) to record the approximate token count of the tool output that generated the observation. Used to compute ROI: `retrieval_count / observation_tokens`
- Add `GET /memory/feedback/stats` endpoint returning aggregate retrieval stats: total memories with `retrieval_count > 0`, top-10 by `retrieval_count`, memories with `retrieval_count = 0` and age > 30 days (candidate for archive)
- Unit test: `POST /memory/{id}/feedback` appends signal and increments `retrieval_count`
- Integration test: add a memory, search for it (should increment `retrieval_count`), POST feedback, verify `retrieval_feedback` list contains the entry

#### Out of scope

- Thompson Sampling or automated reinforcement based on feedback signals (future WP)
- Modifying decay rates based on feedback (would interact with the Ebbinghaus curve in non-obvious ways; design separately)
- Feedback UI (stats endpoint is sufficient for v1)

---

### WP-139 — CLI and API shared-infrastructure DRY pass

> Supersedes: WP-023, WP-025, WP-026, WP-020, WP-021

#### Motivation

Five individually-scoped cleanup WPs all target the same infrastructure spine: `main.py`, `knowledge_routes.py`, `cli.py`, and `memory_repo.add_memory`. Bundling them into a single focused DRY pass reduces per-WP overhead and gives the work coherent scope: a single "shared-infrastructure quality" deliverable rather than five narrow edits.

#### Scope

1. **WP-023** — Extract `get_session` context manager for 503 handling in `main.py` and all 23 handlers in `knowledge_routes.py`.
2. **WP-025** — Extract shared CLI error handler: 22+ identical `except httpx.*` blocks in `cli.py`; add missing `HTTPStatusError` handling to the 4 new knowledge commands from WP-074.
3. **WP-026** — Mirror `MemoryType` enum in `memory_client` package for IDE completion without cross-package import.
4. **WP-020** — Replace per-item `session.run()` loops in `add_memory` with UNWIND queries for person/strand/related_ids writes. Add `related_ids` max-length cap (e.g. 20).
5. **WP-021** — Wrap `get_embedding()` calls in `run_in_executor` in async endpoints to prevent blocking the event loop under concurrent load.

#### Definition of Success

- [ ] `get_session` context manager extracts 503 handling across all main + knowledge handlers
- [ ] Single CLI error handler replaces all `except httpx.*` blocks; knowledge commands handle `HTTPStatusError`
- [ ] `MemoryType` importable from `memory_client` directly
- [ ] UNWIND queries replace loops in `add_memory`; `related_ids` capped
- [ ] `get_embedding()` wrapped with `run_in_executor`
- [ ] All existing tests pass; no behaviour change

---

### WP-140 — WP-049 code-review follow-ups

> Supersedes: WP-122, WP-123, WP-124

#### Motivation

Three pieces of code-review feedback from WP-049 were deferred as individual low-effort items. Bundling them into one WP avoids the overhead of three separate test plan + commit cycles for what is effectively one day's follow-up work on the same module.

#### Scope

1. **WP-122** — Add endpoint-level ordering assertions for companion and conversant anchors to `tests/test_wp049_companion_conversant_anchoring.py`. Tests should call `GET /memory/wake-up` and verify returned lists are in the expected order — not just check Cypher results directly.
2. **WP-123** — Add three unit tests for empty ABOUT-edge paths in `wake_up()`: (a) with `agent_id` set but no matching ABOUT-to-agent nodes → `companion_anchors: None`; (b) with `person_id` set but no matching ABOUT-to-person nodes → `conversant_anchors: None`; (c) `WakeUpResponse` serialises with `None` as JSON null (not `[]`).
3. **WP-124** — Document `WAKE_UP_COMPANION_ANCHOR_LIMIT` and `WAKE_UP_CONVERSANT_ANCHOR_LIMIT` in `.env.example` with commented-out lines following the existing numeric-limit pattern.

#### Definition of Success

- [ ] Endpoint-level ordering assertions exist and pass for companion and conversant anchors
- [ ] Three empty-ABOUT-edge unit tests exist and pass
- [ ] `.env.example` documents both WAKE_UP_*_LIMIT settings

---

### WP-141 — Ingest script hygiene

> Supersedes: WP-135, WP-136, WP-097

#### Motivation

Three small improvements to `scripts/` surfaced from WP-108 and WP-073 simplify reviews. All touch the same surface area (`scripts/`). Bundling avoids three separate plan-test-commit cycles.

#### Scope

1. **WP-135** — Extract a shared `ApiSettings(BaseSettings)` base class into `scripts/script_utils.py` (or equivalent). `CTISettings`, `SeedSettings`, `ETLSettings`, `IngestSettings`, `LoadSettings` are all identical two-field pydantic-settings classes and should inherit from one shared base.
2. **WP-136** — Add optional `embedding: list[float] | None` field to `ThreatCreate`. Allows callers (e.g. `extract_cti_threats.py`) to pass the vector already computed during dedup search, halving encode calls when the embedding cache is cold.
3. **WP-097** — Extend `chunk_markdown` in `scripts/chunkers.py` to treat `# ` (H1) headings as section boundaries, not just `## ` and `### `.

#### Definition of Success

- [ ] `ApiSettings` base class extracted; all identical settings classes inherit from it
- [ ] `ThreatCreate.embedding` optional field added; `extract_cti_threats.py` passes embedding on dedup hit
- [ ] `chunk_markdown` flushes on `# ` H1 headings as well as `## ` and `### `
- [ ] All existing ingest tests pass

---

### WP-142 — MemFabric service startup hardening

#### Motivation

Service startup is currently too brittle across environments. `docker compose up -d` starts the Memgraph containers, but does not by itself guarantee that the FastAPI memory service is actually reachable on port 8000. Separately, `python -m memory_service.main` only loads the app module and does not launch the HTTP server. This creates ambiguous operational state and makes Claude Code baseline verification look flaky even when recovery/import tooling is correct.

#### Scope

1. Define one canonical local startup path for the API service and document it explicitly.
2. Provide a supported launcher for the HTTP service, for example `uvicorn memory_service.main:app --host 0.0.0.0 --port 8000`.
3. Decide whether the API service should be part of `docker compose` or remain a separate host/venv process, then remove the ambiguity from docs and scripts.
4. Add a health-check script or Make target that validates both Memgraph and the HTTP API are actually up.
5. Update any Claude Code / Mara integration docs that still imply `python -m memory_service.main` is a valid service launcher.

#### Definition of Success

- [ ] One documented startup path brings the HTTP API up reliably on port 8000.
- [ ] Health check clearly distinguishes container health from API-service health.
- [ ] No baseline or recovery workflow depends on an implicit or incorrect launcher.

---

### WP-143 — First-class Task nodes for commitment and backlog stewardship

#### Motivation

Task and commitment state is currently fragmented across multiple project-specific backlogs and lists. That makes it hard to answer both "what is the right next task in this project?" and "what is the right project to work on at all?" A first-class `Task` node model inside MemFabric would consolidate active commitments into the existing core substrate, support cross-project prioritisation, and avoid adding a separate task service purely to enable follow-through and backlog stewardship.

This WP also directly enables Mara's expectation-tracking function. The three-layer accountability model (tracking via cron + MemFabric, enforcement via pre-defined consequences, reminders via Telegram) has been designed but has had no operational data substrate to work with. `:Task` nodes are that substrate: expectations set in conversation need to be written to the fabric at the moment they are made, so that a cron-driven `mara-companion` agent has something to act on later. Without durable commitment records, the accountability layer can observe but cannot enforce.

The key insight: most task systems fail because they are passive — nothing happens if you ignore them. `:Task` nodes with `committed_at` / `committed_by` fields give the cron job a live signal: "this commitment was made, by this agent, at this time, and has not been updated since." That is what provides teeth.

#### Scope

1. Add a `Task` graph model with a stable `id` plus core fields:
   - `title`, `description`
   - `status` — `open | active | blocked | done | abandoned`
   - `priority` — numeric score (mirrors the Value/Effort scoring already in use across project backlogs)
   - `urgency` — separate from priority; allows "low priority but time-sensitive" to surface correctly
   - `due_at` — optional; required for the accountability cron to have a trigger
   - `snooze_until` — optional recurrence/deferral marker
   - `created_at`, `updated_at`
   - `committed_at` — when the expectation was explicitly set; distinct from `created_at` because a task can exist for weeks before a commitment is made; the accountability clock starts here
   - `committed_by` — agent_id that made the commitment; determines which agent is responsible for follow-up
   - `last_checked_at` — when Mara last surfaced this task; lets the cron detect staleness without re-scanning full state
   - `source_ref` — optional back-reference to the originating backlog item (e.g. `WP-025`, `JFLP-042`) for traceability
2. Add relationships:
   - `OWNED_BY` from `Task` to `Agent` and/or `Person`
   - `FOR_PROJECT` from `Task` to `Project` (use project string initially, migrate to proper `Project` node when WP-078 lands — `:Task` does not need to wait for WP-078)
   - `RELATES_TO` from `Task` to `Memory` and/or knowledge-layer nodes for context
   - optional task-to-task dependency edges such as `BLOCKS` / `DEPENDS_ON`
3. Expose CRUD and retrieval surfaces across API, CLI, and MCP so Claude-side skills can create, inspect, update, and prioritise tasks.
4. Support practical queries such as:
   - open tasks for the current project/agent
   - open commitments across all projects
   - highest-priority or highest-urgency open tasks
   - blocked tasks and their blockers
   - tasks with `committed_at` set but no `updated_at` change since — the staleness signal for the accountability cron
5. Keep the design aligned with the architectural principle of minimising operational dependencies: this WP exists so the future `commitment stewardship` skill can use MemFabric directly instead of requiring a separate tracker.

#### Schema note — `committed_at` vs `created_at`

These are intentionally separate fields. A task can be created speculatively (by a skill, a hook, or a planning session) without any commitment being made. The accountability layer only activates when `committed_at` is set — that is the moment Oliver explicitly agreed to do something. `committed_by` records which agent witnessed or facilitated the commitment, establishing provenance for follow-up.

#### Relationship to WP-078 (Project node CRUD)

`:Task` nodes are valuable independently of WP-078. Use `project` as a string property initially (consistent with how `add_memory` already handles project tagging). When WP-078 lands, migrate the string to a proper `[:FOR_PROJECT]->(:Project)` relationship. The two WPs are complementary but not sequentially dependent.

#### Out of scope

- Full Kanban or board UI
- External sync with Notion/Jira/Todoist/etc.
- Rich recurring-task scheduler semantics beyond a minimal recurrence marker

#### Definition of Success

- [ ] `Task` nodes exist as a first-class model with stable IDs and core state fields including `committed_at` and `committed_by`
- [ ] Task ownership and project linkage are queryable through graph relationships
- [ ] API, CLI, and MCP provide enough surface for Claude-side task retrieval and updates
- [ ] Cross-project queries can identify what to work on next across projects, not just within one project
- [ ] Staleness query works: tasks with `committed_at` set but no status change since — the cron accountability trigger
- [ ] The planned `commitment stewardship` skill can be explicitly defined as depending on this WP rather than a separate tracking service

---

### WP-144 — Containerise API service + Caddy TLS

#### Motivation

The FastAPI/uvicorn memory service runs as a bare process launched by `scripts/start-local-stack.sh`. Memgraph and Memgraph Lab are Docker containers with `restart: unless-stopped` and compose health checks — they survive WSL2 restarts automatically. The API does not. This causes session hook failures, MCP timeouts, and silent degraded-mode operation across all Claude Code projects whenever the service is not running.

Additionally, the API is HTTP-only (`http://localhost:8000`). Adding Caddy as a TLS reverse proxy gives a reliable `https://localhost:8443` endpoint alongside the existing HTTP one.

These two problems share the same fix: containerise the API service and wire it into docker-compose.yml.

#### Scope

1. **Dockerfile** — single-stage `python:3.12-slim` image; bind-mount HF model cache read-only; `libgomp1` system dep for PyTorch CPU; no `.env` baked in.
2. **Caddyfile** — `tls internal` local CA for `localhost:8443`; `auto_https off`; proxy to `api:8000` on Docker internal network.
3. **docker-compose.yml** — add `api` service (with health check, `restart: unless-stopped`, resource limits per WP-014) and `caddy` service; add `caddy_data`/`caddy_config` volumes.
4. **docker-compose.override.yml** — dev hot-reload override (git-ignored); bind-mounts source and adds `--reload`.
5. **scripts/start-local-stack.sh** — replace bare uvicorn launch with pre-flight checks (port 8000 free, HF cache present) + `wait_for_api`.
6. **Secret hygiene** — `env_file: .env` eliminated; only non-sensitive vars in compose `environment:` block; secrets passed at runtime via shell env.

#### Security notes

- `.env` is never injected via `env_file:` (avoids `docker inspect` leakage of crown jewels).
- `caddy_data` volume persists the local CA — do not run `docker compose down -v` unless prepared to re-import the CA cert.
- `docker-compose.override.yml` is git-ignored to prevent accidental production deployments with live-mounted source code.
- WP-010 (remote access) must use a real cert, not `tls internal`.

#### WP-014 ambient chore — applied here

Resource limits applied to both new services in docker-compose.yml:
- `api`: `mem_limit: 4g`, `cpus: "2.0"`, `pids_limit: 256`
- `caddy`: `mem_limit: 128m`, `cpus: "0.25"`, `pids_limit: 64`

> **Completed 2026-04-15.** Commit `5e0b770` on `master`. API containerised with `restart: unless-stopped`; Caddy v2.11.2 with Cloudflare DNS-01 plugin serving `https://memfabric.carr-it.net` with a real Let's Encrypt cert. All runtime URL references migrated from `http://localhost:8000`. `.env.example` crown-jewel restriction corrected in global and project settings.
>

---

### WP-145 — CalDAV ↔ Fabric bi-directional task sync

#### Motivation

Task nodes (WP-143) are the cross-project commitment store in the Fabric. But they are only accessible at the desk via Memgraph or the API. Nextcloud CalDAV is the canonical task store that already syncs to Betterbird (desktop) and mobile (via DAVx5). Making Fabric a derived projection of Nextcloud — with priority scoring, commitment tracking, and dependency edges — gives both mobile access and intelligence without duplicating the write surface.

#### Mental model

Tasks are commitments to reach a defined state, not time-allocation markers (that is what calendars are for). Two tiers:

- **First-order tasks** (synced to Nextcloud): project-level tasks ("Graph Memory Fabric", "Mara Skills Repository") and external tasks (anything without a `*:WP-*` source_ref). These appear in Betterbird and on mobile.
- **Second-order tasks / WPs** (Fabric only): work packages with `source_ref` matching `{slug}:WP-NNN`. Detail-level commitments managed at the desk. The project-level first-order task is the mobile-visible anchor; the WP queue inside Fabric answers "what's the path to that state?"

Conflict resolution: **Nextcloud wins** on title and status. Fabric retains value, effort, priority_score, and urgency.

#### Implementation

`tools/sync_caldav.py` — idempotent, `--dry-run` supported, `--direction {both,inbound,outbound}`.

**Inbound (Nextcloud → Fabric):**
- VTODOs with `X-FABRIC-TASK-ID` property: update matching Fabric Task node (title, status)
- VTODOs without `X-FABRIC-TASK-ID`: create new Fabric Task node; write UUID back to VTODO
- `STATUS:COMPLETED` → fabric `done`; triggers CHANGELOG write-back

**Outbound (Fabric → Nextcloud):**
- First-order Task nodes (no `*:WP-*` source_ref) without a matching VTODO → push as VTODO
- Fabric UUID stored in VTODO as `X-FABRIC-TASK-ID` for future idempotency

**CHANGELOG write-back:**
- On inbound completion, appends a `## WP-NNN — Title [date]` entry to the project-specific `CHANGELOG.md`
- Project root resolved via `source_ref` slug → `PROJECT_ROOTS` map in the script

**Credentials:** `~/.config/mara/nextcloud.env` — single source of truth, never duplicated.

---

### WP-147 — Strand health diagnostics and thin-strand capture prompts

#### Motivation

The graph holds 1,002 memories across 21 strands, but the distribution is heavily skewed. Companion Domain strands (protocols, projects, AI anchor) are dense and well-reinforced. Several Core Life Domain strands — `health`, `leisure-play`, `finances`, `house-home`, `learning-growth`, `friends` — are sparse: the fabric knows Oliver's trajectory but not his Tuesday. This creates a wake-up gap: Mara returns authoritative context on decisions and projects but cannot make conversation feel lived-in.

The CURIOSITY THREAD pattern already exists in the fabric as a workaround — individual insight memories that document an absence ("we don't know what makes Oliver laugh"). WP-147 turns this ad-hoc pattern into a first-class system.

#### Deliverables

**1. `GET /strand/health`**

Returns a health summary for every strand:

```json
{
  "strands": [
    {
      "id": "strand-core-leisure-play",
      "name": "Leisure & Play",
      "category": "Core Life Domains",
      "memory_count": 3,
      "mean_strength": 0.42,
      "mean_importance": 2.1,
      "last_written_at": "2026-03-21T...",
      "health": "thin"
    }
  ]
}
```

Health thresholds (configurable via env):
- `healthy`: ≥ 10 memories
- `thin`: 3–9 memories
- `empty`: 0–2 memories

**2. `GET /strand/{id}/capture-prompts`**

Returns 3–5 open questions for a strand, derived from:
- The strand's `description` and `category` fields
- Any existing CURIOSITY THREAD memories in that strand (tagged `curiosity-thread` or `open-question`)

No LLM call — template-based generation using strand-aware variable substitution. Example for `strand-core-leisure-play`:

```json
{
  "strand_id": "strand-core-leisure-play",
  "health": "thin",
  "prompts": [
    "What does a good weekend with Tanja look like?",
    "What have you been reading or watching lately that's stuck with you?",
    "Is there anything you've been meaning to pick back up that keeps getting pushed?"
  ],
  "curiosity_threads": ["<existing CURIOSITY THREAD memory IDs if any>"]
}
```

**3. Update `memory_client/COMPANION.md`**

Document the CURIOSITY THREAD pattern as a first-class memory type:
- When to write one (when you notice a gap that matters for relational texture)
- Required tags: `curiosity-thread`, `open-question`
- How capture-prompts uses them (threads surface as context in the prompts response)
- The principle: recording the shape of a gap is useful for retrieval — it surfaces in wake-up as a standing reminder

#### Implementation notes

- `GET /strand/health` is a simple Cypher aggregation: `MATCH (m:Memory)-[:IN_STRAND]->(s:Strand)` grouped by strand, supplemented with a `MATCH (s:Strand)` pass to include zero-memory strands.
- Template library lives in `memory_service/strand_prompts.py` — a dict keyed on strand ID with fallback to category-level templates for any strand not explicitly listed.
- No new dependencies.

#### Acceptance criteria

1. `GET /strand/health` returns all 21 strands with correct counts and health classifications
2. Thin/empty strands are easily identifiable in the response
3. `GET /strand/{id}/capture-prompts` returns context-aware prompts for any strand
4. Existing CURIOSITY THREAD memories surface in the `curiosity_threads` field
5. `COMPANION.md` updated with CURIOSITY THREAD pattern documentation
6. Unit tests cover health classification thresholds and prompt generation
7. Integration test verifies live counts against actual strand data

---

### WP-146 — Windows Task Scheduler entry for CalDAV sync

#### Motivation

WSL cron (set up in WP-145) only fires while the WSL2 instance is running. After a Windows restart, cron is silent until a terminal opens WSL. A Windows Task Scheduler entry bridges this gap — it starts WSL and runs the sync on logon and every 4 hours regardless of whether a terminal is open.

#### Implementation

Create a scheduled task via Task Scheduler UI or `schtasks`:

```powershell
schtasks /create /tn "CalDAV-Fabric-Sync" /tr "wsl -e bash -c 'python3 /home/oliver/projects/graph-memory-fabric/tools/sync_caldav.py >> /tmp/sync_caldav.log 2>&1'" /sc HOURLY /mo 4 /ru oliver /it /f
```

Add a second trigger for on-logon:
- Task Scheduler UI → Triggers → New → At log on → for current user

Verify with `schtasks /query /tn "CalDAV-Fabric-Sync"`.

---

### WP-145 — CalDAV ↔ Fabric bi-directional task sync — seeded state (2026-04-16)

Initial sync pushed:
- 3 project-level Task nodes → Nextcloud (Graph Memory Fabric, Mara Skills Repository, Marabot)
- 4 external VTODOs → Fabric (tax registration, Feedly triage, LinkedIn, Borowski PV)
- 52 WPs seeded in Fabric (not pushed to Nextcloud — second-order tasks)
> **Retrospective:** Went well — pre-mortem caught the `env_file:` secret exposure early. `auto_https off` vs `disable_redirects` was a one-iteration fix. Main friction: `caddy:2.8.4-builder` had a Go/zap version mismatch requiring a jump to Caddy v2.11.2; GHCR required auth so xcaddy build was the right path. Cloudflare DNS-01 cert obtained on first attempt. The URL migration sweep across mara repo and docs was larger than anticipated — worth factoring into future infra WPs.

---

### WP-149 — Fix `person_ids` scoring suppression in `/memory/search`

**Completed 2026-04-29.**

Deleted `_PERSON_SEARCH_QUERY_TEMPLATE` and its dispatch branch. Person-filtered searches now route through the unified vector path (`_SEARCH_QUERY_TEMPLATE`) which already carried an `OPTIONAL MATCH … person` predicate that was previously unreachable. Added `_PERSON_OVERFETCH_MULTIPLIER = 5` and `_PERSON_OVERFETCH_CAP = 200` so person-linked memories outside the natural top-K are still recoverable. `min_score` now applies on person-filtered searches. Rewrote two WP-093 tests that locked in the null-score behaviour; added two new semantic-ranking tests. Live probe confirmed `score=0.8358` (float, not None) for a person-linked memory queried with matching text.

**Retrospective:** Mostly a deletion — ~35 lines of net change. The unused `$person_ids` predicate was already scaffolded in the vector template by WP-093 but never wired up. The hardest part was the test environment: the Memgraph container needed port 7687 published (not in the default compose file), `API_KEYS` had to be cleared, and the pre-existing `StreamableHTTPSessionManager.run()` singleton issue from WP-105 required each integration test to be run in its own `pytest` invocation. All four WP-149 tests and all WP-037 membership tests pass. See CHANGELOG for the breaking-change note.

---

_(WP-150 description block moved to `docs/CHANGELOG.md` on completion 2026-04-29.)_
