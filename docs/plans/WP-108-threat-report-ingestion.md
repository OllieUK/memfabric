# WP-108: Threat Report Ingestion and Cluster Validation — Implementation Plan

**Date:** 2026-04-09
**Status:** Ready for implementation
**Depends on:** WP-107 ✅

---

## Summary

Add `ThreatReport`, `Threat`, and `Asset` node types to the knowledge layer per ADR-002. Expose CRUD API endpoints. Build a **fully automated** CTI report ingestion pipeline that extracts threat descriptions and ATT&CK mappings directly from the 6 PDF reports — no manual YAML curation. Deduplicate `Threat` nodes via embedding similarity search at ingest time. Validate cluster coherence with the WP-107 graph.

---

## Design Decisions

**1. Fully automated extraction, no human-curated YAML.** The PDF text is parsed using `pdfplumber.extract_words()`, sentences are extracted, and ATT&CK techniques are identified via keyword matching (the `CTIReportParser` pattern from `building-attack-pattern-library-from-cti-reports` CTI skill). The reports drive the threat taxonomy — no pre-defined fixed list.

**2. Embedding-based deduplication at ingest time.** Before creating a new `Threat` node, the ingestion script calls `POST /knowledge/search/threats` to find semantically similar existing threats (cosine distance < 0.15 threshold). If a near-duplicate exists, the new `ThreatReport` creates an `IDENTIFIES` edge to the existing node rather than creating a duplicate. The `source_terminology` field on the `IDENTIFIES` edge preserves each report's exact wording.

**3. ATT&CK technique ID resolution.** The extractor builds a keyword→technique_id mapping table (covering ~40 high-frequency threat terms). Where a sentence matches a keyword, the extracted `Threat` is linked to that ATT&CK technique via `MAPPED_TO_TECHNIQUE`. Sentences without keyword matches create `Threat` nodes without ATT&CK links (linkable later via embedding similarity to existing Framework nodes).

**4. Schema migration:** Extend `scripts/init_knowledge_schema.py` in-place. All adds are idempotent. No migration script needed.

**5. Asset seeding:** Seed 4 universal `Asset` class nodes (IT, OT, IoT, IT-OT-integration) from a minimal `data/threats/assets.yaml`. These are structural reference nodes, not report-derived content — no analysis required.

**6. Cluster validation:** Standalone Cypher analysis script that checks whether the top threats (by `IDENTIFIES` edge count) co-cluster with the controls that mitigate their ATT&CK techniques.

---

## Phase 1: Schema Extension

**Files to modify:**
- `scripts/init_knowledge_schema.py` — add constraints + `threat_embedding_idx`
- `memory_service/config.py` — add `threat_index_capacity`

### Changes to `KNOWLEDGE_CONSTRAINTS`

```python
("Threat", "id"),
("ThreatReport", "id"),
("Asset", "id"),
```

### Add to `config.py` Settings class

```python
threat_index_capacity: int = 1000
```

### Add to `main()` after `chunk_embedding_idx` block

```python
# --- threat_embedding_idx ---
print("\nCreating vector index: threat_embedding_idx ...")
try:
    create_vector_index(
        session,
        index_name="threat_embedding_idx",
        label="Threat",
        prop="embedding",
        dim=dim,
        capacity=settings.threat_index_capacity,
    )
except Exception as exc:
    print(f"  [FAIL] threat_embedding_idx: {exc}")
    success = False

print("Validating vector index: threat_embedding_idx ...")
if not validate_vector_index(session, "threat_embedding_idx", "Threat", "embedding"):
    success = False
```

**Acceptance criteria:** `python scripts/init_knowledge_schema.py` adds 3 constraints + 1 vector index, idempotent on re-run.

---

## Phase 2: API Routes and Repo Functions

**Files to modify:**
- `memory_service/knowledge_schemas.py` — add enum sets
- `memory_service/knowledge_routes.py` — add Pydantic models + 15 endpoints
- `memory_service/knowledge_repo.py` — add Cypher functions

### 2a. New enum sets in `knowledge_schemas.py`

