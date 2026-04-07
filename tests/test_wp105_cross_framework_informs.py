"""tests/test_wp105_cross_framework_informs.py — WP-105: Cross-framework INFORMS edges.

Unit tests (no live stack required) and integration tests (require live Memgraph).
"""
from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / 'scripts' / 'create_cross_framework_informs.py'


# ---------------------------------------------------------------------------
# Helpers — import the module under test
# ---------------------------------------------------------------------------

def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'create_cross_framework_informs',
        _SCRIPT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Unit test 1 — cosine_similarity_matrix
# ---------------------------------------------------------------------------

def test_cosine_similarity_matrix():
    """Matrix-multiply cosine sim matches reference (np.dot on normalised vectors)."""
    mod = _import_script()

    rng = np.random.default_rng(42)
    a = rng.random((3, 8)).astype(np.float32)
    b = rng.random((3, 8)).astype(np.float32)

    result = mod.cosine_similarity_matrix(a, b)

    # Reference: manual row-wise normalisation then dot
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    expected = a_norm @ b_norm.T

    assert result.shape == (3, 3)
    np.testing.assert_allclose(result, expected, atol=1e-5)


# ---------------------------------------------------------------------------
# Unit test 2 — threshold_filtering
# ---------------------------------------------------------------------------

def test_threshold_filtering():
    """Pairs above threshold are returned as (i, j, score) tuples."""
    mod = _import_script()

    # 3×4 matrix
    sim = np.array([
        [0.5, 0.8, 0.3, 0.9],
        [0.6, 0.2, 0.7, 0.1],
        [0.4, 0.75, 0.65, 0.85],
    ], dtype=np.float32)

    pairs = mod.threshold_pairs(sim, threshold=0.7)

    # Expected: (row, col, score) where score > 0.7
    # (0,1)=0.8, (0,3)=0.9, (1,2)=0.7 excluded (not strictly above), (2,1)=0.75, (2,3)=0.85
    above = [(i, j, float(sim[i, j])) for i in range(3) for j in range(4) if sim[i, j] > 0.7]
    assert sorted(pairs) == sorted(above)


# ---------------------------------------------------------------------------
# Unit test 3 — level_filtering
# ---------------------------------------------------------------------------

def test_level_filtering():
    """Filter nodes to allowed levels returns only matching rows."""
    mod = _import_script()

    nodes = [
        {'id': 'cobit-2019.edm01', 'level': 'objective', 'embedding': [0.1]},
        {'id': 'cobit-2019.edm01.p1', 'level': 'practice', 'embedding': [0.2]},
        {'id': 'cobit-2019.edm01.p1.a1', 'level': 'activity', 'embedding': [0.3]},
        {'id': 'cobit-2019', 'level': 'framework', 'embedding': [0.4]},
        {'id': 'cobit-2019.apo', 'level': 'domain', 'embedding': [0.5]},
    ]

    allowed = ['objective', 'practice']
    filtered = mod.filter_by_level(nodes, allowed)

    assert len(filtered) == 2
    assert all(n['level'] in allowed for n in filtered)
    ids = [n['id'] for n in filtered]
    assert 'cobit-2019.edm01' in ids
    assert 'cobit-2019.edm01.p1' in ids


# ---------------------------------------------------------------------------
# Unit test 4 — histogram_bins
# ---------------------------------------------------------------------------

def test_histogram_bins():
    """Histogram bin counts are correct for a known list of similarity values."""
    mod = _import_script()

    values = [0.51, 0.53, 0.57, 0.61, 0.62, 0.70, 0.72, 0.80]
    bins = mod.compute_histogram(values, bin_width=0.05, low=0.5, high=0.85)

    # Bins: [0.50,0.55), [0.55,0.60), [0.60,0.65), [0.65,0.70), [0.70,0.75), [0.75,0.80), [0.80,0.85)
    assert bins[(0.50, 0.55)] == 2   # 0.51, 0.53
    assert bins[(0.55, 0.60)] == 1   # 0.57
    assert bins[(0.60, 0.65)] == 2   # 0.61, 0.62
    assert bins[(0.65, 0.70)] == 0
    assert bins[(0.70, 0.75)] == 2   # 0.70, 0.72
    assert bins[(0.75, 0.80)] == 0
    assert bins[(0.80, 0.85)] == 1   # 0.80


