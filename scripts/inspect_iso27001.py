#!/usr/bin/env python3
"""inspect_iso27001.py — Structure-aware extractor for ISO/IEC 27001:2022.

Produces a YAML file with one entry per clause / Annex A control, plus child
entries for each normative sub-statement (list items), ready for human review
before loading into the knowledge graph.

Usage:
    python3 -m scripts.inspect_iso27001 <pdf_path> [--out <output.yaml>]

Output YAML structure:
    - id: "6.1.3"
      heading: "Information security risk treatment"
      type: clause
      text: |
        The organization shall define and apply an information security risk
        treatment process to:
        a) select appropriate information security risk treatment options...
      suggested_control_id: "iso-27001-2022.6.1.3"
      notes: ""
      statements:
        - id: "6.1.3.a"
          label: "a)"
          body: "The organization shall define and apply an information security
            risk treatment process to select appropriate information security
            risk treatment options, taking account of the risk assessment results."
        - id: "6.1.3.b"
          label: "b)"
          body: "The organization shall determine all controls that are necessary
            to implement the information security risk treatment option(s) chosen."
        ...

Extraction approach:
  Uses pdfplumber extract_words() for positional word data rather than
  extract_text(), so that list items (a), b), —) are identified and kept on
  separate lines. Normative sub-statements are fused with the preamble context
  so they are complete, searchable obligations in isolation.
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber
import yaml

# ---------------------------------------------------------------------------
# Heading patterns
# ---------------------------------------------------------------------------

CLAUSE_RE = re.compile(r'^(\d+(?:\.\d+)*)\s{1,3}([A-Z][^\n]{2,})$')
ANNEX_CONTROL_SEP = re.compile(r'^Control\s*$')
ANNEX_CTRL_RE = re.compile(r'^(\d+\.\d+)\s+(.+)$')

# List item starters — these begin normative sub-statements
LIST_ITEM_RE = re.compile(
    r'^('
    r'[a-z]\)\s'     # a) b) c)
    r'|\d+\)\s'      # 1) 2) 3)
    r'|—\s'         # em-dash bullet
    r'|[-•·]\s'      # other bullets
    r')'
)

# NOTE lines (informative, not normative — kept in text but not as statements)
NOTE_RE = re.compile(r'^NOTE\s*\d*\s')

# Extract the label prefix from a list item line: "a) some text" → "a)", "some text"
LIST_LABEL_RE = re.compile(
    r'^('
    r'[a-z]\)'
    r'|\d+\)'
    r'|—'
    r'|[-•·]'
    r')\s+(.*)'
, re.DOTALL)

# ISO licence watermark detection
_WATERMARK_TOKEN_RE = re.compile(r'[`]|(?<=[a-zA-Z]),(?=[a-zA-Z])')

# Skip patterns
SKIP_HEADERS = {
    'ISO/IEC 27001:2022(E)',
    'INTERNATIONAL STANDARD ISO/IEC 27001:2022(E)',
}
SKIP_RE = re.compile(
    r'^(TTaabbllee|Table A\.1|©|ICS \d|Price based|Bibliography|Contents|Foreword|'
    r'Reference number|COPYRIGHT|All rights reserved|ISO copyright|CP 401|CH-\d|Phone:|Email:|'
    r'Website:|Published in|\.{4,})'
)
SECTION_HEADER_RE = re.compile(r'^\d+\s+[A-Z][a-z]+ controls\s*$')


# ---------------------------------------------------------------------------
# Text cleaning
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
# Word-level line reconstruction
# ---------------------------------------------------------------------------

def _words_to_lines(words: list[dict], y_tolerance: float = 3.0) -> list[list[dict]]:
    buckets: dict[float, list[dict]] = defaultdict(list)
    for w in words:
        mid_y = round((w['top'] + w['bottom']) / 2 / y_tolerance) * y_tolerance
        buckets[mid_y].append(w)
    return [sorted(v, key=lambda w: w['x0']) for _, v in sorted(buckets.items())]


def _line_text(line_words: list[dict]) -> str:
    return ' '.join(w['text'] for w in line_words)


# ---------------------------------------------------------------------------
# Body text and statement decomposition
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
    """One preamble→list segment within a clause body."""
    def __init__(self, preamble: str):
        self.preamble = preamble
        self.items: list[dict] = []

    def add_item(self, label: str, text_parts: list[str]) -> None:
        self.items.append({'label': label, 'text': ' '.join(text_parts)})


def _parse_blocks(logical_lines: list[str]) -> list[_Block]:
    """Parse logical lines into one or more preamble→list blocks.

    A clause body may contain multiple sequential blocks, each with its own
    introductory preamble followed by a list. When a prose line appears *after*
    at least one list item has been seen, it resets the preamble for the next block.

    Example (6.1.1):
        Block 1: preamble = "When planning... to:"
                 items = [a), b), c)]
        Block 2: preamble = "The organization shall plan:"
                 items = [d), e)]  where e) has children 1), 2)

    NOTEs are informative and skipped entirely (including their continuations).
    """
    blocks: list[_Block] = []
    current_block = _Block('')
    preamble_parts: list[str] = []
    current_item_label: str | None = None
    current_item_parts: list[str] = []
    in_list = False    # True once we've seen at least one list item in this block
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
            # A non-list line after list items have started.
            # If it looks like a continuation of the current item (starts lowercase,
            # or is clearly a sentence fragment like "processes; and"), absorb it.
            # Otherwise start a new block.
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
    """Remove trailing punctuation fragments from a list item body."""
    # Strip trailing '; and', '; or', '; and', then strip trailing semicolon/comma
    text = re.sub(r'[;,]\s*and\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[;,]\s*or\s*$', '', text, flags=re.IGNORECASE)
    text = text.rstrip(';').rstrip(',').rstrip()
    return text


def _fuse_statement(preamble: str, item_text: str) -> str:
    """Combine preamble + item text into a complete normative sentence.

    If preamble ends with ':' (listing pattern):
        "stem body."  — item_text lowercased to flow naturally from stem.

    If preamble is a standalone sentence (ends with '.'):
        "preamble body." — capitalised separately.

    If no preamble:
        "Body." — capitalised.
    """
    item_text = _clean_item_text(item_text)
    # Strip trailing colon from item text (happens when item itself is a sub-list intro)
    item_text_clean = item_text.rstrip(':').rstrip()
    p = preamble.rstrip()
    if not p:
        body = item_text_clean
        if body and body[0].islower():
            body = body[0].upper() + body[1:]
        return body.rstrip('.') + '.'
    if p.endswith(':'):
        stem = p[:-1].rstrip()
        # Lowercase the first char so it flows as a continuation of the stem
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
    """Convert a flat list of items (with a shared preamble) into statement dicts.

    Items that end with ':' consume following dash/numeric items as children.
    IDs: a)→.a, 1)→.1, —→.stmt-N
    """
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

        # Absorb following child items if this item introduces a sub-list.
        # Triggers: item text ends with ':', 'include', 'to', 'by', 'for', 'how to'
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


def _make_statements(
    clause_id: str,
    logical_lines: list[str],
    id_prefix: str,
    depth: int = 0,
) -> list[dict]:
    """Decompose logical lines into normative statement entries.

    Handles multi-block clauses (e.g. 6.1.1) where multiple preamble→list
    segments appear in sequence. Each block gets its own preamble context.

    When a clause has multiple blocks, the blocks themselves become the top-level
    statements, with their items as children. This matches the ISO structure where
    "When planning... to: a) b) c)" and "The organization shall plan: d) e)" are
    two distinct normative obligations.
    """
    blocks = _parse_blocks(logical_lines)
    if not blocks:
        return []

    if len(blocks) == 1:
        # Simple case: single block, items are top-level statements
        block = blocks[0]
        return _items_to_statements(block.items, block.preamble, id_prefix)

    # Multi-block case: each block becomes a top-level statement (the preamble
    # itself is the obligation), with its items as children
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
# Extraction — normative body (clauses 1–10)
# ---------------------------------------------------------------------------

def extract_clauses(pdf_path: str) -> list[dict]:
    """Extract clauses 1–10 (pages 7–16, 0-indexed 6–15)."""
    entries: list[dict] = []
    current: dict | None = None
    logical_lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            text = _join_body(logical_lines)
            current['text'] = text
            stmts = _make_statements(current['id'], logical_lines, current['suggested_control_id'])
            if stmts:
                current['statements'] = stmts
            entries.append(current)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[6:16]:
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            for line_words in _words_to_lines(words):
                raw = _line_text(line_words)
                line = _clean(raw)
                if not line or _is_skip(line):
                    continue
                m = CLAUSE_RE.match(line)
                if m:
                    _flush()
                    clause_id = m.group(1)
                    current = {
                        'id': clause_id,
                        'heading': _clean(m.group(2)),
                        'type': 'clause',
                        'suggested_control_id': f'iso-27001-2022.{clause_id}',
                        'notes': '',
                    }
                    logical_lines = []
                elif current is not None:
                    logical_lines.append(line)

    _flush()
    return entries


# ---------------------------------------------------------------------------
# Extraction — Annex A controls
# ---------------------------------------------------------------------------

def extract_annex_a(pdf_path: str) -> list[dict]:
    """Extract Annex A controls (pages 17–24, 0-indexed 16–23)."""
    entries: list[dict] = []
    current_id: str | None = None
    heading_parts: list[str] = []
    heading_done = False
    logical_lines: list[str] = []

    def _flush() -> None:
        if current_id is not None:
            heading = _clean(' '.join(heading_parts).rstrip('-'))
            text = _join_body(logical_lines)
            annex_id = f'A.{current_id}'           # e.g. "A.5.1", "A.6.2"
            ctrl_id = f'iso-27001-2022.a.{current_id}'
            entry: dict = {
                'id': annex_id,
                'heading': heading,
                'type': 'annex_control',
                'suggested_control_id': ctrl_id,
                'notes': '',
                'text': text,
            }
            stmts = _make_statements(annex_id, logical_lines, ctrl_id)
            if stmts:
                entry['statements'] = stmts
            entries.append(entry)

    # Annex A uses a two-column table layout. The left column (x0 < 180) contains
    # the control ID and multi-line heading; the right column (x0 >= 180) contains
    # the body text. Both columns interleave on the same visual lines for controls
    # with long headings (e.g. A.5.21, A.5.24). We split by x0 to separate them.
    BODY_COL_X0 = 180.0

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[16:24]:
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            for line_words in _words_to_lines(words):
                # Split words into left-column (heading/id) and right-column (body)
                left_words = [w for w in line_words if w['x0'] < BODY_COL_X0]
                right_words = [w for w in line_words if w['x0'] >= BODY_COL_X0]

                # Process left-column content
                if left_words:
                    raw_left = _line_text(left_words)
                    left = _clean(raw_left)
                    if left and not ANNEX_CONTROL_SEP.match(left) and not SECTION_HEADER_RE.match(left) and not _is_skip(left):
                        m = ANNEX_CTRL_RE.match(left)
                        if m and m.group(1).split('.')[0] in ('5', '6', '7', '8'):
                            _flush()
                            current_id = m.group(1)
                            heading_parts = [m.group(2)]
                            heading_done = False
                            logical_lines = []
                        elif current_id is not None and not heading_done:
                            # Heading continuation in left column
                            prev = heading_parts[-1] if heading_parts else ''
                            if prev.endswith('-') or (left and left[0].islower()):
                                heading_parts.append(left)
                            else:
                                heading_done = True

                # Process right-column content (always body text)
                if right_words and current_id is not None:
                    raw_right = _line_text(right_words)
                    right = _clean(raw_right)
                    if right and not ANNEX_CONTROL_SEP.match(right) and not _is_skip(right):
                        if not heading_done:
                            heading_done = True
                        logical_lines.append(right)

    _flush()
    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_preserved_text(out_path: Path) -> dict[str, str]:
    """Return {id: text} for all entries with non-empty text in the existing YAML.

    This preserves manual corrections made after a previous extraction run.
    The YAML is the human review checkpoint — never discard a human correction
    by blindly overwriting with a fresh extraction.
    """
    if not out_path.exists():
        return {}
    with open(out_path, encoding='utf-8') as f:
        existing = yaml.safe_load(f) or []
    return {e['id']: e['text'] for e in existing if e.get('text')}


def _merge_preserved(entries: list[dict], preserved: dict[str, str]) -> list[dict]:
    """Apply preserved corrections: existing non-empty text wins over fresh extraction."""
    for e in entries:
        if e['id'] in preserved:
            e['text'] = preserved[e['id']]
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('pdf_path', help='Path to ISO/IEC 27001:2022 PDF')
    parser.add_argument('--out', default='scripts/iso27001_inspection.yaml',
                        help='Output YAML file (default: scripts/iso27001_inspection.yaml)')
    parser.add_argument('--no-preserve', action='store_true',
                        help='Overwrite existing YAML without preserving manual corrections')
    args = parser.parse_args()

    out_path = Path(args.out)

    # Read preserved corrections BEFORE extraction so we can restore them afterwards
    preserved: dict[str, str] = {}
    if not args.no_preserve:
        preserved = _load_preserved_text(out_path)
        if preserved:
            print(f'  Preserving {len(preserved)} manually-corrected entries from existing YAML')

    pdf_path = args.pdf_path
    print(f'Extracting clauses from {pdf_path} ...')
    clauses = extract_clauses(pdf_path)
    print(f'  Clauses found: {len(clauses)}')

    print('Extracting Annex A controls ...')
    annex = extract_annex_a(pdf_path)
    print(f'  Annex A controls found: {len(annex)}')

    all_entries = clauses + annex

    # Restore any manual corrections that survived from the previous YAML
    if preserved:
        all_entries = _merge_preserved(all_entries, preserved)

    # Count total statements
    def _count_stmts(entries):
        n = 0
        for e in entries:
            for s in e.get('statements', []):
                n += 1
                n += _count_stmts(s.get('statements', []))
        return n
    total_stmts = _count_stmts(all_entries)
    print(f'  Normative statements extracted: {total_stmts}')

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(all_entries, f, allow_unicode=True, sort_keys=False, width=120)

    empties = [e['id'] for e in all_entries if not e.get('text') and e['type'] == 'annex_control']
    if empties:
        print(f'\n  ⚠  Annex A entries with empty text (manual review needed): {empties}')

    section_empties = [e['id'] for e in all_entries if not e.get('text') and e['type'] == 'clause' and '.' not in str(e['id'])]
    leaf_empties = [e['id'] for e in all_entries if not e.get('text') and e['type'] == 'clause' and '.' in str(e['id'])]
    if section_empties:
        print(f'  (Section headings with no body — expected): {section_empties}')
    if leaf_empties:
        print(f'  ⚠  Leaf clauses with empty text (manual review needed): {leaf_empties}')

    print(f'\nWritten: {out_path}')
    print('Review the YAML, fill in any flagged entries, then load with scripts/load_iso27001_chunks.py')


if __name__ == '__main__':
    main()
