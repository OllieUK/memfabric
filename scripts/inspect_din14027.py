#!/usr/bin/env python3
"""inspect_din14027.py — Extractor for DIN SPEC 14027:2026-04 (Corporate Security).

German-language standard. Extracts normative clauses 1–20 (pages 12–45, 0-indexed).
Annex A (tabular requirements matrix) is skipped — too complex for line extraction.

Usage:
    python3 -m scripts.inspect_din14027 <pdf_path> [--out <output.yaml>]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pdfplumber
import yaml

try:
    from pdf_utils import words_to_lines, line_text
except ImportError:
    from scripts.pdf_utils import words_to_lines, line_text

# ---------------------------------------------------------------------------
# Heading patterns
# ---------------------------------------------------------------------------

# German headings can start with any character (not necessarily uppercase).
# Permissive: number(s), whitespace, then 3+ chars of heading text.
CLAUSE_RE = re.compile(r'^(\d+(?:\.\d+)*)\s{1,3}(.{3,})$')

# List item starters — em-dash (U+2014) and alpha/numeric lettered lists
LIST_ITEM_RE = re.compile(
    r'^('
    r'[a-z]\)\s'     # a) b) c)
    r'|\d+\)\s'      # 1) 2) 3)
    r'|—\s'          # em-dash bullet (U+2014)
    r'|[-•·]\s'      # other bullets
    r')'
)

LIST_LABEL_RE = re.compile(
    r'^([a-z]\)|\d+\)|—|[-•·])\s+(.*)',
    re.DOTALL,
)

# Annex heading — signals boundary (Anhang or Annex)
ANNEX_RE = re.compile(r'^(Anhang|Annex)\s+[A-Z]')

# Page number lines — standalone integers
PAGE_NUMBER_RE = re.compile(r'^\d{1,3}$')

# Skip clause roots — skip clauses 1, 2, 3 (scope, references, terms)
SKIP_CLAUSE_ROOTS = {'1', '2', '3'}

# Known header/footer patterns to discard
SKIP_RE = re.compile(
    r'^(DIN SPEC|©|Schutzrecht|Tabelle |Bild |Figure |Table |'
    r'\.{4,}|ICS |Preis|Gesamtumfang|Normteil|'
    r'Inhalt|Vorwort|Einleitung)'
)

# Watermark threshold: discard words with x0 < 30
WATERMARK_X0_THRESHOLD = 30.0

# Header column threshold: words far to the right or left that are page headers
# Recto header x0 ≈ 424, verso header x0 ≈ 41 — but content starts at ~39.7 on verso
# We detect headers by checking if first word on line is in a known set OR
# if the line is short (1-2 words) and looks like a running header
HEADER_STRINGS = {
    'DIN SPEC 14027:2026-04',
    'DIN SPEC 14027',
}


def _line_min_x0(line_words: list[dict]) -> float:
    return min(w['x0'] for w in line_words)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------

_CID_RE = re.compile(r'\(cid:\d+\)')


def _clean(text: str) -> str:
    text = _CID_RE.sub('', text)               # remove (cid:NNN) encoding artifacts
    text = re.sub(r'(\w)-\s+(\w)', r'\1\2', text)  # soft-hyphen wraps mid-word
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _is_skip(line: str) -> bool:
    if PAGE_NUMBER_RE.match(line):
        return True
    if line in HEADER_STRINGS:
        return True
    if SKIP_RE.match(line):
        return True
    return False


def _is_list_item(text: str) -> bool:
    return bool(LIST_ITEM_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Body text assembly
# ---------------------------------------------------------------------------

def _join_body(logical_lines: list[str]) -> str:
    parts: list[str] = []
    current: list[str] = []

    def _flush() -> None:
        if current:
            # Join lines, merging hyphenated line endings (e.g. "Organisati-\nonswerte")
            joined = ''
            for i, chunk in enumerate(current):
                if i == 0:
                    joined = chunk
                elif joined.endswith('-'):
                    joined = joined[:-1] + chunk
                else:
                    joined = joined + ' ' + chunk
            parts.append(joined)
            current.clear()

    for line in logical_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_list_item(stripped):
            _flush()
            current.append(stripped)
        else:
            current.append(stripped)

    _flush()
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Statement decomposition (list items → normative statements)
# ---------------------------------------------------------------------------

class _Block:
    def __init__(self, preamble: str):
        self.preamble = preamble
        self.items: list[dict] = []

    def add_item(self, label: str, text_parts: list[str]) -> None:
        self.items.append({'label': label, 'text': ' '.join(text_parts)})


def _parse_blocks(logical_lines: list[str]) -> list[_Block]:
    blocks: list[_Block] = []
    current_block = _Block('')
    preamble_parts: list[str] = []
    current_item_label: str | None = None
    current_item_parts: list[str] = []
    in_list = False

    def _flush_item() -> None:
        if current_item_label is not None:
            current_block.add_item(current_item_label, current_item_parts)

    def _flush_block() -> None:
        _flush_item()
        current_block.preamble = ' '.join(preamble_parts)
        if current_block.items:
            blocks.append(current_block)

    for line in logical_lines:
        stripped = line.strip()
        if not stripped:
            continue

        m = LIST_LABEL_RE.match(stripped)
        if m:
            if not in_list:
                in_list = True
            _flush_item()
            current_item_label = m.group(1)
            rest = m.group(2).strip()
            current_item_parts = [rest] if rest else []
        elif in_list:
            # continuation of current item if it starts with lowercase or punctuation
            is_continuation = (
                current_item_label is not None
                and stripped
                and not stripped[0].isupper()
            )
            if is_continuation:
                current_item_parts.append(stripped)
            else:
                _flush_block()
                current_block = _Block('')
                preamble_parts = [stripped]
                current_item_label = None
                current_item_parts = []
                in_list = False
        else:
            preamble_parts.append(stripped)

    _flush_block()
    return blocks


def _clean_item_text(text: str) -> str:
    text = re.sub(r'[;,]\s*und\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[;,]\s*oder\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[;,]\s*and\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[;,]\s*or\s*$', '', text, flags=re.IGNORECASE)
    text = text.rstrip(';').rstrip(',').rstrip()
    return text


def _fuse_statement(preamble: str, item_text: str) -> str:
    item_text = _clean_item_text(item_text)
    item_text_clean = item_text.rstrip(':').rstrip()
    p = preamble.rstrip()
    if not p:
        return item_text_clean.rstrip('.') + '.'
    if p.endswith(':'):
        stem = p[:-1].rstrip()
        body = item_text_clean
        return f"{stem} {body}.".rstrip('..') + '.'
    else:
        return (f"{p} {item_text_clean}").rstrip('.') + '.'


_DASH_LABEL_RE = re.compile(r'^(—|[-•·])$')
_ALPHA_LABEL_RE = re.compile(r'^[a-z]\)$')
_NUMERIC_LABEL_RE = re.compile(r'^\d+\)$')


def _items_to_statements(items: list[dict], preamble: str, id_prefix: str) -> list[dict]:
    statements: list[dict] = []
    dash_counter = 0

    for item in items:
        label = item['label']
        item_text = item['text']

        if _ALPHA_LABEL_RE.match(label):
            slug = label[0]
        elif _NUMERIC_LABEL_RE.match(label):
            slug = label[:-1]
        else:
            dash_counter += 1
            slug = f"stmt-{dash_counter}"

        stmt_id = f"{id_prefix}.{slug}"
        fused_body = _fuse_statement(preamble, item_text)
        stmt: dict = {'id': stmt_id, 'label': label, 'body': fused_body, 'notes': ''}
        statements.append(stmt)

    return statements


def _make_statements(clause_id: str, logical_lines: list[str], id_prefix: str) -> list[dict]:
    blocks = _parse_blocks(logical_lines)
    if not blocks:
        return []

    if len(blocks) == 1:
        block = blocks[0]
        return _items_to_statements(block.items, block.preamble, id_prefix)

    statements: list[dict] = []
    for bi, block in enumerate(blocks, start=1):
        block_id = f"{id_prefix}.block-{bi}"
        block_body = block.preamble.rstrip(':').rstrip() + '.'
        stmt: dict = {
            'id': block_id,
            'label': f'block-{bi}',
            'body': block_body,
            'notes': '',
        }
        child_stmts = _items_to_statements(block.items, block.preamble, block_id)
        if child_stmts:
            stmt['statements'] = child_stmts
        statements.append(stmt)

    return statements


# ---------------------------------------------------------------------------
# Page type detection (recto vs verso)
# ---------------------------------------------------------------------------

def _detect_page_type(words: list[dict]) -> str:
    """Detect recto or verso based on first meaningful word x0 position."""
    for w in words:
        if w['x0'] >= WATERMARK_X0_THRESHOLD:
            return 'verso' if w['x0'] < 55 else 'recto'
    return 'recto'


def _filter_words(words: list[dict]) -> list[dict]:
    """Remove watermark noise (x0 < 30)."""
    return [w for w in words if w['x0'] >= WATERMARK_X0_THRESHOLD]


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

# Page range: pages 12–45 (0-indexed), normative body clauses
PAGE_START = 12
PAGE_END = 45  # inclusive


def extract_clauses(pdf_path: str) -> list[dict]:
    """Extract normative clauses from DIN SPEC 14027:2026-04.

    - Skips clauses 1, 2, 3 (scope/refs/terms).
    - Stops at Annex A (Anhang A) boundary.
    - Pages: 12–45 (0-indexed).
    """
    entries: list[dict] = []
    current: dict | None = None
    logical_lines: list[str] = []
    stop = False

    def _flush() -> None:
        if current is not None:
            text = _join_body(logical_lines)
            current['text'] = text
            stmts = _make_statements(current['id'], logical_lines, current['suggested_control_id'])
            if stmts:
                current['statements'] = stmts
            entries.append(current)

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[PAGE_START:PAGE_END + 1]
        for page in pages:
            if stop:
                break
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            words = _filter_words(words)
            if not words:
                continue

            for line_words in words_to_lines(words):
                if stop:
                    break
                raw = line_text(line_words)
                line = _clean(raw)
                if not line or _is_skip(line):
                    continue

                # Stop at Annex / Anhang
                if ANNEX_RE.match(line):
                    stop = True
                    break

                m = CLAUSE_RE.match(line)
                if m:
                    clause_id = m.group(1)
                    root = clause_id.split('.')[0]

                    # Skip scope/references/terms (clauses 1–3)
                    if root in SKIP_CLAUSE_ROOTS:
                        if current is not None:
                            _flush()
                            current = None
                            logical_lines = []
                        continue

                    _flush()
                    current = {
                        'id': clause_id,
                        'heading': _clean(m.group(2)),
                        'type': 'clause',
                        'suggested_control_id': f'din-spec-14027-2026.{clause_id}',
                        'notes': '',
                    }
                    logical_lines = []
                elif current is not None:
                    logical_lines.append(line)

    _flush()
    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('pdf_path', help='Path to DIN SPEC 14027:2026-04 PDF')
    parser.add_argument(
        '--out',
        default='scripts/din14027_inspection.yaml',
        help='Output YAML file (default: scripts/din14027_inspection.yaml)',
    )
    args = parser.parse_args()

    out_path = Path(args.out)

    pdf_path = args.pdf_path
    print(f'Extracting clauses from {pdf_path} ...')
    entries = extract_clauses(pdf_path)
    print(f'  Clauses found: {len(entries)}')

    def _count_stmts(es: list) -> int:
        n = 0
        for e in es:
            for s in e.get('statements', []):
                n += 1
                n += _count_stmts([s])
        return n

    total_stmts = _count_stmts(entries)
    print(f'  Normative statements extracted: {total_stmts}')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(entries, f, allow_unicode=True, sort_keys=False, width=120)

    empties = [e['id'] for e in entries if not e.get('text')]
    if empties:
        print(f'\n  Clauses with empty text (manual review needed): {empties}')

    print(f'\nWritten: {out_path}')


if __name__ == '__main__':
    main()
