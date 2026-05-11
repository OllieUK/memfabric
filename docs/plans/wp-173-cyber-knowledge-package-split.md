# WP-173 — Cyber Knowledge Package Split (Logical Separation)

| Field | Value |
|-------|-------|
| Status | Plan |
| Author | Oliver + Claude (graph-memory-fabric), 2026-05-11 |
| ADR | [ADR-003](../architecture/ADR-003-cyber-knowledge-package-boundary.md) |
| Value | M |
| Effort | M |
| Priority | 1.0 |
| Depends on | — (must land BEFORE the next cyber WP slate: OSCAL ingest, GS++, KEV, D3FEND, pressure-engine) |

## Goal

Move the cyber knowledge layer into a first-class `cyber_knowledge/` Python sub-package per ADR-003. Logical separation only — same repo, same FastAPI process, same Memgraph instance. **Zero semantic change** to behaviour or data. The full test suite passing afterwards is the primary acceptance signal.

## Non-goals

- No new endpoints, no new features, no new tests for new behaviour.
- No deployment topology changes.
- No data migration in Memgraph (the graph stays exactly as it is).
- No new ADRs beyond ADR-003 (ADR-004 for asset/policy models is a *separate* upcoming WP).
- No removal of `ENABLE_KNOWLEDGE_LAYER` semantics.

## File moves

### memory_service/ → cyber_knowledge/

| From | To |
|------|----|
| `memory_service/knowledge_repo.py` | `cyber_knowledge/repo.py` |
| `memory_service/knowledge_routes.py` | `cyber_knowledge/routes.py` |
| `memory_service/knowledge_schemas.py` | `cyber_knowledge/schemas.py` |
| `memory_service/knowledge_bridge.py` | `cyber_knowledge/bridge.py` |

### scripts/ → cyber_knowledge/ingest/

**Ingest scripts (verified cyber-only):**

| From | To |
|------|----|
| `scripts/ingest_attack.py` | `cyber_knowledge/ingest/attack.py` |
| `scripts/ingest_attack_mitigations.py` | `cyber_knowledge/ingest/attack_mitigations.py` |
| `scripts/ingest_framework.py` | `cyber_knowledge/ingest/framework.py` |
| `scripts/ingest_document.py` | `cyber_knowledge/ingest/document.py` |
| `scripts/ingest_sp800_53.py` | `cyber_knowledge/ingest/sp800_53.py` |
| `scripts/ingest_sp800_53_attack_mappings.py` | `cyber_knowledge/ingest/sp800_53_attack_mappings.py` |
| `scripts/ingest_sp800_53_csf_crosswalk.py` | `cyber_knowledge/ingest/sp800_53_csf_crosswalk.py` |
| `scripts/ingest_all_threat_reports.py` | `cyber_knowledge/ingest/all_threat_reports.py` |
| `scripts/extract_cti_threats.py` | `cyber_knowledge/ingest/cti_extract.py` |
| `scripts/create_cross_framework_informs.py` | `cyber_knowledge/ingest/cross_framework_informs.py` |
| `scripts/create_new_framework_informs.py` | `cyber_knowledge/ingest/cross_framework_informs_new.py` |
| `scripts/create_iso22301_nist_rc_crosswalk.py` | `cyber_knowledge/ingest/iso22301_nist_rc_crosswalk.py` |
| `scripts/calibrate_threat_dedup.py` | `cyber_knowledge/ingest/threat_dedup_calibrate.py` |
| `scripts/apply_threat_dedup_wp138b.py` | `cyber_knowledge/ingest/threat_dedup_apply.py` |
| `scripts/calibrate_threat_ba_influence.py` | `cyber_knowledge/ingest/threat_ba_influence_calibrate.py` |
| `scripts/wire_threat_ba_influence.py` | `cyber_knowledge/ingest/threat_ba_influence_wire.py` |
| `scripts/wire_framework_informs_ba_leaves.py` | `cyber_knowledge/ingest/framework_informs_ba_leaves_wire.py` |
| `scripts/validate_threat_clusters.py` | `cyber_knowledge/ingest/threat_clusters_validate.py` |
| `scripts/analyse_cross_framework_clusters.py` | `cyber_knowledge/ingest/cross_framework_clusters_analyse.py` |
| `scripts/seed_sabsa_architecture.py` | `cyber_knowledge/ingest/sabsa_architecture_seed.py` |
| `scripts/seed_sabsa_cells.py` | `cyber_knowledge/ingest/sabsa_cells_seed.py` |
| `scripts/seed_business_attributes.py` | `cyber_knowledge/ingest/business_attributes_seed.py` |
| `scripts/seed_w100_ict_taxonomy.py` | `cyber_knowledge/ingest/w100_ict_taxonomy_seed.py` |
| `scripts/seed_assets.py` | `cyber_knowledge/ingest/assets_seed.py` |
| `scripts/verify_wp113_t100_aligned_path.py` | `cyber_knowledge/ingest/wp113_t100_verify.py` |
| `scripts/init_knowledge_schema.py` | `cyber_knowledge/ingest/schema_init.py` |

