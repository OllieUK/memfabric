import pathlib
import importlib.util

import numpy as np
import pytest

_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / 'scripts' / 'analyse_cross_framework_clusters.py'


def _import_script():
    spec = importlib.util.spec_from_file_location('analyse_cross_framework_clusters', _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
