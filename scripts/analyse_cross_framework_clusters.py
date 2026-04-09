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
    """Sweep k from k_min to k_max; return k with highest silhouette score."""
    n = len(embs)
    k_max = min(k_max, n - 1)
    k_min = min(k_min, k_max)
    best_k, best_score = k_min, -1.0
    for k in range(k_min, k_max + 1):
        labels = _kmeans_cluster(embs, n_clusters=k, random_state=random_state)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(embs, labels, metric='cosine')
        if score > best_score:
            best_score, best_k = score, k
    return best_k