**Framework inspectors and chunk loaders (cyber-only):**

| From | To |
|------|----|
| `scripts/inspect_iso27001.py` | `cyber_knowledge/ingest/inspect_iso27001.py` |
| `scripts/inspect_iso27005.py` | `cyber_knowledge/ingest/inspect_iso27005.py` |
| `scripts/inspect_iso22301.py` | `cyber_knowledge/ingest/inspect_iso22301.py` |
| `scripts/inspect_nist_csf.py` | `cyber_knowledge/ingest/inspect_nist_csf.py` |
| `scripts/inspect_cobit2019.py` | `cyber_knowledge/ingest/inspect_cobit2019.py` |
| `scripts/inspect_din14027.py` | `cyber_knowledge/ingest/inspect_din14027.py` |
| `scripts/load_iso27001_chunks.py` | `cyber_knowledge/ingest/load_iso27001_chunks.py` |
| `scripts/load_iso27005_chunks.py` | `cyber_knowledge/ingest/load_iso27005_chunks.py` |
| `scripts/load_iso22301_chunks.py` | `cyber_knowledge/ingest/load_iso22301_chunks.py` |
| `scripts/load_nist_csf_chunks.py` | `cyber_knowledge/ingest/load_nist_csf_chunks.py` |
| `scripts/load_cobit2019_chunks.py` | `cyber_knowledge/ingest/load_cobit2019_chunks.py` |
| `scripts/load_din14027_chunks.py` | `cyber_knowledge/ingest/load_din14027_chunks.py` |
| `scripts/build_inspector_notebook.py` | `cyber_knowledge/ingest/build_inspector_notebook.py` |

**Shared helpers — disposition decisions:**

| File | Decision | Rationale |
|------|----------|-----------|
| `scripts/script_utils.py` | **Moves** to `cyber_knowledge/ingest/script_utils.py` | Verified cyber-only: imported by `seed_business_attributes`, `seed_sabsa_architecture`, `seed_sabsa_cells`, `seed_w100_ict_taxonomy`, `wire_threat_ba_influence`, `wire_framework_informs_ba_leaves`, `calibrate_threat_ba_influence`, `verify_wp113_t100_aligned_path`. No episodic-memory consumers. |
| `scripts/chunkers.py` | **Moves** to `cyber_knowledge/ingest/chunkers.py` | Cyber-only: imported by `build_inspector_notebook.py` and `ingest_document.py`. |
| `scripts/pdf_utils.py` | **Moves** to `cyber_knowledge/ingest/pdf_utils.py` | Cyber-only: imported by `extract_cti_threats.py` and all six `inspect_*.py` framework inspectors. |
| `scripts/schema_utils.py` | **STAYS** in `scripts/` | Dual-use: imported by `scripts/init_schema.py` (episodic) AND `scripts/init_knowledge_schema.py` (cyber). After the move, `cyber_knowledge/ingest/schema_init.py` will retain `from scripts.schema_utils import ...` — an exception to the boundary rule, documented inline. Long-term: relocate to `memory_service/_shared_schema_utils.py` once `init_schema.py` is refactored, tracked as ambient chore. |

