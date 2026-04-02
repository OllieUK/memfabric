# ADR-002: Knowledge Layer Graph Model

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-04-02 |
| Supersedes | Portions of WP-070–076 specs in BACKLOG.md |
| Scope | Knowledge layer node types, edge types, hierarchies, scoping model |
| Depends on | [ADR-001](ADR-001-knowledge-layer-placement.md) (feature-flagged peer module, bridge invariant) |

## Decision

The knowledge layer graph model is structured around a control tree (the organisation's security architecture), a norm tree (prescriptive obligations), frameworks (structural guides and threat taxonomies), threat intelligence, and asset classes — connected by Precepts, with metric-based fulfilment, temporal norm versioning, and an org-scoping model designed for multi-org consulting use.

## Context

ADR-001 established that the knowledge layer lives inside graph-memory-fabric as a feature-flagged peer module. It did not specify the internal graph model beyond high-level node labels. During architecture review of WP-070–076, six structural questions were raised and resolved (documented in `knowledge-layer-open-questions.md`). The decisions fundamentally reshape the graph model from the flat norm-owns-controls structure originally specified in the WP backlog.

### Key architectural insights

1. **The control tree is the spine, not the norms.** The organisation's security architecture exists independently of any norm. Norms are inputs that dock into the tree, not owners of controls.
2. **Precepts are the convergence layer.** Source-agnostic security obligations allow multiple norms to converge on shared requirements without duplicating controls.
3. **Both trees are hierarchical.** Norms decompose into chapters, articles, paragraphs. Controls decompose into domains, sub-controls, implementations. Granularity enables precise change tracking and impact analysis.
4. **Jurisdiction derives from norms, not controls.** The control tree is jurisdiction-agnostic; applicability flows from norms through the mapping edges.
5. **Org-scoping lives on edges and implementation-level controls, not on Memory nodes.** This enables a consultant to maintain a shared reference architecture across clients.
6. **Norms are prescriptive; frameworks are structural guides.** Both feed the control tree but with different roles. Norms create obligations via `MAPS_TO`. Frameworks shape the tree's structure and provide taxonomies (including threat taxonomies like ATT&CK).
7. **Threat intelligence normalises through frameworks.** Analyst reports with different perspectives converge on normalised Threat nodes linked to framework techniques, which then connect to the control tree and asset classes.

## Node Types

### Knowledge layer nodes

| Node | Primary key | Embedding | Key properties |
|------|-------------|-----------|----------------|
| `Norm` | `id` | — | `level` (framework/chapter/section/article/paragraph/clause), `title`, `body`, `lang`, `version`, `valid_from`, `valid_until`, `announced_at`, `text_hash` |
| `Control` | `id` | `ctrl_embedding_idx` | `level` (domain/control/sub-control/implementation), `title`, `body`, `code`, `tags`, `text_hash`, `metrics` (optional JSON — metric schema for fulfilment) |
| `Precept` | `id` | — | `text`, `org_id` (null for universal; set for org-scoped resolved precepts) |
| `Document` | `id` | — | `title`, `policy_level` (strategic/tactical/operational/procedure) |
| `Chunk` | `id` | `chunk_embedding_idx` | `heading`, `body`, `section_ref`, `sequence` |
| `BusinessAttribute` | `id` | — | `name` (e.g. customer trust, regulatory standing, operational continuity, competitive advantage, brand reputation) |
| `Organisation` | `id` | — | `name`, `type` (employer/client/regulatory-body/standards-body) |
| `Jurisdiction` | `code` | — | `name`, `type` (geographic/sectoral) |
| `Framework` | `id` | — | `level` (framework/category/technique/sub-technique — varies by framework), `title`, `body`, `domain` (enterprise/ics/mobile — for ATT&CK), `version`, `external_id` (e.g. T1566.001) |
| `Threat` | `id` | `threat_embedding_idx` | `text` (normalised threat statement), `tags` |
| `ThreatReport` | `id` | — | `title`, `publisher`, `published_at`, `valid_from`, `valid_until`, `scope` (geographic/sectoral/vendor), `perspective_notes` (known biases/focus) |
| `Asset` | `id` | — | `title`, `asset_type` (IT/OT/IoT/IT-OT-integration), `exposure` (internet-facing/internal/air-gapped), `data_classification` (public/internal/confidential/restricted) |

### Episodic layer nodes (unchanged by this ADR)

| Node | Key properties |
|------|----------------|
| `Memory` | No `org_id`. Org-scoping is on cross-layer edges, not the node. |

## Edge Types

### Control tree hierarchy

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `CONTAINS` | Control → Control | `coverage` (full/partial/none, default full), `limitation_type` (scope/functional/null), `limitation_detail`, `normative` (must/shall/should/may/must_not/should_not, default must) | Hierarchical tree with coverage semantics. Multiple children may contribute to a parent's requirement. Residual gap belongs to the parent domain. |

### Norm tree hierarchy

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `CONTAINS` | Norm → Norm | — | Hierarchical decomposition (framework → chapter → article → paragraph). Enables granular change tracking. |
| `SUPERSEDED_BY` | Norm → Norm | — | Links old version to new version. Both coexist during transition. Old version retains existing edges; new version starts without any. |

### Norms docking into the control tree

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `MAPS_TO` | Norm → Control | `normative` (must/shall/should/may/must_not/should_not, default must) | Replaces `HAS_CONTROL`. Norms dock into the tree at whatever level their specificity demands. Originates from the most specific normative statement, not the top-level framework. |
| `MAPPED_TO` | Control ↔ Control | — | Retained for explicit cross-framework mapping between a norm's control reference and a tree node (e.g. "ISO 27001 A.8.24 maps to our Encryption at rest"). Bidirectional MERGE. |

### Precepts and attributes

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `REQUIRES` | Norm → Precept | `normative` (default must) | Normative statement demands this obligation. Multiple norms can require the same Precept (convergence). |
| `FULFILS` | Precept → BusinessAttribute | — | Obligation serves this business need. |
| `ADDRESSES` | Control → Precept | — | Top-level Controls address Precepts. Lower-level Controls inherit through tree traversal. |
| `CONFLICTS_WITH` | Precept ↔ Precept | `nature` (contradictory/overlapping) | Follow-on capability. Conflicting obligations between norms. |

### Jurisdiction and organisation

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `APPLIES_IN` | Norm → Jurisdiction | — | Only on Norm nodes (not Controls). Children inherit, may narrow but never widen. |
| `OPERATES_IN` | Organisation → Jurisdiction | — | Where the org operates. Drives applicable norm resolution. |
| `OWNED_BY` | Document → Organisation | — | Document ownership / access scope. |
| `OWNED_BY` | Control → Organisation | — | Implementation-level controls only. Upper tree levels are org-agnostic. |

### Document and evidence

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `HAS_CHUNK` | Document → Chunk | — | Parent-child. |
| `HAS_NEXT` | Chunk → Chunk | — | Sequence within a document. |
| `IMPLEMENTS` | Document → Control | `metrics` (optional JSON — provided values against Control's metric schema) | Human-authored structured fulfilment claim. Assessment computed at query time. |
| `SUPPORTS` | Chunk → Control | `confidence`, `raw_score`, `status` (auto-inferred/confirmed/needs-review/rejected) | Machine-inferred textual evidence. |

### Cross-layer edges (bridge module)

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `ABOUT_CONTROL` | Memory → Control | `relationship_type` (context/evidence/gap), `org_id` | Links episodic memory to knowledge layer. |
| `CITES_DOC` | Memory → Document | — | Memory references this document. |
| `RESOLVES` | Memory → Precept | `scope_org_id` | Follow-on. Decision resolves conflicting precepts. |
| `SUPERSEDES_WITH` | Memory → Precept | — | Follow-on. Decision produces org-scoped resolved precept. |

All cross-layer edges are managed exclusively by `knowledge_bridge.py` (ADR-001 Guardrail 3).

### Framework hierarchy

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `CONTAINS` | Framework → Framework | — | Hierarchical decomposition (framework → category → technique → sub-technique). Same edge type as norm and control trees. |
| `SUPERSEDED_BY` | Framework → Framework | — | Links old version to new version. Both coexist — orgs may evaluate against either. Same pattern as norm versioning but without compliance cascade. |

### Norms referencing frameworks

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `REFERENCES` | Norm → Framework | `version_pinned` | Norm mandates compliance with this specific framework version. Decouples regulatory lifecycle from framework lifecycle. |

### Frameworks shaping the control tree

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `INFORMS` | Framework → Control | — | Framework element shapes or guides this part of the control tree. Non-prescriptive — does not carry normative weight. Distinct from `MAPS_TO` (which is prescriptive, from norms). |
| `MITIGATES` | Control → Framework | — | This control mitigates this framework-defined technique. Primarily for ATT&CK: a control counters a technique. Direction: the control acts on the threat technique. |

### Threat intelligence

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `IDENTIFIES` | ThreatReport → Threat | `severity` (critical/high/medium/low), `confidence` (high/medium/low), `trend` (increasing/stable/decreasing), `source_terminology` (original wording from the report) | Report identifies this normalised threat. Multiple reports can identify the same Threat — convergence layer. |
| `MAPPED_TO_TECHNIQUE` | Threat → Framework | — | Normalised threat maps to a specific framework technique (e.g. ATT&CK T1566.001). Enables structured threat analysis. |
| `TARGETS` | Threat → Asset | — | This threat targets this asset class. |
| `JEOPARDISES` | Threat → Precept | `severity` (critical/high/medium/low), `rationale` | This threat directly undermines this security obligation. Human-curated. Enables strategic risk view: Threat → Precept → BusinessAttribute without traversing the control tree. Critical for novel threats where controls don't yet exist. |

### Asset relationships

| Edge | Direction | Properties | Semantics |
|------|-----------|------------|-----------|
| `OPERATES` | Organisation → Asset | — | This org has/uses this asset class. |
| `PROTECTED_BY` | Asset → Control | — | This asset class is protected by this control. Links the "what we have" to the "what we do". |

## Norms vs Frameworks

Norms and Frameworks are distinct node types with different roles, even though they share the same hierarchical `CONTAINS` pattern.

| Aspect | Norm | Framework |
|--------|------|-----------|
| **Nature** | Prescriptive ("you must") | Structural/descriptive ("here's how to think about it") |
| **Docks into control tree via** | `MAPS_TO` with normative weight | `INFORMS` (non-prescriptive) |
| **Creates obligations** | Yes — via `REQUIRES` → Precept | No |
| **Carries jurisdiction** | Yes — `APPLIES_IN` → Jurisdiction | No |
| **Temporal validity** | Yes — `valid_from`, `valid_until`, `SUPERSEDED_BY` | Yes — frameworks are versioned (ATT&CK v14 → v15) |
| **Examples** | GDPR, NIS2, ISO 27001 (when mandated), KRITIS-DG | MITRE ATT&CK, NIST CSF (when used as guide), C2M2, SABSA, CIS Controls |

Some documents sit on the boundary (e.g. NIST CSF can be either). The distinction is about how the org uses it: if mandated by a regulator, the mandate is a Norm; the framework itself is always a Framework that `INFORMS` the tree.

### Norms referencing Frameworks

When a regulator mandates a framework, the Norm does not duplicate the Framework's content. Instead, the Norm `REFERENCES` a specific Framework version:

```
(:Norm {title: "Regulator X mandate", valid_from: "2024-01-01"})
    -[:REFERENCES {version_pinned: "1.1"}]->
(:Framework {title: "NIST CSF", version: "1.1"})

(:Framework {title: "NIST CSF", version: "1.1"})
    -[:SUPERSEDED_BY]->
(:Framework {title: "NIST CSF", version: "2.0"})
```

This decouples the regulatory lifecycle from the framework lifecycle:

- **Compliance view:** The Norm references CSF 1.1. Compliance is evaluated against that version. The Norm's lifecycle controls when SUPPORTS edges need review.
- **Maturity/readiness view:** CSF 2.0 exists as a Framework. The org can voluntarily evaluate their control tree against v2.0 to assess readiness — without compliance pressure, since no Norm yet references it.
- **Transition:** When the regulator updates the mandate to reference v2.0, the Norm transitions (new version via `SUPERSEDED_BY`, updated `REFERENCES` edge) and the full lifecycle cascade triggers.

Both framework versions coexist and `INFORM` the control tree simultaneously. An org can run gap analysis through both lenses: "are we compliant?" (v1.1 via the Norm) and "are we ready?" (v2.0 as a voluntary lens).

## Threat Intelligence Model

Threat intelligence flows from analyst reports through normalised threats to the control tree and asset classes.

### Flow

```
                                                    BusinessAttribute
                                                          ^
                                                          | FULFILS
                                                          |
ThreatReport -[IDENTIFIES]-> Threat -[JEOPARDISES]-> Precept <-[ADDRESSES]- Control
                                |                                               ^
                                |-[MAPPED_TO_TECHNIQUE]-> Framework (ATT&CK)    |
                                |                              ^                |
                                |                              | MITIGATES      |
                                |                              |                |
                                +-[TARGETS]-> Asset ---[PROTECTED_BY]-----------+
                                                ^
                                                | OPERATES
                                                |
                                          Organisation
```

Three threat-to-defence perspectives:
1. **Strategic** (board): Threat → JEOPARDISES → Precept → FULFILS → BusinessAttribute ("which business needs are under threat?")
2. **Tactical** (SOC): Threat → MAPPED_TO_TECHNIQUE → Framework ← MITIGATES ← Control ("which techniques do we counter?")
3. **Asset-centric** (risk): Threat → TARGETS → Asset → PROTECTED_BY → Control ("which assets are exposed?")

### Multi-source normalisation

Multiple reports with different perspectives converge on the same normalised Threat node. The `IDENTIFIES` edge preserves each source's original terminology, severity assessment, confidence level, and trend direction. No single source is treated as authoritative — the graph holds all perspectives.

### Temporal dimension

ThreatReports carry `valid_from` and `valid_until` (typically annual: the 2026 DBIR covers threats observed in 2025). The Threat nodes themselves are persistent — a threat doesn't disappear when a report expires, but its severity/trend may change as new reports are ingested.

### Key threat-driven queries

| Audience | Query | Traversal |
|----------|-------|-----------|
| Board | "Which business needs are under threat?" | Threat → JEOPARDISES → Precept → FULFILS → BusinessAttribute, aggregated by severity and trend. Heat map: "customer trust faces 6 active threats across 3 of 5 precepts" |
| Board | "How does a new threat change our risk posture?" | New Threat → JEOPARDISES → Precepts → BusinessAttributes → which business needs are newly exposed? |
| Risk | "What threats are relevant to us?" | Org → Assets → Threats targeting those asset classes, weighted by report severity and trend |
| Risk | "What should we prioritise?" | Threats targeting our assets, ranked by severity × trend × gap in control coverage. Cross-check: do jeopardised Precepts have addressing Controls? |
| Ops | "Are we protected?" | Our assets → protecting Controls → do those Controls have implementation evidence? |
| Ops | "How does a new threat report change our priorities?" | New report → identifies Threats → map to ATT&CK → map to our assets → map to our Controls → where are we exposed? |
| Ops | "What's our IT/OT integration risk?" | Assets with `asset_type: "IT-OT-integration"` → threats from both ATT&CK Enterprise and ATT&CK ICS |

## Normative Language

RFC 2119 normative terms belong on edges, not nodes. The same Control can be a MUST from one norm and a SHOULD from another.

| Term | Gap analysis implication |
|------|------------------------|
| MUST / SHALL | Absence is a **finding** (non-compliance) |
| SHOULD | Absence is a **recommendation** (improvement opportunity) |
| MAY | Absence is **acceptable** (no action required) |
| MUST NOT / SHALL NOT | Presence is a **finding** (violation) |

Applies to: `MAPS_TO.normative`, `CONTAINS.normative` (control tree), `REQUIRES.normative`, metric-level `normative` within Control metric schemas.

## Temporal Norm Lifecycle

Norm nodes carry temporal validity:

| Property | Meaning |
|----------|---------|
| `valid_from` | Enforcement date |
| `valid_until` | Expiry date (null = still in force) |
| `announced_at` | Adoption/publication date |
| `version` | Version identifier |

Three temporal states:

| State | Condition | Meaning |
|-------|-----------|---------|
| **Active** | `valid_from <= now` and (`valid_until` is null or `valid_until > now`) | Currently in force |
| **Announced** | `valid_from > now` and `announced_at <= now` | Known, not yet in force — plan for it |
| **Expired** | `valid_until <= now` | No longer in force — historical record |

When a normative statement is amended, a new Norm node is created and linked via `SUPERSEDED_BY`. The old version retains all existing edges. On lifecycle transition:

- `auto-inferred` SUPPORTS edges on affected Controls: **detached** (re-run inference against new text)
- `confirmed` SUPPORTS edges on affected Controls: **reverted to `needs-review`** (preserves human validation, flags for re-review)
- `rejected` SUPPORTS edges: left as-is

## Metric-Based Fulfilment (IMPLEMENTS)

Controls define a metric schema (what must be demonstrated). IMPLEMENTS edges carry provided values. Assessment is computed at query time.

**Two metric types:**

| Type | Defined by | Assessed by |
|------|-----------|-------------|
| Quantitative | Requirement owner: data type, target range, unit | System: compare value against target |
| Qualitative | Requirement owner: description of what to demonstrate | Human: assessor provides judgement + narrative |

**Three-way reconciliation** (IMPLEMENTS vs SUPPORTS):

| Category | Meaning |
|----------|---------|
| `implemented_and_supported` | Formal declaration with metrics AND textual evidence. Healthy. |
| `implemented_not_supported` | Claims fulfilment but no chunk text backs it up. Paper compliance. |
| `supported_not_implemented` | Chunk text is relevant but no formal declaration. Shadow compliance. |

## Org-Scoping Model

Designed for a consultant working across multiple client organisations:

| Layer | Scoping mechanism |
|-------|-------------------|
| Memory nodes | No org_id. Consultant's observations, org-agnostic. |
| Cross-layer edges | `org_id` / `scope_org_id` on edge. Same Memory can be evidence for different orgs. |
| Control tree (upper) | Org-agnostic. Shared reference architecture. |
| Control tree (implementation) | Org-specific via `OWNED_BY` → Organisation. |
| Documents | Org-specific via `OWNED_BY` → Organisation. |
| Norms and Precepts | Universal. No org-scoping. |

### Key consulting use cases

1. **"Minimum viable policy structure"** — org's jurisdictions → applicable norms → required Precepts → addressing Controls → subtree = minimum scope
2. **"Greatest gaps"** — same traversal, compare against org's Documents, Chunks, and Memory evidence
3. **"Impact of norm change"** — announced Norm → predecessor's MAPS_TO → control tree → org's implementation branches

## Conflict Modelling (Follow-On)

Where norms produce conflicting Precepts:

```
(p1:Precept)-[:CONFLICTS_WITH {nature: "contradictory"}]->(p2:Precept)

(m:Memory {type: "decision"})
    -[:RESOLVES {scope_org_id: "org-acme"}]-> (p1)
    -[:RESOLVES {scope_org_id: "org-acme"}]-> (p2)
    -[:SUPERSEDES_WITH]-> (p3:Precept {org_id: "org-acme"})
```

The resolved Precept is org-scoped. The decision Memory carries rationale, author, date. Downstream traceability: "if this decision changes, what breaks?"

## Jurisdiction Inheritance

1. **Within the norm tree:** Framework-level `APPLIES_IN` inherited by child statements. Children may narrow (subset) but never widen. Widening is a data quality error (HTTP 400 at write time).
2. **From norms to controls:** Controls have no `APPLIES_IN`. Jurisdiction is derived from the union of all Norms that `MAPS_TO` a control or its ancestors.
3. **Within the control tree:** Children inherit derived jurisdiction from parents. Additional norms mapping directly to a child add further scope.

## Discovery Mechanism

Knowledge-layer discovery is handled by MCP tool registration (conditional on `ENABLE_KNOWLEDGE_LAYER=true`), not by anchor Memory nodes. This preserves the bridge-as-sole-coupling-surface invariant.

## Alternatives Considered

### Flat norm-owns-controls (original WP specs, rejected)

`Norm -[HAS_CONTROL]-> Control` with norms owning controls directly. Rejected because controls exist independently of any norm; the same control may be required by multiple norms; and the relationship is a mapping, not ownership.

### BusinessRequirement instead of Precept (considered, renamed)

An intermediate "BusinessRequirement" node was considered but renamed to "Precept" because requirements don't only stem from business drivers — they come from norms, culture, ethics, and internal decisions. "Precept" is prescriptive and source-agnostic.

### Binary IMPLEMENTS declaration (rejected)

A simple "this document implements this control" edge without metrics. Rejected because it produces compliance theatre — a declaration without measurable evidence. The SABSA domain model requires the requirement owner to define fulfilment metrics.

### Anchor Memories for discovery (rejected)

Writing Memory nodes on Norm upsert as breadcrumbs for agents. Rejected because it pollutes the data layer to solve a tool-discovery problem, violates the bridge coupling invariant, and is better handled by MCP tool registration.

### Controls with independent APPLIES_IN (rejected)

Controls having their own jurisdiction edges. Rejected because the control tree is the organisation's security architecture — jurisdiction comes from the norms that map to it, not from the tree itself.

### Single node type for norms and frameworks (considered, rejected)

Using the `Norm` node type for both prescriptive and structural/descriptive documents (ATT&CK, NIST CSF as guide, etc.). Rejected because norms create obligations (via `MAPS_TO` with normative weight and `REQUIRES` → Precept), carry jurisdiction (`APPLIES_IN`), and drive compliance findings. Frameworks inform structure and provide taxonomies but do not create obligations. Overloading a single type would require "is this prescriptive?" checks throughout the query layer. Some documents sit on the boundary — the org's usage determines which node type applies.

### Full asset inventory / CMDB integration (rejected for now)

Modelling individual assets rather than asset classes. Rejected because the knowledge layer's purpose is compliance traceability and threat-driven prioritisation, not asset management. Asset classes (IT/OT/IoT/IT-OT-integration with exposure and classification properties) are sufficient to model the threat surface. CMDB integration is acknowledged as a possible future but is not an architectural driver today.

## Consequences

### Enables

- Single control tree as the organisation's security architecture, reusable across clients
- Multi-norm convergence through Precepts
- Granular change tracking and impact analysis through hierarchical norms
- Metric-based fulfilment assessment (quantitative + qualitative)
- Multi-org consulting with shared reference architecture and org-specific implementation branches
- Proactive transition planning through temporal norm lifecycle
- Conflict detection and resolution with full traceability
- Threat-driven prioritisation: which gaps face the most active threats?
- Multi-source threat intelligence with preserved perspectives and normalisation through frameworks
- IT/OT/IoT asset class modelling without requiring a full CMDB
- Framework-agnostic: ATT&CK, NIST CSF, C2M2, etc. all fit the same pattern

### Constrains

- Graph model is significantly more complex than the original WP specs
- CONTAINS edges are overloaded (used for control, norm, and framework hierarchies — distinguished by node label)
- Metric schemas stored as JSON properties (Memgraph edge properties are flat)
- Coverage aggregation and normative-weight-aware gap analysis are computationally heavier than binary checks
- Threat normalisation requires human judgement to map report findings to shared Threat nodes
- Asset classes are intentionally thin — not a CMDB, and not connected to one

### Watch for

- Metric schema complexity growing beyond what JSON properties can handle cleanly — may need dedicated Metric nodes
- CONTAINS edge overload causing confusion — may need separate edge types per hierarchy if queries become ambiguous
- Coverage aggregation performance on deep control trees
- Norm tree depth creating excessively long Cypher path queries
- Threat node proliferation if normalisation is too granular — may need periodic consolidation
- Asset class granularity: too coarse misses real risk differences; too fine approaches CMDB territory
- Framework version upgrades (ATT&CK v15 → v16) requiring bulk edge migration

## MVP Scope Boundaries

The following are defined in the schema but deferred to follow-on WPs:

| Feature | MVP | Follow-on |
|---------|-----|-----------|
| Control/Norm hierarchies | `CONTAINS` edge, `level` property | Coverage aggregation queries |
| Normative language | `normative` property on edges, default `must` | Normative-weight-aware gap analysis |
| Metric-based fulfilment | `metrics` as optional JSON on Control and IMPLEMENTS | Assessment computation endpoint, metric validation |
| Temporal norms | `valid_from`/`valid_until`/`announced_at`/`version`, `SUPERSEDED_BY` | Automated lifecycle transition detection, impact assessment endpoints |
| Conflict modelling | — | `CONFLICTS_WITH`, `RESOLVES`, `SUPERSEDES_WITH` |
| Frameworks | `Framework` node, `CONTAINS`, `INFORMS` | ATT&CK ETL, framework version migration |
| Threat intelligence | `Threat`, `ThreatReport` nodes, `IDENTIFIES`, `MAPPED_TO_TECHNIQUE` | Threat report ingestion pipeline, trend analysis, automated normalisation, `JEOPARDISES` (Threat → Precept) for strategic risk view |
| Asset classes | `Asset` node, `OPERATES`, `PROTECTED_BY`, `TARGETS` | Threat-driven gap prioritisation queries |

## Review Triggers

Re-evaluate this decision if any of the following occur:

1. Metric schemas require nested validation logic that JSON properties cannot support
2. CONTAINS edge overload causes ambiguous queries or performance issues
3. Coverage aggregation on deep trees exceeds acceptable query latency
4. A non-SABSA security architecture framework is adopted that conflicts with the tree model
5. Multi-tenant access control requirements emerge (currently single-user with multi-org data scoping)
6. Asset class modelling proves insufficient and CMDB integration becomes necessary
7. Threat normalisation volume requires automated deduplication beyond what embedding similarity provides
8. The distinction between Norm and Framework becomes untenable for documents that serve both roles simultaneously
