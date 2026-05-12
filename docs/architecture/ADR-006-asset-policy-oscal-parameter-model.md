# ADR-006: Asset and Policy Node Model + OSCAL Parameter Handling

| Field | Value |
|-------|-------|
| Status | Proposed |
| Date | 2026-05-12 |
| Scope | Node model for assets, policies, and OSCAL parameters within the cyber knowledge layer |
| Depends on | [ADR-001](ADR-001-knowledge-layer-placement.md) (placement), [ADR-002](ADR-002-knowledge-layer-graph-model.md) (graph model), [ADR-005](ADR-005-cyber-knowledge-package-boundary.md) (package boundary) |
| See also | OSCAL 1.1.3 catalog schema; BSI Grundschutz++ catalog (`github.com/BSI-Bund/Stand-der-Technik-Bibliothek`) |

## 1. Decision

WP-174 lands the schema scaffolding (uniqueness constraints + vector indexes) for four new labels (`AssetClass`, `Policy`, `PolicySection`, `Param`) and formalises one existing label (`Precept`). The model is committed to the following points; all are numbered so the ADR has a stable contract for the WPs that build on it.

1. Introduce `AssetClass` as a taxonomy node above concrete `Asset` instances. The edge is `Asset -[:CLASSIFIED_AS]-> AssetClass`. `INSTANCE_OF` is rejected because it is already used for recurring-task instances on the memory-fabric side (see CLAUDE.md data-model quick-reference) and reusing the label across the package boundary would cause confusion.
2. Defer industry / business-type sub-axes. Start with a pure class hierarchy: `AssetClass -[:SUBCLASS_OF]-> AssetClass`, a directed acyclic graph. Acyclicity is enforced at edge-create time by WPs that populate the taxonomy, not by schema.
3. Formalise `Precept` with a uniqueness constraint on `(Precept, id)`. Precept is already referenced by four edge types (`REQUIRES`, `FULFILS`, `ADDRESSES`, `JEOPARDISES`) and ADR-006 introduces a fifth producer (`Policy -[:ADDRESSES]-> Precept`); the cost of leaving it informal grows with each WP. No vector index for `Precept` in this WP — search rides on `Control` / `Chunk` indexes for now.
4. Introduce `Policy` and `PolicySection`. The decomposition edge is `Policy -[:HAS_SECTION]-> PolicySection`. Both labels carry an `embedding` property and both get vector indexes — `policy_embedding_idx` and `policy_section_embedding_idx`.
5. **Two-anchor Policy attachment.** A `Policy` (or `PolicySection`) attaches to the lattice at two complementary anchors: `Policy -[:ADDRESSES]-> Precept` (primary, semantically rich — supports "policy review against threat / compliance change") and `Policy -[:IMPLEMENTS]-> Control` (OSCAL-concrete — supports "policy architecture build / review"). Either edge is optional; a Policy may have one, the other, or both.
6. `Param` is a **standalone node**, not a property bag on Control. `Control -[:HAS_PARAM]-> Param` declares the parameter; `Policy -[:BINDS {value, bound_at}]-> Param` records the org-specific resolved value. A property-bag approach was rejected because per-org values cannot live on a property bag without duplicating the Control or stashing JSON; the standalone node makes `BINDS` a normal edge with a `value` property.
7. **Org scoping.** `AssetClass`, `Policy`, and `PolicySection` may be org-scoped via an optional `-[:SCOPED_TO]-> Organisation` edge. Global classes / policies omit the edge. `Param` is **not** org-scoped — it is a property of a Control (which is global to a Framework version); org-specific values live on the `BINDS` edge from a `Policy`. This keeps `Param` de-duplicated across orgs.
8. **Vector index policy.** Only `Policy` and `PolicySection` get vector indexes in this WP. `AssetClass` and `Param` do not — they are taxonomy / structural nodes searched by id or name, never as embedding targets. `Precept` index is deferred until search demand is demonstrated (review trigger named below).
9. `Policy` is **orthogonal to** `Document`, not a specialisation. A `Policy` is an organisational commitment (status, effective_at, bindings); a `Document` is a source artefact (provenance, hash, file). A `Policy` MAY cite `Document`s via `Policy -[:CITES]-> Document`, but the two roles are distinct. The risk that every Policy turns out to have a 1:1 Document is named as a review trigger.
10. **WP-174 is schema-only.** No ingest, no Pydantic CRUD models, no HTTP routes, no bridge surface, no seed data. WP-175 (generic OSCAL ingest), WP-176 (GS++ apply), and WP-179 (pressure engine) will populate the new labels.

## 2. Context

Three product use cases drive ADR-006:

- (i) **Threat-and-compliance-aware maturity review** — needs `Policy` attached to `Precept` so threat-jeopardy traversal reaches policies via the precept layer.
- (ii) **Policy review against threat / compliance change** — needs `Policy -[:ADDRESSES]-> Precept` (primary) and `Policy -[:IMPLEMENTS]-> Control` (concrete) so a change in the threat or compliance layer surfaces every policy that depends on it.
- (iii) **Policy architecture build / review** — needs `PolicySection` granularity and `Policy -[:BINDS]-> Param` so OSCAL parameter resolution is queryable.

