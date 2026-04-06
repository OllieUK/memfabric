#!/usr/bin/env python3
"""inspect_nist_csf.py — Structure-aware extractor for NIST CSF 2.0.

Reads the NIST CSF 2.0 Reference Tool JSON export and optionally enriches
Function descriptions from the official PDF (Section 2, pages 8-9), then
produces two reviewable YAML files:

  1. nist_csf_inspection.yaml   — full framework hierarchy
  2. nist_csf_iso27001_xrefs.yaml — cross-reference mappings to ISO 27001

Usage:
    python3 -m scripts.inspect_nist_csf <json_path> \\
        [--pdf <pdf_path>] \\
        [--out scripts/nist_csf_inspection.yaml] \\
        [--xrefs-out scripts/nist_csf_iso27001_xrefs.yaml] \\
        [--no-preserve]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

ROOT_ID = "nist-csf-2.0"

SKIP_TYPES = {"party"}

# Element types to emit in output order
EMIT_TYPES = ["function", "category", "subcategory", "implementation_example"]


def _graph_id(element_identifier: str) -> str:
    """Convert a CSF element_identifier to a graph node id.

    GV          → nist-csf-2.0.gv
    GV.OC       → nist-csf-2.0.gv.oc
    GV.OC-01    → nist-csf-2.0.gv.oc-01
    GV.OC-01.001 → nist-csf-2.0.gv.oc-01.001
    """
    return f"{ROOT_ID}.{element_identifier.lower()}"


# ---------------------------------------------------------------------------
# Text cleaning (adapted from inspect_iso27001.py)
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Normalise pdfplumber artefacts from a reconstructed line of text."""
    text = re.sub(r'-\s+', '', text)                           # soft-hyphen wraps
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# PDF word-level line reconstruction
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
# PDF skip patterns
# ---------------------------------------------------------------------------

_PDF_SKIP_RE = re.compile(
    r'^('
    r'NIST CSWP 29'           # page header
    r'|February 26, 2024'     # date
    r'|Fig\.\s*\d'            # figure references
    r'|\d{1,2}$'              # bare page numbers
    r')'
)

# Function bullet pattern: "• FUNCTION_NAME (XX) — description..."
# Also handles "• FUNCTION_NAME (XX) —" split across words, or bare "•"
_FUNC_BULLET_RE = re.compile(
    r'^•?\s*([A-Z]{2,})\s+\(([A-Z]{2})\)\s*[—–-]+\s*(.*)$'
)

# Matches lines that are entirely in the intro prose (not function bullets)
# We stop accumulating when we hit the "While many..." paragraph
_STOP_RE = re.compile(r'^While many cybersecurity')


