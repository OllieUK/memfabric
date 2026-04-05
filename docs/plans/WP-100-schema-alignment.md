# WP-100: Schema Alignment with ADR-002

## Overview

Breaking schema change aligning four node types (Framework, Norm, Chunk, Document) with ADR-002. Includes a data migration script for existing Memgraph nodes.

**Files changed:** `knowledge_schemas.py`, `knowledge_routes.py`, `knowledge_repo.py`, `dump_db.py`, `restore_db.py`, `tests/test_wp070.py`, `tests/test_wp076_integration.py`, `tests/test_wp069_knowledge_schema.py`
**New file:** `scripts/migrate_wp100_schema.py`

---

## Step-by-step Implementation (dependency order)

### Step 1 — `knowledge_schemas.py`: add `CHUNK_STATUSES`

Add after `NORMATIVE_MODALITIES`:
```python
CHUNK_STATUSES: frozenset[str] = frozenset({
    "unmatched",    # ingested, not yet linked to any tree node
    "matched",      # candidate match found, pending confirmation
    "confirmed",    # human or automated confirmation of SUPPORTS edge
    "superseded",   # content replaced by a newer chunk
})
```

---

### Step 2 — `knowledge_routes.py`: rebuild Pydantic models + validation

**Framework:**
- `FrameworkCreate`: rename `name: str` → `title: str`, remove `description: Optional[str]`
- `FrameworkResponse`: same
- `FrameworkHit`: rename `name` → `title`
- Route: pass `title` not `name` to repo; call `get_embedding(req.title + " " + (req.body or ""), ...)`

**Norm — complete rebuild:**
- `NormCreate`: replace all fields with `title: str`, `body: str`, `level: str = "article"`, `version: Optional[str]`, `valid_from: Optional[str]`, `valid_until: Optional[str]`, `announced_at: Optional[str]`, `text_hash: Optional[str]`, `lang: Optional[str]`, `domain: Optional[str]`, `maps_to_control_id: Optional[str]`, `references_framework_id: Optional[str]`, `references_version_pinned: Optional[bool] = False`
- `NormResponse`: rebuild to match new fields (id, title, body, level, version, valid_from, valid_until, announced_at, text_hash, lang, domain, created_at)
- Route: call `get_embedding(req.body, ...)` not `get_embedding(req.text, ...)`

**Document:**
- `DocumentCreate`: rename `doc_type: str` → `policy_level: str`; validate against `DOCUMENT_POLICY_LEVELS`; raise HTTP 400 if invalid
- `DocumentResponse`: same

**Chunk:**
- `ChunkCreate`: rename `text: str` → `body: str`; add `heading: Optional[str]`, `section_ref: Optional[str]`, `status: Optional[str] = "unmatched"`; validate `status` against `CHUNK_STATUSES`
- `ChunkResponse`: add `heading`, `section_ref`, `status`
- `ChunkHit`: rename `text` → `body`; add `heading`, `section_ref`, `status`
- `ChunkWithSupports`: rename `text` → `body`; add `heading`, `section_ref`, `status`
- Route: call `get_embedding(req.body, ...)` not `get_embedding(req.text, ...)`

**SupportsCreate / SupportsResponse:**
- Add `raw_score: Optional[float] = None` to both

**Imports:** add `CHUNK_STATUSES`, `DOCUMENT_POLICY_LEVELS` to import from `knowledge_schemas`

---

### Step 3 — `knowledge_repo.py`: update all Cypher

**Framework:**
- `upsert_framework`: `f.name` → `f.title`, remove `f.description`; update ON CREATE SET, ON MATCH SET, RETURN
- `get_framework`: `f.name AS name` → `f.title AS title`, remove `f.description`
- `search_frameworks`: `f.name AS name` → `f.title AS title`

**Norm — complete rewrite of `upsert_norm`:**
- New properties: `title`, `body`, `level`, `version`, `valid_from`, `valid_until`, `announced_at`, `text_hash`, `lang`, `domain`
- Edge `MAPS_TO (Norm→Control)` using `maps_to_control_id` (replaces `IMPLEMENTS`)
- Edge `REFERENCES (Norm→Framework)` with property `version_pinned = $references_version_pinned` (replaces `SOURCED_FROM`)
- `get_norm`: RETURN with new property names
- `list_norms`: RETURN + ORDER BY n.title
- `list_incomplete_jurisdictions`: `n.name` → `n.title`
- `trace_up`: Cypher returns `{id: n.id, name: n.name, status: n.status}` → fix to `{id: n.id, title: n.title}` (status removed from Norm model)

**Document:**
- `upsert_document`: `d.doc_type` → `d.policy_level`; update SET, RETURN, kwargs
- `get_document`: update RETURN
- `list_documents`: update RETURN

**Chunk:**
- `upsert_chunk`: `ch.text` → `ch.body`; add `ch.heading`, `ch.section_ref`, `ch.status`; update kwargs
- `get_chunk`: update RETURN
- `search_chunks`: `ch.text AS text` → `ch.body AS body`; add heading, section_ref, status
- `get_chunks_for_framework`: same as search_chunks
- `trace_down`: `ch.text` → `ch.body` in Cypher alias; `row["chunk_text"]` → `row["chunk_body"]` in Python

**SUPPORTS:**
- `create_supports_edge_framework`: add `s.raw_score = $raw_score` to ON CREATE SET; add `raw_score` param; update RETURN