```python
THREAT_REPORT_SCOPES: frozenset[str] = frozenset({
    "geographic", "sectoral", "vendor",
})
IDENTIFIES_SEVERITIES: frozenset[str] = frozenset({
    "critical", "high", "medium", "low",
})
IDENTIFIES_CONFIDENCES: frozenset[str] = frozenset({
    "high", "medium", "low",
})
IDENTIFIES_TRENDS: frozenset[str] = frozenset({
    "increasing", "stable", "decreasing",
})
ASSET_TYPES: frozenset[str] = frozenset({
    "IT", "OT", "IoT", "IT-OT-integration",
})
ASSET_EXPOSURES: frozenset[str] = frozenset({
    "internet-facing", "internal", "air-gapped",
})
ASSET_DATA_CLASSIFICATIONS: frozenset[str] = frozenset({
    "public", "internal", "confidential", "restricted",
})
```

### 2b. Pydantic models in `knowledge_routes.py`

```python
class ThreatReportCreate(BaseModel):
    id: str
    title: str
    publisher: str
    published_at: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    scope: Optional[str] = None
    perspective_notes: Optional[str] = None

class ThreatReportResponse(BaseModel):
    id: str; title: str; publisher: str
    published_at: Optional[str]; valid_from: Optional[str]
    valid_until: Optional[str]; scope: Optional[str]
    perspective_notes: Optional[str]; created_at: str

class ThreatCreate(BaseModel):
    id: str
    text: str          # normalised threat statement; embedded on creation
    tags: Optional[List[str]] = None

class ThreatResponse(BaseModel):
    id: str; text: str; tags: Optional[List[str]]; created_at: str

class AssetCreate(BaseModel):
    id: str; title: str; asset_type: str
    exposure: Optional[str] = None
    data_classification: Optional[str] = None

class AssetResponse(BaseModel):
    id: str; title: str; asset_type: str
    exposure: Optional[str]; data_classification: Optional[str]; created_at: str

class IdentifiesCreate(BaseModel):
    threat_report_id: str; threat_id: str
    severity: str; confidence: str; trend: str
    source_terminology: Optional[str] = None

class IdentifiesResponse(BaseModel):
    threat_report_id: str; threat_id: str
    severity: str; confidence: str; trend: str
    source_terminology: Optional[str]; created_at: str

class MappedToTechniqueCreate(BaseModel):
    threat_id: str
    framework_id: str   # ATT&CK Framework node id

class MappedToTechniqueResponse(BaseModel):
    threat_id: str; framework_id: str; created_at: str

class TargetsCreate(BaseModel):
    threat_id: str; asset_id: str

class TargetsResponse(BaseModel):
    threat_id: str; asset_id: str; created_at: str

class ThreatSearchRequest(BaseModel):
    query: str
    limit: int = 10

class ThreatHit(BaseModel):
    id: str; text: str; tags: Optional[List[str]]; created_at: str; distance: float
```

### 2c. API endpoints (15 new routes)

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/knowledge/threat-reports` | MERGE upsert, validates `scope` |
| `GET` | `/knowledge/threat-reports/{id}` | 404 if not found |
| `GET` | `/knowledge/threat-reports` | List all |
| `POST` | `/knowledge/threats` | MERGE upsert, generates embedding, validates `tags` |
| `GET` | `/knowledge/threats/{id}` | 404 if not found |
| `GET` | `/knowledge/threats` | List all |
| `POST` | `/knowledge/search/threats` | Vector search over `threat_embedding_idx` |
| `POST` | `/knowledge/assets` | MERGE upsert, validates `asset_type`/`exposure`/`data_classification` |
| `GET` | `/knowledge/assets/{id}` | 404 if not found |
| `GET` | `/knowledge/assets` | List all |
| `POST` | `/knowledge/identifies` | Creates `IDENTIFIES` edge; `ON MATCH SET` updates severity/confidence/trend; 404 if nodes missing |
| `POST` | `/knowledge/mapped-to-technique` | Creates `MAPPED_TO_TECHNIQUE` edge; 404 if nodes missing |
| `POST` | `/knowledge/targets` | Creates `TARGETS` edge; 404 if nodes missing |
| `GET` | `/knowledge/threats/{id}/reports` | List `ThreatReport`s that IDENTIFY this threat |
| `GET` | `/knowledge/threat-reports/{id}/threats` | List `Threat`s identified by this report |

### 2d. Cypher functions in `knowledge_repo.py`

**`upsert_threat_report`** — MERGE on id, ON CREATE SET:
```python
def upsert_threat_report(session, req, now: str) -> dict:
    result = session.run("""
        MERGE (tr:ThreatReport {id: $id})
        ON CREATE SET
            tr.title = $title, tr.publisher = $publisher,
            tr.published_at = $published_at, tr.valid_from = $valid_from,
            tr.valid_until = $valid_until, tr.scope = $scope,
            tr.perspective_notes = $perspective_notes, tr.created_at = $created_at
        RETURN tr.id AS id, tr.title AS title, tr.publisher AS publisher,
               tr.published_at AS published_at, tr.valid_from AS valid_from,
               tr.valid_until AS valid_until, tr.scope AS scope,
               tr.perspective_notes AS perspective_notes, tr.created_at AS created_at
    """, id=req.id, title=req.title, publisher=req.publisher,
        published_at=req.published_at, valid_from=req.valid_from,
        valid_until=req.valid_until, scope=req.scope,
        perspective_notes=req.perspective_notes, created_at=now)
    return dict(result.single())
