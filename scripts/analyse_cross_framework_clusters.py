#!/usr/bin/env python3
"""WP-107: Cross-framework cluster analysis.

Runs MAGE Louvain community detection + embedding k-means clustering across
all Framework nodes. Writes cluster annotations back to Framework nodes and
prints a convergence zone summary.

Usage:
  python scripts/analyse_cross_framework_clusters.py [--write] [--k N] [--top-bridge N]

Flags:
  --write         Write cluster annotations back to Framework nodes (default: dry-run)
  --k N           Force k-means to k=N (default: auto-select via silhouette)
  --k-min N       Minimum k to try in silhouette sweep (default: 5)
  --k-max N       Maximum k to try in silhouette sweep (default: 40)
  --top-bridge N  Number of bridge nodes to report (default: 20)
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
from neo4j.exceptions import AuthError, ServiceUnavailable
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from memory_service.config import Settings, get_driver


def _normalize_embeddings(embs: np.ndarray) -> np.ndarray:
    """L2-normalise each row; zero vectors stay zero."""
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0, 1.0, norms)
    return embs / safe_norms


def _kmeans_cluster(embs: np.ndarray, n_clusters: int, random_state: int = 42) -> np.ndarray:
    """K-means clustering. If n_clusters >= n_samples, falls back to k=1."""
    n = len(embs)
    k = min(n_clusters, n - 1) if n > 1 else 1
    k = max(k, 1)
    model = KMeans(n_clusters=k, random_state=random_state, n_init='auto')
    return model.fit_predict(embs).astype(np.intp)


def _find_optimal_k(
    embs: np.ndarray,
    k_min: int = 5,
    k_max: int = 40,
    random_state: int = 42,
) -> int:
    """Sweep k from k_min to k_max; return k with highest silhouette score.

    Falls back to k_min if the dataset is too small for any valid silhouette
    computation (warns to stderr in that case).
    """
    n = len(embs)
    k_max = min(k_max, n - 1)
    k_min = min(k_min, k_max)
    best_k, best_score = k_min, -1.0
    found_valid = False
    for k in range(k_min, k_max + 1):
        labels = _kmeans_cluster(embs, n_clusters=k, random_state=random_state)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(embs, labels, metric='cosine')
        found_valid = True
        if score > best_score:
            best_score, best_k = score, k
    if not found_valid:
        print(
            f'WARNING: _find_optimal_k: no valid silhouette score found '
            f'(n={n}, k_min={k_min}, k_max={k_max}); returning k_min={k_min}',
            file=sys.stderr,
        )
    return best_k


# ── Graph fetch / MAGE ────────────────────────────────────────────────────────

def _fetch_framework_embeddings(session) -> list[dict[str, Any]]:
    """Fetch all Framework nodes that have an embedding property."""
    result = session.run(
        'MATCH (f:Framework) '
        'WHERE f.embedding IS NOT NULL '
        'RETURN f.id AS id, f.level AS level, f.domain AS domain, '
        '       f.external_id AS external_id, f.title AS title, '
        '       f.embedding AS embedding'
    )
    return [dict(r) for r in result]


def _run_louvain_on_framework_subgraph(session) -> list[dict[str, Any]]:
    """Run MAGE community detection scoped to Framework nodes.

    Primary path: subgraph projection on INFORMS+MITIGATES edges only —
    communities reflect only inter-framework structural relationships.

    Fallback (if subgraph call fails): whole-graph community detection
    filtered to Framework-labelled nodes — community assignments may be
    influenced by non-Framework nodes and edges (e.g. Memory→Framework links).
    A warning is printed to stderr when the fallback is used.
    """
    try:
        result = session.run(
            'MATCH (f:Framework)-[r:INFORMS|MITIGATES]-(:Framework) '
            'WITH collect(DISTINCT f) AS nodes, collect(DISTINCT r) AS rels '
            'CALL community_detection.get_subgraph(nodes, rels) '
            'YIELD node, community_id '
            'RETURN node.id AS id, community_id'
        )
        rows = [dict(r) for r in result]
        if rows:
            return rows
    except Exception as exc:
        print(
            f'WARNING: _run_louvain_on_framework_subgraph: subgraph call failed '
            f'({type(exc).__name__}: {exc}); falling back to whole-graph',
            file=sys.stderr,
        )

    result = session.run(
        'CALL community_detection.get() YIELD node, community_id '
        'WITH node, community_id WHERE node:Framework '
        'RETURN node.id AS id, community_id'
    )
    return [dict(r) for r in result]


def _run_betweenness_on_framework_subgraph(
    session, top_n: int = 20
) -> list[dict[str, Any]]:
    """Run MAGE betweenness centrality, returning top-N Framework nodes.

    Betweenness scores are computed over the whole graph (all node types and
    edge types) — not restricted to the Framework subgraph. Scores reflect
    a Framework node's position in the full graph, not just the
    INFORMS/MITIGATES subgraph. Results are filtered to Framework nodes only.
    """
    result = session.run(
        'CALL betweenness_centrality.get() YIELD node, betweenness_centrality '
        'WITH node, betweenness_centrality WHERE node:Framework '
        'RETURN node.id AS id, '
        '       toFloat(betweenness_centrality) AS betweenness_centrality, '
        '       node.title AS title '
        'ORDER BY betweenness_centrality DESC '
        'LIMIT $top_n',
        top_n=top_n,
    )
    return [dict(r) for r in result]


def _write_cluster_annotations(
    session, annotations: list[dict[str, Any]]
) -> int:
    """Write louvain_community_id, embedding_cluster_id, betweenness_centrality
    back to each Framework node in a single batched query.
    Returns count of nodes actually matched and updated."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            'id': ann['id'],
            'louvain': ann.get('louvain_community_id'),
            'emb_cluster': ann.get('embedding_cluster_id'),
            'betweenness': ann.get('betweenness_centrality'),
        }
        for ann in annotations
    ]
    result = session.run(
        'UNWIND $rows AS row '
        'MATCH (f:Framework {id: row.id}) '
        'SET f.louvain_community_id = row.louvain, '
        '    f.embedding_cluster_id = row.emb_cluster, '
        '    f.betweenness_centrality = row.betweenness, '
        '    f.cluster_updated_at = $now '
        'RETURN count(f) AS updated',
        rows=rows,
        now=now,
    )
    rec = result.single()
    return rec['updated'] if rec else 0