def extract_function_descriptions_from_pdf(pdf_path: str) -> dict[str, str]:
    """Extract full Function descriptions from Section 2 of the NIST CSF PDF.

    Pages 8-9 (0-indexed 7-8) contain the Section 2 prose with bullet
    descriptions for each of the 6 Functions.

    The PDF has several layout quirks:
    - GOVERN/IDENTIFY/PROTECT/DETECT bullets: "• FUNC (XX) — text..." at x0≈90
    - RESPOND bullet: bare "•" at x0≈90, then "RESPOND (RS) — text..." at x0≈108
    - RECOVER bullet: "• Assets and operations..." at x0≈90 (the heading/definition),
      then "RECOVER (RC) —" at x0≈108, then body text at x0≈108

    Returns a dict mapping function abbrev (e.g. "GV") to full description text.
    """
    import pdfplumber

    # Accumulate all lines from both pages before parsing
    all_lines: list[tuple[float, str]] = []  # (x0, text)

    with pdfplumber.open(pdf_path) as pdf:
        for pg_idx in [7, 8]:
            page = pdf.pages[pg_idx]
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            for line_words in _words_to_lines(words):
                raw = _line_text(line_words)
                line = _clean(raw)
                if not line:
                    continue
                if _PDF_SKIP_RE.match(line):
                    continue
                x0 = line_words[0]['x0'] if line_words else 0
                all_lines.append((x0, line))

    # Inline function ID pattern — matches "FUNC (XX) — text" without leading bullet
    # Used for RESPOND which appears at x0=108 and for RECOVER which also appears at x0=108
    _INLINE_FUNC_RE = re.compile(r'^([A-Z]{2,})\s+\(([A-Z]{2})\)\s*[—–-]+\s*(.*)$')

    # Parse the lines into Function descriptions
    desc_parts: dict[str, list[str]] = {}

    current_abbrev: str | None = None
    current_parts: list[str] = []
    pending_prefix: str | None = None   # text accumulated before we know the abbrev (RECOVER)
    bare_bullet_seen: bool = False      # True after a bare "•" line

    def _save_current() -> None:
        if current_abbrev is not None:
            desc_parts[current_abbrev] = current_parts

    for x0, line in all_lines:
        if _STOP_RE.match(line):
            break

        # Detect bare bullet: just "•" on its own line
        if line == '•':
            bare_bullet_seen = True
            continue

        # Full function bullet: "• FUNC (XX) — text..."
        m = _FUNC_BULLET_RE.match(line)
        if m:
            _save_current()
            abbrev = m.group(2)
            rest = m.group(3).strip()
            current_abbrev = abbrev
            # Prepend any pending prefix (e.g. RECOVER's leading definition sentence)
            current_parts = []
            if pending_prefix:
                current_parts.append(pending_prefix)
            if rest:
                current_parts.append(rest)
            pending_prefix = None
            bare_bullet_seen = False
            continue

        # After bare bullet: next line may be "FUNC (XX) — text" (RESPOND)
        # OR next bullet may be "• Sentence that is the definition." (RECOVER)
        if bare_bullet_seen:
            bare_bullet_seen = False
            m2 = _INLINE_FUNC_RE.match(line)
            if m2:
                # RESPOND case: bare "•" then "RESPOND (RS) — text..."
                _save_current()
                abbrev = m2.group(2)
                rest = m2.group(3).strip()
                current_abbrev = abbrev
                current_parts = [rest] if rest else []
                pending_prefix = None
                continue
            # Otherwise treat as continuation (fall through)

        # Check if this is an inline function header at x0≈108 following a "• Sentence" bullet
        # This is RECOVER's layout: "• Assets and operations..." then "RECOVER (RC) —"
        m3 = _INLINE_FUNC_RE.match(line)
        if m3:
            new_abbrev = m3.group(2)
            rest = m3.group(3).strip()
            if new_abbrev != current_abbrev:
                # This starts a new function — but the PREVIOUS bullet line (a sentence
                # starting with "•") was actually this function's leading definition sentence.
                # We need to prepend it to the new function's parts.
                _save_current()
                current_abbrev = new_abbrev
                current_parts = []
                if pending_prefix:
                    current_parts.append(pending_prefix)
                    pending_prefix = None
                if rest:
                    current_parts.append(rest)
                continue

        # Check for a "• Sentence." line that might be a RECOVER-style leading definition
        # (x0≈90, starts with "• " but is not a function name)
        if line.startswith('• ') and current_abbrev is not None:
            sentence = line[2:].strip()
            # This is the RECOVER pattern: save current, start pending
            _save_current()
            current_abbrev = None
            current_parts = []
            pending_prefix = sentence
            continue

        # Normal continuation line
        if current_abbrev is not None:
            current_parts.append(line)

    _save_current()

    # Join parts into full descriptions
    result: dict[str, str] = {}
    for abbrev, parts in desc_parts.items():
        full_text = ' '.join(p for p in parts if p)
        result[abbrev] = full_text

    return result


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def extract_from_json(json_path: str) -> tuple[list[dict], tuple[list[dict], int], dict[str, int]]:
    """Extract CSF entries and ISO 27001 cross-references from the JSON export.

    Returns:
        (entries, xrefs) where entries are the inspection YAML dicts and
        xrefs are the cross-reference dicts.
    """
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    raw = data['response']['elements']
    elements: list[dict] = raw['elements']
    relationships: list[dict] = raw['relationships']

    # Filter to CSF 2.0 elements only, skip party types
    csf_elements = [
        e for e in elements
        if e['doc_identifier'] == 'CSF_2_0_0'
        and e['element_type'] not in SKIP_TYPES
    ]

    # Build parent map from projection relationships
    # projection: source→dest means dest is a child of source
    parent_map: dict[str, str] = {}  # child_identifier → parent_identifier
    csf_ids = {e['element_identifier'] for e in csf_elements}

    for rel in relationships:
        if rel['relationship_identifier'] != 'projection':
            continue
        if rel['source_doc_identifier'] != 'CSF_2_0_0':
            continue
        src = rel['source_element_identifier']
        dst = rel['dest_element_identifier']
        # Only map if destination is a non-party CSF element
        if dst in csf_ids:
            parent_map[dst] = src

    # Build entries grouped by type to maintain the required output order
    by_type: dict[str, list[dict]] = {t: [] for t in EMIT_TYPES}

    for elem in csf_elements:
        etype = elem['element_type']
        if etype not in EMIT_TYPES:
            continue

        eid = elem['element_identifier']
        gid = _graph_id(eid)
        title = elem.get('title', '')
        text = elem.get('text', '')

        entry: dict = {
            'id': gid,
            'type': etype,
            'abbrev': eid,
            'heading': title if title else eid,
            'text': text,
            'notes': '',
        }

        if etype != 'function':
            parent_eid = parent_map.get(eid)
            if parent_eid:
                entry['parent_id'] = _graph_id(parent_eid)
            else:
                entry['parent_id'] = ROOT_ID  # fallback

        by_type[etype].append(entry)

    # Emit in order: functions, categories, subcategories, implementation_examples
    all_entries: list[dict] = []
    counts: dict[str, int] = {}
    for etype in EMIT_TYPES:
        group = by_type[etype]
        counts[etype] = len(group)
        all_entries.extend(group)

    # Build cross-references
    xrefs = _build_xrefs(relationships, csf_ids)

    return all_entries, xrefs, counts


