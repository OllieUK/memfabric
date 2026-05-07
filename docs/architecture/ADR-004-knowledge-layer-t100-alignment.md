# ADR-004: Knowledge-layer T100 alignment for new SABSA constructs

**Status:** Accepted
**Date:** 2026-05-07
**Deciders:** Oliver
**WP:** WP-113

---

## Context

ADR-002 (`docs/architecture/ADR-002-knowledge-layer-graph-model.md`) records the as-built
graph model for the knowledge layer, designed before T100 (Modelling SABSA with ArchiMate
v2.5, Feb 2026) was published. T100 defines a Security Overlay that expresses every SABSA
construct in ArchiMate 3.2 vocabulary using stereotype encoding (out-of-model `<<...>>`
specialisations of existing ArchiMate elements).

Three things are now true:

1. T100 is the authoritative cross-organisation interoperability vocabulary for SABSA-aligned
   data. Adopting it positions the fabric to exchange data with other SABSA-aligned tools
   (the SABSA Institute's own ArchiMate-based tooling, Open Group ADM tools, etc.) without a
   bespoke translation layer.
2. The W100 ICT Business Attribute Taxonomy (pp.19–21, Figures 4 and 5) covers most of what
   ADR-002 modelled as the `Precept` node type. Building Precepts as a parallel construct
   would duplicate the published taxonomy.
3. Re-architecting the existing knowledge-layer nodes (Framework / Norm / Control / Threat /
   ATT&CK / ISO 27001 / NIST CSF / COBIT / SP 800-53) to T100 vocabulary is a substantial
   undertaking that is out of scope for WP-113.

## Decision

For SABSA-aligned constructs introduced from WP-113 onward (WP-113b, WP-113c, WP-113d,
WP-113e, WP-114, WP-133, and any future SABSA / ArchiMate framework ingest), the knowledge
layer adopts T100's Security Overlay vocabulary via stereotype encoding on a new node-type
property `t100_stereotype: str | None`.

Set `t100_stereotype` where T100 has a clean mapping; null otherwise.

The `Precept` node type is **dropped from the as-planned schema**. The W100 BA Taxonomy
(seeded as `BusinessAttribute` nodes in three tiers — architectural-primitive roots, ICT
group headings, ICT leaves) is the authoritative leaf set for `<<sabsa-attribute>>`-stereotyped
Principle nodes. Edge types previously planned around Precept (`FULFILS`, `DRIVES`,
`JEOPARDISES`, `REQUIRES Norm|Framework→Precept`, `ADDRESSES`) collapse into ArchiMate
vocabulary: `INFLUENCE` (with optional `polarity` ∈ `{positive, negative}`), `CONTAINS`
(taxonomy hierarchy), `REALIZES` (Control → Requirement → Goal chain — informational, not
seeded by WP-113), and `INFORMS` (Framework → BA-leaf, semantically extended from its
prior Framework→Framework usage).

Existing knowledge-layer nodes (per ADR-002) are **NOT migrated by this WP**. The full
re-alignment is scoped as a separate Bridge WP (placeholder text in §10 of the WP-113
plan; surface to BACKLOG.md by Oliver, not autonomously by the implementer).

The plan also adopts the matrix structure verbatim from R101: each SABSA matrix is **two
coupled grids**, a 6×6 main matrix (36 cells, including the Operational row) and a 5×6
Service Management Matrix (30 cells, the decomposition of the Operational row). The 6
main-matrix Operational cells and the 30 Service Management cells are **distinct nodes**
(different decomposition levels). Total: 66 cells.

## T100 stereotypes used in WP-113

The following T100 stereotypes are used by WP-113 (refined from the §3.4.2 specialisation
discussion and the worked stereotypes through §5–§9 of T100):

| Stereotype | Applied to | Notes |
|------------|------------|-------|
| `sabsa-attribute` | `BusinessAttribute` (Tier 1 roots, Tier 2 ICT leaves) | T100: stereotype of Principle |
| `regulation` | (deferred — no Regulation nodes seeded by WP-113) | T100: stereotype of Representation |
| `standard` | (deferred) | T100: stereotype of Representation |
| `article` | (deferred) | T100: stereotype of Principle |
| `mandate` | (deferred) | T100: stereotype of Principle |
| `control-objective` | (deferred — no Control nodes seeded) | T100: stereotype of Goal |
| `threat` | (existing Threat nodes — see Bridge WP) | T100: stereotype of Assessment |
| `risk` | (deferred) | T100: stereotype of Assessment |
| `vulnerability` | (deferred) | T100: stereotype of Assessment |
| (all other T100 stereotypes) | (deferred) | Future ingest WPs |

Tier 2 group nodes (Management / User / etc.) carry `t100_stereotype: null` because T100
does not define a stereotype for these — they are W100 taxonomy structure, not T100
vocabulary. Cell nodes carry `t100_stereotype: null` because T100 represents cells as
Grouping containers in diagrams, not as graph nodes.

## Consequences

**Positive:**
- New SABSA constructs are interoperable with T100-aware tooling on day one.
- W100 BA Taxonomy is honoured rather than duplicated.
- Existing knowledge-layer nodes are not destabilised; the Bridge WP migrates them on a
  schedule independent of WP-113.

**Negative:**
- Two-track schema (ADR-002 for existing nodes, ADR-004 for new SABSA constructs) until
  the Bridge WP completes. Documented; finite duration.
- The `t100_stereotype` enum will need refresh as T100 evolves (T100 v2.5 is current; the
  Open Group has indicated v3.0 may revise the stereotype catalogue).

## Long-term interoperability target

T100 publishes XML namespaces `tog`, `tsi`, `custom`. The long-term target is that
`t100_stereotype` values map directly to T100 namespace-qualified stereotype names so the
fabric can emit ArchiMate Open Exchange Format (`*.archimate`) files for any SABSA-aligned
import/export. This is informational; not delivered by WP-113.
