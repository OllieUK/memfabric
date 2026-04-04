# Ingest Pipeline Inspector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Jupyter notebook that lets you inspect each stage of the PDF → knowledge graph ingest pipeline interactively, including a multilingual embedding quality test.

**Architecture:** A single notebook (`notebooks/ingest_pipeline_inspector.ipynb`) built programmatically via a Python script using `nbformat`, so it is version-control-friendly and opens cleanly in JupyterLab. It imports directly from `scripts/chunkers.py` (no subprocess) and calls the live FastAPI service via `httpx` for embedding and graph stages. Graph verification uses the Bolt driver directly (same pattern as `tests/conftest.py`).

**Tech Stack:** Python 3.11+, `nbformat`, `jupyterlab`, `langdetect`, `pdfplumber` (already installed), `httpx` (already installed), `neo4j` Bolt driver (already installed), `pydantic-settings` (already installed).

**Branch:** `feature/ingest-inspector` off `master`. Create it before starting Task 1:
```bash
git checkout master && git pull && git checkout -b feature/ingest-inspector
```

**BACKLOG note:** WP-070–076 are complete and merged (commit `d9b78d0`). The BACKLOG.md entries for those WPs are a bookkeeping gap — update them to Completed as part of Task 9.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `requirements-dev.txt` | **Create** | Dev-only deps: `jupyterlab`, `langdetect`, `nbformat` |
| `tests/fixtures/sample_norm_en_de.md` | **Create** | Bilingual synthetic fixture for embedding quality test |
| `scripts/build_inspector_notebook.py` | **Create** | Generates `notebooks/ingest_pipeline_inspector.ipynb` |
| `notebooks/ingest_pipeline_inspector.ipynb` | **Generated** | The actual notebook (re-generate any time via the build script) |
| `notebooks/.gitignore` | **Create** | Ignore `*.ipynb_checkpoints/` |

---

## Task 1: Dev requirements file

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
# Development-only dependencies — not required by the running service
jupyterlab>=4.0.0,<5
nbformat>=5.9.0,<6
langdetect>=1.0.9,<2
```

- [ ] **Step 2: Install**

```bash
pip install -r requirements-dev.txt
```

Expected: installs without conflicts. Verify with:

```bash
python -c "import jupyterlab, nbformat, langdetect; print('ok')"
```

Expected output: `ok`

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "chore: add dev requirements for notebook inspector"
```

---

## Task 2: Synthetic bilingual fixture

**Files:**
- Create: `tests/fixtures/sample_norm_en_de.md`

- [ ] **Step 1: Create the fixture directory and file**

```bash
mkdir -p tests/fixtures
```

Create `tests/fixtures/sample_norm_en_de.md` with this exact content:

```markdown
## Access Control Policy

Users shall be granted access to information and information processing facilities only after authorisation. Access rights shall be reviewed at regular intervals and updated when roles change or employment ends. Privileged access rights shall be allocated and used in accordance with the access control policy.

## Zugangssteuerung

Benutzern soll der Zugang zu Informationen und informationsverarbeitenden Einrichtungen nur nach Genehmigung gewährt werden. Zugriffsrechte sind regelmäßig zu überprüfen und zu aktualisieren, wenn sich Rollen ändern oder das Arbeitsverhältnis endet. Privilegierte Zugriffsrechte sollen gemäß der Zugangssteuerungsrichtlinie zugewiesen und genutzt werden.

## Data Retention Requirements

Personal data shall not be retained for longer than is necessary for the purpose for which it was collected. Retention periods shall be defined, documented, and reviewed annually. Data that has exceeded its retention period shall be securely destroyed or anonymised.

## Datenspeicherungsanforderungen

Personenbezogene Daten dürfen nicht länger aufbewahrt werden, als es für den Zweck, für den sie erhoben wurden, erforderlich ist. Aufbewahrungsfristen sind zu definieren, zu dokumentieren und jährlich zu überprüfen. Daten, deren Aufbewahrungsfrist überschritten ist, sind sicher zu vernichten oder zu anonymisieren.

## Incident Response and Reporting

Information security events shall be reported through appropriate management channels as quickly as possible. All employees and contractors shall be required to note and report any observed or suspected information security weaknesses. Response procedures shall be tested regularly to ensure effectiveness.
```

- [ ] **Step 2: Verify chunker works on it**

