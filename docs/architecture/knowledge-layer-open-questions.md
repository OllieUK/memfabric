# Knowledge Layer Graph Architecture — Open Questions

Raised during architecture review of WP-070 through WP-076 (2026-04-02).
Remove each question once resolved and the decision is captured in the relevant ADR or WP spec.

---

## RESOLVED: Standard → Norm rename

**Decision:** Rename the `Standard` node label to `Norm`. "Norm" is prescriptive-agnostic — it covers frameworks (NIST CSF), standards (ISO 27001), regulations (NIS2), and guidelines without implying a position in a policy pyramid (Policy → Standard → Work Instruction). Avoids the "is this a standard or a framework?" debate. Propagates to edge names, schema scripts, YAML seed data, API endpoints, and documentation.

**Impact:** WP-070, WP-071, WP-074, WP-075, WP-076, ADR-001, knowledge_schemas.py, init_knowledge_schema.py, seed YAML files.

---

## RESOLVED: Q1 — Control tree as the spine; Precepts, Norms, and Attributes dock in from the side

### Core architectural insight

The control tree is the organisation's security architecture — it exists independently of any norm. Norms are *inputs*, not *owners*. They dock into the tree at whatever level of specificity they demand. The tree carries all drivers downward into implementation specifics.

This maps to the SABSA matrix: contextual layer (attributes, culture, ethics) → conceptual layer (precepts, high-level controls) → logical/physical/component layers (progressively more specific controls).

### The control tree

A single `Control` node type with a self-referential hierarchy via `CONTAINS` edges. Depth varies by domain (2–6+ levels). No fixed types like ControlDomain/SubControl — a `level` property distinguishes depth.

```
(:Control {level: "domain", title: "Cryptography"})
    -[:CONTAINS]->
(:Control {level: "control", title: "Encryption at rest"})
    -[:CONTAINS]->
(:Control {level: "sub-control", title: "Removable media encryption"})
    -[:CONTAINS]->
(:Control {level: "implementation", title: "AES-256 with centralised KMS"})
```

### The norm tree

Norms also form a self-referential hierarchy via `CONTAINS` edges, mirroring the control tree. This enables granular change tracking: when a single article is amended, only its `MAPS_TO` edges and downstream `SUPPORTS` edges need review — not the entire framework mapping.

```
(:Norm {level: "framework", title: "GDPR"})
    -[:CONTAINS]->
(:Norm {level: "chapter", title: "Chapter IV - Controller and Processor"})
    -[:CONTAINS]->
(:Norm {level: "article", title: "Article 25 - Data protection by design"})
    -[:CONTAINS]->
(:Norm {level: "paragraph", title: "Article 25(1)"})
```

The `level` property uses norm-appropriate values (framework/chapter/section/article/paragraph/clause — varies by norm type). Same `CONTAINS` edge type as the control tree.

**`MAPS_TO` originates from the most specific normative statement**, not the top-level framework. Article 25(1) `MAPS_TO` your "privacy by design" control, not "GDPR" as a whole.

**`REQUIRES` (Norm → Precept) also originates from specific statements:**

```
(:Norm {level: "paragraph", title: "Art 25(1)"})
    -[:REQUIRES {normative: "must"}]-> (:Precept {text: "data protection measures must be implemented by design"})
```

**Benefits:**
- Granular `text_hash` invalidation: a change to one paragraph re-triggers only its SUPPORTS inference
- Granular normative language: Article 25(1) is a MUST, Article 25(2) is a SHOULD — precision at the statement level
- Granular `APPLIES_IN`: framework-level jurisdiction inherited by child statements unless narrowed (same narrowing rule as controls — see Q2)

### What docks into the top of the tree

The topmost Control nodes are the integration point for all drivers:

- **Precepts** — source-agnostic security obligations (`Control -[ADDRESSES]-> Precept`)
- **BusinessAttributes** — abstract qualities (`Precept -[FULFILS]-> BusinessAttribute`)
- **Cultural/ethical requirements** — internal drivers not (yet) regulated by external norms
- **Risk appetite decisions** — accepted residual risk levels per domain

### How Norms dock in

Norms do not own controls. They **map to** nodes in the control tree at the appropriate level:

```
Norm -[MAPS_TO]-> Control    (at whatever level the norm's specificity demands)
```

