# ADR-003: Cyber Knowledge Package Boundary

| Field | Value |
|-------|-------|
| Status | Proposed |
| Date | 2026-05-11 |
| Scope | Logical separation of the InfoSec/cyber knowledge layer from episodic memory within the same repo and process |
| Supersedes | ADR-001 §3 "Module naming and structure" (the rest of ADR-001 stands) |
| See also | [ADR-001](ADR-001-knowledge-layer-placement.md) (placement decision), [ADR-002](ADR-002-knowledge-layer-graph-model.md) (graph model) |

## Decision

Promote the InfoSec/cyber knowledge layer from a set of `knowledge_*` modules sitting alongside episodic memory into a **first-class Python sub-package `cyber_knowledge/`** inside `graph-memory-fabric`. Keep the single repository, single Memgraph instance, single FastAPI process. Introduce a documented bridge contract for the (single) module that crosses the boundary, a dedicated pytest marker, and a separate roadmap doc so the cyber surface can be developed and reasoned about independently from the memory fabric.

Do **not** split into a separate repository or service. Both remain on the table as later steps, but only when their named review triggers fire.

## Context

ADR-001 (2026-04-02) placed the knowledge layer inside graph-memory-fabric as a feature-flagged peer module, with `knowledge_*` prefixed file names as the only structural boundary. Eight months on, three things have shifted:

1. **Product identity divergence.** The three target use cases (threat-and-compliance-aware maturity review, policy review against landscape change, policy architecture build/review — Oliver 2026-05-11) are a *cyber knowledge service*, not features of an episodic-memory fabric. The repo now serves two products, not one.
2. **Forthcoming code-volume tip.** ADR-001's review trigger #2 ("knowledge code exceeds 50% of total codebase") is already close. The next slate (OSCAL ingest, GS++ ingestion, CISA KEV, CVE enrichment, D3FEND, pressure-engine, policy node model + policy gap report) will land 8–12 substantial modules + ingest scripts + tests over the next quarter. Without a package boundary, those land in the same flat namespace as the memory fabric.
3. **OSCAL changes the ingest shape.** BSI publishes Grundschutz++ as a CC-BY-SA-4.0 OSCAL 1.1.3 catalog (`github.com/BSI-Bund/Stand-der-Technik-Bibliothek`, 998 controls). A generic OSCAL-aware ingest pipeline benefits Grundschutz++, NIST SP 800-53, and any future OSCAL-published standard equally. Its natural home is in `cyber_knowledge/ingest/oscal/`, not in the top-level `scripts/` namespace shared with episodic-memory operational scripts.

ADR-001 explicitly anticipated this: "knowledge code volume exceeding 50% of total codebase" is a named review trigger, and "carve-out cost scales with cross-layer edge count" was an accepted constraint. ADR-003 acts on those triggers without paying the higher cost of full extraction yet.

## Three split points considered

| # | Split | Cost | What it gives us |
|---|-------|------|------------------|
| 1 | **Logical separation** — sub-package inside same repo and process | ~1–2 days, mechanical | Independent dev process, cleaner mental model, all new cyber files land inside the boundary, pre-positions for #2 |
| 2 | **Repo split, shared deployment** — separate repo, same FastAPI process via mounted router | ~3–5 days | Independent release cadence, separate issue/PR streams, cleaner narrative for clients |
| 3 | **Service split** — separate service, possibly separate Memgraph | Significant (data migration project, per ADR-001) | Independent scaling, multi-tenancy capability, per-client isolation |

This ADR adopts **only split #1**. Splits #2 and #3 are deferred behind explicit review triggers (see below).

## Architectural Guardrails

### 1. Package layout

