# Cyber Knowledge Layer

First-class sub-package for the InfoSec/cyber knowledge layer of graph-memory-fabric. Logically separated from episodic memory per [ADR-003](../docs/architecture/ADR-003-cyber-knowledge-package-boundary.md); same repo, same FastAPI process, same Memgraph instance.

## Mission (per Oliver, 2026-05-11)

Three target use cases:

1. **Threat-and-compliance-aware maturity review.** Score an organisation's controls against current threat intelligence and regulatory expectation simultaneously.
2. **Policy review against landscape change.** Detect when an external change (new norm version, new threat report, new ATT&CK technique) invalidates or stresses a policy clause.
3. **Policy architecture build/review.** Compose a coherent policy set from norms, frameworks, and business-attribute pressures; identify gaps and redundancies.

## Current scope

In:

- Framework ingest (NIST CSF, SP 800-53, ISO 27001/27005/22301, COBIT 2019, DIN 14027, Grundschutz forthcoming via OSCAL)
- Threat report ingest (CTI extraction, dedup, clustering, BA influence)
- SABSA business-attribute taxonomy + matrix
- Cross-framework cross-walks and INFORMS edges
- Two-door bridge contract for episodic-memory ↔ cyber-knowledge cross-layer edges

Deferred (next slate, blocked on this WP):

- OSCAL ingest pipeline (WP-175)
- Grundschutz++ ingestion (WP-176)
- CISA KEV (WP-177)
- D3FEND (WP-178)
- Pressure engine (WP-179)
- Asset + policy node model (ADR-004 / WP-174)

## Bridge contract — two doors only

Per [ADR-003 §2](../docs/architecture/ADR-003-cyber-knowledge-package-boundary.md):

- **`cyber_knowledge/bridge.py`** — consumed by `memory_service.main` for cross-layer edge ops during episodic-memory CRUD. Surface: `validate_controls`, `validate_documents`, `link_controls`, `link_documents`, `replace_control_edges`, `replace_doc_edges`, `hydrate_controls_and_documents`, `rewire_cross_layer_edges`.
- **`cyber_knowledge/mcp_tools.py`** — consumed by `mcp_server.server` via `register(mcp_app)`. Registers `knowledge_search_controls`, `knowledge_search_chunks`, `knowledge_list_norms`, `knowledge_get_control`, `knowledge_get_norm`.

No other `cyber_knowledge.*` module may be imported from outside the package.

## Test marker

All tests covering this package are tagged with `pytest.mark.cyber`:

- `pytest -m cyber` — cyber-only test runs
- `pytest -m 'not cyber'` — episodic-memory-only runs

The marker is a selection filter, not an isolation barrier — tests still share the same process and Memgraph.

## See also

- [ADR-001](../docs/architecture/ADR-001-knowledge-layer-placement.md) — placement decision (peer module inside the repo)
- [ADR-002](../docs/architecture/ADR-002-knowledge-layer-graph-model.md) — graph model
- [ADR-003](../docs/architecture/ADR-003-cyber-knowledge-package-boundary.md) — this package boundary
- `docs/cyber/` — cyber-specific design notes (forthcoming)