```bash
python - <<'EOF'
import sys
sys.path.insert(0, '.')
from scripts.chunkers import chunk_markdown
text = open('tests/fixtures/sample_norm_en_de.md').read()
chunks = chunk_markdown(text)
print(f"Chunk count: {len(chunks)}")
for c in chunks:
    print(f"  [{c.sequence}] heading={c.heading!r} len={len(c.text)}")
EOF
```

Expected output: 5 chunks, each with a non-empty heading, each >= 200 chars.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/sample_norm_en_de.md
git commit -m "test: add bilingual EN/DE fixture for embedding quality test"
```

---

## Task 3: Notebook build script — Setup cell

**Files:**
- Create: `scripts/build_inspector_notebook.py`
- Create: `notebooks/.gitignore`

The build script creates the notebook programmatically using `nbformat`. Run it once to (re)generate `notebooks/ingest_pipeline_inspector.ipynb`. This is split across Tasks 3–9 — each task adds one cell group and regenerates the notebook to verify it opens.

- [ ] **Step 1: Create `notebooks/.gitignore`**

```
.ipynb_checkpoints/
```

- [ ] **Step 2: Create `scripts/build_inspector_notebook.py` with the Setup cell group**

```python
#!/usr/bin/env python3
"""Generate notebooks/ingest_pipeline_inspector.ipynb.

Run this script any time you want to regenerate the notebook:
    python scripts/build_inspector_notebook.py

The notebook is checked into git so teammates can open it directly.
Re-run this script if you need to update cell content.
"""
from __future__ import annotations

from pathlib import Path

import nbformat

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