`HAS_CONTROL` is replaced by `MAPS_TO`. A broad norm (GDPR) maps high in the tree. A specific technical regulation maps lower. If two norms both map to the same node, cross-framework equivalence is implicit — no separate `MAPPED_TO` edge needed between the norms' original definitions. The control tree *is* the reconciliation layer.

`MAPPED_TO` (Control ↔ Control cross-framework equivalence) is retained only for cases where external norms define their own control numbering and we need to record the explicit mapping between a norm's control reference and our tree node (e.g. "ISO 27001 A.8.24 maps to our Cryptography/Encryption at rest").

### Precepts

A `Precept` is a distilled, source-agnostic statement of what must be true. Example: "personal data must be protected from unauthorised disclosure".

```
Norm -[REQUIRES]-> Precept -[FULFILS]-> BusinessAttribute
                      ^
                      |
          Control -[ADDRESSES]-> Precept   (top-level controls)
```

Multiple Norms can `REQUIRE` the same Precept (GDPR, UK-GDPR, CCPA converge). Top-level Controls `ADDRESS` Precepts. Lower-level Controls inherit the Precept relationship through tree traversal — they don't need their own `ADDRESSES` edge.

Precepts also accommodate drivers that don't stem from external norms — internal culture, ethics, or proactive security decisions can produce Precepts that exist without any `REQUIRES` edge from a Norm.

### Coverage attribution on CONTAINS edges

The relationship between a child control and its parent carries coverage semantics. A child may fully satisfy, partially satisfy, or not satisfy the parent's requirement. Partial satisfaction has a cause: scope limitation ("covers removable media only, not databases") or functional limitation ("uses AES-128, below recommended key length").

Multiple children may contribute to the same parent requirement. The **residual gap belongs to the parent domain**, not to any individual child. The parent is responsible for knowing whether its requirement is fully covered by its children.

**CONTAINS edge properties:**

```
(:Control)-[:CONTAINS {
    coverage: "partial",              // full | partial | none
    limitation_type: "scope",         // scope | functional | null (when coverage=full)
    limitation_detail: "covers removable media only, not databases or backups",
    normative: "must"                 // must | shall | should | may | must_not | should_not
}]->(:Control)
```

Gap analysis aggregates coverage across all children of a parent. Residual gap is attributed to the parent domain: "encryption at rest has 60% child coverage; 40% residual gap is this domain's responsibility."

### Normative language on edges

RFC 2119 normative terms (MUST, SHALL, SHOULD, MAY, MUST NOT, SHOULD NOT) change the *nature* of the requirement, not just whether it is met. The same Control node can be a MUST from one norm and a SHOULD from another.

Normative weight belongs on edges, not nodes:

```
Norm -[MAPS_TO {normative: "must"}]-> Control      // GDPR: mandatory
Norm -[MAPS_TO {normative: "should"}]-> Control    // ISO 27001: recommended
Control -[CONTAINS {normative: "must"}]-> Control   // parent domain: mandatory child
Control -[CONTAINS {normative: "may"}]-> Control    // parent domain: optional child
```

**Gap analysis implications:**
- A MUST control with partial coverage → **finding** (non-compliance)
- A SHOULD control with partial coverage → **recommendation** (improvement opportunity)
- A MAY control with no coverage → **acceptable** (no action required)
- A MUST NOT control with evidence of presence → **finding** (violation)

### Scope boundary for WP-070 MVP

Coverage attribution and normative language are edge properties, not structural changes. The node types and edge types already defined can carry them.

- **WP-070 MVP:** Define `CONTAINS` and `MAPS_TO` with these properties in the schema, but make them optional. Default `normative` to `"must"`, default `coverage` to `"full"`.
- **Follow-on WP:** Coverage aggregation queries, normative-weight-aware gap analysis, residual gap attribution to parent domains.

### Conflict modelling (follow-on capability)

Where norms disagree (e.g. implicit vs. explicit consent):

```
(p1:Precept)-[:CONFLICTS_WITH {nature: "contradictory"}]->(p2:Precept)
```

Resolved by an org-scoped decision (a Memory node with type=decision):