```
graph-memory-fabric/
├── memory_service/                 # episodic memory + service shell (HTTP, scheduler, MCP)
│   ├── main.py                      # FastAPI app; mounts cyber router via feature flag
│   ├── memory_repo.py
│   ├── memory_routes.py             # /memory/* endpoints
│   ├── schemas.py
│   ├── embeddings.py
│   ├── config.py
│   └── ...
├── cyber_knowledge/                # NEW — first-class sub-package
│   ├── __init__.py
│   ├── README.md                   # roadmap, current use cases, scope, owners
│   ├── repo.py                     # (was knowledge_repo.py)
│   ├── routes.py                   # (was knowledge_routes.py)
│   ├── schemas.py                  # (was knowledge_schemas.py)
│   ├── bridge.py                   # (was knowledge_bridge.py) — door 1 (memory_service)
│   ├── mcp_tools.py                # NEW — door 2 (mcp_server)
│   └── ingest/                     # ingest scripts + cyber-only helpers
│       ├── __init__.py
│       ├── attack.py               # (was scripts/ingest_attack.py)
│       ├── attack_mitigations.py
│       ├── framework.py
│       ├── document.py
│       ├── sp800_53.py
│       ├── sp800_53_attack_mappings.py
│       ├── sp800_53_csf_crosswalk.py
│       ├── all_threat_reports.py
│       ├── cti_extract.py          # (was extract_cti_threats.py)
│       ├── cross_framework_informs.py
│       ├── cross_framework_informs_new.py    # (was create_new_framework_informs.py)
│       ├── iso22301_nist_rc_crosswalk.py     # (was create_iso22301_nist_rc_crosswalk.py)
│       ├── threat_dedup_calibrate.py
│       ├── threat_dedup_apply.py
│       ├── threat_ba_influence_calibrate.py  # (was calibrate_threat_ba_influence.py)
│       ├── threat_ba_influence_wire.py       # (was wire_threat_ba_influence.py)
│       ├── framework_informs_ba_leaves_wire.py
│       ├── threat_clusters_validate.py
│       ├── cross_framework_clusters_analyse.py
│       ├── sabsa_architecture_seed.py
│       ├── sabsa_cells_seed.py
│       ├── business_attributes_seed.py
│       ├── w100_ict_taxonomy_seed.py
│       ├── assets_seed.py
│       ├── wp113_t100_verify.py              # (was verify_wp113_t100_aligned_path.py)
│       ├── inspect_iso27001.py
│       ├── inspect_iso27005.py
│       ├── inspect_iso22301.py
│       ├── inspect_nist_csf.py
│       ├── inspect_cobit2019.py
│       ├── inspect_din14027.py
│       ├── load_iso27001_chunks.py
│       ├── load_iso27005_chunks.py
│       ├── load_iso22301_chunks.py
│       ├── load_nist_csf_chunks.py
│       ├── load_cobit2019_chunks.py
│       ├── load_din14027_chunks.py
│       ├── build_inspector_notebook.py
│       ├── schema_init.py          # (was init_knowledge_schema.py)
│       ├── script_utils.py         # cyber-only — moved with consumers
│       ├── chunkers.py             # cyber-only — moved with consumers
│       └── pdf_utils.py            # cyber-only — moved with consumers
├── scripts/                        # operational scripts NOT specific to cyber layer
│   ├── init_schema.py
│   ├── seed_strands.py
│   ├── dump_db.py / restore_db.py
│   ├── smoke_test.py
│   └── ... (episodic-memory and infrastructure-only scripts)
├── data/
│   ├── frameworks/                 # stays as-is — data is data
│   └── threats/                    # stays as-is
├── tests/                          # marked tests (see §4); no directory split
└── docs/
    ├── architecture/               # ADRs (all of them, in one place)
    ├── cyber/                      # NEW — cyber-specific specs, roadmap, use-case notes
    └── workflows/
```

The `cyber_knowledge.ingest` package gets a small CLI shim so commands like `python -m cyber_knowledge.ingest.framework --file ...` work, replacing today's `python scripts/ingest_framework.py ...`. Deployment-side wrappers (`backup-nightly.sh`, `claude-diag`) get updated paths in the same WP.

