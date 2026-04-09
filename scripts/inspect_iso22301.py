#!/usr/bin/env python3
"""inspect_iso22301.py — Structure-aware extractor for ISO 22301:2019.

Produces a YAML file with one entry per normative clause, plus child entries
for each normative sub-statement (list items), ready for human review before
loading into the knowledge graph.

Usage:
    python3 -m scripts.inspect_iso22301 <pdf_path> [--out <output.yaml>]

Key differences from ISO 27005:
  - Framework prefix: iso-22301-2019
  - 30 pages total. Normative clauses 4-10 span roughly pages 8-25 (0-indexed ~7-24).
  - Skip: Foreword, Introduction (pages 0-6), Annex (informative only), Bibliography.
  - No normative Annex — Annex A is informative. Stop at first Annex heading.
  - Clause 3 (Terms and definitions) is skipped like ISO 27005.
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

CLAUSE_RE = re.compile(r'^(\d+(?:\.\d+)*)\s{1,3}([A-Z][^\n]{2,})$')

# List item starters — these begin normative sub-statements
LIST_ITEM_RE = re.compile(
    r'^('
    r'[a-z]\)\s'     # a) b) c)
    r'|\d+\)\s'      # 1) 2) 3)
    r'|—\s'         # em-dash bullet
    r'|[-•·]\s'      # other bullets
    r')'
)

# NOTE lines (informative, not normative)
NOTE_RE = re.compile(r'^NOTE\s*\d*\s')

# Extract the label prefix from a list item: "a) text" → ("a)", "text")
LIST_LABEL_RE = re.compile(
    r'^([a-z]\)|\d+\)|—|[-•·])\s+(.*)',
    re.DOTALL,
)

# ISO licence watermark detection
_WATERMARK_TOKEN_RE = re.compile(r'[`]|(?<=[a-zA-Z]),(?=[a-zA-Z])')

# Skip patterns
SKIP_HEADERS = {
    'ISO 22301:2019(E)',
    'INTERNATIONAL STANDARD ISO 22301:2019(E)',
}
SKIP_RE = re.compile(
    r'^(TTaabbllee|Table |Figure |©|ICS \d|Price based|Bibliography|Contents|Foreword|'
    r'Reference number|COPYRIGHT|All rights reserved|ISO copyright|CP 401|CH-\d|Phone:|Email:|'
    r'Website:|Published in|\.{4,})'
)

# Clauses to skip — Terms & Definitions (clause 3) are definitions, not obligations
SKIP_CLAUSE_ROOTS = {'1', '2', '3'}

# Annex heading — signals start of informative annex (stop normative extraction).
ANNEX_RE = re.compile(r'^Annex\s+[A-Z](\s*\(|$)')


# ---------------------------------------------------------------------------
# Text cleaning  (identical pipeline to inspect_iso27005.py)
# ---------------------------------------------------------------------------

def _clean_token(token: str) -> str:
    """Strip ISO licence watermark from a single PDF word token."""
    if not _WATERMARK_TOKEN_RE.search(token):
        return token
    token = re.sub(r'[^a-zA-Z0-9()\'"  ;:.!?/-]', '', token)
    token = re.sub(r'-{2,}', '', token)
    token = re.sub(r'(?<=[a-zA-Z])-(?=[a-zA-Z])', '', token)
    return token


def _clean(text: str) -> str:
    """Normalise pdfplumber artefacts from a reconstructed line of text."""
    tokens = text.split()
    tokens = [_clean_token(t) for t in tokens]
    text = ' '.join(t for t in tokens if t)
    text = re.sub(r'-\s+', '', text)                           # soft-hyphen wraps
    text = re.sub(r'(?<=[A-Z])\s(?=[a-z]{2,})', '', text)     # space-in-word artefact
    text = re.sub(r'\[\d+\]', '', text)                        # superscript refs [1]
    text = re.sub(r'\s+\d{1,2}$', '', text)                    # trailing page numbers
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def _is_skip(line: str) -> bool:
    if re.match(r'^\d{1,2}$', line):
        return True
    return line in SKIP_HEADERS or bool(SKIP_RE.match(line))


def _is_list_item(text: str) -> bool:
    return bool(LIST_ITEM_RE.match(text.strip()))


def _is_note(text: str) -> bool:
    return bool(NOTE_RE.match(text.strip()))


# ---------------------------------------------------------------------------
# Body text and statement decomposition  (shared with inspect_iso27005.py)
# ---------------------------------------------------------------------------

def _join_body(logical_lines: list[str]) -> str:
    """Assemble clause body text: list items on own lines, prose joined with spaces."""
    parts: list[str] = []
    current: list[str] = []

    def _flush() -> None:
        if current:
            parts.append(' '.join(current))
            current.clear()

    for line in logical_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_list_item(stripped) or _is_note(stripped):
            _flush()
            current.append(stripped)
        else:
            current.append(stripped)

    _flush()
    return '\n'.join(parts)


class _Block:
    def __init__(self, preamble: str):
        self.preamble = preamble
        self.items: list[dict] = []

    def add_item(self, label: str, text_parts: list[str]) -> None:
        self.items.append({'label': label, 'text': ' '.join(text_parts)})


def _parse_blocks(logical_lines: list[str]) -> list[_Block]:
    """Parse logical lines into one or more preamble→list blocks."""
    blocks: list[_Block] = []
    current_block = _Block('')
    preamble_parts: list[str] = []
    current_item_label: str | None = None
    current_item_parts: list[str] = []
    in_list = False
    in_note = False

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
        if _is_note(stripped):
            in_note = True
            continue
        if in_note:
            if LIST_LABEL_RE.match(stripped):
                in_note = False
            else:
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
            is_continuation = (
                current_item_label is not None
                and (
                    stripped[0].islower()
                    or stripped.startswith('processes')
                    or not stripped[0].isupper()
                )
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
    text = re.sub(r'[;,]\s*and\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[;,]\s*or\s*$', '', text, flags=re.IGNORECASE)
    text = text.rstrip(';').rstrip(',').rstrip()
    return text


def _fuse_statement(preamble: str, item_text: str) -> str:
    """Combine preamble + item text into a complete normative sentence."""
    item_text = _clean_item_text(item_text)
    item_text_clean = item_text.rstrip(':').rstrip()
    p = preamble.rstrip()
    if not p:
        body = item_text_clean
        if body and body[0].islower():
            body = body[0].upper() + body[1:]
        return body.rstrip('.') + '.'
    if p.endswith(':'):
        stem = p[:-1].rstrip()
        body = item_text_clean
        if body and body[0].isupper():
            body = body[0].lower() + body[1:]
        return f"{stem} {body}.".rstrip('..') + '.'
    else:
        body = item_text_clean
        if body and body[0].islower():
            body = body[0].upper() + body[1:]
        return (f"{p} {body}").rstrip('.') + '.'


_DASH_LABEL_RE = re.compile(r'^(—|[-•·])$')
_ALPHA_LABEL_RE = re.compile(r'^[a-z]\)$')
_NUMERIC_LABEL_RE = re.compile(r'^\d+\)$')


def _items_to_statements(items: list[dict], preamble: str, id_prefix: str) -> list[dict]:
    statements: list[dict] = []
    dash_counter = 0
    i = 0

    while i < len(items):
        item = items[i]
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

        _SUB_LIST_ENDINGS = (':', 'include', ' to', ' by', ' for', 'how to')
        child_items = []
        item_text_stripped = item_text.rstrip()
        if any(item_text_stripped.endswith(e) for e in _SUB_LIST_ENDINGS):
            j = i + 1
            while j < len(items) and (
                _DASH_LABEL_RE.match(items[j]['label'])
                or _NUMERIC_LABEL_RE.match(items[j]['label'])
            ):
                child_items.append(items[j])
                j += 1
            if child_items:
                i = j
            else:
                i += 1
        else:
            i += 1

        fused_body = _fuse_statement(preamble, item_text)
        stmt: dict = {'id': stmt_id, 'label': label, 'body': fused_body, 'notes': ''}

        if child_items:
            child_preamble = fused_body.rstrip('.')
            child_stmts = []
            child_dash_counter = 0
            for ci in child_items:
                cl = ci['label']
                if _NUMERIC_LABEL_RE.match(cl):
                    cslug = cl[:-1]
                elif _ALPHA_LABEL_RE.match(cl):
                    cslug = cl[0]
                else:
                    child_dash_counter += 1
                    cslug = f"stmt-{child_dash_counter}"
                child_id = f"{stmt_id}.{cslug}"
                child_body = _fuse_statement(child_preamble + ':', ci['text'])
                child_stmts.append({'id': child_id, 'label': cl, 'body': child_body, 'notes': ''})
            stmt['statements'] = child_stmts

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
        block_body = block_body[0].upper() + block_body[1:] if block_body else ''
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
# Extraction — normative clauses (4 onwards, stop at Annex)
# ---------------------------------------------------------------------------

def extract_clauses(pdf_path: str) -> list[dict]:
    """Extract normative clauses 4-10 from ISO 22301:2019.

    - Skips clauses 1, 2, 3 (scope/refs/terms — not normative obligations).
    - Stops at the first Annex heading (informative, not normative).
    - Pages: starts at page 8 (0-indexed 7), ISO 22301 has 30 pages.
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
        for page in pdf.pages[7:]:   # start at page 8 (0-indexed 7)
            if stop:
                break
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            for line_words in words_to_lines(words):
                raw = line_text(line_words)
                line = _clean(raw)
                if not line or _is_skip(line):
                    continue

                # Stop at Annex
                if ANNEX_RE.match(line):
                    stop = True
                    break

                m = CLAUSE_RE.match(line)
                if m:
                    clause_id = m.group(1)
                    root = clause_id.split('.')[0]

                    # Skip terms/definitions/scope/refs (clauses 1-3)
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
                        'suggested_control_id': f'iso-22301-2019.{clause_id}',
                        'notes': '',
                    }
                    logical_lines = []
                elif current is not None:
                    logical_lines.append(line)

    _flush()
    return entries