# ---------------------------------------------------------------------------
# Unit test 5 — dry_run_creates_no_edges
# ---------------------------------------------------------------------------

def test_dry_run_creates_no_edges():
    """dry_run=True returns candidate pairs without calling session.run for MERGE."""
    mod = _import_script()

    mock_session = MagicMock()

    src_nodes = [
        {'id': 'cobit-2019.edm01', 'level': 'objective', 'embedding': [1.0, 0.0]},
        {'id': 'cobit-2019.apo01', 'level': 'objective', 'embedding': [0.0, 1.0]},
    ]
    dst_nodes = [
        {'id': 'iso-27001-2022.5.1', 'level': 'clause', 'embedding': [0.9, 0.1]},
    ]

    created, errors = mod.create_informs_edges(
        session=mock_session,
        src_nodes=src_nodes,
        dst_nodes=dst_nodes,
        threshold=0.5,
        dry_run=True,
        now='2026-04-07T00:00:00+00:00',
    )

    # dry_run must not invoke session.run for MERGE
    merge_calls = [
        c for c in mock_session.run.call_args_list
        if 'MERGE' in str(c)
    ]
    assert merge_calls == [], 'dry_run must not create any edges'
    assert created == 0, 'dry_run must return created=0'
    assert errors == 0


# ---------------------------------------------------------------------------
# Integration tests — require live Memgraph
# ---------------------------------------------------------------------------

_TEST_PREFIX = 'test-wp105-'


@pytest.fixture(scope='session', autouse=True)
def _cleanup_test_frameworks(test_driver):
    yield
    with test_driver.session() as s:
        s.run('MATCH (f:Framework) WHERE f.id STARTS WITH $prefix DELETE f', prefix=_TEST_PREFIX)


@pytest.mark.integration
def test_informs_edge_created(test_driver):
    """Edge-creation logic creates INFORMS edge with correct properties."""
    mod = _import_script()

    src_id = f'{_TEST_PREFIX}cobit-obj-01'
    dst_id = f'{_TEST_PREFIX}iso-ctrl-01'

    embedding_a = [1.0, 0.0, 0.0, 0.0]
    embedding_b = [0.95, 0.1, 0.0, 0.0]

    now = '2026-04-07T00:00:00+00:00'

    try:
        with test_driver.session() as session:
            session.run(
                'CREATE (:Framework {id: $id, level: $level, embedding: $emb})',
                id=src_id, level='objective', emb=embedding_a,
            )
            session.run(
                'CREATE (:Framework {id: $id, level: $level, embedding: $emb})',
                id=dst_id, level='clause', emb=embedding_b,
            )

        src_nodes = [{'id': src_id, 'level': 'objective', 'embedding': embedding_a}]
        dst_nodes = [{'id': dst_id, 'level': 'clause', 'embedding': embedding_b}]

        with test_driver.session() as session:
            created, errors = mod.create_informs_edges(
                session=session,
                src_nodes=src_nodes,
                dst_nodes=dst_nodes,
                threshold=0.5,
                dry_run=False,
                now=now,
            )

        assert created >= 1, 'Expected at least one edge to be created'
        assert errors == 0

        with test_driver.session() as session:
            result = session.run(
                'MATCH (s:Framework {id: $src})-[r:INFORMS]->(d:Framework {id: $dst}) '
                'RETURN r.source AS source, r.similarity AS similarity, r.created_at AS created_at',
                src=src_id, dst=dst_id,
            ).single()

        assert result is not None, 'INFORMS edge not found after creation'
        assert result['source'] == 'embedding-similarity'
        assert isinstance(result['similarity'], float)
        assert result['created_at'] == now

    finally:
        with test_driver.session() as session:
            session.run('MATCH (n:Framework {id: $id}) DETACH DELETE n', id=src_id)
            session.run('MATCH (n:Framework {id: $id}) DETACH DELETE n', id=dst_id)