```

**`upsert_threat`** — MERGE on id, embed `text` via `threat_embedding_idx`:
```python
def upsert_threat(session, req, embedding: list[float], now: str) -> dict:
    result = session.run("""
        MERGE (t:Threat {id: $id})
        ON CREATE SET t.text = $text, t.tags = $tags,
                      t.embedding = $embedding, t.created_at = $created_at
        RETURN t.id AS id, t.text AS text, t.tags AS tags, t.created_at AS created_at
    """, id=req.id, text=req.text, tags=req.tags or [],
        embedding=embedding, created_at=now)
    return dict(result.single())
```

**`search_threats`** — vector search over `threat_embedding_idx` (same pattern as `search_frameworks`):
```python
def search_threats(session, embedding: list[float], limit: int) -> list[dict]:
    result = session.run("""
        CALL vector_search.search_nodes("threat_embedding_idx", $limit, $embedding)
        YIELD node, distance
        RETURN node.id AS id, node.text AS text, node.tags AS tags,
               node.created_at AS created_at, distance
        ORDER BY distance ASC
    """, embedding=embedding, limit=limit)
    return [dict(r) for r in result]
```

**`create_identifies_edge`** — MERGE with ON MATCH SET (updates per new report version):
```python
def create_identifies_edge(session, threat_report_id, threat_id,
                           severity, confidence, trend, source_terminology, now):
    result = session.run("""
        MATCH (tr:ThreatReport {id: $tr_id}), (t:Threat {id: $t_id})
        MERGE (tr)-[r:IDENTIFIES]->(t)
        ON CREATE SET r.severity = $severity, r.confidence = $confidence,
                      r.trend = $trend, r.source_terminology = $source_terminology,
                      r.created_at = $created_at
        ON MATCH SET  r.severity = $severity, r.confidence = $confidence,
                      r.trend = $trend, r.source_terminology = $source_terminology
        RETURN tr.id AS threat_report_id, t.id AS threat_id,
               r.severity AS severity, r.confidence AS confidence,
               r.trend AS trend, r.source_terminology AS source_terminology,
               r.created_at AS created_at
    """, tr_id=threat_report_id, t_id=threat_id, severity=severity,
        confidence=confidence, trend=trend,
        source_terminology=source_terminology, created_at=now)
    record = result.single()
    return dict(record) if record else None
```

**`create_mapped_to_technique_edge`**, **`create_targets_edge`** — MERGE, return None if nodes missing (same pattern as `create_mitigates_edge`).

**List + get functions** for all three node types — same MATCH-RETURN pattern as existing `get_framework`, `list_norms`.

---

## Phase 3: CTI Extraction Pipeline

### Core design

```
PDF
 └─► pdfplumber.extract_words()  →  raw words + bounding boxes
      └─► words_to_lines()       →  visual lines (same helper as pdf-ingest skill)
           └─► sentence splitter  →  prose sentences
                └─► CTIReportParser.parse_report()
                     ├─► behaviour_verb detection  →  candidate sentences
                     └─► keyword→technique_id lookup  →  ATT&CK technique hints
                          └─► per-sentence Threat node candidate
                               └─► search_threats() deduplication check
                                    ├─► distance < 0.15: reuse existing Threat id
                                    └─► distance >= 0.15: create new Threat node
                                         └─► IDENTIFIES edge + MAPPED_TO_TECHNIQUE edge
