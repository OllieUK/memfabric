# Knowledge Layer — Operational Runbook

## 1. Overview

The knowledge layer is a feature-flagged module inside graph-memory-fabric that manages reference
data for Information Security compliance: control trees, normative requirements, policy documents,
and chunk-level textual evidence. It shares the same Memgraph instance and FastAPI process as
episodic memory but operates as a structurally separate concern.

**Episodic memory** stores personal, temporal, agent-generated facts that decay over time and are
reinforced through recall. **The knowledge layer** stores reference data — controls, norms,
documents — that does not decay, carry strength scores, or participate in recall counting. It is
ingested once and queried indefinitely.

Cross-layer edges (Memory → Control, Memory → Document) connect the two layers. These are
managed exclusively by `memory_service/knowledge_bridge.py` and are the primary value of
co-location. All other queries within each layer remain isolated.

See ADR-001 for the placement rationale and ADR-002 for the full graph model.


## 2. Feature Flag

```
ENABLE_KNOWLEDGE_LAYER=true
```

Set in `.env`. Default is `false`.

When `false`:
- All `/knowledge/*` endpoints return 404 (the router is never registered).
- Knowledge-layer embedding model is not loaded.
- Episodic memory is unaffected.

When `true`:
- The router is registered and all `/knowledge/*` endpoints are active.
- Schema must have been initialised separately (see section 5).
- The service can operate without any Memory nodes populated.

Schema initialisation is not automatic. Run `scripts/init_knowledge_schema.py` once after enabling
the flag for the first time.


## 3. Separation Invariants

Three invariants are enforced by convention and code structure. Never violate them.

**Invariant 1: `knowledge_bridge.py` is the sole cross-layer importer.**
`knowledge_routes.py` and `knowledge_repo.py` must not import from `memory_repo.py`. The only
module that imports from both is `knowledge_bridge.py`. This makes the coupling surface explicit
and auditable.

**Invariant 2: Knowledge routes never call memory repo.**
All Cypher queries for knowledge nodes go through `knowledge_repo.py`. If a route needs to
connect a Memory node to a knowledge node, that logic belongs in `knowledge_bridge.py`, not in
`knowledge_routes.py`.

**Invariant 3: Episodic search never returns knowledge nodes.**
The `mem_embedding_idx` vector index covers only `:Memory` nodes. The `ctrl_embedding_idx` covers
only `:Control` nodes, and `chunk_embedding_idx` covers only `:Chunk` nodes. Label-scoped indexes
are the structural enforcement mechanism.


## 4. Node and Edge Reference

### Node Labels

| Label | Embedding index | Key properties |
|-------|----------------|----------------|
| `Framework` | none | `id`, `name`, `version`, `description`, `created_at` |
| `Control` | `ctrl_embedding_idx` | `id`, `name`, `description`, `framework_id`, `embedding`, `created_at` |
| `Norm` | none (text stored; embedding on node) | `id`, `name`, `text`, `status`, `effective_date`, `embedding`, `created_at` |
| `Document` | none | `id`, `title`, `doc_type`, `source_url`, `created_at` |
| `Chunk` | `chunk_embedding_idx` | `id`, `text`, `sequence`, `doc_id`, `embedding`, `created_at` |

`Norm` carries an embedding on the node but does not have a named index in the current MVP. The
embedding is stored for future index creation.

`Document` carries no embedding — semantic search operates on Chunks, not Document headers.

The full ADR-002 graph model defines additional node types (`Precept`, `BusinessAttribute`,
`Organisation`, `Jurisdiction`, `Threat`, `ThreatReport`, `Asset`) that are part of the schema
design but are not yet wired into active routes. They can be queried directly in Memgraph Lab.

### Edge Types

Edges produced by the current MVP routes:

