# WP-174: ADR-006 — Asset and Policy node model + OSCAL parameter handling

**Date:** 2026-05-12
**Status:** Ready for implementation
**Type:** Schema-only (ADR + constraint/index additions; no ingest, no seeding, no API surface)
**Unblocks:** WP-175 (generic OSCAL ingest), WP-176 (GS++ apply), WP-179 (pressure engine)
**Depends on:** ADR-001, ADR-002, ADR-005

---

## Summary

Land **ADR-006** to formalise four new node concepts — `AssetClass`, `Policy`, `PolicySection`, `Param` — and the edges that bind them into the existing cyber-knowledge lattice (Framework / Control / Norm / Precept / BusinessAttribute / Asset / Chunk / Threat / Organisation). Land the **schema-init delta** (uniqueness constraints + vector indexes) that the next slate of WPs (175 / 176 / 179) will populate. No ingestion, no seeds, no Pydantic CRUD, no routes, no bridge surface in this WP.

---

## Approach

1. Draft `docs/architecture/ADR-006-asset-policy-oscal-parameter-model.md` against the section outline below. Make every node/edge decision explicit and numbered in the Decision block. Reference ADR-001 (placement), ADR-002 (graph model), ADR-005 (package boundary).
2. Extend `cyber_knowledge/ingest/schema_init.py` to add:
   - Uniqueness constraints for `AssetClass`, `Policy`, `PolicySection`, `Param`, **and** `Precept` (formalised here — see Decision Point B).
   - Vector indexes for `Policy.embedding` and `PolicySection.embedding`. **No** vector index for `AssetClass` or `Param`.
3. Add enum frozensets to `cyber_knowledge/schemas.py` for the constrained string properties introduced by ADR-006: `POLICY_STATUS`, `PARAM_TYPE`, `ASSET_CLASS_KIND`. **No** Pydantic models in this WP — those land with WP-175 when ingest needs them.
4. Run schema-init against a clean Memgraph (acceptance gate); re-run for idempotence.
5. Confirm `cyber_knowledge/bridge.py` and `cyber_knowledge/mcp_tools.py` remain untouched. ADR-006 is schema-only; no new label is exposed across the package boundary yet.

---

## Affected Files

| File | Change |
|------|--------|
| `docs/architecture/ADR-006-asset-policy-oscal-parameter-model.md` | New — full ADR per section outline below |
| `cyber_knowledge/ingest/schema_init.py` | Add 5 constraints + 2 vector indexes (Policy, PolicySection) + their `validate_vector_index` calls + settings hooks for index capacity |
| `cyber_knowledge/schemas.py` | Add `POLICY_STATUS`, `PARAM_TYPE`, `ASSET_CLASS_KIND` frozensets near existing enum frozensets |
| `memory_service/config.py` (or wherever knowledge index capacities live) | Add `policy_index_capacity`, `policy_section_index_capacity` settings with sensible defaults |
| `CLAUDE.md` data-model quick-reference | Append the four new node labels + new edges (small documentation delta, kept consistent with existing table style) |
| `docker-compose.yml` | Add `ports: ["127.0.0.1:7687:7687"]` to `memfabric-db` service so live-stack verification (this WP and future schema-affecting WPs) can reach Memgraph via SSH tunnel-to-loopback. Bound to `127.0.0.1` only — no LAN exposure; Memgraph has no auth configured, so auth boundary stays at SSH. Bundled into WP-174 because this WP is the first to need it. |
| `BACKLOG.md` | Move WP-174 to "Currently In Progress" at start; to Completed at end |

No changes in this WP to: `cyber_knowledge/repo.py`, `cyber_knowledge/routes.py`, `cyber_knowledge/bridge.py`, `cyber_knowledge/mcp_tools.py`, `cyber_knowledge/ingest/sp800_53.py`, `cyber_knowledge/ingest/gs_pp.py`.

---

## ADR-006 outline — section headings + one-line intent

### Frontmatter (mirror ADR-005 style)
- **Status:** Proposed
- **Date:** 2026-05-12
- **Scope:** Node model for assets, policies, and OSCAL parameters within the cyber knowledge layer
- **Depends on:** ADR-001 (placement), ADR-002 (graph model), ADR-005 (package boundary)
- **See also:** OSCAL 1.1.3 catalog schema; BSI Grundschutz++ catalog

