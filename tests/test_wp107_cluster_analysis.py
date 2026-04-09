import pathlib
import importlib.util

import numpy as np
import pytest

_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / 'scripts' / 'analyse_cross_framework_clusters.py'

# Cache at module level — exec_module triggers heavy sklearn/numpy imports on every call.
def _import_script():
    return _MODULE


def _load_module():
    spec = importlib.util.spec_from_file_location('analyse_cross_framework_clusters', _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_MODULE = _load_module()


class TestNormalizeEmbeddings:
    def test_unit_vectors_unchanged(self):
        mod = _import_script()
        v = np.array([[1.0, 0.0], [0.0, 1.0]])
        result = mod._normalize_embeddings(v)
        np.testing.assert_allclose(result, v, atol=1e-6)

    def test_zero_vector_stays_zero(self):
        mod = _import_script()
        v = np.array([[0.0, 0.0], [1.0, 0.0]])
        result = mod._normalize_embeddings(v)
        np.testing.assert_allclose(result[0], [0.0, 0.0])
        np.testing.assert_allclose(result[1], [1.0, 0.0], atol=1e-6)

    def test_normalizes_arbitrary_vector(self):
        mod = _import_script()
        v = np.array([[3.0, 4.0]])
        result = mod._normalize_embeddings(v)
        np.testing.assert_allclose(result[0], [0.6, 0.8], atol=1e-6)


class TestKmeansCluster:
    def test_three_tight_clusters(self):
        """Three clearly separated groups should land in 3 clusters."""
        mod = _import_script()
        rng = np.random.default_rng(42)
        a = rng.normal([1, 0], 0.01, (20, 2))
        b = rng.normal([0, 1], 0.01, (20, 2))
        c = rng.normal([-1, 0], 0.01, (20, 2))
        embs = np.vstack([a, b, c]).astype(np.float32)
        labels = mod._kmeans_cluster(embs, n_clusters=3, random_state=0)
        # All points in the same original group should share a label
        assert len(set(labels[:20])) == 1
        assert len(set(labels[20:40])) == 1
        assert len(set(labels[40:60])) == 1

    def test_returns_integer_array_of_right_length(self):
        mod = _import_script()
        embs = np.random.default_rng(0).normal(size=(30, 8)).astype(np.float32)
        labels = mod._kmeans_cluster(embs, n_clusters=5, random_state=0)
        assert labels.shape == (30,)
        assert labels.dtype.kind == 'i'  # integer

    def test_single_cluster_falls_back(self):
        """When n_clusters >= n_samples, should fall back to k=1."""
        mod = _import_script()
        embs = np.random.default_rng(0).normal(size=(2, 4)).astype(np.float32)
        labels = mod._kmeans_cluster(embs, n_clusters=10, random_state=0)
        assert labels.shape == (2,)
        assert len(set(labels.tolist())) == 1  # all in the same cluster


class TestFindOptimalK:
    def test_recovers_correct_k(self):
        """find_optimal_k should return k=3 for three tight clusters."""
        mod = _import_script()
        rng = np.random.default_rng(7)
        a = rng.normal([5, 0], 0.05, (30, 2))
        b = rng.normal([0, 5], 0.05, (30, 2))
        c = rng.normal([-5, 0], 0.05, (30, 2))
        embs = np.vstack([a, b, c]).astype(np.float32)
        k = mod._find_optimal_k(embs, k_min=2, k_max=8, random_state=0)
        assert k == 3

    def test_respects_k_min_when_data_is_small(self):
        mod = _import_script()
        embs = np.random.default_rng(0).normal(size=(10, 4)).astype(np.float32)
        k = mod._find_optimal_k(embs, k_min=2, k_max=5, random_state=0)
        assert 2 <= k <= 5

    def test_warns_and_returns_k_min_when_no_valid_silhouette(self, capsys):
        """With only 3 samples and k_min=2, k_max=2: only k=2 is tried.
        KMeans with k=2 on 3 points gives 2 distinct labels, so silhouette
        runs fine — but with k_min=3 on 3 samples, k_max clamps to 2,
        k_min clamps to 2, and the single iteration at k=2 gives 2 labels
        which is >= 2, so silhouette does run. Use a true degenerate: 2 samples.
        With 2 samples, k_max clamps to 1, k_min clamps to 1, KMeans k=1
        gives only 1 label, silhouette guard fires, no valid score found."""
        mod = _import_script()
        embs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        k = mod._find_optimal_k(embs, k_min=2, k_max=5, random_state=0)
        assert k == 1  # clamped to k_max = n-1 = 1, then k_min clamped to 1
        captured = capsys.readouterr()
        assert 'WARNING' in captured.err


# ── Integration fixtures ─────────────────────────────────────────────────────

_TEST_PREFIX = 'test-wp107-'


@pytest.fixture(scope='session')
def test_driver():
    from neo4j import GraphDatabase as _GDB
    driver = _GDB.driver('bolt://localhost:7687', auth=('', ''))
    try:
        with driver.session() as s:
            s.run('RETURN 1')
    except Exception:
        pytest.skip('Memgraph not reachable')
    yield driver
    driver.close()


@pytest.fixture(scope='session')
def seeded_framework_graph(test_driver):
    """Seed 9 Framework nodes in 3 groups with known embeddings and INFORMS edges."""
    dim = 384
    groups = {
        'access': [f'{_TEST_PREFIX}access-{i}' for i in range(3)],
        'audit':  [f'{_TEST_PREFIX}audit-{i}' for i in range(3)],
        'risk':   [f'{_TEST_PREFIX}risk-{i}' for i in range(3)],
    }
    group_vecs = {
        'access': ([1.0] + [0.0] * (dim - 1)),
        'audit':  ([0.0, 1.0] + [0.0] * (dim - 2)),
        'risk':   ([0.0, 0.0, 1.0] + [0.0] * (dim - 3)),
    }
    with test_driver.session() as s:
        for group, ids in groups.items():
            vec = group_vecs[group]
            for node_id in ids:
                s.run(
                    'MERGE (f:Framework {id: $id}) '
                    'SET f.title = $title, f.level = $level, '
                    'f.embedding = $emb, f.domain = $domain',
                    id=node_id,
                    title=f'{group} {node_id}',
                    level='clause',
                    emb=vec,
                    domain='test',
                )
        for group, ids in groups.items():
            for i in range(len(ids) - 1):
                s.run(
                    'MATCH (a:Framework {id: $a}), (b:Framework {id: $b}) '
                    'MERGE (a)-[:INFORMS]->(b)',
                    a=ids[i],
                    b=ids[i + 1],
                )
    yield groups
    with test_driver.session() as s:
        s.run(
            'MATCH (f:Framework) WHERE f.id STARTS WITH $prefix DETACH DELETE f',
            prefix=_TEST_PREFIX,
        )


# ── Integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestFetchFrameworkEmbeddings:
    def test_returns_seeded_nodes(self, seeded_framework_graph, test_driver):
        mod = _import_script()
        with test_driver.session() as s:
            nodes = mod._fetch_framework_embeddings(s)
        seeded_ids = {nid for ids in seeded_framework_graph.values() for nid in ids}
        fetched_ids = {n['id'] for n in nodes}
        assert seeded_ids.issubset(fetched_ids)

    def test_all_returned_nodes_have_embedding(self, seeded_framework_graph, test_driver):
        mod = _import_script()
        with test_driver.session() as s:
            nodes = mod._fetch_framework_embeddings(s)
        for n in nodes:
            assert n['embedding'] is not None
            assert len(n['embedding']) > 0


@pytest.mark.integration
class TestMageLouvainIntegration:
    def test_louvain_returns_community_ids_for_seeded_nodes(self, seeded_framework_graph, test_driver):
        mod = _import_script()
        with test_driver.session() as s:
            communities = mod._run_louvain_on_framework_subgraph(s)
        seeded_ids = {nid for ids in seeded_framework_graph.values() for nid in ids}
        found_ids = {r['id'] for r in communities}
        assert seeded_ids.issubset(found_ids), f'Missing: {seeded_ids - found_ids}'

    def test_louvain_assigns_integer_community_ids(self, seeded_framework_graph, test_driver):
        mod = _import_script()
        with test_driver.session() as s:
            communities = mod._run_louvain_on_framework_subgraph(s)
        for row in communities:
            assert isinstance(row['community_id'], int)


@pytest.mark.integration
class TestBetweennessIntegration:
    def test_betweenness_returns_scores(self, seeded_framework_graph, test_driver):
        mod = _import_script()
        with test_driver.session() as s:
            results = mod._run_betweenness_on_framework_subgraph(s, top_n=5)
        assert len(results) > 0
        for r in results:
            assert 'id' in r
            assert 'betweenness_centrality' in r
            assert isinstance(r['betweenness_centrality'], float)


@pytest.mark.integration
class TestWriteBackIntegration:
    def test_write_annotations_persists_cluster_id(self, seeded_framework_graph, test_driver):
        mod = _import_script()
        sample_ids = [ids[0] for ids in seeded_framework_graph.values()]
        annotations = [
            {
                'id': nid,
                'louvain_community_id': i,
                'embedding_cluster_id': i,
                'betweenness_centrality': 0.1 * i,
            }
            for i, nid in enumerate(sample_ids)
        ]
        with test_driver.session() as s:
            count = mod._write_cluster_annotations(s, annotations)
        assert count == len(sample_ids)
        with test_driver.session() as s:
            for ann in annotations:
                rec = s.run(
                    'MATCH (f:Framework {id: $id}) '
                    'RETURN f.louvain_community_id AS louvain, '
                    '       f.embedding_cluster_id AS emb_cluster, '
                    '       f.betweenness_centrality AS betweenness',
                    id=ann['id'],
                ).single()
                assert rec['louvain'] == ann['louvain_community_id']
                assert rec['emb_cluster'] == ann['embedding_cluster_id']
                assert abs(rec['betweenness'] - ann['betweenness_centrality']) < 1e-6


class TestGenerateSummaryReport:
    def _make_nodes(self):
        return [
            {
                'id': 'iso-27001-2022.A.5.1',
                'title': 'Policies for IS',
                'level': 'clause',
                'domain': None,
                'louvain_community_id': 0,
                'embedding_cluster_id': 0,
            },
            {
                'id': 'nist-csf.GV.OC-01',
                'title': 'Mission understanding',
                'level': 'subcategory',
                'domain': None,
                'louvain_community_id': 0,
                'embedding_cluster_id': 0,
            },
            {
                'id': 'attack-enterprise.T1566',
                'title': 'Phishing',
                'level': 'technique',
                'domain': 'enterprise',
                'louvain_community_id': 1,
                'embedding_cluster_id': 1,
            },
        ]

    def test_report_is_non_empty_string(self):
        mod = _import_script()
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=[])
        assert 'WP-107 Cross-Framework Cluster Analysis' in report

    def test_report_contains_community_section(self):
        mod = _import_script()
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=[])
        assert 'Community' in report or 'community' in report

    def test_report_includes_iso_framework_label(self):
        mod = _import_script()
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=[])
        assert 'ISO 27001' in report

    def test_report_includes_attack_framework_label(self):
        mod = _import_script()
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=[])
        assert 'ATT&CK' in report

    def test_report_includes_bridge_nodes_when_provided(self):
        mod = _import_script()
        bridge = [{'id': 'sp800-53r5.AC-1', 'title': 'Access Control Policy', 'betweenness_centrality': 0.9}]
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=bridge)
        assert 'sp800-53r5.AC-1' in report

    def test_report_omits_bridge_section_when_empty(self):
        mod = _import_script()
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=[])
        # Bridge section heading must be absent when no bridge nodes supplied
        assert 'Bridge' not in report

    def test_report_includes_convergence_zone_section(self):
        mod = _import_script()
        report = mod._generate_summary_report(self._make_nodes(), top_bridge=[])
        assert 'Convergence' in report or 'convergence' in report