@pytest.mark.integration
def test_merge_idempotency(test_driver):
    """Running edge-creation twice for the same pair creates only one INFORMS edge."""
    mod = _import_script()

    src_id = f'{_TEST_PREFIX}cobit-obj-02'
    dst_id = f'{_TEST_PREFIX}iso-ctrl-02'

    embedding_a = [0.8, 0.6, 0.0, 0.0]
    embedding_b = [0.7, 0.7, 0.0, 0.0]
    now = '2026-04-07T00:00:00+00:00'

    try:
        with test_driver.session() as session:
            session.run(
                'CREATE (:Framework {id: $id, level: $level, embedding: $emb})',
                id=src_id, level='objective', emb=embedding_a,
            )
            session.run(
                'CREATE (:Framework {id: $id, level: $level, embedding: $emb})',
                id=dst_id, level='clause', emb=embedding_b,
            )

        src_nodes = [{'id': src_id, 'level': 'objective', 'embedding': embedding_a}]
        dst_nodes = [{'id': dst_id, 'level': 'clause', 'embedding': embedding_b}]

        for _ in range(2):
            with test_driver.session() as session:
                mod.create_informs_edges(
                    session=session,
                    src_nodes=src_nodes,
                    dst_nodes=dst_nodes,
                    threshold=0.5,
                    dry_run=False,
                    now=now,
                )

        with test_driver.session() as session:
            result = session.run(
                'MATCH (:Framework {id: $src})-[r:INFORMS]->(:Framework {id: $dst}) '
                'RETURN count(r) AS cnt',
                src=src_id, dst=dst_id,
            ).single()

        assert result['cnt'] == 1, f'Expected exactly 1 INFORMS edge, got {result["cnt"]}'

    finally:
        with test_driver.session() as session:
            session.run('MATCH (n:Framework {id: $id}) DETACH DELETE n', id=src_id)
            session.run('MATCH (n:Framework {id: $id}) DETACH DELETE n', id=dst_id)


@pytest.mark.integration
def test_existing_edge_source_preserved(test_driver):
    """ON CREATE SET does not overwrite source on an existing INFORMS edge."""
    mod = _import_script()

    src_id = f'{_TEST_PREFIX}cobit-obj-03'
    dst_id = f'{_TEST_PREFIX}iso-ctrl-03'

    embedding_a = [1.0, 0.0, 0.0, 0.0]
    embedding_b = [0.9, 0.3, 0.0, 0.0]
    now = '2026-04-07T00:00:00+00:00'
    original_source = 'nist-csf-2.0-reference-tool'

    try:
        with test_driver.session() as session:
            session.run(
                'CREATE (:Framework {id: $id, level: $level, embedding: $emb})',
                id=src_id, level='objective', emb=embedding_a,
            )
            session.run(
                'CREATE (:Framework {id: $id, level: $level, embedding: $emb})',
                id=dst_id, level='clause', emb=embedding_b,
            )
            # Pre-create an INFORMS edge with a different source
            session.run(
                'MATCH (s:Framework {id: $src}), (d:Framework {id: $dst}) '
                'CREATE (s)-[:INFORMS {source: $source, created_at: $now}]->(d)',
                src=src_id, dst=dst_id, source=original_source, now=now,
            )

        src_nodes = [{'id': src_id, 'level': 'objective', 'embedding': embedding_a}]
        dst_nodes = [{'id': dst_id, 'level': 'clause', 'embedding': embedding_b}]

        with test_driver.session() as session:
            mod.create_informs_edges(
                session=session,
                src_nodes=src_nodes,
                dst_nodes=dst_nodes,
                threshold=0.5,
                dry_run=False,
                now=now,
            )

        with test_driver.session() as session:
            result = session.run(
                'MATCH (:Framework {id: $src})-[r:INFORMS]->(:Framework {id: $dst}) '
                'RETURN r.source AS source',
                src=src_id, dst=dst_id,
            ).single()

        assert result is not None, 'INFORMS edge not found'
        assert result['source'] == original_source, (
            f'Expected source={original_source!r} but got {result["source"]!r}'
        )

    finally:
        with test_driver.session() as session:
            session.run('MATCH (n:Framework {id: $id}) DETACH DELETE n', id=src_id)
            session.run('MATCH (n:Framework {id: $id}) DETACH DELETE n', id=dst_id)
