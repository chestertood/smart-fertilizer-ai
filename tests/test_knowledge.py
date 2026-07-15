"""RAG knowledge tests — Voyage always mocked, no live API calls."""
import unittest
import numpy as np

from app.services import knowledge


class TestCosineTopK(unittest.TestCase):
    def test_ranks_most_similar_first(self):
        matrix = np.array([
            [1.0, 0.0, 0.0],   # 0
            [0.0, 1.0, 0.0],   # 1
            [0.9, 0.1, 0.0],   # 2  (close to query)
        ], dtype=np.float32)
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        idx, scores = knowledge._cosine_top_k(query, matrix, k=2)
        self.assertEqual(list(idx), [0, 2])          # 0 identical, 2 next
        self.assertTrue(scores[0] >= scores[1])       # descending

    def test_k_larger_than_rows_is_clamped(self):
        matrix = np.array([[1.0, 0.0]], dtype=np.float32)
        idx, scores = knowledge._cosine_top_k(
            np.array([1.0, 0.0], dtype=np.float32), matrix, k=5)
        self.assertEqual(len(idx), 1)

    def test_empty_matrix_returns_empty(self):
        idx, scores = knowledge._cosine_top_k(
            np.array([1.0, 0.0], dtype=np.float32),
            np.zeros((0, 2), dtype=np.float32), k=3)
        self.assertEqual(len(idx), 0)
        self.assertEqual(len(scores), 0)


if __name__ == "__main__":
    unittest.main()