### 2. Bridge contract — two doors

The cross-package surface is small, explicit, and has exactly **two doors**, one per consuming peer package. Both are inside `cyber_knowledge/`. No other modules in `cyber_knowledge/` may be imported from outside the package.

**Door 1 — `cyber_knowledge/bridge.py`** — consumed by `memory_service.main` for cross-layer edge operations during episodic-memory CRUD. Stable function-level surface: `validate_controls`, `validate_documents`, `link_controls`, `link_documents`, `replace_control_edges`, `replace_doc_edges`, `hydrate_controls_and_documents`, `rewire_cross_layer_edges`. Used only when `ENABLE_KNOWLEDGE_LAYER=true`.

**Door 2 — `cyber_knowledge/mcp_tools.py`** — consumed by `mcp_server.server` to register the cyber-knowledge MCP tools (`knowledge_search_controls`, `knowledge_search_chunks`, `knowledge_list_norms`, `knowledge_get_control`, `knowledge_get_norm`). Exposes a single `register(mcp_app)` function that the MCP server calls under the feature flag. This replaces the current pattern where `mcp_server.server:845` imports `knowledge_repo` directly and defines the tools inline.

**Audit rules:**
- `grep -r 'from cyber_knowledge' memory_service/` returns import lines from `cyber_knowledge.bridge` (and possibly `cyber_knowledge.routes` from the conditional `include_router` block) only.
- `grep -r 'from cyber_knowledge' mcp_server/` returns import lines from `cyber_knowledge.mcp_tools` only.
- No other `memory_service` or `mcp_server` import of any `cyber_knowledge.*` module is permitted.

`cyber_knowledge.*` modules other than `bridge.py` and `mcp_tools.py` may import from `memory_service.config`, `memory_service.embeddings`, `memory_service.ingest_guard`, and `memory_service.schemas` (shared infrastructure). They must not import from `memory_service.memory_repo` or `memory_service.memory_routes`. Episodic-memory data access from cyber code goes through `bridge`.

`bridge.py` and `mcp_tools.py` are the only modules in `cyber_knowledge/` that may import from elsewhere in `cyber_knowledge/`; they are explicitly *outward-facing* by design.

### 3. Feature flag and router mounting (unchanged from ADR-001)

`ENABLE_KNOWLEDGE_LAYER=true` continues to gate cyber router mounting:

```python
# memory_service/main.py
if settings.enable_knowledge_layer:
    from cyber_knowledge.routes import router as cyber_router
    app.include_router(cyber_router)
```

All bridge calls in `memory_service.main` continue to be wrapped in `if settings.enable_knowledge_layer:` checks. The flag's semantics are unchanged — only the import path moves.

### 4. Test marker and CI surface