def md(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(source)


def code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(source)


# ---------------------------------------------------------------------------
# Cell Group 1 — Setup
# ---------------------------------------------------------------------------
cells.append(md("# Ingest Pipeline Inspector\n\nRun cells top-to-bottom for a first run. "
                "Re-run individual cell groups to re-inspect a specific stage.\n\n"
                "**Prerequisites:** stack running (`docker compose up -d`), "
                "`ENABLE_KNOWLEDGE_LAYER=true` in `.env`."))

cells.append(code("""\
import sys
import os
from pathlib import Path

# Allow imports from the project root
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

# --- Health checks ---
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

print(f"API reachable:              {'✓' if _api_ok else '✗  (start with: docker compose up -d)'}")
print(f"Memgraph reachable:         {'✓' if _graph_ok else '✗  (start with: docker compose up -d)'}")
print(f"ENABLE_KNOWLEDGE_LAYER:     {'✓' if _flag_ok else '✗  (set in .env)'}")
"""))

cells.append(code("""\
# --- User configuration — edit these before running ---
PDF_PATH = PROJECT_ROOT / "path/to/your.pdf"   # ← point at your PDF
DOC_ID   = "my-doc-001"                         # ← unique ID for this document
DOC_TITLE = "My Document Title"
DOC_TYPE  = "standard"                           # policy | procedure | standard | guideline

# Chunking parameters (change and re-run Cell Group 3 to experiment)
CHUNK_SIZE    = cfg.ingest_chunk_size
OVERLAP       = cfg.ingest_chunk_overlap
MIN_CHUNK_CHARS = cfg.ingest_min_chunk_chars

print(f"PDF_PATH : {PDF_PATH}")
print(f"DOC_ID   : {DOC_ID}")
print(f"CHUNK_SIZE={CHUNK_SIZE}  OVERLAP={OVERLAP}  MIN_CHARS={MIN_CHUNK_CHARS}")
"""))

# ---------------------------------------------------------------------------
# Write notebook
# ---------------------------------------------------------------------------
nb.cells = cells
out = PROJECT_ROOT / "notebooks" / "ingest_pipeline_inspector.ipynb"
out.parent.mkdir(exist_ok=True)
nbformat.write(nb, out)
print(f"Written: {out}")


if __name__ == "__main__":
    main()
```

Wait — the script defines cells and writes at module level, so it needs a small fix to call correctly. Replace the last block:

```python
#!/usr/bin/env python3
"""Generate notebooks/ingest_pipeline_inspector.ipynb."""
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

    cells.append(code(
        "import sys\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "PROJECT_ROOT = Path().resolve().parent\n"
        "if str(PROJECT_ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(PROJECT_ROOT))\n"
        "\n"
        "import httpx\n"
        "from neo4j import GraphDatabase\n"
        "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
        "\n"
        "\n"
        "class NotebookSettings(BaseSettings):\n"
        "    api_base_url: str = 'http://localhost:8000'\n"
        "    memgraph_uri: str = 'bolt://localhost:7687'\n"
        "    memgraph_user: str = ''\n"
        "    memgraph_password: str = ''\n"
        "    enable_knowledge_layer: bool = False\n"
        "    ingest_chunk_size: int = 2000\n"
        "    ingest_chunk_overlap: int = 200\n"
        "    ingest_min_chunk_chars: int = 50\n"
        "    ingest_auto_supports_threshold: float = 0.20\n"
        "\n"
        "    model_config = SettingsConfigDict(\n"
        "        env_file=str(PROJECT_ROOT / '.env'), env_file_encoding='utf-8'\n"
        "    )\n"
        "\n"
        "\n"
        "cfg = NotebookSettings()\n"
        "\n"
        "_api_ok = False\n"
        "_graph_ok = False\n"
        "_flag_ok = cfg.enable_knowledge_layer\n"
        "\n"
        "try:\n"
        "    r = httpx.get(f'{cfg.api_base_url}/health', timeout=3)\n"
        "    _api_ok = r.status_code == 200\n"
        "except Exception:\n"
        "    pass\n"
        "\n"
        "try:\n"
        "    _driver = GraphDatabase.driver(\n"
        "        cfg.memgraph_uri,\n"
        "        auth=(cfg.memgraph_user, cfg.memgraph_password) if cfg.memgraph_user else ('', ''),\n"
        "    )\n"
        "    _driver.verify_connectivity()\n"
        "    _graph_ok = True\n"
        "except Exception:\n"
        "    _driver = None\n"
        "\n"
        "print(f'API reachable:          {chr(10003) if _api_ok else chr(10007) + \"  (start: docker compose up -d)\"}')\n"
        "print(f'Memgraph reachable:     {chr(10003) if _graph_ok else chr(10007) + \"  (start: docker compose up -d)\"}')\n"
        "print(f'ENABLE_KNOWLEDGE_LAYER: {chr(10003) if _flag_ok else chr(10007) + \"  (set in .env)\"}')\n"
    ))

    cells.append(code(
        "# --- User configuration — edit these before running ---\n"
        "PDF_PATH      = PROJECT_ROOT / 'path/to/your.pdf'  # ← point at your PDF\n"
        "DOC_ID        = 'my-doc-001'                        # ← unique ID\n"
        "DOC_TITLE     = 'My Document Title'\n"
        "DOC_TYPE      = 'standard'                          # policy|procedure|standard|guideline\n"
        "\n"
        "CHUNK_SIZE      = cfg.ingest_chunk_size\n"
        "OVERLAP         = cfg.ingest_chunk_overlap\n"
        "MIN_CHUNK_CHARS = cfg.ingest_min_chunk_chars\n"
        "\n"
        "print(f'PDF_PATH : {PDF_PATH}')\n"
        "print(f'DOC_ID   : {DOC_ID}')\n"
        "print(f'CHUNK_SIZE={CHUNK_SIZE}  OVERLAP={OVERLAP}  MIN_CHARS={MIN_CHUNK_CHARS}')\n"
    ))

    nb.cells = cells
    out = PROJECT_ROOT / "notebooks" / "ingest_pipeline_inspector.ipynb"
    out.parent.mkdir(exist_ok=True)
    nbformat.write(nb, out)
    print(f"Written: {out}")


if __name__ == "__main__":
    build()
```

- [ ] **Step 3: Run the build script and verify the notebook opens**

```bash
python scripts/build_inspector_notebook.py
```

Expected output: `Written: .../notebooks/ingest_pipeline_inspector.ipynb`

```bash
jupyter nbconvert --to notebook --execute --ExecutePreprocessor.timeout=30 \
  notebooks/ingest_pipeline_inspector.ipynb --output /tmp/test_nb.ipynb 2>&1 | tail -5
```

Expected: completes without `ERROR`. (Health checks will show ✗ if stack is not running — that is fine at this stage.)

- [ ] **Step 4: Commit**

```bash
git add scripts/build_inspector_notebook.py notebooks/ notebooks/.gitignore
git commit -m "feat: notebook build script — setup cell group"
```

---

## Task 4: Cell Group 2 — Load PDF

**Files:**
- Modify: `scripts/build_inspector_notebook.py` (add cells to `build()`)

- [ ] **Step 1: Add the Load PDF cell group inside `build()`, before `nb.cells = cells`**

```python
    # -----------------------------------------------------------------------
    # Cell Group 2 — Load PDF
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 2 — Load PDF\n\n"
        "Inspect the raw PDF before chunking. "
        "Catches garbled text (scanned/image PDFs) before wasting time on later stages."
    ))

    cells.append(code(
        "import pdfplumber\n"
        "from langdetect import detect\n"
        "\n"
        "if not PDF_PATH.exists():\n"
        "    raise FileNotFoundError(f'PDF not found: {PDF_PATH}')\n"
        "\n"
        "page_langs = []\n"
        "total_chars = 0\n"
        "first_500 = ''\n"
        "\n"
        "with pdfplumber.open(PDF_PATH) as pdf:\n"
        "    page_count = len(pdf.pages)\n"
        "    for i, page in enumerate(pdf.pages):\n"
        "        text = page.extract_text() or ''\n"
        "        total_chars += len(text)\n"
        "        if not first_500 and text.strip():\n"
        "            first_500 = text[:500]\n"
        "        try:\n"
        "            lang = detect(text) if len(text) > 50 else 'unknown'\n"
        "        except Exception:\n"
        "            lang = 'unknown'\n"
        "        page_langs.append(lang)\n"
        "\n"
        "from collections import Counter\n"
        "lang_counts = Counter(page_langs)\n"
        "\n"
        "print(f'Pages       : {page_count}')\n"
        "print(f'Total chars : {total_chars:,}')\n"
        "print(f'Languages   : {dict(lang_counts)}')\n"
        "if total_chars < 1000:\n"
        "    print('WARNING: very low character count — this may be a scanned/image PDF')\n"
        "print()\n"
        "print('--- First 500 chars ---')\n"
        "print(first_500)\n"
    ))