---

### Step 4 — `dump_db.py` / `restore_db.py`: update edge allowlists

- Add `MAPS_TO` and `REFERENCES` to the edge type lists
- Do NOT remove `IMPLEMENTS` (it remains as Document→Control per ADR-002)
- `SOURCED_FROM` was never in the allowlists — no removal needed

---

### Step 5 — Tests: update to new field names

**`tests/test_wp070.py`:**
- Framework mock data: `name` → `title`, remove `description`
- Norm mock data: rebuild with `title`, `body`, `level`, etc.; edge assertions `IMPLEMENTS`/`SOURCED_FROM` → `MAPS_TO`/`REFERENCES`
- Chunk mock data: `text` → `body`; add `heading`, `section_ref`, `status`
- Document mock data: `doc_type` → `policy_level`
- All route JSON payloads updated accordingly

**`tests/test_wp076_integration.py`:**
- All payloads: `name` → `title` (frameworks/norms), `text` → `body` (norms/chunks), `doc_type` → `policy_level`
- `test_upsert_norm_creates_implements_edge` → `test_upsert_norm_creates_maps_to_edge` (check `MAPS_TO`)
- `test_upsert_norm_creates_sourced_from_edge` → `test_upsert_norm_creates_references_edge` (check `REFERENCES`)

**`tests/test_wp069_knowledge_schema.py`:**
- Add test for `CHUNK_STATUSES` constant
- Add `MAPS_TO` and `REFERENCES` to `_KNOWLEDGE_EDGE_TYPES` set

---

### Step 6 — Migration script: `scripts/migrate_wp100_schema.py`

Template: `scripts/migrate_remove_standard_chunks.py`

Queries (in order):
1. `MATCH (f:Framework) WHERE f.name IS NOT NULL SET f.title = f.name REMOVE f.name, f.description`
2. `MATCH (n:Norm) WHERE n.name IS NOT NULL SET n.title = n.name, n.body = n.text REMOVE n.name, n.text, n.status, n.effective_date`
3. `MATCH (ch:Chunk) WHERE ch.text IS NOT NULL SET ch.body = ch.text, ch.status = "unmatched" REMOVE ch.text`
4. `MATCH (ch:Chunk) WHERE ch.heading IS NULL SET ch.heading = null, ch.section_ref = null`
5. `MATCH (d:Document) WHERE d.doc_type IS NOT NULL SET d.policy_level = d.doc_type REMOVE d.doc_type`
6. Count then DELETE: `MATCH (n:Norm)-[r:IMPLEMENTS]->() DELETE r`
7. Count then DELETE: `MATCH (n:Norm)-[r:SOURCED_FROM]->() DELETE r`

Flags: `--dry-run` (print counts, skip mutations)

---

## Risks and Gotchas

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | `trace_down` references `ch.text` alias and `row["chunk_text"]` — easy to miss | Search for `chunk_text` as well as `ch.text` |
| 2 | `list_incomplete_jurisdictions` returns `n.name` — callers see field rename | Update RETURN and Python dict key |
| 3 | `trace_up` returns `n.name`/`n.status` for Norm nodes — field shape changes | Update Cypher dict; remove `status` |
| 4 | `IMPLEMENTS` in dump_db allowlist is Document→Control, NOT Norm→Control — must keep | Only delete Norm-originated `IMPLEMENTS` in migration |
| 5 | Embedding call in norm route uses `req.text` — will raise AttributeError after rename | Update to `req.body` |
| 6 | `REFERENCES` edge needs `version_pinned` property per ADR-002 | Pass `references_version_pinned` in MERGE |
| 7 | No live Norm nodes yet — Norm migration is a no-op but write it anyway for correctness | Script runs but reports 0 affected |

---

## Test Plan

| Test | Type | Criteria |
|------|------|---------|
| `CHUNK_STATUSES` constant exists and has 4 values | Unit | Pass |
| `DocumentCreate` with invalid `policy_level` returns 400 | Unit | Pass |
| `ChunkCreate` with invalid `status` returns 400 | Unit | Pass |
| `FrameworkResponse` has `title` not `name` | Unit | Pass |
| `NormCreate` with new fields round-trips via upsert → get | Integration | title/body/level stored correctly |
| `MAPS_TO` edge created when `maps_to_control_id` provided | Integration | Edge exists in graph |
| `REFERENCES` edge created when `references_framework_id` provided | Integration | Edge + version_pinned exists |
| `Chunk.body` stored and returned, no `text` property on node | Integration | Pass |
| `Document.policy_level` stored, no `doc_type` property | Integration | Pass |
| Migration script `--dry-run` reports counts without mutating | Manual smoke | Pass |
| Migration script applied — no Framework nodes have `name` | Manual smoke | `MATCH (f:Framework) WHERE f.name IS NOT NULL RETURN count(f)` = 0 |

---

## Acceptance Criteria

1. All existing unit tests pass (46 baseline failures unchanged)
2. All 12+ integration tests pass against live stack with `ENABLE_KNOWLEDGE_LAYER=true`
3. No knowledge node has `name`, `text`, `doc_type` properties after migration
4. `MAPS_TO` replaces `IMPLEMENTS` on all Norm→Control edges
5. `REFERENCES` replaces `SOURCED_FROM` on all Norm→Document edges