| Edge | Direction | Properties | Description |
|------|-----------|------------|-------------|
| `CONTAINS` | Control → Control | none (MVP) | Hierarchical tree: parent control contains child control. Created when `parent_id` is set on a `ControlCreate` request. |
| `IMPLEMENTS` | Norm → Control | none (MVP) | Normative requirement implements this control. Created when `control_id` is set on a `NormCreate` request. |
| `SOURCED_FROM` | Norm → Document | none | Norm was extracted from this document. Created when `doc_id` is set on a `NormCreate` request. |
| `HAS_CHUNK` | Document → Chunk | none | Parent-child: document owns this chunk. Always created on chunk upsert. |
| `HAS_NEXT` | Chunk → Chunk | none | Sequential ordering within a document. Created when `prev_chunk_id` is set on a `ChunkCreate` request. |
| `SUPPORTS` | Chunk → Control | `confidence float`, `status string`, `created_at` | Machine-inferred or human-confirmed textual evidence. Status values: `auto-inferred`, `confirmed`, `needs-review`, `rejected`. |

Cross-layer edges (managed by `knowledge_bridge.py` only):

| Edge | Direction | Properties | Description |
|------|-----------|------------|-------------|
| `ABOUT_CONTROL` | Memory → Control | `relationship_type`, `org_id` | Episodic memory linked to a control. `relationship_type`: `context`, `evidence`, or `gap`. |
| `CITES_DOC` | Memory → Document | none | Episodic memory references this document. |

Additional edges defined in ADR-002 (not yet in active routes):

| Edge | Direction | Description |
|------|-----------|-------------|
| `MAPS_TO` | Norm → Control | Prescriptive docking edge (replaces the original HAS_CONTROL pattern). |
| `REQUIRES` | Norm → Precept | Normative obligation. |
| `ADDRESSES` | Control → Precept | Control satisfies this obligation. |
| `FULFILS` | Precept → BusinessAttribute | Obligation serves this business need. |
| `APPLIES_IN` | Norm → Jurisdiction | Jurisdictional scope. |
| `SUPERSEDED_BY` | Norm → Norm | Temporal lifecycle: old version to new. |
| `JEOPARDISES` | Threat → Precept | Strategic risk path. |


## 5. How to Ingest a Framework

Use `scripts/ingest_framework.py` to bulk-load a framework from a YAML catalogue file.

### YAML file structure

```yaml
framework_id: iso27001-2022
framework_name: ISO/IEC 27001:2022
framework_version: "2022"
framework_description: Information security management systems

controls:
  - id: iso27001-2022-a5
    name: Organisational controls
    description: Section A.5 controls

  - id: iso27001-2022-a5.1
    name: Policies for information security
    description: Management direction for information security
    parent_id: iso27001-2022-a5    # creates CONTAINS edge: a5 → a5.1

norms:
  - id: iso27001-2022-a5.1-req1
    name: Policy existence requirement
    text: Information security policies shall be defined, approved by management...
    status: active
    effective_date: "2022-10-25"
    control_id: iso27001-2022-a5.1    # creates IMPLEMENTS edge: norm → control

documents: []
chunks: []
jurisdictions: []
business_attributes: []
```

### Steps

1. Confirm the service is running:

   ```
   curl http://localhost:8000/health
   # {"status": "ok"}
   ```

2. Confirm `ENABLE_KNOWLEDGE_LAYER=true` in `.env` (or the current environment).

3. Validate the YAML without making API calls:

   ```
   python scripts/ingest_framework.py my_framework.yaml --dry-run
   ```

4. Ingest:

   ```
   python scripts/ingest_framework.py my_framework.yaml
   ```

   Output shows counts per entity type and `created` / `already existed` per item. The operation
   is idempotent — re-running the same YAML file is safe.

### Upsert order

The script ingests in dependency order: Framework → Controls → Norms → Documents → Chunks →
Jurisdictions → BusinessAttributes. List controls in parent-before-child order within the YAML so
that `CONTAINS` edges resolve correctly (the parent must exist before the child is upserted).


## 6. How to Ingest a Document