```

- [ ] **Step 2: Rebuild and verify**

```bash
python scripts/build_inspector_notebook.py
python - <<'EOF'
import nbformat
nb = nbformat.read("notebooks/ingest_pipeline_inspector.ipynb", as_version=4)
print(f"Cell count: {len(nb.cells)}")
# Expect: 6 cells (3 setup + 1 markdown header + 1 code for load)
# Actually: 3 setup + 1 md + 1 code = 5 cells
assert any("pdfplumber" in c.source for c in nb.cells if c.cell_type == "code"), "missing load cell"
print("ok")
EOF
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add scripts/build_inspector_notebook.py notebooks/ingest_pipeline_inspector.ipynb
git commit -m "feat: notebook — load PDF cell group"
```

---

## Task 5: Cell Group 3 — Chunk

**Files:**
- Modify: `scripts/build_inspector_notebook.py`

- [ ] **Step 1: Add the Chunk cell group inside `build()`, before `nb.cells = cells`**

```python
    # -----------------------------------------------------------------------
    # Cell Group 3 — Chunk
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 3 — Chunk\n\n"
        "Calls `chunk_pdf()` directly. Re-run this cell with different "
        "`CHUNK_SIZE` / `OVERLAP` values (set in Cell Group 1) to tune chunking "
        "without touching the graph."
    ))

    cells.append(code(
        "from scripts.chunkers import chunk_pdf\n"
        "import statistics\n"
        "\n"
        "chunks = chunk_pdf(str(PDF_PATH), CHUNK_SIZE, OVERLAP, MIN_CHUNK_CHARS)\n"
        "lengths = [len(c.text) for c in chunks]\n"
        "\n"
        "print(f'Total chunks : {len(chunks)}')\n"
        "if lengths:\n"
        "    print(f'Chars  min={min(lengths)}  max={max(lengths)}  '\n"
        "          f'mean={statistics.mean(lengths):.0f}  '\n"
        "          f'p50={statistics.median(lengths):.0f}')\n"
        "    sorted_lens = sorted(lengths)\n"
        "    p95_idx = int(0.95 * len(sorted_lens))\n"
        "    print(f'       p95={sorted_lens[p95_idx]}')\n"
        "print()\n"
        "\n"
        "def _preview(chunk, max_chars=300):\n"
        "    t = chunk.text.replace('\\n', ' ')\n"
        "    return t[:max_chars] + ('...' if len(t) > max_chars else '')\n"
        "\n"
        "print('--- First 3 chunks ---')\n"
        "for c in chunks[:3]:\n"
        "    print(f'[{c.sequence}] {len(c.text)} chars: {_preview(c)}')\n"
        "    print()\n"
        "\n"
        "print('--- Last 3 chunks ---')\n"
        "for c in chunks[-3:]:\n"
        "    print(f'[{c.sequence}] {len(c.text)} chars: {_preview(c)}')\n"
        "    print()\n"
    ))