```

### Keyword→technique_id table (in the extraction script)

Based on the `CTIReportParser.TECHNIQUE_KEYWORDS` pattern from the CTI skill, extended with threat-report-relevant terms:

```python
TECHNIQUE_KEYWORDS: dict[str, str] = {
    # Initial Access
    "phishing": "T1566",
    "spearphishing": "T1566",
    "phishing attachment": "T1566.001",
    "phishing link": "T1566.002",
    "supply chain": "T1195",
    "exploit public": "T1190",
    "valid account": "T1078",
    # Execution
    "powershell": "T1059.001",
    "command line": "T1059.003",
    "wmi": "T1047",
    "scheduled task": "T1053.005",
    # Persistence
    "registry run": "T1547.001",
    "web shell": "T1505.003",
    # Credential Access
    "credential": "T1110",
    "credential stuffing": "T1110.004",
    "brute force": "T1110",
    "password spray": "T1110.003",
    "kerberoasting": "T1558.003",
    "pass the hash": "T1550.002",
    "lsass": "T1003.001",
    "credential dumping": "T1003",
    # Lateral Movement
    "lateral movement": "T1021",
    "remote desktop": "T1021.001",
    "rdp": "T1021.001",
    "smb": "T1021.002",
    # Collection/Exfiltration
    "data exfiltration": "T1041",
    "exfiltration": "T1041",
    "dns tunneling": "T1071.004",
    "data staging": "T1074",
    # Impact
    "ransomware": "T1486",
    "encryption": "T1486",
    "wiper": "T1485",
    "data destruction": "T1485",
    "denial of service": "T1498",
    "ddos": "T1498",
    # Resource Development
    "infrastructure": "T1583",
    # Cloud
    "cloud misconfiguration": "T1530",
    "cloud storage": "T1530",
    # Resource Hijacking
    "cryptojacking": "T1496",
    "resource hijacking": "T1496",
    # Business Email Compromise
    "business email compromise": "T1534",
    "bec": "T1534",
}
```

### Threat ID generation

Threat IDs are generated as `threat-{report_id}-{sequence}` for new nodes (e.g. `threat-verizon-dbir-2025-001`). When an existing node is reused via deduplication, the report's `IDENTIFIES` edge points to that node's existing ID.

### Deduplication threshold

`0.15` cosine distance (same scale as the existing `search_frameworks` and `search_controls` endpoints). This is conservative — only near-exact semantic matches are merged. Slightly different phrasings get their own nodes and will be connected by the `RELATED_TO` decay/similarity pass later.

### File to create: `scripts/extract_cti_threats.py`

Standalone extraction script:

```
python scripts/extract_cti_threats.py \
    --pdf "/mnt/c/Users/olive/.../Threat Reports/m-trends-2026-en.pdf" \
    --report-id "report-mandiant-mtrends-2026" \
    --title "M-Trends 2026" \
    --publisher "Mandiant" \
    --published-at "2026-04-01" \
    --valid-from "2025-01-01" \
    --valid-until "2026-12-31" \
    --scope "vendor" \
    --perspective-notes "Incident response data. Strong on dwell time, lateral movement, ransomware." \
    [--dry-run] [--dedup-threshold 0.15] [--page-range 5 80]