Use `scripts/ingest_document.py` to ingest a PDF or Markdown file as a Document with chunked
Chunk nodes.

### Supported formats

- `.pdf` — extracted using `scripts/chunkers.chunk_pdf`
- `.md`, `.markdown` — split using `scripts/chunkers.chunk_markdown`

### Steps

1. Confirm the service is running.

2. Ingest a PDF policy document:

   ```
   python scripts/ingest_document.py /path/to/policy.pdf \
       --doc-id acme-isms-policy-2024 \
       --title "ACME ISMS Policy 2024" \
       --doc-type policy \
       --source-url https://acme.internal/policies/isms-2024.pdf
   ```

3. Ingest a Markdown standard:

   ```
   python scripts/ingest_document.py /path/to/standard.md \
       --doc-id acme-access-control-std \
       --title "ACME Access Control Standard" \
       --doc-type standard
   ```

### Chunking configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `INGEST_CHUNK_SIZE` | 2000 | Maximum characters per chunk |
| `INGEST_CHUNK_OVERLAP` | 200 | Character overlap between adjacent chunks |
| `INGEST_MIN_CHUNK_CHARS` | 50 | Minimum characters; shorter chunks are discarded |
| `INGEST_AUTO_SUPPORTS` | false | If true, run vector search after ingestion and create SUPPORTS edges |
| `INGEST_AUTO_SUPPORTS_THRESHOLD` | 0.20 | Maximum cosine distance to create a SUPPORTS edge |
| `INGEST_CHUNK_REVIEW_MODE` | true | If true, print SUPPORTS candidates but do not write them |

### Auto-SUPPORTS edge creation

When `INGEST_AUTO_SUPPORTS=true`, after all chunks are ingested the script runs a vector search
over controls for each chunk text. Chunk-to-control pairs below the distance threshold become
SUPPORTS candidates.

When `INGEST_CHUNK_REVIEW_MODE=true` (default), candidates are printed to stdout for human review
and no edges are written. This is the safe default for first ingestion.

To apply the candidates after review:

```
INGEST_CHUNK_REVIEW_MODE=false python scripts/ingest_document.py ...
```

SUPPORTS edges are created with `status=auto-inferred`. Promote them to `confirmed` via the
`POST /knowledge/chunk/supports` endpoint after manual review.


## 7. How to Search

### CLI

The `memory` CLI exposes episodic memory search only. Knowledge layer search is done directly via
the HTTP API or via Memgraph Lab.

### HTTP API

**Search controls by semantic query:**

```
POST /knowledge/search/controls
Content-Type: application/json

{
  "query": "encryption at rest for databases",
  "limit": 10,
  "framework_id": "iso27001-2022"    // optional filter
}
```

Response:
```json
[
  {
    "id": "iso27001-2022-a8.24",
    "name": "Use of cryptography",
    "description": "...",
    "framework_id": "iso27001-2022",
    "created_at": "2024-01-15T10:00:00+00:00",
    "distance": 0.123
  }
]
```

`distance` is cosine distance (0 = identical, 2 = maximally dissimilar). Lower is more relevant.

**Filter caveat:** Vector search returns up to `limit` nodes before the `framework_id` filter is
applied. If the filter is tight and all top-`limit` hits are from other frameworks, the response
may be empty even when matching nodes exist. Increase `limit` to compensate.

**Search chunks by semantic query:**

```
POST /knowledge/search/chunks
Content-Type: application/json

{
  "query": "key management rotation procedures",
  "limit": 10,
  "doc_id": "acme-isms-policy-2024"    // optional filter
}
```

**Get chunks supporting a control:**

```
GET /knowledge/controls/{control_id}/chunks
```

Returns all Chunk nodes with a SUPPORTS edge to this control, ordered by confidence descending.

**List all norms:**

```
GET /knowledge/norms
```

**List all documents:**

```
GET /knowledge/documents
```

**Get a single control:**