```

- [ ] **Step 2: Rebuild and verify**

```bash
python scripts/build_inspector_notebook.py
python - <<'EOF'
import nbformat
nb = nbformat.read("notebooks/ingest_pipeline_inspector.ipynb", as_version=4)
assert any("chunk_pdf" in c.source for c in nb.cells if c.cell_type == "code"), "missing chunk cell"
print(f"Cell count: {len(nb.cells)} — ok")
EOF
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build_inspector_notebook.py notebooks/ingest_pipeline_inspector.ipynb
git commit -m "feat: notebook — chunk cell group"
```

---

## Task 6: Cell Group 4 — Embedding Preview + Bilingual Test

**Files:**
- Modify: `scripts/build_inspector_notebook.py`

- [ ] **Step 1: Add the Embedding Preview cell group inside `build()`, before `nb.cells = cells`**

```python
    # -----------------------------------------------------------------------
    # Cell Group 4 — Embedding Preview
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 4 — Embedding Preview\n\n"
        "Samples 10 chunks and shows which controls the multilingual model matches them to.\n\n"
        "**Requires:** stack running, at least one framework loaded "
        "(e.g. `python scripts/ingest_framework.py data/frameworks/iso-27001-2022.yaml`).\n\n"
        "Also runs a **bilingual pair test** using the synthetic fixture at "
        "`tests/fixtures/sample_norm_en_de.md` to verify EN/DE cross-lingual quality."
    ))

    cells.append(code(
        "# Embedding preview — 10 evenly-spaced chunks\n"
        "import math\n"
        "\n"
        "if not chunks:\n"
        "    print('No chunks — run Cell Group 3 first')\n"
        "else:\n"
        "    step = max(1, math.floor(len(chunks) / 10))\n"
        "    sample = chunks[::step][:10]\n"
        "\n"
        "    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:\n"
        "        for c in sample:\n"
        "            preview = c.text[:80].replace('\\n', ' ')\n"
        "            resp = client.post(\n"
        "                '/knowledge/search/controls',\n"
        "                json={'query': c.text, 'limit': 3},\n"
        "            )\n"
        "            if resp.status_code != 200:\n"
        "                print(f'[{c.sequence}] ERROR {resp.status_code}')\n"
        "                continue\n"
        "            hits = resp.json()\n"
        "            print(f'[{c.sequence}] \"{preview}\"')\n"
        "            for h in hits:\n"
        "                print(f'        dist={h[\"distance\"]:.4f}  {h[\"id\"]}  {h.get(\"name\",\"\")[:60]}')\n"
        "            print()\n"
    ))

    cells.append(code(
        "# Bilingual pair test — same concept in EN and DE\n"
        "# Loads the synthetic fixture from tests/fixtures/sample_norm_en_de.md\n"
        "# Top-3 overlap >= 2 out of 3 indicates the multilingual model is working\n"
        "\n"
        "BILINGUAL_PAIRS = [\n"
        "    ('access control', 'Zugangssteuerung'),\n"
        "    ('data retention', 'Datenspeicherung'),\n"
        "    ('incident response', 'Vorfallreaktion'),\n"
        "]\n"
        "\n"
        "with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:\n"
        "    print(f'{'EN query':<30} {'DE query':<30} overlap/3  pass?')\n"
        "    print('-' * 80)\n"
        "    for en_q, de_q in BILINGUAL_PAIRS:\n"
        "        en_hits = {h['id'] for h in client.post('/knowledge/search/controls', json={'query': en_q, 'limit': 3}).json()}\n"
        "        de_hits = {h['id'] for h in client.post('/knowledge/search/controls', json={'query': de_q, 'limit': 3}).json()}\n"
        "        overlap = len(en_hits & de_hits)\n"
        "        passed = overlap >= 2\n"
        "        print(f'{en_q:<30} {de_q:<30} {overlap}/3        {chr(10003) if passed else chr(10007)}')\n"
    ))
