#!/usr/bin/env python3
"""create_new_framework_informs.py — Create INFORMS edges between the newly loaded frameworks
(ISO 22301, ISO 27005, DIN SPEC 14027) and the existing ones (ISO 27001, NIST CSF, COBIT,
SP 800-53) via embedding cosine similarity.

Pairs created:
  ISO 27005  → ISO 27001, NIST CSF, COBIT
  ISO 22301  → ISO 27001, NIST CSF, COBIT
  DIN SPEC 14027 → ISO 27001, ISO 22301, NIST CSF

Usage:
    python3 -m scripts.create_new_framework_informs \\
        [--threshold 0.55] \\
        [--dry-run] \\
        [--histogram]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

import numpy as np
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyber_knowledge.ingest.cross_framework_informs import (
    _fetch_nodes,
    create_informs_edges,
    threshold_pairs,
    cosine_similarity_matrix,
    _print_histogram,
)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    memgraph_host: str = 'localhost'
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


# ---------------------------------------------------------------------------
# Framework node config — new frameworks
# ---------------------------------------------------------------------------

_ISO22301_PREFIX = 'iso-22301-2019.'
_ISO22301_LEVELS = ['clause', 'sub-clause']

_ISO27005_PREFIX = 'iso-27005-2022.'
_ISO27005_LEVELS = ['clause', 'sub-clause']

_DINSPEC14027_PREFIX = 'din-spec-14027-2026.'
_DINSPEC14027_LEVELS = ['clause', 'sub-clause']

# ---------------------------------------------------------------------------
# Framework node config — existing targets
# ---------------------------------------------------------------------------

_ISO27001_PREFIX = 'iso-27001-2022.'
_ISO27001_LEVELS = ['clause', 'sub-clause', 'annex_control']

_NIST_PREFIX = 'nist-csf-2.0.'
_NIST_LEVELS = ['category', 'subcategory']

_COBIT_PREFIX = 'cobit-2019.'
_COBIT_LEVELS = ['objective', 'practice']

_SP800_53_PREFIX = 'sp800-53r5.'
_SP800_53_LEVELS = ['control']


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Create INFORMS edges between newly loaded frameworks (ISO 22301, ISO 27005, '
            'DIN SPEC 14027) and existing frameworks (ISO 27001, NIST CSF, COBIT, SP 800-53).'
        ),
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.55,
        help='Cosine similarity threshold (default: 0.55)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Compute similarities and print stats without creating edges',
    )
    parser.add_argument(
        '--histogram',
        action='store_true',
        default=False,
        help='Print similarity distribution histogram for each pair',
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = Settings()

    driver = GraphDatabase.driver(
        f'bolt://{cfg.memgraph_host}:{cfg.memgraph_port}',
        auth=('', ''),
    )

    try:
        now = datetime.now(timezone.utc).isoformat()
        total_created = 0
        total_errors = 0

        with driver.session() as session:

            # ------------------------------------------------------------------
            # Fetch all framework node sets
            # ------------------------------------------------------------------

            print('Fetching ISO 22301 nodes...')
            iso22301_nodes = _fetch_nodes(session, _ISO22301_PREFIX, _ISO22301_LEVELS)
            print(f'  {len(iso22301_nodes)} nodes fetched (levels: {_ISO22301_LEVELS})')

            print('Fetching ISO 27005 nodes...')
            iso27005_nodes = _fetch_nodes(session, _ISO27005_PREFIX, _ISO27005_LEVELS)
            print(f'  {len(iso27005_nodes)} nodes fetched (levels: {_ISO27005_LEVELS})')

            print('Fetching DIN SPEC 14027 nodes...')
            din14027_nodes = _fetch_nodes(session, _DINSPEC14027_PREFIX, _DINSPEC14027_LEVELS)
            print(f'  {len(din14027_nodes)} nodes fetched (levels: {_DINSPEC14027_LEVELS})')

            print('Fetching ISO 27001 nodes...')
            iso27001_nodes = _fetch_nodes(session, _ISO27001_PREFIX, _ISO27001_LEVELS)
            print(f'  {len(iso27001_nodes)} nodes fetched (levels: {_ISO27001_LEVELS})')

            print('Fetching NIST CSF 2.0 nodes...')
            nist_nodes = _fetch_nodes(session, _NIST_PREFIX, _NIST_LEVELS)
            print(f'  {len(nist_nodes)} nodes fetched (levels: {_NIST_LEVELS})')

            print('Fetching COBIT 2019 nodes...')
            cobit_nodes = _fetch_nodes(session, _COBIT_PREFIX, _COBIT_LEVELS)
            print(f'  {len(cobit_nodes)} nodes fetched (levels: {_COBIT_LEVELS})')

            # ------------------------------------------------------------------
            # Helper: run one pair and accumulate totals
            # ------------------------------------------------------------------

            def _run_pair(
                label: str,
                src_nodes: list[dict[str, Any]],
                dst_nodes: list[dict[str, Any]],
            ) -> None:
                nonlocal total_created, total_errors

                if not src_nodes:
                    print(f'[WARN] No source nodes for {label} — skipping.', file=sys.stderr)
                    return
                if not dst_nodes:
                    print(f'[WARN] No destination nodes for {label} — skipping.', file=sys.stderr)
                    return

                src_arr = np.array([n['embedding'] for n in src_nodes], dtype=np.float32)
                dst_arr = np.array([n['embedding'] for n in dst_nodes], dtype=np.float32)
                sim = cosine_similarity_matrix(src_arr, dst_arr)

                if args.histogram:
                    _print_histogram(sim, label)

                pairs = threshold_pairs(sim, args.threshold)
                print(f'\n{label}: {len(pairs)} pairs above threshold {args.threshold}')

                if not args.dry_run:
                    created, errors = create_informs_edges(
                        session=session,
                        src_nodes=src_nodes,
                        dst_nodes=dst_nodes,
                        threshold=args.threshold,
                        dry_run=False,
                        now=now,
                    )
                else:
                    created = len(pairs)
                    errors = 0

                suffix = ' (dry-run)' if args.dry_run else ' created'
                print(f'{label}: {created} edges{suffix}')
                total_created += created
                total_errors += errors

            # ------------------------------------------------------------------
            # ISO 27005 → ISO 27001, NIST CSF, COBIT
            # ------------------------------------------------------------------

            _run_pair('ISO 27005 → ISO 27001', iso27005_nodes, iso27001_nodes)
            _run_pair('ISO 27005 → NIST CSF',  iso27005_nodes, nist_nodes)
            _run_pair('ISO 27005 → COBIT',      iso27005_nodes, cobit_nodes)

            # ------------------------------------------------------------------
            # ISO 22301 → ISO 27001, NIST CSF, COBIT
            # ------------------------------------------------------------------

            _run_pair('ISO 22301 → ISO 27001', iso22301_nodes, iso27001_nodes)
            _run_pair('ISO 22301 → NIST CSF',  iso22301_nodes, nist_nodes)
            _run_pair('ISO 22301 → COBIT',      iso22301_nodes, cobit_nodes)

            # ------------------------------------------------------------------
            # DIN SPEC 14027 → ISO 27001, ISO 22301, NIST CSF
            # (skip DIN → COBIT — too different in scope)
            # ------------------------------------------------------------------

            _run_pair('DIN SPEC 14027 → ISO 27001', din14027_nodes, iso27001_nodes)
            _run_pair('DIN SPEC 14027 → ISO 22301', din14027_nodes, iso22301_nodes)
            _run_pair('DIN SPEC 14027 → NIST CSF',  din14027_nodes, nist_nodes)

        # ----------------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------------

        suffix = ' (dry-run, no edges written)' if args.dry_run else ''
        print(f'\nTotal: {total_created} edges{suffix}, {total_errors} errors')

    finally:
        driver.close()

    return 0 if total_errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
