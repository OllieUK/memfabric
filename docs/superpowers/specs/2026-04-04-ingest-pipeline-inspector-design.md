# Ingest Pipeline Inspector — Design Spec

**Date:** 2026-04-04
**Status:** Draft — awaiting user review
**Scope:** PDF → knowledge graph ingest pipeline, staged inspection notebook

---

## Context

The knowledge layer ETL pipeline (WP-070–WP-076) is fully implemented and merged. Before ingesting real regulatory PDFs (ISO 27001, NIS2, BSI IT-Grundschutz), we need to validate each stage of the pipeline interactively:

- Does the PDF extract cleanly?
- Are chunks a sensible size and do they preserve evidence at boundaries?
- Does the multilingual embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) match English and German text to the same controls?
- Are HAS_CHUNK and HAS_NEXT edges created correctly?
- Which chunks plausibly SUPPORT which controls, before committing edges?

The answer is a Jupyter notebook — one cell group per pipeline stage, designed for exploratory use before the first real import, and reusable for each new document thereafter.

**Out of scope:** Excel cross-standard mapping files (format TBD — deferred to a future WP).

---

## Architecture

```
notebooks/
  ingest_pipeline_inspector.ipynb   ← main artefact

tests/fixtures/
  sample_norm_en_de.md              ← bilingual synthetic fixture (checked in)
```

The notebook imports directly from existing modules:
- `scripts/chunkers.chunk_pdf` — chunking logic (no subprocess)
- `scripts/chunkers.chunk_markdown` — used for the synthetic fixture test
- `httpx.Client` → live FastAPI service (same `API_BASE_URL` from `.env`)
- `neo4j.GraphDatabase` → live Memgraph (same Bolt pattern as `conftest.py`)

No new production code is added. The notebook is a consumer of existing interfaces.

---

## Notebook Structure

### Cell Group 1 — Setup
- Imports, config loaded from `.env` via `pydantic-settings`
- Bolt driver + httpx client created
- Health check printed: API reachable ✓, Memgraph reachable ✓, `ENABLE_KNOWLEDGE_LAYER=true` ✓
- Variables to set: `PDF_PATH`, `DOC_ID`, `DOC_TITLE`, `DOC_TYPE`

### Cell Group 2 — Load PDF
- Opens PDF with `pdfplumber`, counts pages
- Detects language per page using `langdetect` (identifies multilingual docs)
- Prints total character count + first 500 chars preview
- Catches: garbled text (scanned/image PDFs), encoding issues

### Cell Group 3 — Chunk
- Calls `chunk_pdf()` directly with configurable `CHUNK_SIZE` / `OVERLAP` / `MIN_CHUNK_CHARS` variables
- Displays: chunk count, char length distribution (min/max/mean/p50/p95)
- Prints first 3 and last 3 chunks in full
- Lists any chunks filtered by `MIN_CHUNK_CHARS`
- Re-runnable with different parameters without touching the graph

### Cell Group 4 — Embedding Preview
- Samples 10 chunks (evenly spaced across the document)
- For each, calls `POST /knowledge/search/controls` and prints top 3 nearest controls with cosine distance
- Validates model is matching chunks to semantically correct controls

**Bilingual pair test (uses synthetic fixture):**
- Requires at least one framework already loaded in the graph (e.g. `data/frameworks/iso-27001-2022.yaml` via `ingest_framework.py`)
- Queries `POST /knowledge/search/controls` with the same concept in English and German
- Compares top-3 result sets — overlap % indicates cross-lingual embedding quality
- Example pairs: "access control" / "Zugangssteuerung", "data retention" / "Datenspeicherung"

### Cell Group 5 — Upsert
- Creates Document node via `POST /knowledge/documents`
- Posts all chunks via `POST /knowledge/chunks` with `prev_chunk_id` chaining
- Displays progress table: sequence | char count | created/already-existed
- Idempotent — safe to re-run (409 = already existed, not an error)

### Cell Group 6 — Link Verify
- Queries Memgraph via Bolt to confirm:
  - `HAS_CHUNK` edge count matches chunk count
  - `HAS_NEXT` chain is complete (no sequence gaps)
  - No orphaned chunks (chunks without `HAS_CHUNK`)
- Prints SUPPORTS candidates table (review mode — no edges created)
  - Columns: chunk_id | chunk_text_preview | control_id | control_name | confidence

### Cell Group 7 — SUPPORTS Edge Creation (explicit, optional)
- Clearly marked: "Run this cell to commit SUPPORTS edges"
- Re-displays candidates table
- Creates edges via `POST /knowledge/chunk/supports` with `status=auto-inferred`
- Prints created count

---

## Synthetic Fixture

**File:** `tests/fixtures/sample_norm_en_de.md`

A small Markdown document with 5 sections mixing English and German norm text. Designed to contain semantically similar content in both languages so the bilingual pair test in Cell Group 4 can assert meaningful overlap.

Example sections:
- `## Access Control Policy` (English, ISO 27001-style)
- `## Zugangssteuerung` (German, BSI IT-Grundschutz-style, same concept)
- `## Data Retention Requirements` / `## Datenspeicherungsanforderungen`

Checked into git. Used only for the embedding quality test — not inserted into the graph.

---

## Excel Deferred

Cross-standard mapping Excel files are noted as a future requirement. Format is TBD pending inspection of a real file.

**New backlog item to add:** `WP-NNN: Excel cross-standard mapping importer — design parser once a real file is available to inspect.`

---

## Implementation Order

Build in this sequence so the real ISO 27001 PDF can be tested as early as possible:

1. **Synthetic fixture + Cell Groups 1–3** — get chunking working and visible with known content
2. **Cell Group 4 (embedding preview)** — validate multilingual model against the synthetic fixture
3. **Point at real ISO 27001 PDF** — Cell Groups 1–4 work on real data from this point
4. **Cell Groups 5–7** — upsert and link verify against live stack

## Verification

1. Open notebook, set `PDF_PATH` to the synthetic fixture, run Cell Groups 1–3 without the API running — chunking is pure Python
2. Start the stack (`docker compose up -d`), load `iso-27001-2022.yaml` via `ingest_framework.py`, run Cell Group 4 — embedding preview should show controls with distance < 0.4 for topical chunks
3. Bilingual pair test: top-3 overlap ≥ 2/3 for the same concept in EN/DE indicates multilingual model is working
4. Switch `PDF_PATH` to the real ISO 27001 PDF — Cell Groups 1–4 should work without any code changes
5. Run Cell Groups 5–6: edge counts in Memgraph should match chunk count exactly
6. Cell Group 7: run once, verify SUPPORTS edges exist in Memgraph Lab at `http://localhost:3000`

---

## Dependencies

| Dependency | Already installed? | Note |
|---|---|---|
| `pdfplumber` | Yes (WP-073) | PDF extraction |
| `langdetect` | No | New: language detection per page |
| `jupyter` / `jupyterlab` | Likely not | Dev-only, not added to service requirements |
| `neo4j` (Bolt driver) | Yes | Graph verification |
| `httpx` | Yes | API calls |
| `pydantic-settings` | Yes | `.env` config |

`langdetect` and `jupyter`/`jupyterlab` to be added to `requirements-dev.txt` (not `requirements.txt`).