### Stays put (episodic memory / infrastructure)

`scripts/init_schema.py`, `scripts/seed_strands.py`, `scripts/seed_companion_anchors.py`, `scripts/dump_db.py`, `scripts/restore_db.py`, `scripts/smoke_test.py`, `scripts/cleanup_bare_strands.py`, `scripts/dedup_cleanup.py`, `scripts/migrate_embeddings.py`, `scripts/migrate_fact_so_what.py`, `scripts/migrate_person_nodes.py`, `scripts/migrate_reinforcement_defaults.py`, `scripts/maintenance_runner.py`, `scripts/schema_utils.py` (dual-use, see above), `scripts/start-local-stack.sh`, `scripts/homeserver/*`, `scripts/templates/*`.

### Tests (no directory move; marker only)

All test files matching the cyber surface get `pytestmark = pytest.mark.cyber` added at the top, but **stay in `tests/`**. Files (verified existence + cyber-surface match):

**Cyber-only — mark:**
`tests/test_knowledge_bridge.py`, `tests/test_threat_integration.py`, `tests/test_threat_models.py`, `tests/test_threat_repo.py`, `tests/test_cti_extractor.py`, `tests/test_wp069_knowledge_schema.py`, `tests/test_wp070.py`, `tests/test_wp071.py`, `tests/test_wp073_ingest.py`, `tests/test_wp074_knowledge_cli_mcp.py`, `tests/test_wp075_traceability.py`, `tests/test_wp099_framework_schema.py`, `tests/test_wp105_cross_framework_informs.py`, `tests/test_wp106_attack_ingestion.py`, `tests/test_wp107_cluster_analysis.py`, `tests/test_wp111_attack_mitigations.py`, `tests/test_wp112_sp800_53.py`, `tests/test_wp113_endpoints.py`, `tests/test_wp113_models.py`, `tests/test_wp113_repo.py`, `tests/test_wp113_schema_init.py`, `tests/test_wp138_threat_dedup_calibration.py`, `tests/test_wp138b_threat_merge.py`.

**Mixed — leave unmarked:**
- `tests/test_wp102_housekeeping.py` — touches both surfaces.
- `tests/test_wp105_mcp_http.py` — MCP HTTP transport tests covering both episodic and cyber tools.

**Special handling — lockstep edit with settings file:**
- `tests/test_wp_sec_r_settings.py` — asserts on the literal path string `scripts/init_knowledge_schema.py` (lines ~75, ~80). After the move + corresponding `.claude/settings.json` edit, this test must be updated to assert on `cyber_knowledge/ingest/schema_init.py`. **HITL-gated** because it's linked to the security-relevant settings file edit (see "HITL-gated steps" below).

**Conftest fixture:** `tests/conftest.py:73` defines a `knowledge_client` fixture that sets `ENABLE_KNOWLEDGE_LAYER=true`. Leaves in place — harmless when unused. Possible follow-up: relocate to a `tests/cyber/conftest.py` if the cyber test count grows substantially.

If a test file mixes episodic and cyber concerns, leave it unmarked rather than mark cyber tests that aren't cyber-only.

## Import updates

### Internal cyber imports

Inside the moved files, every `from memory_service.knowledge_repo|knowledge_routes|knowledge_schemas|knowledge_bridge` becomes `from cyber_knowledge.repo|routes|schemas|bridge`. Within `cyber_knowledge/ingest/*` modules, all `from memory_service.knowledge_*` imports likewise rebase.

### memory_service.main imports