The proximate trigger is the OSCAL 1.1.3 inspection done during WP-173: `control.params` and `{{ insert: param }}` placeholders in `control.parts.statement` have no home in the current schema. Without `Param`, every OSCAL ingest either drops parameters (correctness loss) or smuggles them into `Control` as JSON (modelling loss). ADR-006 lands the `Param` node so WP-175 can do the ingest correctly.

Oliver's 2026-05-11 direction on the asset side was "class-based taxonomy with industry / business-type axes deferred." ADR-006 honours that: `AssetClass` ships with a `kind` enum that covers the IT/OT/IoT/integration/data/process/people/facility split, and the industry axis is named as a review trigger.

## 3. Node Model

### 3.1 AssetClass

- **Purpose.** Taxonomy node above concrete `Asset` instances. An `Asset` is *classified as* one or more `AssetClass` nodes.
- **Uniqueness.** `(AssetClass, id)`.
- **Properties.** `id` (kebab-case), `name`, `description`, `kind` (enum from `ASSET_CLASS_KIND`: `it | ot | iot | integration | data | process | people | facility`).
- **Vector index.** None — taxonomy node, searched by id / name.
- **Examples.** `it-endpoint`, `ot-plc`, `data-pii`, `people-privileged-user`.

### 3.2 Policy

- **Purpose.** Organisational policy artefact representing a commitment (status + effective date + bindings).
- **Uniqueness.** `(Policy, id)`.
- **Properties.** `id`, `title`, `summary`, `status` (enum from `POLICY_STATUS`: `draft | active | deprecated | retired`), `version`, `effective_at`, `review_due_at`, `embedding`.
- **Vector index.** `policy_embedding_idx` on `Policy(embedding)`.
- **Examples.** `pol-acme-access-control-v2`, `pol-acme-incident-response-v1`.

### 3.3 PolicySection

- **Purpose.** Chunked subsection of a `Policy`, the granular target of `ADDRESSES` / `IMPLEMENTS` / `BINDS` edges and of semantic search.
- **Uniqueness.** `(PolicySection, id)`.
- **Properties.** `id`, `policy_id` (denormalised for cheap filters), `heading`, `text`, `order` (int), `embedding`.
- **Vector index.** `policy_section_embedding_idx` on `PolicySection(embedding)`.
- **Note.** `PolicySection` is *not* a `Chunk`. `Chunk` lives in the source-document lattice (`Document -[:HAS_CHUNK]-> Chunk`); `PolicySection` lives in the policy-commitment lattice (`Policy -[:HAS_SECTION]-> PolicySection`). Cross-mixing risks edge-direction ambiguity — see review trigger.

### 3.4 Param

- **Purpose.** OSCAL parameter declaration, addressable by qualified id.
- **Uniqueness.** `(Param, id)` where `id` is qualified, e.g. `sp800-53:ac-1_prm_1` or `gs-pp:SYS.1.1.A1_prm_2`.
- **Properties.** `id`, `control_id` (denormalised), `label`, `param_type` (enum from `PARAM_TYPE`: `string | integer | enum | select | datetime | duration`), `allowed_values` (list of strings, for `enum` / `select` types), `guidance`.
- **Vector index.** None — structural node, never a search target.

### 3.5 Precept (formalised)

- **Purpose.** Already in use at runtime (referenced by `REQUIRES`, `FULFILS`, `ADDRESSES`, `JEOPARDISES`); ADR-006 promotes it to a first-class label with a uniqueness constraint.
- **Uniqueness.** `(Precept, id)`.
- **Properties.** `id`, `name`, `text`, `framework_id` (optional).
- **Vector index.** None in this WP — deferred until search demand is demonstrated. Currently rides on `Control` / `Chunk` text indexes.

## 4. Edge Model

| Edge | From → To | Direction | Cardinality | Properties |
|------|-----------|-----------|-------------|------------|
| `CLASSIFIED_AS` | Asset → AssetClass | one-way | n:m | none |
| `SUBCLASS_OF` | AssetClass → AssetClass | one-way (DAG) | n:1 typical | none |
| `HAS_SECTION` | Policy → PolicySection | one-way | 1:n | `order int` |
| `ADDRESSES` (extended) | Policy / PolicySection → Precept | one-way | n:m | `confidence float` (optional) |
| `IMPLEMENTS` | Policy / PolicySection → Control | one-way | n:m | none |
| `HAS_PARAM` | Control → Param | one-way | 1:n | none |
| `BINDS` | Policy / PolicySection → Param | one-way | n:m | `value string` (org-resolved value), `bound_at datetime` |
| `CITES` | Policy / PolicySection → Document | one-way | n:m | none |
| `SCOPED_TO` | AssetClass / Policy / PolicySection → Organisation | one-way | n:1 | none |

The pre-WP-174 edges (`REQUIRES`, `FULFILS`, `ADDRESSES Control→Precept`, `JEOPARDISES`, `MAPS_TO`, `HAS_CHUNK`, etc.) are unaffected. The `ADDRESSES` edge is widened to also originate from `Policy` and `PolicySection`, in addition to the existing `Control → Precept` use.

