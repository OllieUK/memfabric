# ADR-001: Information Security Knowledge Layer Placement

| Field | Value |
|-------|-------|
| Status | Accepted |
| Date | 2026-04-02 |
| Scope | WP-069 through WP-076 |

## Decision

Implement the Information Security knowledge layer inside graph-memory-fabric as a **feature-flagged peer module** sharing the same Memgraph instance, FastAPI process, and deployment unit as episodic memory.

## Context

Graph-memory-fabric serves two fundamentally different paradigms:

- **Episodic memory**: personal, temporal, decay-driven, recall-based. Serves AI companions maintaining continuity about the user's life, decisions, and context.
- **Knowledge layer**: reference data, organisational decisions, exceptions, and traceability. Serves compliance and governance for Information Security (IT Sec, OT Sec, IoT, Physical, Human security).

The knowledge layer must operate in **dual mode**:
1. **Standalone**: compliance traceability and gap analysis without involving episodic memory
2. **Integrated**: cross-layer edges enriching episodic memories with control/document references

Cross-layer edges (Memory <-> Control, Memory <-> Document) are the differentiating value of co-location. Without them, the knowledge layer is commodity compliance software.

## Systemic Constraints

1. **Single Memgraph instance.** Running two doubles RAM (~1.5GB to ~3GB). Cross-layer graph queries must share an instance or accept HTTP-mediated joins.
2. **Single-user, single-machine deployment (WSL2).** Microservice separation adds operational cost with no scaling benefit today.
3. **Cross-layer edges are the core value.** Gap analysis, traceability, and evidence linking require single-graph traversals spanning both layers.
4. **Embedding model is shared infrastructure.** Two services means two model loads (~400MB each) unless a third embedding microservice is introduced.
5. **The knowledge layer needs standalone mode.** It must be usable for compliance without episodic memory being populated or active.

## Assumptions

### Explicit

1. **Label-based isolation is sufficient.** Memgraph's label-scoped vector indexes (`mem_embedding_idx ON :Memory`, `ctrl_embedding_idx ON :Control`) provide structural separation without needing a `layer` property or separate database.
2. **Scope is Information Security, not enterprise GRC.** Growth stays within infosec subdomains (IT, OT, IoT, Physical, Human). No legal, financial, or HR compliance layers.
3. **Cross-layer edges are append-only.** No bulk migration or schema evolution of cross-layer edges is anticipated.
4. **Knowledge data is reference, not episodic.** Standards, Controls, Documents do not decay, have no strength scores, and do not participate in recall counting. Ingested once, queried indefinitely.
5. **Embedding models are independently configurable per layer.** Both layers may eventually use multilingual models, but they can migrate on independent timelines. Cross-layer vector similarity is not needed; explicit edges serve that purpose.

### Implicit (now explicit)

1. **Single-user today, possibly multi-user later.** Multi-user is not a near-term architectural driver but is acknowledged as a possible future. If it materialises, access control for the knowledge layer would need to be addressed.
2. **Knowledge layer could grow substantially within InfoSec.** The scope covers multiple subdomains. Code volume could become significant but is not expected to approach enterprise GRC complexity.
3. **Shared Memgraph is an asset with manageable risk.** Cross-layer traversals are the core value. Bulk knowledge imports (thousands of controls, tens of thousands of document chunks) could temporarily pressure Memgraph resources; mitigated by batch import patterns.
4. **Embedding migration timelines are decoupled, not capabilities.** Multilingual episodic memory is in scope for the memory graph. It simply should not be forced by the knowledge layer's requirements.
5. **Carve-out cost scales with cross-layer edge count.** Every ABOUT_CONTROL and CITES_DOC edge is a foreign key between layers. At 50 edges, extraction is trivial. At 5,000, it is a data migration project. The more successful the integration, the harder the separation. This is acknowledged and accepted.

## Architectural Guardrails

### 1. Feature-flagged router

```
ENABLE_KNOWLEDGE_LAYER=true  # .env, default false
```

- `app.include_router(knowledge_routes.router)` is conditional on this flag
- Knowledge endpoints are fully functional without any Memory nodes in the graph
- Schema initialisation is a separate script (`init_knowledge_schema.py`)
- The knowledge layer can be enabled for compliance use even if episodic memory is empty

### 2. Independently configurable embedding models

```
EMBEDDING_MODEL=all-MiniLM-L6-v2                                    # episodic memory
KNOWLEDGE_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2     # knowledge layer
```

- Decouples migration timelines: knowledge gets multilingual from day one; episodic memory migrates independently when ready
- Each layer's vector index uses its own model

### 3. Module naming and structure

Modules use the `knowledge_*` prefix (not `cybersec_*`):
- `knowledge_routes.py` — FastAPI router for `/knowledge/*` endpoints
- `knowledge_repo.py` — Cypher queries for knowledge nodes
- `knowledge_schemas.py` — Pydantic models and enums
- `knowledge_bridge.py` — Cross-layer edge logic (the only module importing from both `memory_repo` and `knowledge_repo`)

The bridge module makes the coupling surface explicit and auditable.

### 4. Dual-mode endpoint design

- **Knowledge-only queries** (`/knowledge/search/controls`, `/knowledge/control/{id}/trace-up`, `/knowledge/gap-analysis`) must never depend on Memory nodes existing
- **Cross-layer queries** (gap analysis with Memory evidence, search with control hydration) are an optional capability that enhances but does not gate knowledge layer functionality

## Alternatives Considered

### Separate project (rejected)

A standalone `infosec-knowledge-fabric` with its own FastAPI service.

**Rejected because:** The core value proposition (cross-layer edges enabling gap analysis and traceability) becomes a distributed join problem. Gap analysis requires traversing Memory -> Control -> Standard -> BusinessAttribute in a single query; across service boundaries this becomes an orchestration nightmare. Operational overhead is disproportionate for a single-user, single-machine deployment.

### Implement and carve out later (rejected as distinct from chosen approach)

Build inside graph-memory-fabric with explicit abstraction layers for future extraction.

**Rejected because:** Cross-layer edges make extraction hard regardless of how clean the module boundaries are. The chosen approach (feature flag, separate models, bridge module) achieves the same modularity without speculative abstraction. This IS the minimal, pragmatic version of "design for carve-out" — just without pretending extraction will be cheap.

## Consequences

### Enables
- Single-graph traversals for gap analysis and traceability
- Standalone compliance use via feature flag
- Independent embedding model migration timelines
- Incremental adoption: flag off by default, enable when ready

### Constrains
- Both layers share Memgraph resources (memory, locks, index rebuilds)
- Project identity must accommodate two paradigms (episodic + knowledge)
- Knowledge layer code grows inside this repository

### Watch for
- Knowledge code volume exceeding 50% of total codebase
- Memgraph resource pressure during bulk knowledge imports
- Accidental coupling: imports crossing the bridge module boundary
- Cross-layer edge count growing beyond manageable extraction threshold

## Review Triggers

Re-evaluate this decision if any of the following occur:

1. Multi-user or multi-tenant becomes a real requirement
2. Knowledge layer code exceeds 50% of total codebase
3. A second non-InfoSec knowledge domain is requested
4. Cross-layer edge count exceeds 10,000
5. Memgraph resource contention measurably affects episodic memory performance