```
(m:Memory {type: "decision"})
    -[:RESOLVES {scope_org_id: "org-acme"}]-> (p1:Precept)
    -[:RESOLVES {scope_org_id: "org-acme"}]-> (p2:Precept)
    -[:SUPERSEDES_WITH]-> (p3:Precept {org_id: "org-acme"})
```

The resolved Precept (p3) is org-scoped. Original conflicting Precepts remain universal. Controls then `ADDRESS` the resolved Precept. Downstream traceability: "if this decision changes, what breaks?" — follow the graph downstream.

### Gap analysis changes

Instead of "which controls from Norm X are not implemented?", the questions become:
- "Which nodes in our control tree have no norm coverage?"
- "Which norms map to parts of our tree that have no implementation evidence?"
- "Which precepts have no controls addressing them?"
- "Which top-level control domains have conflicting precepts?"

### Cross-layer implications

- `RESOLVES` (Memory → Precept) is a cross-layer edge — belongs in `knowledge_bridge.py`
- `SUPERSEDES_WITH` (Memory → Precept) is cross-layer — belongs in `knowledge_bridge.py`
- Conflict modelling (`CONFLICTS_WITH`, `RESOLVES`, `SUPERSEDES_WITH`) is not needed for WP-070 MVP

### New/changed nodes

| Node | Key properties |
|------|---------------|
| `Precept` (new) | id, text, org_id (optional — null for universal, set for org-scoped resolved precepts) |
| `Control` (changed) | Added: `level` property (domain/control/sub-control/implementation/etc.) |
| `Norm` (changed) | Added: `level` property (framework/chapter/section/article/paragraph/clause/etc.); self-referential hierarchy via `CONTAINS` |

### New/changed edges