## 5. Relationship to existing labels

- **Asset.** Gains a `CLASSIFIED_AS` edge upward to `AssetClass`. The existing `asset_type` property remains in place; `AssetClass.kind` covers a similar vocabulary at the taxonomy layer. The overlap is accepted tech debt until industry / business-type axes land (Risk A).
- **Precept.** Now first-class with a uniqueness constraint; runtime behaviour unchanged.
- **Framework / Control / Norm.** Unchanged structurally. `Control` gains an outgoing `HAS_PARAM` edge.
- **BusinessAttribute.** Unchanged; `FULFILS` still terminates here.
- **Chunk.** Unchanged. `PolicySection` is deliberately *not* a `Chunk`. If a future need arises to chunk `PolicySection.text` for full-text search, those `Chunk` nodes would attach inside the source-document lattice, not replace `PolicySection`.
- **Document.** Unchanged. `Policy -[:CITES]-> Document`; `Policy` is not a `Document` subtype.

## 6. OSCAL parameter binding

How `control.params` from OSCAL catalogs resolve to org-specific values:

1. Ingest (WP-175) creates one `Param` node per `control.params[*]`, linked `Control -[:HAS_PARAM]-> Param`.
2. The `{{ insert: param, param-id="ac-1_prm_1" }}` placeholders in `control.parts.statement` survive verbatim in the corresponding `Chunk.text`.
3. An org-specific `Policy` (or `PolicySection`) resolves a `Param` via `Policy -[:BINDS {value: "30 days", bound_at: <ts>}]-> Param`.
4. Rendering "control statement as configured for org X" is then: look up the `Chunk.text`, resolve each placeholder against the `BINDS` edges originating from active `Policy` nodes that are `SCOPED_TO` that `Organisation`.
5. ADR-006 specifies the data model only. The resolution algorithm is WP-175 / WP-176 work.

## 7. Review triggers (when to revisit ADR-006)

- Industry / business-type sub-axes become necessary → revisit `AssetClass` shape and the overlap with `Asset.asset_type`.
- `Policy -[:CITES]-> Document` edge volume grows to suggest Policy *is* a Document specialisation → consider merge.
- MITRE ATT&CK or D3FEND introduce param-like fields that don't fit `Param` cleanly → consider widening `Param` or splitting by source taxonomy.
- `Precept` text search becomes required → add `precept_embedding_idx`.
- Cross-org `Policy` reuse becomes common → revisit `SCOPED_TO` edge direction.

## 8. Consequences

**Positive.**

- Unblocks WP-175 (generic OSCAL ingest) — `Param` now has a target.
- Unblocks WP-176 (GS++ apply) — `Policy` / `PolicySection` now exist.
- Unblocks WP-179 (pressure engine) — org-scoped `Policy` + `AssetClass` surface available.
- `Precept` becomes a first-class queryable label with a stable uniqueness contract.

**Negative.**

- `AssetClass.kind` and `Asset.asset_type` overlap until industry axes land (Risk A).
- Two-anchor `Policy` attachment (`Precept` and `Control`) gives flexibility but adds a modelling decision to every Policy ingest path.
- Five new constraints + two new vector indexes add a small operational cost on schema-init; index capacity must be sized and tuned.

**Boundary note (per ADR-005).** When a follow-on WP exposes `Policy` or `AssetClass` over the HTTP API or MCP surface, the addition MUST go through `cyber_knowledge/bridge.py` per ADR-005's two-door contract. WP-174 does not cross that boundary — no new label is exposed in this WP.

## 9. Risks / Open Questions

**A. AssetClass.kind vs Asset.asset_type overlap.** Both enumerate IT/OT/IoT/integration. Until industry / business-type axes land, `asset_type` is redundant with the simplest `AssetClass.kind`. Accepted tech debt; review trigger named in §7.

**B. Policy ↔ Document overlap.** A written policy *is* a document at the filesystem level. ADR-006 asserts they are **orthogonal roles**, not subtypes. The risk is that in practice every Policy has a 1:1 Document and the second label becomes pure overhead. Review trigger named in §7.

**C. Param composition with non-OSCAL frameworks.** MITRE ATT&CK has no `params`; D3FEND has structured fields but not OSCAL-shaped. If future ingests need param-like values that don't fit the OSCAL-derived shape, options are (i) widen `Param`, (ii) split `Param` by source taxonomy. ADR-006 commits only to the OSCAL shape for WP-174.

**D. Industry / business-type axes deferred — but how soon?** If WP-179 (pressure engine) needs business-type scoping to produce useful pressure scores, the deferral may collapse. WP-179's scope spec should be checked against this before WP-174 lands as the basis for new ingests.

**E. Should PolicySection reuse Chunk?** Chunk already has `embedding` + `text` + position semantics. Kept distinct in this ADR — Chunks live in the source-document lattice (`Document → Chunk`); PolicySection lives in the policy-commitment lattice (`Policy → PolicySection`). Cross-mixing risks edge-direction ambiguity. Review trigger: PolicySection content turns out to be 1:1 chunked source-doc passages.