```

- [ ] **Step 2: Rebuild and verify**

```bash
python scripts/build_inspector_notebook.py
python - <<'EOF'
import nbformat
nb = nbformat.read("notebooks/ingest_pipeline_inspector.ipynb", as_version=4)
assert any("bilingual" in c.source.lower() for c in nb.cells if c.cell_type == "code"), "missing bilingual cell"
print(f"Cell count: {len(nb.cells)} — ok")
EOF
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build_inspector_notebook.py notebooks/ingest_pipeline_inspector.ipynb
git commit -m "feat: notebook — embedding preview and bilingual pair test"
```

---

## Task 7: Cell Groups 5–6 — Upsert + Link Verify

**Files:**
- Modify: `scripts/build_inspector_notebook.py`

- [ ] **Step 1: Add Upsert + Link Verify cell groups inside `build()`, before `nb.cells = cells`**

```python
    # -----------------------------------------------------------------------
    # Cell Group 5 — Upsert
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 5 — Upsert\n\n"
        "Creates the Document node and posts all chunks to the graph. "
        "Idempotent — safe to re-run (409 = already existed, shown as `exists`)."
    ))

    cells.append(code(
        "import uuid\n"
        "\n"
        "_chunk_ids: list[str | None] = []\n"
        "\n"
        "with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:\n"
        "    # Create document node\n"
        "    resp = client.post('/knowledge/documents', json={\n"
        "        'id': DOC_ID, 'title': DOC_TITLE, 'doc_type': DOC_TYPE\n"
        "    })\n"
        "    status = 'created' if resp.status_code == 200 else ('exists' if resp.status_code == 409 else f'ERROR {resp.status_code}')\n"
        "    print(f'Document {DOC_ID}: {status}')\n"
        "    print()\n"
        "\n"
        "    prev_chunk_id: str | None = None\n"
        "    for chunk in chunks:\n"
        "        chunk_id = str(uuid.uuid4())\n"
        "        body: dict = {\n"
        "            'id': chunk_id, 'doc_id': DOC_ID,\n"
        "            'text': chunk.text, 'sequence': chunk.sequence,\n"
        "        }\n"
        "        if prev_chunk_id:\n"
        "            body['prev_chunk_id'] = prev_chunk_id\n"
        "        resp = client.post('/knowledge/chunks', json=body)\n"
        "        if resp.status_code in (200, 409):\n"
        "            _chunk_ids.append(chunk_id)\n"
        "            status = 'created' if resp.status_code == 200 else 'exists'\n"
        "            prev_chunk_id = chunk_id\n"
        "        else:\n"
        "            _chunk_ids.append(None)\n"
        "            status = f'ERROR {resp.status_code}'\n"
        "            prev_chunk_id = None\n"
        "        print(f'  [{chunk.sequence:>4}] {len(chunk.text):>5} chars  {status}')\n"
        "\n"
        "ok_count = sum(1 for c in _chunk_ids if c is not None)\n"
        "print(f'\\nUpserted: {ok_count}/{len(chunks)} chunks')\n"
    ))

    # -----------------------------------------------------------------------
    # Cell Group 6 — Link Verify
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 6 — Link Verify\n\n"
        "Queries Memgraph directly via Bolt to confirm edge integrity, "
        "then shows SUPPORTS candidates (review mode — no edges created here)."
    ))

    cells.append(code(
        "if _driver is None:\n"
        "    print('Memgraph not connected — run Setup cell first')\n"
        "else:\n"
        "    with _driver.session() as session:\n"
        "        has_chunk_count = session.run(\n"
        "            'MATCH (:Document {id: $doc_id})-[:HAS_CHUNK]->(c:Chunk) RETURN count(c) AS n',\n"
        "            doc_id=DOC_ID\n"
        "        ).single()['n']\n"
        "\n"
        "        has_next_count = session.run(\n"
        "            'MATCH (:Document {id: $doc_id})-[:HAS_CHUNK]->(c:Chunk)-[:HAS_NEXT]->() RETURN count(c) AS n',\n"
        "            doc_id=DOC_ID\n"
        "        ).single()['n']\n"
        "\n"
        "        orphan_count = session.run(\n"
        "            'MATCH (c:Chunk {doc_id: $doc_id}) WHERE NOT ()-[:HAS_CHUNK]->(c) RETURN count(c) AS n',\n"
        "            doc_id=DOC_ID\n"
        "        ).single()['n']\n"
        "\n"
        "    expected_chunks = len([c for c in _chunk_ids if c is not None])\n"
        "    hc_ok = has_chunk_count == expected_chunks\n"
        "    hn_ok = has_next_count == max(0, expected_chunks - 1)\n"
        "    orph_ok = orphan_count == 0\n"
        "\n"
        "    print(f'HAS_CHUNK edges : {has_chunk_count} (expected {expected_chunks})  {chr(10003) if hc_ok else chr(10007)}')\n"
        "    print(f'HAS_NEXT  edges : {has_next_count} (expected {max(0, expected_chunks-1)})  {chr(10003) if hn_ok else chr(10007)}')\n"
        "    print(f'Orphaned chunks : {orphan_count}  {chr(10003) if orph_ok else chr(10007)}')\n"
    ))

    cells.append(code(
        "# SUPPORTS candidates — review mode, no edges created\n"
        "candidates: list[dict] = []\n"
        "\n"
        "with httpx.Client(base_url=cfg.api_base_url, timeout=60) as client:\n"
        "    for chunk_id, chunk in zip(_chunk_ids, chunks):\n"
        "        if chunk_id is None:\n"
        "            continue\n"
        "        resp = client.post('/knowledge/search/controls', json={'query': chunk.text, 'limit': 3})\n"
        "        if resp.status_code != 200:\n"
        "            continue\n"
        "        for hit in resp.json():\n"
        "            if hit['distance'] < cfg.ingest_auto_supports_threshold:\n"
        "                candidates.append({\n"
        "                    'chunk_id': chunk_id,\n"
        "                    'chunk_preview': chunk.text[:60].replace('\\n', ' '),\n"
        "                    'control_id': hit['id'],\n"
        "                    'control_name': hit.get('name', ''),\n"
        "                    'confidence': round(1.0 - hit['distance'], 4),\n"
        "                })\n"
        "\n"
        "print(f'SUPPORTS candidates: {len(candidates)}')\n"
        "print(f'{\"chunk_id\"[:8]:<10} {\"chunk preview\":<62} {\"control_id\":<36} conf')\n"
        "print('-' * 120)\n"
        "for c in candidates:\n"
        "    print(f'{c[\"chunk_id\"][:8]:<10} {c[\"chunk_preview\"]:<62} {c[\"control_id\"]:<36} {c[\"confidence\"]:.4f}')\n"
        "print('\\nReview mode: no edges created. Run Cell Group 7 to commit.')\n"
    ))