# ── Report ────────────────────────────────────────────────────────────────────

_REPORT_TOP_N = 20  # max items per section in the summary report

_FRAMEWORK_PREFIX_MAP = {
    'iso-27001-2022':    'ISO 27001',
    'nist-csf':          'NIST CSF',
    'cobit':             'COBIT 2019',
    'attack-enterprise': 'ATT&CK',
    'sp800-53r5':        'SP 800-53',
}


def _framework_label(node_id: str) -> str:
    """Map a Framework node id to a short human-readable label."""
    for prefix, label in _FRAMEWORK_PREFIX_MAP.items():
        if node_id.startswith(prefix):
            return label
    fallback = node_id.split('.')[0]
    print(
        f'WARNING: _framework_label: unrecognised prefix in id {node_id!r}; '
        f'using fallback {fallback!r}',
        file=sys.stderr,
    )
    return fallback


def _render_group_section(
    lines: list[str],
    heading: str,
    groups: dict[int, list[dict]],
    label_fn: str,
) -> None:
    """Append a community/cluster breakdown section to *lines* in-place."""
    lines.append(f'{heading} — {len(groups)} {"communities" if "Community" in heading else "clusters"}')
    lines.append('─' * 50)
    for cid in sorted(groups, key=lambda k: -len(groups[k]))[:_REPORT_TOP_N]:
        members = groups[cid]
        fw_counts = Counter(_framework_label(n['id']) for n in members)
        total = len(members)
        fw_summary = ', '.join(
            f'{fw} ({round(100 * cnt / total)}%)'
            for fw, cnt in fw_counts.most_common(4)
        )
        lines.append(f'  {label_fn} {cid}: {total} nodes — {fw_summary}')
    lines.append('')


