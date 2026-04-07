#!/usr/bin/env python3
"""create_cross_framework_informs.py — Create INFORMS edges between COBIT 2019 and ISO/NIST
framework nodes via embedding cosine similarity.

Fetches Framework node embeddings from Memgraph, computes pairwise cosine similarity,
and creates INFORMS edges above the chosen threshold.

Usage:
    python3 -m scripts.create_cross_framework_informs \\
        [--threshold 0.55] \\
        [--include-activities] \\
        [--dry-run] \\
        [--histogram] \\
        [--calibrate]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    memgraph_host: str = 'localhost'
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


# ---------------------------------------------------------------------------
# Framework node config
# ---------------------------------------------------------------------------

_COBIT_PREFIX = 'cobit-2019.'
_ISO_PREFIX = 'iso-27001-2022.'
_NIST_PREFIX = 'nist-csf-2.0.'

_COBIT_LEVELS_DEFAULT = ['objective', 'practice']
_COBIT_LEVELS_WITH_ACTIVITIES = ['objective', 'practice', 'activity']
_ISO_LEVELS = ['clause', 'annex_control']
_NIST_LEVELS = ['category', 'subcategory']


# ---------------------------------------------------------------------------
# Core math helpers (tested directly)
# ---------------------------------------------------------------------------

def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Return cosine similarity matrix of shape (m, n).

    Rows with zero norm are treated as having zero similarity to all targets.
    """
    a_norms = np.linalg.norm(a, axis=1, keepdims=True)
    b_norms = np.linalg.norm(b, axis=1, keepdims=True)
    a_norm = np.where(a_norms > 0, a / a_norms, 0.0)
    b_norm = np.where(b_norms > 0, b / b_norms, 0.0)
    return (a_norm @ b_norm.T).astype(np.float32)


def threshold_pairs(
    sim: np.ndarray,
    threshold: float,
) -> list[tuple[int, int, float]]:
    """Return (i, j, score) tuples where sim[i, j] > threshold (strictly)."""
    rows, cols = np.where(sim > threshold)
    return [(int(i), int(j), float(sim[i, j])) for i, j in zip(rows, cols)]


def filter_by_level(
    nodes: list[dict[str, Any]],
    allowed_levels: list[str],
) -> list[dict[str, Any]]:
    """Return only nodes whose 'level' field is in allowed_levels."""
    return [n for n in nodes if n.get('level') in allowed_levels]


def compute_histogram(
    values: list[float],
    bin_width: float = 0.05,
    low: float = 0.0,
    high: float = 1.0,
) -> dict[tuple[float, float], int]:
    """Count values into fixed-width bins in [low, high).

    Returns a dict mapping (bin_lo, bin_hi) → count.
    Boundary: value v belongs to bin [lo, hi) if lo <= v < hi.
    Values equal to high go into the last bin.
    """
    bins: dict[tuple[float, float], int] = {}
    lo = low
    while lo < high - 1e-9:
        hi = round(lo + bin_width, 10)
        bins[(round(lo, 10), round(hi, 10))] = 0
        lo = hi

    for v in values:
        placed = False
        for (blo, bhi) in bins:
            if blo <= v < bhi:
                bins[(blo, bhi)] += 1
                placed = True
                break
        if not placed:
            # value == high: put in last bin
            last_key = max(bins.keys())
            bins[last_key] += 1

    return bins


# ---------------------------------------------------------------------------
# Graph fetch helpers
# ---------------------------------------------------------------------------

def _fetch_nodes(
    session,
    prefix: str,
    allowed_levels: list[str],
) -> list[dict[str, Any]]:
    """Fetch Framework nodes with embeddings for the given ID prefix and levels."""
    query = (
        'MATCH (f:Framework) '
        'WHERE f.id STARTS WITH $prefix AND f.embedding IS NOT NULL '
        'RETURN f.id AS id, f.level AS level, f.embedding AS embedding'
    )
    result = session.run(query, prefix=prefix)
    nodes = []
    for record in result:
        lvl = record['level']
        if lvl in allowed_levels:
            nodes.append({
                'id': record['id'],
                'level': lvl,
                'embedding': list(record['embedding']),
            })
    return nodes


# ---------------------------------------------------------------------------
# Edge creation
# ---------------------------------------------------------------------------

_MERGE_CYPHER = (
    'MATCH (src:Framework {id: $src_id}), (dst:Framework {id: $dst_id}) '
    'MERGE (src)-[r:INFORMS]->(dst) '
    'ON CREATE SET r.source = \'embedding-similarity\', '
    '              r.similarity = $similarity, '
    '              r.created_at = $now '
    'RETURN type(r) AS rel_type'
)