```
GET /knowledge/controls/{control_id}
```

**Get a single framework:**

```
GET /knowledge/frameworks/{framework_id}
```

**Diagnostic: norms and controls without jurisdiction edges:**

```
GET /knowledge/incomplete-jurisdictions
```

Returns lists of Norm and Control nodes that have no `APPLIES_IN` edge. Useful for data quality
checks after bulk ingestion.


## 8. Re-ingestion After Control Text Updates

Controls are upserted using `MERGE ... ON CREATE SET`. If a control's `name` or `description`
changes, the text change will not be applied by re-running ingest, and the stored embedding will
be stale.

To update a control and refresh its embedding:

1. Delete the control node in Memgraph Lab or via direct Cypher:

   ```cypher
   MATCH (c:Control {id: $id})
   DETACH DELETE c
   ```

   Note: `DETACH DELETE` does not support a `RETURN` clause. Count nodes before deleting if you
   need confirmation.

2. Re-run the ingest script. The MERGE will treat it as a new node (ON CREATE SET applies) and
   re-embed the updated text.

3. Any SUPPORTS edges from Chunks to the deleted control are also deleted by `DETACH DELETE`.
   If you need to preserve them, record the chunk-to-control pairs before deletion and re-create
   them after re-ingestion using `POST /knowledge/chunk/supports`.

For norm text changes the same process applies. Because norms carry embeddings on the node (not
via a named index yet), stale embeddings do not affect active vector search — but keep them
consistent for future use.

When a normative document is revised, the preferred pattern is to create a new Norm node with a
`SUPERSEDED_BY` edge from the old version rather than deleting and re-ingesting. This preserves
the compliance audit trail. The old version retains its IMPLEMENTS and SOURCED_FROM edges; the new
version starts clean and accrues its own edges.


## 9. Embedding Model Configuration

```
# episodic memory
EMBEDDING_MODEL=all-MiniLM-L6-v2

# knowledge layer
KNOWLEDGE_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

The two layers use independently configured embedding models. This is an ADR-001 guardrail, not
an incidental detail.

**Why separate models?**

- Compliance documents are often multilingual (GDPR in German, NIS2 in French, KRITIS in German).
  The knowledge layer uses a multilingual model from day one.
- Episodic memory today is English-only. Migrating its model requires re-embedding all Memory
  nodes and rebuilding the vector index. That migration can happen independently, on its own
  timeline, without coupling to the knowledge layer.
- Cross-layer vector similarity is not needed. The bridge between layers uses explicit graph edges
  (ABOUT_CONTROL, CITES_DOC), not embedding similarity. Both models can therefore differ without
  any cross-layer semantic gap.

**What this means operationally:**

- `KNOWLEDGE_EMBEDDING_MODEL` is used by all knowledge routes that produce embeddings: control
  upsert, norm upsert, and chunk upsert.
- `KNOWLEDGE_EMBEDDING_MODEL` is also used at search time: `POST /knowledge/search/controls` and
  `POST /knowledge/search/chunks` embed the query text with this model before calling
  `vector_search.search`.
- If you change `KNOWLEDGE_EMBEDDING_MODEL`, you must re-ingest all Controls, Norms, and Chunks
  to regenerate embeddings. Mixing embeddings from different models in the same vector index
  produces meaningless distances.
- The model is loaded once at service startup. Changing it requires a service restart.

Both models are resolved from `.env` via `pydantic-settings`. No model name is hardcoded in
source files.


## 10. References

- [ADR-001: Knowledge Layer Placement](docs/architecture/ADR-001-knowledge-layer-placement.md)
  — feature flag, module structure, bridge invariant, co-location rationale.

- [ADR-002: Knowledge Layer Graph Model](docs/architecture/ADR-002-knowledge-layer-graph-model.md)
  — full node and edge type definitions, norm vs framework distinction, org-scoping model, metric-
  based fulfilment, temporal norm lifecycle, threat intelligence model.