def _generate_summary_report(
    nodes: list[dict[str, Any]],
    top_bridge: list[dict[str, Any]],
) -> str:
    """Generate a human-readable convergence zone summary report."""
    lines = ['', 'WP-107 Cross-Framework Cluster Analysis', '=' * 50, '']

    # ── Louvain communities ──────────────────────────────────────────────────
    communities: dict[int, list[dict]] = defaultdict(list)
    for n in nodes:
        cid = n.get('louvain_community_id')
        if cid is not None:
            communities[cid].append(n)
    _render_group_section(lines, 'Graph-Based Communities (Louvain)', communities, 'Community')

    # ── Embedding clusters ───────────────────────────────────────────────────
    emb_clusters: dict[int, list[dict]] = defaultdict(list)
    for n in nodes:
        cid = n.get('embedding_cluster_id')
        if cid is not None:
            emb_clusters[cid].append(n)
    _render_group_section(lines, 'Embedding-Based Clusters (k-means)', emb_clusters, 'Cluster')

    # ── Convergence zones ────────────────────────────────────────────────────
    convergence: dict[tuple, list[dict]] = defaultdict(list)
    for n in nodes:
        lc = n.get('louvain_community_id')
        ec = n.get('embedding_cluster_id')
        if lc is not None and ec is not None:
            convergence[(lc, ec)].append(n)

    top_zones = sorted(convergence.items(), key=lambda kv: -len(kv[1]))[:_REPORT_TOP_N]
    lines.append(f'Convergence Zones (Louvain ∩ k-means) — top {len(top_zones)} of {len(convergence)}')
    lines.append('─' * 50)
    for (lc, ec), members in top_zones:
        fw_counts = Counter(_framework_label(n['id']) for n in members)
        sample_titles = ', '.join(n['title'] for n in members[:3] if n.get('title'))
        lines.append(
            f'  Zone L{lc}/K{ec}: {len(members)} nodes — '
            + ', '.join(f'{fw}({cnt})' for fw, cnt in fw_counts.most_common(3))
        )
        if sample_titles:
            lines.append(f'    e.g. {sample_titles}')
    lines.append('')

    # ── Bridge nodes ─────────────────────────────────────────────────────────
    if top_bridge:
        lines.append('Top Bridge Nodes (Betweenness Centrality)')
        lines.append('─' * 50)
        for i, node in enumerate(top_bridge[:_REPORT_TOP_N], 1):
            score = node.get('betweenness_centrality', 0)
            title = node.get('title', '')
            lines.append(f'  {i:2}. {node["id"]}  betweenness={score:.4f}  {title}')
        lines.append('')

    return '\n'.join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='WP-107: Cross-framework cluster analysis')
    parser.add_argument(
        '--write', action='store_true',
        help='Write cluster annotations back to Framework nodes (default: dry-run)',
    )
    parser.add_argument(
        '--k', type=int, default=None,
        help='Force k-means to k=N (default: auto-select via silhouette)',
    )
    parser.add_argument('--k-min', type=int, default=5, dest='k_min')
    parser.add_argument('--k-max', type=int, default=40, dest='k_max')
    parser.add_argument('--top-bridge', type=int, default=20, dest='top_bridge')
    args = parser.parse_args(argv)

    if args.k is not None and args.k < 2:
        parser.error('--k must be >= 2')
    if args.k is None and args.k_min > args.k_max:
        parser.error(f'--k-min ({args.k_min}) must be <= --k-max ({args.k_max})')

    settings = Settings()
    driver = get_driver(settings)

    try:
        print('Fetching Framework embeddings...', flush=True)
        with driver.session() as s:
            raw_nodes = _fetch_framework_embeddings(s)

        print(f'  {len(raw_nodes)} Framework nodes with embeddings found.')
        if not raw_nodes:
            print(
                'ERROR: No Framework nodes with embeddings. '
                'Has the knowledge layer been ingested?',
                file=sys.stderr,
            )
            sys.exit(1)

        # ── Embedding clustering ──────────────────────────────────────────────
        print('Running embedding k-means clustering...', flush=True)
        embs = np.array([n['embedding'] for n in raw_nodes], dtype=np.float32)
        normalized = _normalize_embeddings(embs)
        k = args.k if args.k is not None else _find_optimal_k(
            normalized, k_min=args.k_min, k_max=args.k_max,
        )
        print(f'  k={k} ({"forced" if args.k is not None else "auto-selected via silhouette"})')
        emb_labels = _kmeans_cluster(normalized, n_clusters=k)
        for i, node in enumerate(raw_nodes):
            node['embedding_cluster_id'] = int(emb_labels[i])

        id_to_node: dict[str, dict[str, Any]] = {n['id']: n for n in raw_nodes}

        # ── MAGE community detection ──────────────────────────────────────────
        print('Running MAGE community detection...', flush=True)
        with driver.session() as s:
            louvain_rows = _run_louvain_on_framework_subgraph(s)
        print(f'  {len(louvain_rows)} community assignments returned.')
        for row in louvain_rows:
            if row['id'] in id_to_node:
                id_to_node[row['id']]['louvain_community_id'] = row['community_id']
            else:
                id_to_node[row['id']] = {
                    'id': row['id'],
                    'louvain_community_id': row['community_id'],
                    'embedding_cluster_id': None,
                    'title': '',
                    'level': '',
                    'domain': '',
                }

        # ── Betweenness centrality ────────────────────────────────────────────
        print('Running MAGE betweenness centrality...', flush=True)
        with driver.session() as s:
            bridge_nodes = _run_betweenness_on_framework_subgraph(s, top_n=args.top_bridge)
        merged_bridge = 0
        for row in bridge_nodes:
            if row['id'] in id_to_node:
                id_to_node[row['id']]['betweenness_centrality'] = row['betweenness_centrality']
                merged_bridge += 1
        print(f'  {len(bridge_nodes)} bridge nodes returned, {merged_bridge} merged into node set.')

        all_nodes = list(id_to_node.values())

        # ── Write-back ────────────────────────────────────────────────────────
        if args.write:
            print('Writing cluster annotations to Framework nodes...', flush=True)
            with driver.session() as s:
                count = _write_cluster_annotations(s, all_nodes)
            print(f'  {count} Framework nodes annotated.')
        else:
            print('  [DRY-RUN] Pass --write to commit annotations to graph.')

        # ── Report ────────────────────────────────────────────────────────────
        report = _generate_summary_report(all_nodes, top_bridge=bridge_nodes)
        print(report)

    except (ServiceUnavailable, AuthError) as exc:
        print(
            f'ERROR: Cannot connect to Memgraph at '
            f'bolt://{settings.memgraph_host}:{settings.memgraph_port} — {exc}',
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        driver.close()


if __name__ == '__main__':
    main()