Introduce a `pytest` marker `cyber` for all tests covering `cyber_knowledge/*` and its ingest scripts. Configured in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "cyber: tests covering the cyber knowledge layer (cyber_knowledge/*)",
    # ... existing markers ...
]
```

Selective runs:
- `pytest -m cyber` — cyber-layer-only test runs (for cyber-focused dev cycles)
- `pytest -m 'not cyber'` — episodic-memory-only runs (for memory-fabric-focused dev cycles)
- `pytest` (no marker) — full suite (default, used in CI)

This is a **selection** marker, not an isolation marker — tests still run in the same process against the same Memgraph instance. The marker exists so developer feedback loops can be shorter when working in one layer.

### 5. Roadmap and documentation home

`cyber_knowledge/README.md` becomes the cyber layer's living document:
- Mission statement (three use cases verbatim)
- Current scope (what's in, what's deferred)
- Roadmap (next slate of WPs)
- Bridge contract (link to this ADR)
- Pointer to `docs/cyber/` for deeper specs

`docs/cyber/` becomes the home for cyber-specific design notes (e.g. OSCAL parameter handling, asset taxonomy, policy node model). ADRs themselves stay in `docs/architecture/` regardless of layer — having all ADRs in one place is more valuable than per-layer ADR trees.

## Alternatives Considered

### Status quo (rejected)

Keep `knowledge_*` flat-prefixed inside `memory_service/`.

**Rejected because:** The cyber surface is about to double in size with OSCAL ingest, GS++, KEV/CVE, D3FEND, pressure engine, and policy model work. The flat prefix has carried us this far but does not survive the next quarter cleanly. Renaming later is more disruptive than renaming now (every new module would land in the wrong place).

### Full repo extraction now (deferred to split #2)

Pull cyber into its own repository, mount as a shared dependency or sub-app.

**Deferred because:** The memory fabric still has active feature work (WP-145 CalDAV sync, WP-085 analytics, WP-128 tiered search). A repo split right now would force a release-cadence decoupling before it provides value. Costs ~3–5 days plus ongoing dual-repo overhead. Revisit when triggers fire (see below).

### Service extraction now (deferred to split #3)

Run cyber knowledge as a separate FastAPI service, possibly with its own Memgraph.

**Deferred because:** Single-user, single-machine deployment makes microservice separation pure overhead today. ADR-001 already considered this and rejected it on cross-layer-edge grounds — that argument still holds.

## Consequences

### Enables
- Independent cyber and episodic-memory dev workflows (test selection, README focus, roadmap clarity)
- All cyber WPs from now on land inside a clear boundary
- Pre-positions for split #2 (repo extraction) — most of that work becomes pure relocation, not refactor
- Clearer narrative when discussing the project externally ("memory fabric + cyber knowledge layer" vs. "monolith")

### Constrains
- Existing imports break; ~30 file moves; one mechanical WP needed before any new cyber work
- Cross-package bridge contract must be enforced via code review (no linter today)
- The pytest `cyber` marker is a soft boundary — easy to forget on a new test

### Watch for
- Cross-package imports outside the bridge (review trigger for tightening the boundary or splitting)
- `cyber_knowledge/` growing a second sub-product that wants to escape the package (review trigger for split #2)
- Memgraph resource contention from cyber ingest pressuring episodic-memory performance (re-evaluation per ADR-001 trigger #5)

## Review Triggers

### For split #2 (repo extraction, shared deployment)

Re-evaluate `cyber_knowledge` as a separate repository if **any two** of the following are true:

1. The cyber roadmap is driving the release cadence and the memory fabric is in pure maintenance mode for two consecutive months.
2. The number of contributors (human or agent) actively working in `cyber_knowledge/` exceeds those in `memory_service/` over a quarter, and merge conflicts on shared CI/docs become friction-worthy.
3. A first paying client engagement requires per-client cyber-layer releases on a cadence independent of the memory fabric.
4. The bridge contract has stayed stable (no signature changes) for a full quarter — proves the cross-package surface is small enough to be a versioned dependency.

### For split #3 (service extraction)

Re-evaluate as per ADR-001's existing review triggers, plus:

5. First multi-tenant or multi-client requirement materialises (per-client data isolation or RBAC).
6. Cross-layer edge count exceeds 10,000 *and* episodic-memory query performance is measurably impacted.

## Out of Scope

- ADR-002 (graph model, node/edge types) — unchanged.
- The `ENABLE_KNOWLEDGE_LAYER` feature-flag semantics — unchanged.
- `data/frameworks/` and `data/threats/` location — stays at repo root. Data is data; moving it does not earn its keep.
- Deployment topology (single Memgraph, single FastAPI process, single container) — unchanged.
- Multi-tenant access control, RBAC, audit logging for the cyber layer — out of scope for this ADR; would be addressed when split #3's triggers fire.
- Asset and Policy node models (the original ADR-003 scope) — moved to a separate ADR-004 to keep this one tightly focused on the package boundary. ADR-004 follows immediately.