The four `from memory_service import knowledge_bridge` lines in `memory_service/main.py` (lines ~281, 382, 1232, 1288) become `from cyber_knowledge import bridge as knowledge_bridge` (alias preserved to minimise inline edits). The router include (line ~1506) becomes:

```python
if settings.enable_knowledge_layer:
    from cyber_knowledge.routes import router as knowledge_router
    app.include_router(knowledge_router)
```

### mcp_server cyber tool extraction (new sub-task per ADR-003 §2 door 2)

Today `mcp_server/server.py:845` does `from memory_service import knowledge_repo` and defines five cyber-knowledge MCP tools inline (`knowledge_search_controls`, `knowledge_search_chunks`, `knowledge_list_norms`, `knowledge_get_control`, `knowledge_get_norm`, lines ~848–921). This is the **second cross-package consumer** the original plan missed.

**Refactor:**

1. Create `cyber_knowledge/mcp_tools.py` exposing a single `register(mcp_app)` function. Inside it, import `from cyber_knowledge import repo as knowledge_repo` and register the five tools against the passed `mcp_app` (FastMCP instance) using the same decorator-and-signature pattern as today.
2. In `mcp_server/server.py`, replace the entire inline block (lines ~845–921) with:

   ```python
   if settings.enable_knowledge_layer:
       from cyber_knowledge.mcp_tools import register as register_cyber_tools
       register_cyber_tools(mcp_app)
   ```

3. Verify that `mcp_server/server.py` after the change has **zero** other `cyber_knowledge` imports.
4. Existing tests covering these MCP tools (`tests/test_wp074_knowledge_cli_mcp.py`, `tests/test_wp105_mcp_http.py`) continue to pass without change — the tool surface (names, signatures, behaviour) is unchanged.

This refactor preserves the feature-flag semantics: with `ENABLE_KNOWLEDGE_LAYER=false`, no cyber MCP tools are registered.

### Tests

Search-and-replace `from memory_service.knowledge_*` → `from cyber_knowledge.*` across the 12 files Grep identified earlier. Test fixtures and conftest entries get the same treatment.

### Docs

Update import path references in:
- `docs/plans/wp-070.md`, `docs/plans/wp-072.md`
- `docs/superpowers/plans/2026-04-04-wp099-framework-hierarchy-schema-correction.md`
- `docs/superpowers/plans/2026-04-02-wp094-adr001-alignment.md`

These are historical plan files; the right edit is a single note at the top of each ("Note 2026-05-11: import paths in this plan refer to the pre-WP-173 layout; see ADR-003.") rather than rewriting body content.

## CLI shim

Add `cyber_knowledge/ingest/__main__.py` that lets ingest scripts be invoked as `python -m cyber_knowledge.ingest.<name>`. Each ingest module must already be invokable via `if __name__ == "__main__":` (most are — verify during the move) so `python -m cyber_knowledge.ingest.framework --help` works the same as today's `python scripts/ingest_framework.py --help`.

Update operational wrappers:
- `scripts/homeserver/backup-nightly.sh` — if it references any moved script path, update.
- `scripts/homeserver/claude-diag` — same.
- `docs/operations/*.md` — any documented `python scripts/ingest_*.py` invocation gets a parallel `python -m cyber_knowledge.ingest.*` note plus a deprecation marker on the old form.

For one release cycle, leave thin shim files in `scripts/` that just do `from cyber_knowledge.ingest.X import main; main()` so external operational scripts and habit invocations don't break overnight. Add a deprecation banner. Plan to remove the shims in WP-174 or whenever feels right.

## pyproject.toml changes

**Verified current state (lines 28–29):**

```toml
[tool.setuptools.packages.find]
include = ["memory_client*", "memory_service*", "mcp_server*"]
```

**Edit 1 — extend `packages.find` `include` list**, preserving existing order:

```toml
[tool.setuptools.packages.find]
include = ["memory_client*", "memory_service*", "mcp_server*", "cyber_knowledge*"]
```

