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
from datetime import datetime, timezone
from typing import Any

import numpy as np
from neo4j import GraphDatabase
from pydantic_settings import BaseSettings
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


class Settings(BaseSettings):
    memgraph_host: str = 'localhost'
    memgraph_port: int = 7687

    model_config = {'env_file': '.env', 'extra': 'ignore'}


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
    back to each Framework node. Returns count of nodes actually updated."""
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for ann in annotations:
        result = session.run(
            'MATCH (f:Framework {id: $id}) '
            'SET f.louvain_community_id = $louvain, '
            '    f.embedding_cluster_id = $emb_cluster, '
            '    f.betweenness_centrality = $betweenness, '
            '    f.cluster_updated_at = $now '
            'RETURN count(f) AS updated',
            id=ann['id'],
            louvain=ann.get('louvain_community_id'),
            emb_cluster=ann.get('embedding_cluster_id'),
            betweenness=ann.get('betweenness_centrality'),
            now=now,
        )
        rec = result.single()
        if rec:
            count += rec['updated']
    return count