```

- [ ] **Step 2: Rebuild and verify**

```bash
python scripts/build_inspector_notebook.py
python - <<'EOF'
import nbformat
nb = nbformat.read("notebooks/ingest_pipeline_inspector.ipynb", as_version=4)
assert any("HAS_CHUNK" in c.source for c in nb.cells if c.cell_type == "code"), "missing link verify cell"
print(f"Cell count: {len(nb.cells)} — ok")
EOF
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build_inspector_notebook.py notebooks/ingest_pipeline_inspector.ipynb
git commit -m "feat: notebook — upsert and link verify cell groups"
```

---

## Task 8: Cell Group 7 — SUPPORTS Edge Creation

**Files:**
- Modify: `scripts/build_inspector_notebook.py`

- [ ] **Step 1: Add the SUPPORTS creation cell group inside `build()`, before `nb.cells = cells`**

```python
    # -----------------------------------------------------------------------
    # Cell Group 7 — SUPPORTS Edge Creation (explicit, optional)
    # -----------------------------------------------------------------------
    cells.append(md(
        "## Cell Group 7 — SUPPORTS Edge Creation\n\n"
        "⚠️ **Run this cell only when you are happy with the candidates above.**\n\n"
        "Creates `SUPPORTS` edges with `status=auto-inferred`. "
        "These can be reviewed and confirmed/rejected via the traceability API."
    ))

    cells.append(code(
        "if not candidates:\n"
        "    print('No candidates — run Cell Group 6 first')\n"
        "else:\n"
        "    created = 0\n"
        "    with httpx.Client(base_url=cfg.api_base_url, timeout=30) as client:\n"
        "        for c in candidates:\n"
        "            resp = client.post('/knowledge/chunk/supports', json={\n"
        "                'chunk_id': c['chunk_id'],\n"
        "                'control_id': c['control_id'],\n"
        "                'confidence': c['confidence'],\n"
        "                'status': 'auto-inferred',\n"
        "            })\n"
        "            if resp.status_code == 200:\n"
        "                created += 1\n"
        "                print(f'  [OK] {c[\"chunk_id\"][:8]} -> {c[\"control_id\"]}')\n"
        "            else:\n"
        "                print(f'  [ERR {resp.status_code}] {c[\"chunk_id\"][:8]} -> {c[\"control_id\"]}')\n"
        "    print(f'\\nCreated {created}/{len(candidates)} SUPPORTS edges (status=auto-inferred)')\n"
        "    print('View in Memgraph Lab: http://localhost:3000')\n"
    ))