### 1. Decision (numbered, ≤10 commitments)
1. Introduce `AssetClass` as a taxonomy node above `Asset` instances. `Asset -[:CLASSIFIED_AS]-> AssetClass` (see Decision Point A).
2. Defer industry / business-type sub-axes; start with pure class hierarchy. `AssetClass -[:SUBCLASS_OF]-> AssetClass` (self-edge, DAG; uniqueness enforced at edge create time, not by schema).
3. Formalise `Precept` with a uniqueness constraint on `id` (see Decision Point B). No vector index in this WP.
4. Introduce `Policy` and `PolicySection`. `Policy -[:HAS_SECTION]-> PolicySection`. Both get vector indexes on `embedding`.
5. `Policy` attaches at two anchors: `Policy -[:ADDRESSES]-> Precept` (primary, semantically rich) and `Policy -[:IMPLEMENTS]-> Control` (where the policy is the org's concrete realisation of an OSCAL control). Both edges optional; a Policy may have either or both. (Decision Point C.)
6. Introduce `Param` as a standalone node, not a property bag on Control (Decision Point D). `Control -[:HAS_PARAM]-> Param` and `Policy -[:BINDS]-> Param` with `value` property on the BINDS edge (org-specific resolution).
7. Org scoping: `AssetClass`, `Policy`, `PolicySection` may be org-scoped via `-[:SCOPED_TO]-> Organisation` (optional edge — global classes/policies omit it). `Param` is not org-scoped; resolution is via Policy bindings. (Decision Point E.)
8. Vector index policy: only `Policy.embedding` and `PolicySection.embedding` get indexes in this WP (Decision Point F). `AssetClass` and `Param` do not — they are taxonomy / structural nodes, not search targets.
9. `Policy` is **orthogonal to** `Document`, not a specialisation. A `Policy` is an organisational commitment; a `Document` is a source artefact. A Policy MAY cite Documents (`Policy -[:CITES]-> Document`), but the two roles are distinct. (See Risks.)
10. WP-174 is schema-only: no ingest, no CRUD, no bridge surface, no API. WPs 175/176/179 will populate the new labels.

### 2. Context
- The three use cases that drive ADR-006:
  - (i) threat-and-compliance-aware maturity review
  - (ii) policy review against threat/compliance change
  - (iii) policy architecture build/review
- The GS++ OSCAL 1.1.3 finding (from WP-173 inspection): control.params + `{{ insert: param }}` placeholders have no home in the current schema.
- Oliver's 2026-05-11 direction: class-based asset taxonomy with industry/business-type deferred.

### 3. Node Model (one subsection per new label)

For each: **purpose · uniqueness constraint · key properties · vector index decision · examples**.

- **3.1 AssetClass** — taxonomy node above `Asset`. Constraint: `(AssetClass, id)`. Properties: `id` (kebab-case), `name`, `description`, `kind` (enum from `ASSET_CLASS_KIND`: `it|ot|iot|integration|data|process|people|facility`). No vector index.
- **3.2 Policy** — organisational commitment / policy artefact. Constraint: `(Policy, id)`. Properties: `id`, `title`, `summary`, `status` (enum from `POLICY_STATUS`: `draft|active|deprecated|retired`), `version`, `effective_at`, `review_due_at`, `embedding`. Vector index: `policy_embedding_idx`.
- **3.3 PolicySection** — chunked subsection of a Policy (for fine-grained `ADDRESSES`/`BINDS`/search). Constraint: `(PolicySection, id)`. Properties: `id`, `policy_id` (denormalised for cheap filters), `heading`, `text`, `order`, `embedding`. Vector index: `policy_section_embedding_idx`.
- **3.4 Param** — OSCAL parameter declaration. Constraint: `(Param, id)` where `id` is qualified, e.g. `sp800-53:ac-1_prm_1` or `gs-pp:SYS.1.1.A1_prm_2`. Properties: `id`, `control_id` (denormalised), `label`, `param_type` (enum from `PARAM_TYPE`: `string|integer|enum|select|datetime|duration`), `allowed_values` (list of strings, for enum/select), `guidance`. No vector index.
- **3.5 Precept (formalised)** — already used at runtime; add uniqueness constraint on `(Precept, id)`. Properties existing today: `id`, `name`, `text`, `framework_id` (optional). No vector index in this WP (deferred — Precept text search currently rides on Control/Chunk indexes).

### 4. Edge Model
| Edge | From → To | Direction | Cardinality | Properties |
|------|-----------|-----------|-------------|------------|
| `CLASSIFIED_AS` | Asset → AssetClass | one-way | n:m (asset may sit in several class facets later) | none |
| `SUBCLASS_OF` | AssetClass → AssetClass | one-way (DAG) | n:1 typical | none |
| `HAS_SECTION` | Policy → PolicySection | one-way | 1:n | `order int` |
| `ADDRESSES` (extended) | Policy / PolicySection → Precept | one-way | n:m | `confidence float` (optional) |
| `IMPLEMENTS` | Policy / PolicySection → Control | one-way | n:m | none |
| `HAS_PARAM` | Control → Param | one-way | 1:n | none |
| `BINDS` | Policy / PolicySection → Param | one-way | n:m | `value string` (org-resolved value), `bound_at datetime` |
| `CITES` | Policy / PolicySection → Document | one-way | n:m | none |
| `SCOPED_TO` | AssetClass / Policy / PolicySection → Organisation | one-way | n:1 | none |

Existing edges (REQUIRES, FULFILS, ADDRESSES Control→Precept, JEOPARDISES, MAPS_TO) are unaffected. The `ADDRESSES` edge is widened to also originate from `Policy` and `PolicySection` (in addition to the existing `Control → Precept` use).

### 5. Relationship to existing labels
- **Asset**: gains a CLASSIFIED_AS edge upward. `asset_type` property stays (it is the low-level IT/OT/IoT/integration distinction); `AssetClass.kind` covers the same vocabulary at the taxonomy layer, deliberately overlapping until industry/business-type axes are introduced (see Risk A).
- **Precept**: now first-class with a uniqueness constraint; behaviour unchanged.
- **Framework / Control / Norm**: unchanged structurally. Control gains `HAS_PARAM` outgoing.
- **BusinessAttribute**: unchanged; FULFILS still terminates here.
- **Chunk**: unchanged. `PolicySection` is *not* a Chunk — it lives in the policy lattice, not the source-document lattice. PolicySection text *may* be chunked into Chunk nodes later if full-text search needs warrant it (defer).
- **Document**: unchanged. Policy CITES Document; Policy is not a Document subtype.

### 6. OSCAL parameter binding
How `control.params` from OSCAL catalogs resolve to org-specific values:

1. Ingest (WP-175) creates one `Param` node per `control.params[*]`, linked `Control -[:HAS_PARAM]-> Param`.
2. The `{{ insert: param, param-id="ac-1_prm_1" }}` placeholders in `control.parts.statement` survive verbatim in `Chunk.text`.
3. An org-specific `Policy` (or `PolicySection`) resolves a Param via `Policy -[:BINDS {value: "30 days"}]-> Param`.
4. Rendering a control statement "as configured for org X" = lookup Chunk text, resolve each placeholder against the BINDS edges from active Policies SCOPED_TO that Organisation.
5. ADR-006 specifies the data model only. Resolution algorithm is WP-175/176 work.

### 7. Review triggers (when to revisit ADR-006)
- Industry / business-type sub-axes become necessary → revisit AssetClass shape.
- Policy CITES → Document edge volume exceeds a threshold suggesting Policy *is* a Document specialisation → consider merge.
- MITRE ATT&CK or D3FEND introduce param-like fields that don't fit `Param` cleanly → consider splitting Param by source taxonomy.
- Precept text search becomes required → add `precept_embedding_idx`.
- Cross-org Policy reuse → revisit org-scoping edge direction.

### 8. Consequences
**Positive:**
- Unblocks WP-175 generic OSCAL ingest (Param now has a target).
- Unblocks WP-176 GS++ apply (Policy/PolicySection now exist).
- Unblocks WP-179 pressure engine (org-scoped Policy + AssetClass exposure surface available).
- Precept becomes a first-class queryable label.

**Negative:**
- AssetClass.kind and Asset.asset_type overlap until industry axes land (Risk A).
- Two-anchor Policy attachment (Precept and Control) gives flexibility but adds a modelling decision to every Policy ingest path.
- Adds 5 constraints + 2 vector indexes — small operational cost on schema-init, but real (index capacity must be sized).

---

## Cypher Patterns (schema-init only — NO inserts in this WP)

```cypher
CREATE CONSTRAINT ON (n:AssetClass) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Policy) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:PolicySection) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Param) ASSERT n.id IS UNIQUE;
CREATE CONSTRAINT ON (n:Precept) ASSERT n.id IS UNIQUE;

CREATE VECTOR INDEX policy_embedding_idx
  ON :Policy(embedding)
  WITH CONFIG {"dimension": $dim, "capacity": $policy_index_capacity, "metric": "cos"};

CREATE VECTOR INDEX policy_section_embedding_idx
  ON :PolicySection(embedding)
  WITH CONFIG {"dimension": $dim, "capacity": $policy_section_index_capacity, "metric": "cos"};
```

(Exact `CREATE VECTOR INDEX` syntax follows the existing pattern in `schema_init.create_vector_index`; parameters via `$dim`, capacity via settings — same as `ctrl_embedding_idx` etc.)

---

## Schema-init delta (concrete)

In `cyber_knowledge/ingest/schema_init.py`:

1. Extend `KNOWLEDGE_CONSTRAINTS` (lines 18–31) with:
   ```python
   ("Precept", "id"),
   ("AssetClass", "id"),
   ("Policy", "id"),
   ("PolicySection", "id"),
   ("Param", "id"),
   ```
2. After `business_attribute_embedding_idx` block (line ~273), insert two new vector-index blocks following the existing `try / create_vector_index / validate_vector_index` template:
   - `policy_embedding_idx` on `Policy.embedding`, capacity `settings.policy_index_capacity`.
   - `policy_section_embedding_idx` on `PolicySection.embedding`, capacity `settings.policy_section_index_capacity`.
3. In settings (`memory_service/config.py` or the knowledge-layer settings module): add `policy_index_capacity: int = 5_000` and `policy_section_index_capacity: int = 20_000` (informed defaults — Policy count low, PolicySection ≈4× Policy count assuming average 4 sections; tune later).

---

## `schemas.py` delta

Add three frozensets near the existing enum frozensets (no Pydantic models):

```python
POLICY_STATUS = frozenset({"draft", "active", "deprecated", "retired"})
PARAM_TYPE = frozenset({"string", "integer", "enum", "select", "datetime", "duration"})
ASSET_CLASS_KIND = frozenset({"it", "ot", "iot", "integration", "data", "process", "people", "facility"})
```

These mirror the property values asserted in the ADR §3 Node Model.

---

## Pydantic CRUD models — deferred

WP-174 adds **no** Pydantic models. WP-175 (OSCAL ingest) will add `ParamCreate` / `PolicyCreate` / `PolicySectionCreate` when it needs them. This plan flags that explicitly so the implementer does not pre-build them.

---

## Bridge door impact

**None.** No new label is exposed across the `cyber_knowledge/bridge.py` or `cyber_knowledge/mcp_tools.py` surface in this WP. The schema lives entirely inside the knowledge package; the memory fabric does not see any of the new labels. ADR-005's two-door contract is preserved.

A note will be added to ADR-006 §8 Consequences stating: "When WP-175+ exposes Policy or AssetClass over the API, the addition MUST go through bridge.py per ADR-005."

---

## Decision Points (surfaced explicitly, with the plan's recommendation)

| # | Decision | Plan recommendation | Rationale |
|---|----------|---------------------|-----------|
| A | AssetClass → Asset edge name + direction | `Asset -[:CLASSIFIED_AS]-> AssetClass` | Reads naturally ("asset *is classified as* class"); aligns with existing `MAPS_TO` / `ADDRESSES` directional convention. `INSTANCE_OF` rejected because it is already used for recurring-task instances on the memory fabric side (CLAUDE.md data-model table) and reuse would cause confusion across the package boundary. |
| B | Formalise Precept now or defer? | **Formalise now** — add `(Precept, id)` uniqueness constraint | Precept is already used by 4 edge types (REQUIRES, FULFILS, ADDRESSES, JEOPARDISES). Ad-hoc creation in `repo.py:857–870` is a latent uniqueness bug. ADR-006 introduces a 5th producer (Policy ADDRESSES Precept) — the cost of leaving it informal grows with each WP. |
| C | Policy attachment anchor | **Both** — `ADDRESSES` to Precept (primary, semantic) and `IMPLEMENTS` to Control (concrete, OSCAL-aligned) | Use case (ii) ("policy review against threat/compliance change") needs the Precept anchor (precept is what threats jeopardise). Use case (iii) ("policy architecture build/review") needs the Control anchor (controls are the OSCAL units). Forcing a single anchor loses one of the two queries. |
| D | Param node or property bag on Control? | **Standalone Param node** | Property-bag does not compose with org-scoped `Policy -[:BINDS]-> Param` bindings; you cannot put per-org values on a property bag without duplicating Control or stashing JSON. Standalone node makes BINDS a normal edge with a `value` property. Also matches OSCAL's own data model (params are addressable by id). |
| E | Org scoping | `SCOPED_TO Organisation` on AssetClass / Policy / PolicySection (optional). Param NOT org-scoped. | Param is a property of a Control (which is global to a Framework version); org-specific values live on the BINDS edge from Policy. This keeps Param de-duplicated across orgs. |
| F | Vector indexes | **Yes** for Policy + PolicySection. **No** for AssetClass + Param + (this WP) Precept. | Policy/PolicySection are search targets ("show me policies addressing this threat"). AssetClass is a structural taxonomy node — searched by id/name, not embedding. Param is a structural node — never search target. Precept index deferred until search demand is demonstrated. |

---

## Test Plan

### Unit tests
- `tests/cyber_knowledge/test_schemas_enums.py` (new) — assert `POLICY_STATUS`, `PARAM_TYPE`, `ASSET_CLASS_KIND` exist with the documented members. Pure import-and-assert; no DB.
- `tests/cyber_knowledge/test_schema_init_constants.py` (extend if exists, else new) — assert that the five new labels (`Precept`, `AssetClass`, `Policy`, `PolicySection`, `Param`) are present in `KNOWLEDGE_CONSTRAINTS`.

### Integration tests (require live stack — Memgraph running; FastAPI not required for this WP)
- `tests/cyber_knowledge/test_schema_init_integration.py::test_new_constraints_created` — wipe DB, run `python -m cyber_knowledge.ingest.schema_init`, query `SHOW CONSTRAINT INFO`, assert all 5 new uniqueness constraints are present alongside the existing ones.
- `tests/cyber_knowledge/test_schema_init_integration.py::test_new_vector_indexes_created` — same DB, query `SHOW INDEX INFO`, assert `policy_embedding_idx` and `policy_section_embedding_idx` exist with `Label=Policy/PolicySection`, `Property=embedding`, type vector, and the configured capacity.
- `tests/cyber_knowledge/test_schema_init_integration.py::test_schema_init_idempotent` — run schema-init twice in succession on the same DB; second run must exit 0 with no `ClientError` surfaced.
- `tests/cyber_knowledge/test_schema_init_integration.py::test_uniqueness_enforced` — for each new label, create two nodes with the same `id`; assert the second `CREATE` raises a uniqueness violation. Clean up after each.
- `tests/cyber_knowledge/test_schema_init_integration.py::test_existing_constraints_intact` — after re-running schema-init, every pre-WP-174 constraint (Framework / Control / Norm / Document / Chunk / BusinessAttribute / Organisation / Jurisdiction / Threat / ThreatReport / Asset) is still present and unchanged. Guards against accidental rewrites of the existing schema spine.
- `tests/cyber_knowledge/test_schema_init_integration.py::test_no_data_inserted` — `MATCH (n:AssetClass) RETURN count(n)` and same for Policy / PolicySection / Param / Precept all return 0 after schema-init. Proves the WP is genuinely schema-only — no seed data leaked in.

All six integration tests carry `@pytest.mark.integration` and run under `pytest -m integration` against live Memgraph (CLAUDE.md "DoD" gate 3).

### ADR file lint (unit-level, no DB)
- `tests/cyber_knowledge/test_adr_006_present.py::test_adr_006_file_present` — `docs/architecture/ADR-006-asset-policy-oscal-parameter-model.md` exists.
- Same file `::test_adr_006_references_prior_adrs` — file content mentions `ADR-001`, `ADR-002`, and `ADR-005` at least once each.
- Same file `::test_adr_006_decision_has_numbered_list` — the section after `## 1. Decision` contains at least 5 numbered list items.
- Same file `::test_adr_006_names_every_new_label` — file mentions `AssetClass`, `Policy`, `PolicySection`, `Param`, `Precept` at least once each.

### Smoke / live-stack verification (manual, not pytest)
1. `docker compose down -v && docker compose up -d memgraph` — Memgraph clean.
2. `python -m cyber_knowledge.ingest.schema_init` — exits 0; prints constraints OK / indexes OK.
3. `python -m cyber_knowledge.ingest.schema_init` (re-run) — exits 0; idempotent.
4. `docker compose up -d api` then `curl -s http://localhost:8000/openapi.json | jq '.paths | keys | length'` — path count unchanged vs master (zero new routes — schema-only WP).
5. `pytest -m integration -k knowledge` — all green; no regressions in the existing knowledge-layer integration suite.

### Acceptance criteria
- `docs/architecture/ADR-006-asset-policy-oscal-parameter-model.md` exists and references ADR-001, ADR-002, ADR-005 by relative link.
- ADR-006 contains all 8 sections in the outline above; Decision section is a numbered list with ≥5 commitments; every new label (`AssetClass`, `Policy`, `PolicySection`, `Param`, `Precept`) is named in the file.
- `cyber_knowledge/schemas.py` exports `POLICY_STATUS`, `PARAM_TYPE`, `ASSET_CLASS_KIND` as frozensets matching the ADR §3 Node Model.
- `cyber_knowledge/ingest/schema_init.py` declares uniqueness constraints for `AssetClass`, `Policy`, `PolicySection`, `Param`, `Precept` and vector indexes `policy_embedding_idx` + `policy_section_embedding_idx`.
- `python -m cyber_knowledge.ingest.schema_init` runs cleanly against an empty Memgraph: all constraints + vector indexes created, all validated, exit 0.
- Re-running schema-init on a populated DB is idempotent (exit 0, no errors).
- After schema-init, zero nodes exist with any of the new labels (no seed data leaked in).
- All existing constraints and vector indexes from pre-WP-174 are intact and unchanged.
- All existing `pytest -m integration` tests still pass.
- All existing `pytest` (unit) tests still pass.
- `/openapi.json` path list unchanged vs master — proves no API surface added.
- No new entries in `cyber_knowledge/bridge.py` or `cyber_knowledge/mcp_tools.py`; ADR-005 two-door contract preserved.
- `CLAUDE.md` data-model quick-reference updated with the four new node labels and the new edges.
- `/simplify` run on the diff produces no high-value / low-effort findings (schema-only WP — minimal surface).
- `engineering:deploy-checklist` completed and all gates green.

---

## Risks / Open Questions

**A. AssetClass.kind vs Asset.asset_type overlap.** Both enumerate IT/OT/IoT/integration. Until industry/business-type axes land, `asset_type` is redundant with the simplest AssetClass kind. ADR-006 documents this as accepted tech debt; review trigger is "industry/business-type axes introduced" — at that point, choose to deprecate `Asset.asset_type` or repurpose it.

**B. Policy ↔ Document overlap.** A written policy IS a document at the filesystem level. ADR-006 asserts they are **orthogonal roles**, not subtypes: Policy = organisational commitment (status, effective_at, bindings); Document = source artefact (provenance, hash, file). A Policy may CITE one or more Documents. The risk: in practice every Policy may have a 1:1 Document, and the second label becomes pure overhead. Review trigger named.

**C. Param composition with non-OSCAL frameworks.** MITRE ATT&CK has no `params`; D3FEND has structured fields but not OSCAL-shaped. If future ingests need param-like values that don't fit `Param`'s OSCAL-derived shape, options are (i) widen Param, (ii) split Param by source taxonomy. ADR-006 names this as a review trigger; WP-174 commits only to the OSCAL shape.

**D. Industry/business-type axes deferred — but how soon?** Oliver's 2026-05-11 direction is "deferred". If WP-179 (pressure engine) needs business-type scoping to produce useful pressure scores, the deferral may collapse. Open question for the implementer: WP-179's scope spec should be checked against this before WP-174 lands.

**E. Should `PolicySection` reuse Chunk?** Chunk already has embedding + text + position semantics. Decision in this plan: keep PolicySection distinct — Chunks live in the **source-document** lattice (Document → Chunk), PolicySection lives in the **policy-commitment** lattice (Policy → PolicySection). Cross-mixing risks edge-direction ambiguity. Review trigger if PolicySection content turns out to be 1:1 chunked source-doc passages.

---

## Out of Scope (explicit checklist — WP-174 does NOT do these)

- [ ] OSCAL parser implementation (WP-175)
- [ ] GS++ catalog ingest (WP-176)
- [ ] SP 800-53 re-ingest using new Param shape (WP-175 follow-on)
- [ ] Asset taxonomy seed file or hierarchy data (later WP)
- [ ] Pydantic create/read/update models for the new labels (WP-175)
- [ ] HTTP routes for Policy / AssetClass / Param (later WP)
- [ ] Bridge / MCP-tool exposure of new labels (later WP)
- [ ] Pressure-engine logic against AssetClass × Policy × Threat (WP-179)
- [ ] Policy authoring UI (out of repo scope)
- [ ] Migration of any existing `Asset` nodes to attach `CLASSIFIED_AS` edges (no existing data; deferred to whichever WP introduces AssetClass instances)
- [ ] Vector index for `Precept` (deferred — see Decision Point F)
- [ ] Re-running existing ingest scripts (`sp800_53.py`, `gs_pp.py`) — schema additions are additive; existing ingests continue to work unchanged

---

## Implementer hand-off notes

1. Move WP-174 to "Currently In Progress" in BACKLOG.md before starting.
2. Write the ADR first; let the section-by-section drafting force any clarification of the Decision Points. If a Decision Point shifts during drafting, flag it before writing code.
3. Land the schema-init delta as a single commit alongside the ADR.
4. Run `python -m cyber_knowledge.ingest.schema_init` twice against a clean Memgraph; capture the output in the WP completion notes.
5. Run `pytest -m integration` and `pytest` (unit). Both must pass.
6. `/simplify` → `engineering:deploy-checklist` → commit `WP-174: ADR-006 — asset and policy node model + OSCAL parameter handling` → BACKLOG.md write-back + retrospective note.

---

## /simplify findings (2026-05-12)

Three review agents (code-reuse, code-quality, efficiency) flagged a converging set of issues. Acted on the high-value findings inside this WP; deferred the structural refactors to follow-up WPs.

### Acted on in this WP

- **Schema-utils duplication eliminated.** First cut had inlined `get_embedding_dimension` and `create_constraint` into `cyber_knowledge/ingest/schema_init.py` to work around the WP-173 acceptance gap (`/app/scripts/` not in the docker image). Refactored: helpers now live at `cyber_knowledge/ingest/schema_utils.py` (inside the package boundary); `scripts/schema_utils.py` becomes a deprecation shim re-exporting from the new location for `scripts/init_schema.py` and `tests/test_wp077_schema_utils.py`. Same pattern WP-173 used for `script_utils.py`.
- **Source-of-truth drift.** `NEW_LABELS`/`NEW_CONSTRAINTS`/`EXISTING_CONSTRAINTS` hand-maintained string-tuple lists in three test files were duplicating `KNOWLEDGE_CONSTRAINTS`. Replaced with slices of `KNOWLEDGE_CONSTRAINTS[-5:]` (new) / `[:-5]` (pre-existing). `test_adr_006_present.py` imports `NEW_LABELS` from `test_schema_init_constants.py` rather than hard-coding.
- **Redundant enum tests collapsed.** `test_schemas_enums.py` had two tests per frozenset (`isinstance` + member-equality); consolidated into one parametrised test per frozenset.
- **Repeated `init_main()` calls.** Six integration tests each ran `init_main()` fresh (including a multi-second SentenceTransformer load per call). Replaced with a single `@pytest.fixture(scope="module") initialised_schema` that calls `init_main()` once. `test_schema_init_idempotent` keeps the second-call check.
- **WP/ADR narration comments dropped.** Removed `# WP-174 / ADR-006: ...` lines from `schema_init.py`, `schemas.py` (banner block above the three new enums), and `test_schema_init_constants.py`.
- **Numeric literal style.** `policy_index_capacity: int = 5_000` → `5000`; same for `20_000` → `20000`, matching the convention on the adjacent capacity settings.
- **WP-077 test patch target.** Updated `tests/test_wp077_schema_utils.py` from `patch("schema_utils.SentenceTransformer")` to `patch("cyber_knowledge.ingest.schema_utils.SentenceTransformer")` so the test follows the moved code.

### Deferred — added to BACKLOG.md

- **WP-181** — Revert dead `memfabric-db` port-bind in `docker-compose.yml` (commit `b0b0d40` provides no useful access because sshd has `AllowTcpForwarding no`).
- **WP-182** — Refactor `schema_init.py` vector-index creation into a table-driven loop (seven near-identical 18-line blocks → ~25 lines). Out of scope for additive WP-174 because it touches all pre-existing blocks.
- **WP-183** — Promote `_get_constraints` / `_get_vector_indexes` to a shared test helper; `tests/cyber_knowledge/test_schema_init_integration.py` and `tests/test_wp069_knowledge_schema.py` carry near-identical copies.