```

The script:
1. Creates the `ThreatReport` node via `POST /knowledge/threat-reports`
2. Extracts text from the PDF using `pdfplumber.extract_words()` + `words_to_lines()`
3. Splits into sentences; runs `CTIReportParser.parse_report()` to detect behaviour verbs and ATT&CK keywords
4. For each candidate threat sentence:
   a. Calls `POST /knowledge/search/threats` to check for near-duplicates (distance < threshold)
   b. If duplicate found: uses existing threat_id
   c. If no duplicate: generates new `threat-{report_id}-{N}` id, creates `Threat` node via `POST /knowledge/threats`
5. Creates `IDENTIFIES` edge via `POST /knowledge/identifies` (severity/confidence/trend are extracted heuristically from the sentence context, defaulting to `high`/`medium`/`stable` where not determinable)
6. Creates `MAPPED_TO_TECHNIQUE` edges for matched ATT&CK technique IDs via `POST /knowledge/mapped-to-technique`
7. Prints a summary: N threats extracted, M deduplicated against existing, K new nodes created, L technique edges created

### Severity/trend heuristics

Parse sentence context for signal words before creating the `IDENTIFIES` edge:
- severity: `critical`/`severe`/`major` → `critical`; `widespread`/`significant` → `high`; `moderate` → `medium`; default → `high`
- trend: `increasing`/`growing`/`rise`/`more` → `increasing`; `declining`/`decreasing`/`fewer` → `decreasing`; default → `stable`
- confidence: always `high` for keyword-matched techniques, `medium` for behaviour-verb-only matches

### File to create: `scripts/ingest_all_threat_reports.py`

Orchestration script that calls `extract_cti_threats.py` for each of the 6 reports:

```python
REPORTS = [
    {
        "pdf": "/mnt/c/Users/olive/OneDrive/Dokumente/CyberSec/Standards Frameworks/Threat Reports/2025-dbir-data-breach-investigations-report.pdf",
        "report_id": "report-verizon-dbir-2025",
        "title": "2025 Data Breach Investigations Report",
        "publisher": "Verizon",
        "published_at": "2025-05-01",
        "valid_from": "2024-01-01",
        "valid_until": "2025-12-31",
        "scope": "geographic",
        "perspective_notes": "US-heavy sample. Strong on credential-based and social engineering breach data.",
        "page_range": (4, 90),
    },
    {
        "pdf": "...Cloudflare Threat Report 2026.pdf",
        "report_id": "report-cloudflare-2026",
        "title": "Cloudflare Threat Report 2026",
        "publisher": "Cloudflare",
        "published_at": "2026-01-01",
        "valid_from": "2025-01-01",
        "valid_until": "2026-12-31",
        "scope": "vendor",
        "perspective_notes": "DDoS-heavy, API abuse, bot traffic. Vendor perspective on network-layer threats.",
        "page_range": (3, 80),
    },
    # ... ENISA, BSI, Microsoft, Mandiant
]
```

### File to create: `data/threats/assets.yaml`

Minimal — 4 universal asset class reference nodes only:
```yaml
assets:
  - id: asset-it
    title: "Information Technology Systems"
    asset_type: IT
  - id: asset-ot
    title: "Operational Technology Systems"
    asset_type: OT
  - id: asset-iot
    title: "Internet of Things Devices"
    asset_type: IoT
  - id: asset-it-ot-integration
    title: "IT-OT Integration Points"
    asset_type: IT-OT-integration
```

### File to create: `scripts/seed_assets.py`

Simple script that reads `data/threats/assets.yaml` and calls `POST /knowledge/assets` for each entry. Idempotent.

---

## Phase 4: Cluster Validation

**File to create:** `scripts/validate_threat_clusters.py`

Standalone script (direct Memgraph driver, pattern: `analyse_cross_framework_clusters.py`).

**Query 1 — top threats by report coverage:**
```cypher
MATCH (tr:ThreatReport)-[r:IDENTIFIES]->(t:Threat)
WITH t, count(tr) AS report_count,
     collect(DISTINCT r.severity) AS severities,
     collect(DISTINCT r.trend) AS trends
ORDER BY report_count DESC LIMIT 15
RETURN t.id AS threat_id, t.text AS threat_text,
       report_count, severities, trends
```

**Query 2 — ATT&CK technique coverage per threat:**
```cypher
MATCH (t:Threat)-[:MAPPED_TO_TECHNIQUE]->(tech:Framework)
OPTIONAL MATCH (ctrl:Control)-[:MITIGATES]->(tech)
RETURN t.id AS threat_id,
       collect(DISTINCT tech.external_id) AS techniques,
       count(DISTINCT ctrl) AS mitigating_controls,
       collect(DISTINCT ctrl.embedding_cluster_id)[0..3] AS sample_clusters
```

**Query 3 — unmitigated technique gaps:**
```cypher
MATCH (t:Threat)-[:MAPPED_TO_TECHNIQUE]->(tech:Framework)
WHERE NOT (tech)<-[:MITIGATES]-(:Control)
RETURN t.id AS threat_id,
       collect(tech.external_id) AS unmitigated_techniques