```

- [ ] **Step 2: Rebuild and verify final notebook**

```bash
python scripts/build_inspector_notebook.py
python - <<'EOF'
import nbformat
nb = nbformat.read("notebooks/ingest_pipeline_inspector.ipynb", as_version=4)
print(f"Total cells: {len(nb.cells)}")
code_cells = [c for c in nb.cells if c.cell_type == "code"]
md_cells   = [c for c in nb.cells if c.cell_type == "markdown"]
print(f"  Code cells     : {len(code_cells)}")
print(f"  Markdown cells : {len(md_cells)}")
# Expected: ~14 code cells, ~8 markdown cells
required = ["pdfplumber", "chunk_pdf", "bilingual", "HAS_CHUNK", "SUPPORTS"]
for kw in required:
    found = any(kw.lower() in c.source.lower() for c in code_cells)
    print(f"  {kw:<20} : {'ok' if found else 'MISSING'}")
EOF
```

Expected: all 5 keywords found.

- [ ] **Step 3: Commit**

```bash
git add scripts/build_inspector_notebook.py notebooks/ingest_pipeline_inspector.ipynb
git commit -m "feat: notebook — SUPPORTS edge creation cell group (complete notebook)"
```

---

## Task 9: Update BACKLOG.md

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 1: Mark WP-070 through WP-076 as Completed**

WP-070–076 are merged (commit `d9b78d0`) but still show as open in BACKLOG.md. Move each of them from the open backlog table into the Completed section. Use this retrospective note for all of them:

```
WP-070–076: Knowledge layer implemented and merged via feature/knowledge-layer (d9b78d0). All tests passing.
```

- [ ] **Step 2: Add the Excel importer WP to the Backlog section**

Find the next available WP number by checking the highest existing `WP-NNN` in BACKLOG.md, then add:

```markdown
| WP-NNN | Excel cross-standard mapping importer | Design a parser for Excel files mapping controls across frameworks (e.g. ISO 27001 ↔ NIST CSF). Format TBD — pending inspection of a real mapping file. | Low | — |
```

- [ ] **Step 3: Commit**

```bash
git add BACKLOG.md
git commit -m "chore: mark WP-070–076 completed in BACKLOG.md, add Excel importer WP"
```

---

## Verification Checklist

Run these after all tasks are complete:

**Without stack:**
```bash
# Chunking is pure Python — no stack needed
python - <<'EOF'
import sys; sys.path.insert(0, '.')
from scripts.chunkers import chunk_markdown
chunks = chunk_markdown(open('tests/fixtures/sample_norm_en_de.md').read())
assert len(chunks) == 5, f"Expected 5 chunks, got {len(chunks)}"
print("Fixture chunking: ok")
EOF
```

**With stack (`docker compose up -d`):**

1. Load the ISO 27001 framework:
   ```bash
   python scripts/ingest_framework.py data/frameworks/iso-27001-2022.yaml
   ```

2. Open JupyterLab and run the notebook:
   ```bash
   jupyter lab notebooks/ingest_pipeline_inspector.ipynb
   ```

3. In Cell Group 1: verify all three health checks show ✓

4. In Cell Group 2: set `PDF_PATH` to your ISO 27001 PDF and run — verify page count and first 500 chars look correct (not garbled)

5. In Cell Group 3: verify chunk count is reasonable (ISO 27001 PDF ~100 pages → expect 100–300 chunks at default settings)

6. In Cell Group 4: verify top-3 controls for access-control chunks include `iso-27001-2022.A.5.15` or similar; bilingual pair test should show ≥ 2/3 overlap for "access control" / "Zugangssteuerung"

7. In Cell Groups 5–6: verify HAS_CHUNK and HAS_NEXT edge counts match chunk count

8. In Cell Group 7 (optional): create SUPPORTS edges and verify in Memgraph Lab at `http://localhost:3000`