def create_informs_edges(
    session,
    src_nodes: list[dict[str, Any]],
    dst_nodes: list[dict[str, Any]],
    threshold: float,
    dry_run: bool,
    now: str,
) -> tuple[int, int]:
    """Compute cosine similarities and create INFORMS edges above threshold.

    Returns (created_count, error_count).
    In dry_run mode no MERGE calls are made and (0, 0) is returned.
    The candidate pair count is computed separately in main().
    """
    if not src_nodes or not dst_nodes:
        return 0, 0

    src_embeddings = np.array([n['embedding'] for n in src_nodes], dtype=np.float32)
    dst_embeddings = np.array([n['embedding'] for n in dst_nodes], dtype=np.float32)

    sim = cosine_similarity_matrix(src_embeddings, dst_embeddings)
    pairs = threshold_pairs(sim, threshold)

    created = 0
    errors = 0

    for i, j, score in pairs:
        if dry_run:
            continue
        src_id = src_nodes[i]['id']
        dst_id = dst_nodes[j]['id']
        try:
            session.run(
                _MERGE_CYPHER,
                src_id=src_id,
                dst_id=dst_id,
                similarity=float(score),
                now=now,
            )
            created += 1
            if created % 100 == 0:
                print(f'   Created {created} edges so far...')
        except Exception as exc:  # noqa: BLE001
            print(f'   [ERR] {src_id} → {dst_id}: {exc}', file=sys.stderr)
            errors += 1

    return created, errors


# ---------------------------------------------------------------------------
# Histogram printing
# ---------------------------------------------------------------------------

def _print_histogram(
    sim: np.ndarray,
    label: str,
    bin_width: float = 0.05,
) -> None:
    """Print a text histogram of similarity values."""
    values = sim.flatten().tolist()
    bins = compute_histogram(values, bin_width=bin_width, low=0.0, high=1.0 + bin_width)

    print(f'\nSimilarity distribution ({label}):')
    bar_scale = 40
    max_count = max(bins.values()) or 1
    for (blo, bhi), count in sorted(bins.items()):
        if count == 0 and blo < 0.3:
            continue  # skip leading zero bins below 0.3 for readability
        bar_len = int(count / max_count * bar_scale)
        bar = '\u2588' * bar_len
        print(f'  {blo:.2f}-{bhi:.2f}: {bar} {count}')


# ---------------------------------------------------------------------------
# Calibrate mode
# ---------------------------------------------------------------------------