```

Output: plain-text report with top threats, their ATT&CK mappings, control coverage, cluster alignment, and gaps.

---

## Phase 5: Test Plan

### Unit tests — `tests/test_threat_models.py`

No live stack required:
1. `ThreatReportCreate` rejects missing `title`, `publisher`
2. `ThreatCreate` rejects missing `text`
3. `AssetCreate` — valid `asset_type` accepted, invalid rejected via HTTP 422
4. `IdentifiesCreate` — invalid `severity`/`confidence`/`trend` rejected
5. All new `knowledge_schemas.py` enum sets are non-empty and contain expected values
6. `assets.yaml` loads and validates: each asset has `id`, `title`, `asset_type`

### Unit tests — `tests/test_threat_repo.py`

Mocked session (pattern: `test_knowledge_bridge.py`):
1. `upsert_threat_report` — calls session.run with correct params
2. `upsert_threat` — passes embedding as parameter, not null
3. `create_identifies_edge` — returns None when nodes don't exist (empty result)
4. `create_mapped_to_technique_edge` — returns None when Framework node missing
5. `search_threats` — returns list of dicts with expected keys

### Unit tests — `tests/test_cti_extractor.py`

Tests for the extraction logic in `extract_cti_threats.py`, no PDF or network required:
1. `CTIReportParser.parse_report()` — extracts behaviours from a known sample sentence containing "ransomware"
2. `CTIReportParser._match_techniques()` — maps "ransomware" → `T1486`, "phishing" → `T1566`
3. Severity heuristic — "critical vulnerability" → severity `critical`, no signal → `high`
4. Trend heuristic — "increasing ransomware" → `increasing`, no signal → `stable`
5. Threat ID generation — `threat-{report_id}-001`, `threat-{report_id}-002` sequence

### Integration tests — `tests/test_threat_integration.py`

Require live Memgraph + FastAPI. Mark all `@pytest.mark.integration`.

1. Schema: after running `init_knowledge_schema.py`, `SHOW INDEX INFO` includes `threat_embedding_idx`
2. Round-trip: POST threat → GET `/knowledge/threats/{id}` returns correct fields
3. Deduplication: POST same text twice → second call hits existing node, no duplicate
4. Vector search: `POST /knowledge/search/threats` with "ransomware encryption" → closest hit is a ransomware threat node
5. Edge traversal: after `ingest_all_threat_reports.py`, `GET /knowledge/threat-reports/report-mandiant-mtrends-2026/threats` returns non-empty list
6. ATT&CK links: `MATCH ()-[r:MAPPED_TO_TECHNIQUE]->() RETURN count(r)` > 0

---

## Acceptance Criteria (Full WP-108)

- `python scripts/init_knowledge_schema.py` adds 3 constraints + 1 vector index; idempotent
- All 15 API endpoints respond correctly with proper enum validation and 404 handling
- 6 `ThreatReport` nodes loaded
- `Threat` nodes created automatically from PDF extraction — no manual curation
- Near-duplicate threats merged via embedding search at ingest time
- `MAPPED_TO_TECHNIQUE` edges link extracted threats to ATT&CK Framework nodes where keywords match
- 4 `Asset` reference nodes seeded
- `validate_threat_clusters.py` runs and produces a meaningful report
- All unit tests pass; integration tests pass against live stack

---

## Implementation Sequence

Phases 1, 2, and 3 (API code + extractor) are **parallelisable** — API code does not need the extractor and vice versa.

| Phase | Files | Parallel? |
|-------|-------|-----------|
| 1 Schema | `init_knowledge_schema.py`, `config.py` | ✅ with 2+3 |
| 2 API routes + repo | `knowledge_routes.py`, `knowledge_repo.py`, `knowledge_schemas.py` | ✅ with 1+3 |
| 3 Extractor | `extract_cti_threats.py`, `ingest_all_threat_reports.py` | ✅ with 1+2 |
| 3 Asset seed | `data/threats/assets.yaml`, `seed_assets.py` | ✅ with 1+2 |
| 4 Cluster validation | `validate_threat_clusters.py` | After Phase 3 run |
| 5 Tests | `test_threat_models.py`, `test_threat_repo.py`, `test_cti_extractor.py`, `test_threat_integration.py` | After Phase 2 |

---

## Files Summary

**Modify:**
- `scripts/init_knowledge_schema.py`
- `memory_service/config.py`
- `memory_service/knowledge_schemas.py`
- `memory_service/knowledge_routes.py`
- `memory_service/knowledge_repo.py`

**Create:**
- `data/threats/assets.yaml`
- `scripts/seed_assets.py`
- `scripts/extract_cti_threats.py`
- `scripts/ingest_all_threat_reports.py`
- `scripts/validate_threat_clusters.py`
- `tests/test_threat_models.py`
- `tests/test_threat_repo.py`
- `tests/test_cti_extractor.py`
- `tests/test_threat_integration.py`
