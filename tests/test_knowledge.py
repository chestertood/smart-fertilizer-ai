"""RAG knowledge tests — Voyage always mocked, no live API calls."""
import os
import unittest
from unittest import mock

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


class TestEmbed(unittest.TestCase):
    def test_embed_returns_float32_matrix(self):
        fake_client = mock.Mock()
        fake_client.embed.return_value = mock.Mock(
            embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        with mock.patch.object(knowledge, "_voyage", return_value=fake_client):
            out = knowledge._embed(["a", "b"], input_type="document")
        self.assertEqual(out.shape, (2, 3))
        self.assertEqual(out.dtype, np.float32)
        fake_client.embed.assert_called_once()
        # input_type is forwarded to Voyage
        _, kwargs = fake_client.embed.call_args
        self.assertEqual(kwargs.get("input_type"), "document")

    def test_voyage_without_key_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                knowledge._voyage()


if __name__ == "__main__":
    unittest.main()