def _calibrate(session) -> None:
    """Fetch existing NIST→ISO xref INFORMS edges and report cosine similarity percentiles."""
    query = (
        'MATCH (src:Framework)-[r:INFORMS]->(dst:Framework) '
        'WHERE r.source = \'nist-csf-2.0-reference-tool\' '
        '  AND src.embedding IS NOT NULL AND dst.embedding IS NOT NULL '
        'RETURN src.id AS src_id, dst.id AS dst_id, '
        '       src.embedding AS src_emb, dst.embedding AS dst_emb'
    )
    result = session.run(query)
    rows = list(result)

    if not rows:
        print('No NIST→ISO xref edges found (source=nist-csf-2.0-reference-tool).')
        return

    src_embs = np.array([list(r['src_emb']) for r in rows], dtype=np.float32)
    dst_embs = np.array([list(r['dst_emb']) for r in rows], dtype=np.float32)

    # Diagonal similarity (each row is a matched pair)
    src_norms = np.linalg.norm(src_embs, axis=1, keepdims=True)
    dst_norms = np.linalg.norm(dst_embs, axis=1, keepdims=True)
    src_norm = np.where(src_norms > 0, src_embs / src_norms, 0.0)
    dst_norm = np.where(dst_norms > 0, dst_embs / dst_norms, 0.0)
    sims = (src_norm * dst_norm).sum(axis=1)

    percentiles = [10, 25, 50, 75, 90]
    print(f'\nCalibration: cosine similarity of {len(rows)} NIST→ISO xref edges')
    for p in percentiles:
        print(f'  p{p:02d}: {np.percentile(sims, p):.4f}')
    print(f'  min: {sims.min():.4f}  max: {sims.max():.4f}')


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Create INFORMS edges between COBIT 2019 and ISO/NIST framework nodes.',
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.55,
        help='Cosine similarity threshold (default: 0.55)',
    )
    parser.add_argument(
        '--include-activities',
        action='store_true',
        default=False,
        help='Include COBIT activity-level nodes (default: objectives + practices only)',
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
        help='Print similarity distribution histogram',
    )
    parser.add_argument(
        '--calibrate',
        action='store_true',
        default=False,
        help='Report percentiles of existing NIST→ISO xref edge similarities',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    cfg = Settings()

    driver = GraphDatabase.driver(
        f'bolt://{cfg.memgraph_host}:{cfg.memgraph_port}',
        auth=('', ''),
    )

    try:
        now = datetime.now(timezone.utc).isoformat()

        cobit_levels = (
            _COBIT_LEVELS_WITH_ACTIVITIES if args.include_activities
            else _COBIT_LEVELS_DEFAULT
        )

        with driver.session() as session:

            # --calibrate mode
            if args.calibrate:
                _calibrate(session)

            # Fetch node embeddings
            print('Fetching COBIT 2019 nodes...')
            cobit_nodes = _fetch_nodes(session, _COBIT_PREFIX, cobit_levels)
            print(f'  {len(cobit_nodes)} nodes fetched (levels: {cobit_levels})')

            print('Fetching ISO 27001 nodes...')
            iso_nodes = _fetch_nodes(session, _ISO_PREFIX, _ISO_LEVELS)
            print(f'  {len(iso_nodes)} nodes fetched (levels: {_ISO_LEVELS})')

            print('Fetching NIST CSF 2.0 nodes...')
            nist_nodes = _fetch_nodes(session, _NIST_PREFIX, _NIST_LEVELS)
            print(f'  {len(nist_nodes)} nodes fetched (levels: {_NIST_LEVELS})')

            if not cobit_nodes:
                print('[WARN] No COBIT nodes found — aborting.', file=sys.stderr)
                return 1

            # Compute similarity matrices and optionally print histograms
            total_created = 0
            total_errors = 0

            # ---- COBIT → ISO 27001 ----
            if iso_nodes:
                cobit_arr = np.array([n['embedding'] for n in cobit_nodes], dtype=np.float32)
                iso_arr = np.array([n['embedding'] for n in iso_nodes], dtype=np.float32)
                sim_cobit_iso = cosine_similarity_matrix(cobit_arr, iso_arr)

                if args.histogram:
                    _print_histogram(sim_cobit_iso, 'COBIT → ISO 27001')

                pairs_cobit_iso = threshold_pairs(sim_cobit_iso, args.threshold)
                print(
                    f'\nCOBIT → ISO 27001: {len(pairs_cobit_iso)} pairs above threshold {args.threshold}'
                )

                if not args.dry_run:
                    created, errors = create_informs_edges(
                        session=session,
                        src_nodes=cobit_nodes,
                        dst_nodes=iso_nodes,
                        threshold=args.threshold,
                        dry_run=False,
                        now=now,
                    )
                else:
                    created = len(pairs_cobit_iso)
                    errors = 0

                print(f'COBIT → ISO 27001: {created} edges {"(dry-run)" if args.dry_run else "created"} ({len(pairs_cobit_iso)} pairs above threshold)')
                total_created += created
                total_errors += errors
            else:
                print('[WARN] No ISO 27001 nodes found — skipping COBIT → ISO edges.', file=sys.stderr)

            # ---- COBIT → NIST CSF 2.0 ----
            if nist_nodes:
                cobit_arr = np.array([n['embedding'] for n in cobit_nodes], dtype=np.float32)
                nist_arr = np.array([n['embedding'] for n in nist_nodes], dtype=np.float32)
                sim_cobit_nist = cosine_similarity_matrix(cobit_arr, nist_arr)

                if args.histogram:
                    _print_histogram(sim_cobit_nist, 'COBIT → NIST CSF 2.0')

                pairs_cobit_nist = threshold_pairs(sim_cobit_nist, args.threshold)
                print(
                    f'\nCOBIT → NIST CSF: {len(pairs_cobit_nist)} pairs above threshold {args.threshold}'
                )

                if not args.dry_run:
                    created, errors = create_informs_edges(
                        session=session,
                        src_nodes=cobit_nodes,
                        dst_nodes=nist_nodes,
                        threshold=args.threshold,
                        dry_run=False,
                        now=now,
                    )
                else:
                    created = len(pairs_cobit_nist)
                    errors = 0

                print(f'COBIT → NIST CSF:  {created} edges {"(dry-run)" if args.dry_run else "created"} ({len(pairs_cobit_nist)} pairs above threshold)')
                total_created += created
                total_errors += errors
            else:
                print('[WARN] No NIST CSF nodes found — skipping COBIT → NIST edges.', file=sys.stderr)

        suffix = ' (dry-run, no edges written)' if args.dry_run else ''
        print(f'\nTotal: {total_created} edges{suffix}, {total_errors} errors')

    finally:
        driver.close()

    return 0 if total_errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