def _normalise_iso_ids(dest_raw: str) -> list[str]:
    """Normalise a raw ISO 27001 dest_element_identifier to one or more graph ids.

    'Mandatory Clause:  4.1'    → ['iso-27001-2022.4.1']
    'Mandatory Clause:  6.1,'   → ['iso-27001-2022.6.1']
    'Mandatory Clause: 7.1, 7.2'→ ['iso-27001-2022.7.1', 'iso-27001-2022.7.2']
    'Annex A Controls: 5.1'     → ['iso-27001-2022.a.5.1']
    'Annex A Controls:'         → [] (skip)

    Returns an empty list when the entry should be skipped entirely.
    """
    dest_raw = dest_raw.strip()

    if dest_raw.startswith('Mandatory Clause:'):
        rest = dest_raw[len('Mandatory Clause:'):].strip()
        # Handle multiple clause numbers separated by commas: "7.1, 7.2"
        parts = [p.strip().rstrip(',').strip() for p in rest.split(',')]
        return [f'iso-27001-2022.{p}' for p in parts if p]

    if dest_raw.startswith('Annex A Controls:'):
        rest = dest_raw[len('Annex A Controls:'):].strip().rstrip(',').strip()
        if not rest:
            return []
        return [f'iso-27001-2022.a.{rest}']

    return []


def _build_xrefs(relationships: list[dict], csf_ids: set[str]) -> tuple[list[dict], int]:
    """Extract and normalise CSF → ISO 27001 cross-references."""
    xrefs = []
    skipped = 0

    for rel in relationships:
        if rel['relationship_identifier'] != 'external_reference':
            continue
        if rel['source_doc_identifier'] != 'CSF_2_0_0':
            continue

        src_eid = rel['source_element_identifier']
        dest_raw = rel['dest_element_identifier']

        # Only include cross-refs from non-party CSF elements
        if src_eid not in csf_ids:
            continue

        dest_ids = _normalise_iso_ids(dest_raw)
        if not dest_ids:
            skipped += 1
            continue

        for dest_id in dest_ids:
            xrefs.append({
                'source_id': _graph_id(src_eid),
                'dest_id': dest_id,
                'dest_raw': dest_raw,
                'relationship': 'external_reference',
            })

    return xrefs, skipped