# ---------------------------------------------------------------------------
# Preserve manual corrections
# ---------------------------------------------------------------------------

def _load_preserved_text(out_path: Path) -> dict[str, str]:
    """Return {id: text} for all entries with non-empty text in the existing YAML."""
    if not out_path.exists():
        return {}
    with open(out_path, encoding='utf-8') as f:
        existing = yaml.safe_load(f) or []
    return {e['id']: e['text'] for e in existing if e.get('text')}


def _merge_preserved(entries: list[dict], preserved: dict[str, str]) -> list[dict]:
    for e in entries:
        if e['id'] in preserved:
            e['text'] = preserved[e['id']]
    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('pdf_path', help='Path to ISO 22301:2019 PDF')
    parser.add_argument(
        '--out',
        default='scripts/iso22301_inspection.yaml',
        help='Output YAML file (default: scripts/iso22301_inspection.yaml)',
    )
    parser.add_argument(
        '--no-preserve',
        action='store_true',
        help='Overwrite existing YAML without preserving manual corrections',
    )
    args = parser.parse_args()

    out_path = Path(args.out)

    preserved: dict[str, str] = {}
    if not args.no_preserve:
        preserved = _load_preserved_text(out_path)
        if preserved:
            print(f'  Preserving {len(preserved)} manually-corrected entries from existing YAML')

    pdf_path = args.pdf_path
    print(f'Extracting clauses from {pdf_path} ...')
    entries = extract_clauses(pdf_path)
    print(f'  Clauses found: {len(entries)}')

    if preserved:
        entries = _merge_preserved(entries, preserved)

    def _count_stmts(es):
        n = 0
        for e in es:
            for s in e.get('statements', []):
                n += 1
                n += _count_stmts(s.get('statements', []))
        return n

    total_stmts = _count_stmts(entries)
    print(f'  Normative statements extracted: {total_stmts}')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(entries, f, allow_unicode=True, sort_keys=False, width=120)

    empties = [e['id'] for e in entries if not e.get('text')]
    if empties:
        print(f'\n  Warning: Clauses with empty text (manual review needed): {empties}')

    print(f'\nWritten: {out_path}')
    print('Review the YAML, then load with scripts/load_iso22301_chunks.py')


if __name__ == '__main__':
    main()