| Edge | Direction | Properties | Change |
|------|-----------|------------|--------|
| `CONTAINS` (new) | Control → Control | `coverage` (full/partial/none), `limitation_type` (scope/functional/null), `limitation_detail`, `normative` (must/shall/should/may/must_not/should_not, default must) | Hierarchical control tree with coverage semantics |
| `CONTAINS` (new) | Norm → Norm | — | Hierarchical norm tree (framework → chapter → article → paragraph) |
| `MAPS_TO` (new) | Norm → Control | `normative` (must/shall/should/may/must_not/should_not, default must) | Replaces `HAS_CONTROL`; norms dock into the tree |
| `REQUIRES` (new) | Norm → Precept | `normative` (default must) | Norm demands this obligation |
| `FULFILS` (new) | Precept → BusinessAttribute | — | Obligation serves this abstract quality |
| `ADDRESSES` (retargeted) | Control → Precept | — | Was Control → BusinessAttribute; now top-level Controls → Precepts |
| `MAPPED_TO` (retained) | Control ↔ Control | — | Cross-framework mapping (norm's control ref ↔ our tree node) |
| `CONFLICTS_WITH` (new, follow-on) | Precept ↔ Precept | `nature` (contradictory/overlapping) | Conflicting obligations |
| `RESOLVES` (new, follow-on, cross-layer) | Memory → Precept | `scope_org_id` | Decision resolves conflict |
| `SUPERSEDES_WITH` (new, follow-on, cross-layer) | Memory → Precept | — | Decision produces resolved precept |

### Impact

WP-070 (add Precept, CONTAINS, MAPS_TO; retarget ADDRESSES; add `level` to Control), WP-071 (search may need Precept), WP-074 (seed data, ETL — tree structure in YAML), WP-075 (gap analysis traces through tree and Precepts), WP-076 (tests), init_knowledge_schema.py (Precept constraint), knowledge_schemas.py (level enum).

---

## RESOLVED: Q2 — Jurisdiction inheritance within both trees, narrowing only

**Decision:** `APPLIES_IN` jurisdiction is inherited downward within both the norm tree and the control tree. Children can narrow but never widen their parent's scope. Controls in the control tree derive their jurisdictional applicability from the norms that map to them, not from independent `APPLIES_IN` edges.

### Jurisdiction flows through three mechanisms

**1. Within the norm tree (Norm → child Norm via CONTAINS):**

The framework-level Norm carries `APPLIES_IN` → Jurisdiction. Child statements (chapters, articles, paragraphs) inherit that scope by default. A child statement may have its own `APPLIES_IN` edges that **narrow** the scope (e.g. "this article applies only to essential entities in critical infrastructure sectors"). Widening is a data quality error.

```
(:Norm {level: "framework", title: "NIS2"}) -[:APPLIES_IN]-> (:Jurisdiction {code: "EU"})
    -[:CONTAINS]->
(:Norm {level: "article", title: "Article 21(2)(a)"}) -[:APPLIES_IN]-> (:Jurisdiction {code: "EU-critical-infrastructure"})
```

Article 21(2)(a) narrows from EU to EU-critical-infrastructure. Valid. An article claiming `APPLIES_IN → US` under a Norm that only applies in EU is rejected.

**2. From norms to the control tree (Norm → Control via MAPS_TO):**

Controls in the tree do not have their own `APPLIES_IN` edges. A Control's applicable jurisdictions are **derived** from the union of all Norms (at their specific statement level) that `MAPS_TO` it or its ancestors in the control tree.

```
(:Norm {title: "Art 25(1)"}) -[:APPLIES_IN]-> (:Jurisdiction {code: "EU"})
(:Norm {title: "Art 25(1)"}) -[:MAPS_TO]-> (:Control {title: "Privacy by design"})
```

The control "Privacy by design" is applicable in the EU because a EU-scoped norm maps to it. If CCPA also maps to the same control, it additionally becomes applicable in the US. The control tree is jurisdiction-agnostic; jurisdiction comes from the norms.

**3. Within the control tree (Control → child Control via CONTAINS):**

A child Control inherits the jurisdictional scope of its parent (which is itself derived from norms). A child may additionally have norms mapping directly to it, adding further jurisdictional scope. A child never has its own `APPLIES_IN` edges — scope always derives from norms.

### Diagnostic endpoints

- `/knowledge/jurisdiction-violations` — Norm statements whose `APPLIES_IN` exceeds their parent Norm's scope (catches violations introduced by Norm scope changes after child statements were already written)
- `/knowledge/incomplete-jurisdictions` — Norms and Norm statements with no `APPLIES_IN` edges (neither own nor inherited)
- "Which Controls have no jurisdictional coverage?" = Controls with no `MAPS_TO` edges from any Norm (directly or via ancestors)

### Validation

- **Write-time (norm tree):** `POST /knowledge/norm` with `APPLIES_IN` jurisdiction codes checks against parent Norm's `APPLIES_IN` (if a parent exists). Returns HTTP 400 if any jurisdiction exceeds the parent's scope.
- **No write-time validation on Controls for jurisdiction** — Controls don't have `APPLIES_IN` edges; jurisdiction is derived.
- **Diagnostic query** catches drift when a parent Norm's scope is narrowed after children were written.

### Gap analysis query pattern

For "which controls are applicable to org X?":
1. Resolve org's jurisdictions: `(org)-[:OPERATES_IN]->(j:Jurisdiction)`
2. Find norms applicable in those jurisdictions: `(n:Norm)-[:APPLIES_IN]->(j)` (with inheritance within the norm tree)
3. Find controls those norms map to: `(n)-[:MAPS_TO]->(c:Control)` (and their children via `CONTAINS`)
4. Result: the set of applicable controls, each with the norms and jurisdictions that drive them

**Impact:** WP-070 (write-time validation on norm statements, remove `APPLIES_IN` from Control upsert), WP-071 (diagnostic endpoints), WP-075 (gap analysis derives jurisdiction from norms, not controls), WP-076 (tests for inheritance, narrowing, derived jurisdiction on controls).

---

## RESOLVED: Q3 — Drop anchor Memories; tool discovery via MCP, not data layer

**Decision:** Remove anchor Memory creation from the Norm upsert path. Knowledge-layer discovery is handled by MCP tool registration (conditional on feature flag), not by synthetic Memory nodes.

**Rationale:**

- Anchor Memories solved a **tool discovery** problem by polluting the data layer — knowledge-layer code writing Memory nodes violates the bridge-as-sole-coupling-surface invariant (ADR-001 Guardrail 3).
- MCP tools are registered with descriptive docstrings when `ENABLE_KNOWLEDGE_LAYER=true`. LLM-based agents discover the knowledge layer through tool descriptions, not breadcrumb data.
- The bridge module handles cross-layer data relationships (`ABOUT_CONTROL`, `RESOLVES`, etc.). Discovery of the knowledge layer's *existence* is an infrastructure concern, not a data concern.
- A companion agent that is not knowledge-layer-aware should not be making compliance decisions based on a breadcrumb Memory.

**Impact:** WP-070 (remove anchor Memory creation from norm upsert; remove "Anchor Memory created on norm upsert" from Definition of Success), WP-071 (remove "anchor Memory written on standard upsert" from test spec), WP-074 (remove anchor Memory verification from integration test).

---

## RESOLVED: Q4 — Org-scoping on edges and implementation controls, not on Memory nodes

**Decision:** Memory nodes remain org-agnostic. Org-scoping is carried by cross-layer edges (`org_id` on `ABOUT_CONTROL`, `scope_org_id` on `RESOLVES`) and by implementation-level Control nodes (`OWNED_BY` → Organisation). The control tree has a shared reference skeleton (org-agnostic) and org-specific implementation branches.

### Scoping model

**Memory nodes (episodic layer):** No `org_id`. Memories are the consultant's observations and knowledge. The same Memory can be linked to controls in different orgs' contexts via different cross-layer edges.

**Control tree (knowledge layer):**
- **Upper levels (domains, controls, sub-controls):** Org-agnostic. This is the shared reference architecture — security domains like cryptography, access control, incident management exist regardless of org.
- **Implementation levels:** Org-specific. Linked to Organisation via `OWNED_BY`. "AES-256 with AWS KMS" belongs to Org A; "ChaCha20 with HashiCorp Vault" belongs to Org B.

**Cross-layer edges:** Carry `org_id` to scope the relationship. A Memory about Org A's firewall rules links to the relevant control with `ABOUT_CONTROL {org_id: "org-a"}`. The same consultant might make a similar observation about Org B and create a different edge with `org_id: "org-b"`.

**Documents:** Org-scoped via `OWNED_BY` → Organisation (already in the spec). Org A's encryption policy is a different Document from Org B's.

**Norms and Precepts:** Universal — no org-scoping. GDPR applies to all orgs operating in the EU, regardless of which client you're working with.

### Multi-org consulting work model

When switching between clients:
- **Same control tree skeleton** — your reference architecture
- **Different implementation branches** — org-specific controls via `OWNED_BY`
- **Different norm mappings** — different jurisdictions via `OPERATES_IN`, therefore different applicable norms
- **Different evidence** — different Memory → Control edges scoped by `org_id`
- **Different documents** — different policies scoped by `OWNED_BY`

### Key consulting use cases enabled

1. **"Minimum viable policy structure"** — traverse org's jurisdictions → applicable norms → required Precepts → addressing Controls → subtree = minimum scope. Documents with `IMPLEMENTS` edges fill out the policy structure.
2. **"Greatest gaps"** — same traversal, compare against org's Documents, Chunks, and Memory evidence. Three-way reconciliation scoped to org.
3. **"Impact of norm change"** — changed article → its `MAPS_TO` edges to control tree → its `REQUIRES` edges to Precepts → downstream through org's implementation branches.

### Gap analysis org-scoping

Gap analysis queries scope by:
- `(org)-[:OPERATES_IN]->(j:Jurisdiction)` for applicable norms
- `ABOUT_CONTROL.org_id` for Memory evidence
- `(doc)-[:OWNED_BY]->(org)` for Document/Chunk evidence
- `(control)-[:OWNED_BY]->(org)` for implementation-level controls

A Memory with no `ABOUT_CONTROL` edge to a specific org is invisible to that org's gap analysis — it's the consultant's private knowledge until explicitly linked.

**Impact:** WP-070 (Control nodes gain optional `OWNED_BY` → Organisation for implementation-level scoping; no `org_id` on Memory), WP-072 (cross-layer edges carry `org_id` as already specified), WP-075 (gap analysis scopes by org through edges and `OWNED_BY`, not node properties).

---

## RESOLVED: Q5 — Temporal validity on normative statements; review triggered by lifecycle transitions

**Decision:** Normative statements carry temporal validity (`valid_from`, `valid_until`, `announced_at`). When a statement is superseded, the replacement is a new Norm node linked via `SUPERSEDED_BY`. SUPPORTS edge review is triggered by lifecycle transitions, not by raw text changes.

### Temporal properties on Norm nodes

```
(:Norm {
    level: "paragraph",
    title: "Article 25(1)",
    valid_from: "2018-05-25",       // enforcement date
    valid_until: null,               // still in force (null = no known end)
    announced_at: "2016-04-27",     // adoption/publication date
})
```

### Norm versioning via SUPERSEDED_BY

When a normative statement is amended, the original node is **not modified**. A new version is created and linked:

```
(:Norm {title: "Art 25(1)", version: "2018", valid_from: "2018-05-25", valid_until: "2026-12-31"})
    -[:SUPERSEDED_BY]->
(:Norm {title: "Art 25(1)", version: "2027", valid_from: "2027-01-01", valid_until: null, announced_at: "2025-06-15"})
```

Both versions coexist in the graph during the transition period. The old version retains all existing `MAPS_TO` and `REQUIRES` edges. The new version starts without any — establishing those edges is a review exercise.

### Three temporal states

| State | Condition | Meaning |
|-------|-----------|---------|
| **Active** | `valid_from <= now` and (`valid_until` is null or `valid_until > now`) | Currently in force |
| **Announced** | `valid_from > now` and `announced_at <= now` | Known but not yet in force — plan for it |
| **Expired** | `valid_until <= now` | No longer in force — historical record |

### SUPPORTS edge lifecycle on normative transition

When an active normative statement expires and its replacement becomes active:

1. The old statement's `MAPS_TO` edges identify which Controls are affected
2. **`auto-inferred` SUPPORTS edges** on those Controls: detached entirely (no human validation to preserve; re-run inference against the new statement's text)
3. **`confirmed` SUPPORTS edges** on those Controls: reverted to `needs-review` (preserves the fact that a human once validated them; flags for re-review against the new normative text)
4. **`rejected` SUPPORTS edges:** left as-is (already excluded from compliance claims)

The `needs-review` status is added to the SUPPORTS status enum: `auto-inferred`, `confirmed`, `needs-review`, `rejected`.

### SUPPORTS status enum (updated)

| Status | Meaning | Set by |
|--------|---------|--------|
| `auto-inferred` | Machine-inferred from vector similarity | Chunk ingestion / `--link-controls` |
| `confirmed` | Human-validated as correct | `knowledge_confirm_supports` |
| `needs-review` | Previously confirmed, but normative text has changed | Lifecycle transition automation |
| `rejected` | Human-validated as incorrect | `knowledge_reject_supports` |

### Impact assessment use case

"What impact does the change in norm X have?" — query all `announced` Norm nodes that have a predecessor via `SUPERSEDED_BY`, follow the predecessor's `MAPS_TO` edges to the control tree, and the full impact scope is visible before the change takes effect. This enables proactive transition planning.

### New/changed elements

| Element | Change |
|---------|--------|
| `Norm` node | Added: `valid_from`, `valid_until`, `announced_at`, `version` properties |
| `SUPERSEDED_BY` (new edge) | Norm → Norm; links old version to new version |
| `SUPPORTS` edge | Added `needs-review` to status enum |

### Scope boundary for WP-070 MVP

- **WP-070 MVP:** Define `valid_from`, `valid_until`, `announced_at`, `version` as optional properties on Norm nodes. Define `SUPERSEDED_BY` edge type. Add `needs-review` to SUPPORTS status enum in `knowledge_schemas.py`.
- **Follow-on WP:** Automated lifecycle transition detection (scheduled maintenance pass that checks for expired/activated statements and triggers SUPPORTS edge review). Impact assessment query endpoints.

**Impact:** WP-070 (Norm properties, SUPERSEDED_BY edge, SUPPORTS status enum), WP-073 (text_hash invalidation replaced by lifecycle-aware transition logic), WP-074 (YAML seed data includes validity dates), WP-075 (gap analysis filters by active statements only; impact assessment endpoint), knowledge_schemas.py.

---

## RESOLVED: Q6 — IMPLEMENTS as structured metric-based fulfilment, not binary declaration

**Decision:** IMPLEMENTS edges are human-authored structured evidence submissions, not binary declarations or machine inferences. The requirement-owning domain (parent Control) defines the metrics by which fulfilment must be demonstrated. The requirement-fulfilling domain (Document/Organisation) provides measured values against those metrics. Assessment is computed by comparing provided values against defined targets.

This follows the SABSA domain model: the requirement owner sets the requirement *and* the criteria for demonstrating fulfilment. The fulfilling domain provides evidence within those bounds.

### Metric definitions on Controls

Controls that own requirements define a metric schema — what must be demonstrated and what the target is:

```
(:Control {
    title: "Encryption at rest",
    metrics: [
        {
            id: "algorithm",
            type: "quantitative",
            data_type: "enum",
            target: ["AES-256", "ChaCha20"],
            normative: "must"
        },
        {
            id: "key_length",
            type: "quantitative",
            data_type: "integer",
            target_min: 256,
            unit: "bits",
            normative: "must"
        },
        {
            id: "coverage_pct",
            type: "quantitative",
            data_type: "float",
            target_min: 95.0,
            unit: "percent",
            normative: "should"
        },
        {
            id: "role_scoping",
            type: "qualitative",
            description: "Access controls take the scope of the user's organisational role into account",
            normative: "must"
        }
    ]
})
```

### Evidence on IMPLEMENTS edges

The IMPLEMENTS edge carries the provided metric values:

```
(:Document) -[:IMPLEMENTS {
    metrics: {
        algorithm: "AES-256",
        key_length: 256,
        coverage_pct: 87.0,
        role_scoping: {
            assessor: "oliver",
            assessed_at: "2026-03-15",
            judgement: "met",
            narrative: "RBAC model verified; permissions matrix reviewed against org chart"
        }
    }
}]-> (:Control)
```

### Two metric types

| Type | Defined by | Assessed by | Evidence format |
|------|-----------|-------------|-----------------|
| **Quantitative** | Requirement owner: data type, target range, unit | System: compare provided value against target | Numeric/enum value |
| **Qualitative** | Requirement owner: description of what must be demonstrated | Human: assessor provides judgement + narrative | Judgement (met/partially_met/not_met) + narrative |

### Assessment computation

Assessment is **computed at query time**, not stored, by comparing provided values against metric definitions:

- Quantitative: value within target range → `met`; outside → `not_met`; no value provided → `missing`
- Qualitative: uses the human-provided `judgement` field directly
- Overall assessment per IMPLEMENTS edge: `met` (all metrics met), `partially_met` (some met), `not_met` (none met), `incomplete` (metrics missing)

Normative weight from the metric affects severity:
- A `must` metric not met → **finding**
- A `should` metric not met → **recommendation**
- A `may` metric not met → **acceptable**

### IMPLEMENTS vs SUPPORTS — distinct signals

| Edge | Created by | Meaning | Source |
|------|-----------|---------|--------|
| `IMPLEMENTS` | Human (policy owner, consultant, GRC team) | Structured fulfilment claim with metrics | Document registration, ETL, API |
| `SUPPORTS` | Machine (vector similarity) | Inferred textual evidence | Chunk ingestion pipeline |

The three-way reconciliation retains its diagnostic value:
- **implemented_and_supported** — formal declaration with metrics AND textual evidence. Healthy.
- **implemented_not_supported** — org claims fulfilment but no chunk text backs it up. Paper compliance — metrics may be met but the policy content is thin.
- **supported_not_implemented** — chunk text is relevant but no formal declaration with metrics. Shadow compliance — doing the right thing without governance structure.

### Scope boundary for WP-070 MVP

- **WP-070 MVP:** Define `metrics` as an optional JSON property on Control nodes (empty by default). IMPLEMENTS edge accepts optional `metrics` property (flat JSON). No automated assessment computation at write time.
- **Follow-on WP:** Assessment computation endpoint/query. Metric schema validation (check that provided values match expected data types). Dashboard-ready coverage reports with quantitative/qualitative breakdown. Metric completeness diagnostic ("which IMPLEMENTS edges are missing required metrics?").

**Impact:** WP-070 (Control gains optional `metrics` schema; IMPLEMENTS edge gains optional `metrics` values), WP-074 (YAML ETL supports metric definitions on controls and metric values on IMPLEMENTS declarations), WP-075 (gap analysis uses computed assessment rather than binary implemented/not-implemented), knowledge_schemas.py (metric type enums).