# ---------------------------------------------------------------------------
# Preserve/merge pattern (from inspect_iso27001.py)
# ---------------------------------------------------------------------------

def _load_preserved_text(out_path: Path) -> dict[str, str]:
    """Return {id: text} for all entries with non-empty text in the existing YAML."""
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('json_path', help='Path to NIST CSF 2.0 Reference Tool JSON export')
    parser.add_argument('--pdf', default=None, help='Path to NIST CSF 2.0 PDF (NIST.CSWP.29.pdf)')
    parser.add_argument(
        '--out',
        default='scripts/nist_csf_inspection.yaml',
        help='Output inspection YAML (default: scripts/nist_csf_inspection.yaml)',
    )
    parser.add_argument(
        '--xrefs-out',
        default='scripts/nist_csf_iso27001_xrefs.yaml',
        help='Output cross-references YAML (default: scripts/nist_csf_iso27001_xrefs.yaml)',
    )
    parser.add_argument(
        '--no-preserve',
        action='store_true',
        help='Overwrite existing YAML without preserving manual corrections',
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    xrefs_path = Path(args.xrefs_out)

    # Load preserved corrections before extraction
    preserved: dict[str, str] = {}
    if not args.no_preserve:
        preserved = _load_preserved_text(out_path)
        if preserved:
            print(f'  Preserving {len(preserved)} manually-corrected entries from existing YAML')

    print(f'Extracting NIST CSF 2.0 from {args.json_path} ...')
    entries, xref_data, counts = extract_from_json(args.json_path)
    xrefs, skipped_xrefs = xref_data

    print(f'  Functions: {counts["function"]}')
    print(f'  Categories: {counts["category"]}')
    print(f'  Subcategories: {counts["subcategory"]}')
    print(f'  Implementation examples: {counts["implementation_example"]}')

    # Enrich Function descriptions from PDF
    if args.pdf:
        print(f'\nEnriching Function descriptions from PDF ...')
        try:
            func_descriptions = extract_function_descriptions_from_pdf(args.pdf)
            func_entries = [e for e in entries if e['type'] == 'function']
            for fe in func_entries:
                abbrev = fe['abbrev']
                if abbrev in func_descriptions:
                    desc = func_descriptions[abbrev]
                    fe['text'] = desc
                    print(f'  {fe["heading"]} ({abbrev}): {len(desc)} chars')
                else:
                    print(f'  WARNING: no PDF description found for {abbrev}')
        except Exception as exc:
            print(f'  WARNING: PDF enrichment failed: {exc}')

    total_xrefs = len(xrefs) + skipped_xrefs
    print(f'\nCross-references: {total_xrefs} → {len(xrefs)} after normalisation ({skipped_xrefs} skipped)')

    # Apply preserved corrections
    if preserved:
        entries = _merge_preserved(entries, preserved)

    # Warn about empty text entries
    empties = [e['id'] for e in entries if not e.get('text')]
    if empties:
        print(f'\nWARNING: {len(empties)} entries with empty text:')
        for eid in empties[:10]:
            print(f'  {eid}')
        if len(empties) > 10:
            print(f'  ... and {len(empties) - 10} more')

    # Write inspection YAML
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.dump(entries, f, allow_unicode=True, sort_keys=False, width=120)
    print(f'\nWritten: {out_path} ({len(entries)} entries)')

    # Write cross-references YAML
    xrefs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(xrefs_path, 'w', encoding='utf-8') as f:
        yaml.dump(xrefs, f, allow_unicode=True, sort_keys=False, width=120)
    print(f'Written: {xrefs_path} ({len(xrefs)} entries)')


if __name__ == '__main__':
    main()