**Edit 2 — `[tool.pytest.ini_options]` section does NOT currently exist in `pyproject.toml`.** Either pytest configuration lives in a separate file (`pytest.ini` / `tox.ini` / `setup.cfg`) or is purely default. Implementer steps:

1. Check for an existing `pytest.ini`, `tox.ini`, or `setup.cfg` at repo root. If `integration` (or any other) marker is registered there, add `cyber` to the same file.
2. If no pytest config file exists, create the section in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: tests requiring live Memgraph + FastAPI",
    "cyber: tests covering the cyber knowledge layer (cyber_knowledge/*)",
]
```

   Note: declaring `integration` here when it was previously implicit may surface "unknown marker" warnings that were already present but ignored. Run the full suite once with `-W error::pytest.PytestUnknownMarkWarning` to confirm clean state.

## New files

- `cyber_knowledge/__init__.py` — minimal, just exports nothing; the package boundary marker.
- `cyber_knowledge/ingest/__init__.py` — same.
- `cyber_knowledge/mcp_tools.py` — door 2 (mcp_server consumer), `register(mcp_app)` function holding the five cyber MCP tool registrations extracted from `mcp_server/server.py`.
- `cyber_knowledge/README.md` — roadmap doc per ADR-003 §5. Sections: Mission (three use cases verbatim from Oliver 2026-05-11); Current scope; Roadmap (next slate); Bridge contract (link to ADR-003); See also (link to docs/cyber/).
- `docs/cyber/README.md` — placeholder pointing back to `cyber_knowledge/README.md` and the ADR.
- `docs/architecture/ADR-003-cyber-knowledge-package-boundary.md` — **already written.**

## Dockerfile and container changes

`Dockerfile` at repo root currently has explicit `COPY` directives (lines 13–15) for `memory_service/`, `memory_client/`, `mcp_server/`. **It does NOT use `COPY . /app`.** Therefore the moved package must be added explicitly:

```dockerfile
COPY cyber_knowledge/ ./cyber_knowledge/
```

Place this line adjacent to the existing `COPY` directives. Without it, `ENABLE_KNOWLEDGE_LAYER=true` will fail at startup inside the container because `from cyber_knowledge.routes import router` will raise `ModuleNotFoundError`.

`docker-compose.yml` and `docker-compose.override.yml` were verified to have no path references to `scripts/` or `memory_service/knowledge_*` — no changes needed.

**Note on shim scope:** because `scripts/` is not COPY'd into the image (per ambient chore WP-167), the deprecation-shim soft-landing applies only to host-side direct invocations, not in-container `docker exec`. Operational wrappers that run inside the container (`backup-nightly.sh` does `docker cp` of `dump_db.py`) are unaffected because those scripts are not moving.

## Documentation updates

The plan moves a substantial cyber surface, so several docs and subagent definitions carry stale path references that must be updated:

| File | Type of update |
|------|----------------|
| `.claude/agents/knowledge-ingester.md` | **Edit in place** — 6 references to `scripts/ingest_framework.py` and `scripts/ingest_document.py` (description and body lines ~17, 25, 26, 46, 47, 55) get updated to `python -m cyber_knowledge.ingest.framework` and `python -m cyber_knowledge.ingest.document`. Subagent functionality depends on these prompts being current; do not just note-at-top. |
| `KNOWLEDGE_LAYER.md` | **Edit in place** — multiple references to `scripts/ingest_framework.py`, `scripts/init_knowledge_schema.py`, etc. User-facing documentation; replace with the `python -m cyber_knowledge.ingest.*` form. |
| `notebooks/ingest_pipeline_inspector.ipynb` | **Header-note only** — add a markdown cell at the top noting that paths in this notebook are pre-WP-173 and pointing at the new locations. Notebook code execution may still work via the `scripts/` shim layer for one cycle. |
| `docs/plans/wp-070.md`, `docs/plans/wp-072.md` | **Header-note only** — historical plan files; one-line note at top. |
| `docs/superpowers/plans/2026-04-04-wp099-framework-hierarchy-schema-correction.md` | **Header-note only.** |
| `docs/superpowers/plans/2026-04-02-wp094-adr001-alignment.md` | **Header-note only.** |
| `BACKLOG.md` ambient chores | **Path-column updates only** for WP-115 (`scripts/create_cross_framework_informs.py` → `cyber_knowledge/ingest/cross_framework_informs.py`), WP-SEC-R15b (`scripts/ingest_attack_mitigations.py` → `cyber_knowledge/ingest/attack_mitigations.py`), WP-172 (`memory_service/knowledge_*` → `cyber_knowledge/*`). WP-167 (Dockerfile + scripts/ baking) is now partially addressed by this WP's Dockerfile change. |

## HITL-gated steps (security-relevant)

Per the global Mara baseline rule "Do not autonomously edit security-relevant settings, controls, or protective data without explicit HITL approval", the following two edits **must not be done autonomously by an implementer agent** — they require explicit Oliver approval and direct execution:

1. **`.claude/settings.json` permission paths** — lines 44, 49 hard-code `Edit/Write(.../scripts/init_knowledge_schema.py)`. After the move, the path is `cyber_knowledge/ingest/schema_init.py`. The implementer agent flags this as a required follow-up edit and pauses; Oliver performs the edit personally.

2. **`tests/test_wp_sec_r_settings.py`** — asserts on the literal path string from `.claude/settings.json` (lines ~75, ~80). Must be updated in lockstep with edit #1. Same HITL gate — Oliver performs the edit personally to keep the security-test surface coherent.

These are the final two steps of WP-173 and gate the WP from being marked Done. The implementer agent must leave these in a clearly-flagged state at the end of its run.

## Test strategy

Per `engineering:testing-strategy`:

### Unit
No new unit tests. The move is pure mechanical refactor. The 22 existing cyber-flagged test files cover the moved code; their continued passing is the unit-level acceptance signal.

### Integration
No new integration tests. Re-run the existing integration suite (`pytest -m integration`) against a live Memgraph + FastAPI stack with `ENABLE_KNOWLEDGE_LAYER=true`. All currently-passing tests must continue to pass.

### Smoke
After the move, run the existing `scripts/smoke_test.py` and verify:
1. `/health` returns 200
2. `/memory/wake-up` returns the expected shape
3. `/knowledge/frameworks/{id}` returns a known framework (e.g. ISO 27001 root) — proves the router mount survived
4. `POST /memory` with `control_ids=[...]` succeeds — proves the bridge contract survived

### Manual verification
- `python -m cyber_knowledge.ingest.framework --help` returns the same usage text as today's `python scripts/ingest_framework.py --help`
- `pytest -m cyber` runs a non-empty subset of the suite and all selected tests pass
- `pytest -m 'not cyber'` runs the episodic-memory subset and all pass
- `grep -r 'from cyber_knowledge' memory_service/` returns only `bridge` and `routes` (door 1) imports
- `grep -r 'from cyber_knowledge' mcp_server/` returns only `mcp_tools` (door 2) imports
- `grep -r 'from memory_service.knowledge_' .` returns no results (or only historical doc notes)
- `grep -rn 'from cyber_knowledge' cyber_knowledge/` (excluding `bridge.py` and `mcp_tools.py`) shows that intra-package imports do not bypass the two-door discipline

### Acceptance criteria

| # | Criterion | How verified |
|---|-----------|--------------|
| 1 | All currently-passing unit tests continue to pass | `pytest -m 'not integration'` exit 0 |
| 2 | All currently-passing integration tests continue to pass against live stack | `pytest -m integration` exit 0 |
| 3 | `pytest -m cyber` works as a selection filter | non-empty count, all pass |
| 4 | `pytest -m 'not cyber'` runs the episodic-memory tests | non-empty count, all pass |
| 5 | `memory_service/main.py` imports only `cyber_knowledge.bridge` and `cyber_knowledge.routes`, never any other cyber module | `grep -r 'from cyber_knowledge' memory_service/` review |
| 6 | `mcp_server/server.py` imports only `cyber_knowledge.mcp_tools`, never `cyber_knowledge.repo` directly | `grep -r 'from cyber_knowledge' mcp_server/` review |
| 7 | All cyber ingest scripts run via `python -m cyber_knowledge.ingest.<name>` | spot-check 3 (framework, attack, document) for `--help` parity |
| 8 | Smoke script passes against running stack | manual run |
| 9 | `ENABLE_KNOWLEDGE_LAYER=false` still cleanly disables the cyber layer at both surfaces | start service with flag off, verify `/knowledge/*` returns 404, MCP tool list excludes `knowledge_*`, `/memory/*` works |
| 10 | Container build succeeds and cyber endpoints respond inside the image | `docker compose build && docker compose up -d && curl https://localhost:8443/knowledge/...` |
| 11 | HITL-gated edits flagged and queued | Implementer ends run with `.claude/settings.json` and `test_wp_sec_r_settings.py` updates documented but not executed |

## Definition of Done

1. ✅ ADR-003 committed (this WP creates it).
2. ✅ Plan file (this file) committed.
3. ✅ Test plan attached (this section).
4. ✅ Test strategy run before any code (`engineering:testing-strategy` — outputs above).
5. ✅ All file moves completed (4 in `memory_service/`, 26 ingest + 12 inspector/loader + 3 shared helpers in `scripts/`); imports updated.
6. ✅ `mcp_server/server.py` cyber tool block extracted into `cyber_knowledge/mcp_tools.py`; `register(mcp_app)` registration pattern verified.
7. ✅ `pyproject.toml` updated (package list + `[tool.pytest.ini_options]` markers — including verifying current location of marker config).
8. ✅ `Dockerfile` updated with `COPY cyber_knowledge/ ./cyber_knowledge/`.
9. ✅ `cyber_knowledge/README.md` and `docs/cyber/README.md` exist; subagent definition and `KNOWLEDGE_LAYER.md` edited in place.
10. ✅ Shim files in `scripts/` for one cycle.
11. ✅ All 11 acceptance criteria met.
12. ✅ `/simplify` run; findings acted on or deferred to BACKLOG.md with ID.
13. ✅ `engineering:deploy-checklist` run.
14. ✅ BACKLOG.md updated: WP-173 moved to Completed (or referenced in CHANGELOG); shim-removal item added as ambient chore.
15. ✅ HITL-gated edits completed by Oliver: `.claude/settings.json` path updated; `tests/test_wp_sec_r_settings.py` updated; both verified to keep test suite green.
16. ✅ Retrospective note in BACKLOG.md.
17. ✅ Git commit: `WP-173: cyber-knowledge package split (logical separation per ADR-003)`.

## BACKLOG.md insertion (proposed)

Insert at the top of the Prioritised Backlog table, above the current Order 1 (WP-116):

```
| 0 | R1 | WP-173 | Cyber knowledge package split (logical separation per ADR-003) | M | M | 1.0 | — | Mechanical refactor: promote `memory_service/knowledge_*` → `cyber_knowledge/` sub-package; move ~40 cyber ingest scripts to `cyber_knowledge/ingest/`; extract cyber MCP tools into `cyber_knowledge/mcp_tools.py`; add `cyber` pytest marker; thin shim layer in `scripts/` for one cycle. Zero semantic change. Blocks: WP-174 (ADR-004 asset/policy model), WP-175 (OSCAL ingest), WP-176 (Grundschutz++ ingest), WP-177 (KEV), WP-178 (D3FEND, supersedes WP-114), WP-179 (pressure engine), WP-180 (remove shim). See [ADR-003](docs/architecture/ADR-003-cyber-knowledge-package-boundary.md) and [plan](docs/plans/wp-173-cyber-knowledge-package-split.md). |
```

Adjust the existing "Currently In Progress" section to list WP-173 as the active item when execution starts.

## Risks

| Risk | Mitigation |
|------|-----------|
| Hidden import paths break tests in non-obvious ways | Test suite is the safety net; run full suite after move before any commits |
| Operational scripts called from outside the repo break | Shim layer in `scripts/` for one cycle |
| `pyproject.toml` package discovery misses something | `pip install -e .` after the move; verify `python -c "import cyber_knowledge; import cyber_knowledge.ingest; import cyber_knowledge.mcp_tools"` works |
| Historical plan docs reference paths that no longer exist | Add note-at-top rather than rewrite; docs remain accurate-for-their-time |
| The `cyber` pytest marker is forgotten on new tests | Document in `cyber_knowledge/README.md`; add a CI lint check in a follow-up WP if it becomes a real problem |
| `ENABLE_KNOWLEDGE_LAYER=false` path regresses | Acceptance criterion #9 explicitly covers this — both router mount and MCP tool registration |
| `Dockerfile` does not COPY new package → container build appears clean but runtime fails on flag-on | Dockerfile edit is mandatory; acceptance criterion #10 covers it |
| `cyber_knowledge.ingest.schema_init` keeps `from scripts.schema_utils import ...` (dual-use exception) | Documented inline as a deliberate exception; revisit when `init_schema.py` is refactored |
| `.claude/agents/knowledge-ingester.md` references go stale → subagent silently runs against missing paths | Mandatory edit-in-place during WP-173; not header-note treatment |
| `[tool.pytest.ini_options]` may not exist in `pyproject.toml` → creating it may surface previously-suppressed warnings | Run suite once with strict warning flag to confirm clean state before commit |
| HITL-gated `.claude/settings.json` edit forgotten → cyber ingest scripts permission-prompt at every invocation | Acceptance criterion #11 explicitly leaves these flagged; WP cannot be marked Done until Oliver applies them |
| `mcp_server` cyber-tool extraction regresses tool surface | Existing `tests/test_wp074_knowledge_cli_mcp.py` and `tests/test_wp105_mcp_http.py` cover tool name + signature + behaviour; their continued passing is the safety net |

## Out-of-scope notes for the implementer

- Do **not** rename `ENABLE_KNOWLEDGE_LAYER` to `ENABLE_CYBER_LAYER` in this WP. That's a flag-rename WP for later — coupling it here doubles the cognitive surface of the change for no immediate gain.
- Do **not** touch `data/frameworks/` or `data/threats/` paths. Data stays at repo root.
- Do **not** touch `knowledge_routes.py`'s URL prefix (`/knowledge/*`). The URL surface is the API contract; even though the module moves, `/knowledge/*` endpoints stay. URL renaming is a separate breaking-change WP that needs version planning.
- Do **not** start any new cyber WP (OSCAL, GS++, KEV, D3FEND, pressure-engine, ADR-004) until this lands.

## Follow-up WPs unblocked by this

(Numbered placeholders; refine when planned.)

- **WP-174** — Drafting ADR-004 (asset + policy node model + OSCAL parameter handling).
- **WP-175** — Generic OSCAL Catalog ingest pipeline (`cyber_knowledge/ingest/oscal/`).
- **WP-176** — Grundschutz++ ingestion (apply WP-175 against the BSI CC-BY-SA-4.0 OSCAL catalog).
- **WP-177** — CISA KEV ingestion (CVE node label, KEV flag, ATT&CK mapping).
- **WP-178** — D3FEND ingestion (promoted from existing WP-114).
- **WP-179** — Pressure-engine endpoint (`GET /pressure/business-attribute`).
- **WP-180** — Remove the `scripts/` shim layer.

These should be added to BACKLOG.md when WP-173 is closed out.
