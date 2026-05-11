#!/usr/bin/env python3
"""Generate notebooks/ingest_pipeline_inspector.ipynb.

Run this script any time you want to regenerate the notebook:
    python3 scripts/build_inspector_notebook.py

The notebook is checked into git so teammates can open it directly.
Re-run this script if you need to update cell content.
"""
from __future__ import annotations

from pathlib import Path

import nbformat

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def md(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(source)


def code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(source)


def build() -> None:
    nb = nbformat.v4.new_notebook()
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11.0"},
    }

    cells: list = []

    # -----------------------------------------------------------------------
    # Cell Group 1 — Setup
    # -----------------------------------------------------------------------
    cells.append(md(
        "# Ingest Pipeline Inspector\n\n"
        "Run cells top-to-bottom for a first run. "
        "Re-run individual cell groups to re-inspect a specific stage.\n\n"
        "**Prerequisites:** stack running (`docker compose up -d`), "
        "`ENABLE_KNOWLEDGE_LAYER=true` in `.env`."
    ))

    cells.append(code("""\
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path().resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotebookSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    memgraph_uri: str = "bolt://localhost:7687"
    memgraph_user: str = ""
    memgraph_password: str = ""
    enable_knowledge_layer: bool = False
    ingest_chunk_size: int = 2000
    ingest_chunk_overlap: int = 200
    ingest_min_chunk_chars: int = 50
    ingest_auto_supports_threshold: float = 0.20

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"), env_file_encoding="utf-8"
    )


cfg = NotebookSettings()

_api_ok = False
_graph_ok = False
_flag_ok = cfg.enable_knowledge_layer

try:
    r = httpx.get(f"{cfg.api_base_url}/health", timeout=3)
    _api_ok = r.status_code == 200
except Exception:
    pass

try:
    _driver = GraphDatabase.driver(
        cfg.memgraph_uri,
        auth=(cfg.memgraph_user, cfg.memgraph_password) if cfg.memgraph_user else ("", ""),
    )
    _driver.verify_connectivity()
    _graph_ok = True
except Exception:
    _driver = None

tick = chr(10003)
cross = chr(10007)
print(f"API reachable:          {tick if _api_ok else cross + '  (start: docker compose up -d)'}")
print(f"Memgraph reachable:     {tick if _graph_ok else cross + '  (start: docker compose up -d)'}")
print(f"ENABLE_KNOWLEDGE_LAYER: {tick if _flag_ok else cross + '  (set in .env)'}")
"""))

    cells.append(code("""\
# --- User configuration — edit these before running ---
PDF_PATH      = PROJECT_ROOT / "path/to/your.pdf"  # ← point at your PDF
DOC_ID        = "my-doc-001"                        # ← unique ID for this document
DOC_TITLE     = "My Document Title"
DOC_TYPE      = "standard"                          # policy | procedure | standard | guideline

# Chunking parameters — change and re-run Cell Group 3 to experiment without touching the graph
CHUNK_SIZE      = cfg.ingest_chunk_size
OVERLAP         = cfg.ingest_chunk_overlap
MIN_CHUNK_CHARS = cfg.ingest_min_chunk_chars

print(f"PDF_PATH : {PDF_PATH}")
print(f"DOC_ID   : {DOC_ID}")
print(f"CHUNK_SIZE={CHUNK_SIZE}  OVERLAP={OVERLAP}  MIN_CHARS={MIN_CHUNK_CHARS}")
"""))

    # -----------------------------------------------------------------------
    # Cell Group 2 — Load PDF
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 2 — Load PDF\n\n"
        "Inspect the raw PDF before chunking. "
        "Catches garbled text (scanned/image PDFs) before wasting time on later stages."
    ))

    cells.append(code("""\
import pdfplumber
from langdetect import detect
from collections import Counter

if not PDF_PATH.exists():
    raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

page_langs = []
total_chars = 0
first_500 = ""

with pdfplumber.open(PDF_PATH) as pdf:
    page_count = len(pdf.pages)
    for page in pdf.pages:
        text = page.extract_text() or ""
        total_chars += len(text)
        if not first_500 and text.strip():
            first_500 = text[:500]
        try:
            lang = detect(text) if len(text) > 50 else "unknown"
        except Exception:
            lang = "unknown"
        page_langs.append(lang)

lang_counts = Counter(page_langs)

print(f"Pages       : {page_count}")
print(f"Total chars : {total_chars:,}")
print(f"Languages   : {dict(lang_counts)}")
if total_chars < 1000:
    print("WARNING: very low character count — this may be a scanned/image PDF")
print()
print("--- First 500 chars ---")
print(first_500)
"""))

    # -----------------------------------------------------------------------
    # Cell Group 3 — Chunk
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 3 — Chunk\n\n"
        "Calls `chunk_pdf()` directly from `scripts/chunkers.py`. "
        "Re-run this cell with different `CHUNK_SIZE` / `OVERLAP` values "
        "(set in Cell Group 1) to tune chunking without touching the graph."
    ))

    cells.append(code("""\
from cyber_knowledge.ingest.chunkers import chunk_pdf
import statistics

chunks = chunk_pdf(str(PDF_PATH), CHUNK_SIZE, OVERLAP, MIN_CHUNK_CHARS)
lengths = [len(c.text) for c in chunks]

print(f"Total chunks : {len(chunks)}")
if lengths:
    sorted_lens = sorted(lengths)
    p95_idx = int(0.95 * len(sorted_lens))
    print(
        f"Chars  min={min(lengths)}  max={max(lengths)}"
        f"  mean={statistics.mean(lengths):.0f}"
        f"  p50={statistics.median(lengths):.0f}"
        f"  p95={sorted_lens[p95_idx]}"
    )
print()


def _preview(chunk, max_chars: int = 300) -> str:
    t = chunk.text.replace("\\n", " ")
    return t[:max_chars] + ("..." if len(t) > max_chars else "")


print("--- First 3 chunks ---")
for c in chunks[:3]:
    print(f"[{c.sequence}] {len(c.text)} chars: {_preview(c)}")
    print()

print("--- Last 3 chunks ---")
for c in chunks[-3:]:
    print(f"[{c.sequence}] {len(c.text)} chars: {_preview(c)}")
    print()
"""))

    # -----------------------------------------------------------------------
    # Cell Group 4 — Embedding Preview + Bilingual Test
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 4 — Embedding Preview\n\n"
        "Samples 10 evenly-spaced chunks and shows which controls the multilingual model "
        "matches them to.\n\n"
        "**Requires:** stack running, at least one framework loaded "
        "(e.g. `python3 scripts/ingest_framework.py data/frameworks/iso-27001-2022.yaml`).\n\n"
        "Also runs a **bilingual pair test** to verify EN/DE cross-lingual quality."
    ))

    cells.append(code("""\
import math

if not chunks:
    print("No chunks — run Cell Group 3 first")
else:
    step = max(1, math.floor(len(chunks) / 10))
    sample = chunks[::step][:10]

    print(f"Sampling {len(sample)} chunks (every {step})\\n")
    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:
        for c in sample:
            preview = c.text[:80].replace("\\n", " ")
            resp = client.post(
                "/knowledge/search/controls",
                json={"query": c.text, "limit": 3},
            )
            if resp.status_code != 200:
                print(f"[{c.sequence}] ERROR {resp.status_code}: {resp.text[:80]}")
                continue
            hits = resp.json()
            print(f"[{c.sequence}] \\"{preview}\\"")
            for h in hits:
                print(f"        dist={h['distance']:.4f}  {h['id']}  {h.get('name', '')[:60]}")
            print()
"""))

    cells.append(code("""\
# Bilingual pair test
# Requires at least one framework loaded in the graph.
# Top-3 overlap >= 2/3 for each pair indicates cross-lingual embedding is working.

BILINGUAL_PAIRS = [
    ("access control", "Zugangssteuerung"),
    ("data retention", "Datenspeicherung"),
    ("incident response", "Vorfallreaktion"),
]

with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:
    print(f"{'EN query':<30} {'DE query':<30} overlap/3  pass?")
    print("-" * 82)
    for en_q, de_q in BILINGUAL_PAIRS:
        en_resp = client.post("/knowledge/search/controls", json={"query": en_q, "limit": 3})
        de_resp = client.post("/knowledge/search/controls", json={"query": de_q, "limit": 3})
        en_hits = {h["id"] for h in en_resp.json()} if en_resp.status_code == 200 else set()
        de_hits = {h["id"] for h in de_resp.json()} if de_resp.status_code == 200 else set()
        overlap = len(en_hits & de_hits)
        passed = overlap >= 2
        tick = chr(10003)
        cross = chr(10007)
        print(f"{en_q:<30} {de_q:<30} {overlap}/3        {tick if passed else cross}")
"""))

    # -----------------------------------------------------------------------
    # Cell Group 5 — Upsert
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 5 — Upsert\n\n"
        "Creates the Document node and posts all chunks to the graph. "
        "Idempotent — safe to re-run (409 = already existed, shown as `exists`)."
    ))

    cells.append(code("""\
import uuid

_chunk_ids: list[str | None] = []

with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:
    resp = client.post("/knowledge/documents", json={
        "id": DOC_ID, "title": DOC_TITLE, "doc_type": DOC_TYPE
    })
    doc_status = "created" if resp.status_code == 200 else ("exists" if resp.status_code == 409 else f"ERROR {resp.status_code}")
    print(f"Document {DOC_ID}: {doc_status}\\n")

    prev_chunk_id: str | None = None
    for chunk in chunks:
        chunk_id = str(uuid.uuid4())
        body: dict = {
            "id": chunk_id,
            "doc_id": DOC_ID,
            "text": chunk.text,
            "sequence": chunk.sequence,
        }
        if prev_chunk_id:
            body["prev_chunk_id"] = prev_chunk_id
        resp = client.post("/knowledge/chunks", json=body)
        if resp.status_code in (200, 409):
            _chunk_ids.append(chunk_id)
            status = "created" if resp.status_code == 200 else "exists"
            prev_chunk_id = chunk_id
        else:
            _chunk_ids.append(None)
            status = f"ERROR {resp.status_code}"
            prev_chunk_id = None
        print(f"  [{chunk.sequence:>4}] {len(chunk.text):>5} chars  {status}")

ok_count = sum(1 for c in _chunk_ids if c is not None)
print(f"\\nUpserted: {ok_count}/{len(chunks)} chunks")
"""))

    # -----------------------------------------------------------------------
    # Cell Group 6 — Link Verify
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 6 — Link Verify\n\n"
        "Queries Memgraph directly via Bolt to confirm edge integrity, "
        "then shows SUPPORTS candidates in review mode (no edges created here)."
    ))

    cells.append(code("""\
if _driver is None:
    print("Memgraph not connected — run Setup cell first")
else:
    with _driver.session() as session:
        has_chunk_count = session.run(
            "MATCH (:Document {id: $doc_id})-[:HAS_CHUNK]->(c:Chunk) RETURN count(c) AS n",
            doc_id=DOC_ID,
        ).single()["n"]

        has_next_count = session.run(
            "MATCH (:Document {id: $doc_id})-[:HAS_CHUNK]->(c:Chunk)-[:HAS_NEXT]->() RETURN count(c) AS n",
            doc_id=DOC_ID,
        ).single()["n"]

        orphan_count = session.run(
            "MATCH (c:Chunk {doc_id: $doc_id}) WHERE NOT ()-[:HAS_CHUNK]->(c) RETURN count(c) AS n",
            doc_id=DOC_ID,
        ).single()["n"]

    expected_chunks = sum(1 for c in _chunk_ids if c is not None)
    expected_next = max(0, expected_chunks - 1)
    tick = chr(10003)
    cross = chr(10007)
    print(f"HAS_CHUNK edges : {has_chunk_count} (expected {expected_chunks})  {tick if has_chunk_count == expected_chunks else cross}")
    print(f"HAS_NEXT  edges : {has_next_count} (expected {expected_next})  {tick if has_next_count == expected_next else cross}")
    print(f"Orphaned chunks : {orphan_count}  {tick if orphan_count == 0 else cross}")
"""))

    cells.append(code("""\
# SUPPORTS candidates — review mode, no edges created
_candidates: list[dict] = []

with httpx.Client(base_url=cfg.api_base_url, timeout=60) as client:
    for chunk_id, chunk in zip(_chunk_ids, chunks):
        if chunk_id is None:
            continue
        resp = client.post("/knowledge/search/controls", json={"query": chunk.text, "limit": 3})
        if resp.status_code != 200:
            continue
        for hit in resp.json():
            if hit["distance"] < cfg.ingest_auto_supports_threshold:
                _candidates.append({
                    "chunk_id": chunk_id,
                    "chunk_preview": chunk.text[:60].replace("\\n", " "),
                    "control_id": hit["id"],
                    "control_name": hit.get("name", ""),
                    "confidence": round(1.0 - hit["distance"], 4),
                })

print(f"SUPPORTS candidates: {len(_candidates)}")
if _candidates:
    print(f"{'chunk_id'[:8]:<10} {'chunk preview':<62} {'control_id':<36} conf")
    print("-" * 120)
    for c in _candidates:
        print(f"{c['chunk_id'][:8]:<10} {c['chunk_preview']:<62} {c['control_id']:<36} {c['confidence']:.4f}")
print("\\nReview mode: no edges created. Run Cell Group 7 to commit.")
"""))

    # -----------------------------------------------------------------------
    # Cell Group 7 — SUPPORTS Edge Creation (explicit, optional)
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 7 — SUPPORTS Edge Creation\n\n"
        "⚠️ **Run this cell only when you are happy with the candidates above.**\n\n"
        "Creates `SUPPORTS` edges with `status=auto-inferred`. "
        "These can be reviewed and confirmed/rejected via the traceability API."
    ))

    cells.append(code("""\
if not _candidates:
    print("No candidates — run Cell Group 6 first")
else:
    created = 0
    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:
        for c in _candidates:
            resp = client.post("/knowledge/chunks/supports", json={
                "chunk_id": c["chunk_id"],
                "control_id": c["control_id"],
                "confidence": c["confidence"],
                "status": "auto-inferred",
            })
            tick = chr(10003)
            cross = chr(10007)
            if resp.status_code == 200:
                created += 1
                print(f"  [{tick}] {c['chunk_id'][:8]} -> {c['control_id']}")
            else:
                print(f"  [{cross} {resp.status_code}] {c['chunk_id'][:8]} -> {c['control_id']}")
    print(f"\\nCreated {created}/{len(_candidates)} SUPPORTS edges (status=auto-inferred)")
    print("View in Memgraph Lab: http://localhost:3000")
"""))

    # -----------------------------------------------------------------------
    # Write notebook
    # -----------------------------------------------------------------------
    nb.cells = cells
    out = PROJECT_ROOT / "notebooks" / "ingest_pipeline_inspector.ipynb"
    out.parent.mkdir(exist_ok=True)
    nbformat.write(nb, out)
    print(f"Written: {out}")


if __name__ == "__main__":
    build()
