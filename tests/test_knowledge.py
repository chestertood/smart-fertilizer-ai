"""RAG knowledge tests — Voyage always mocked, no live API calls."""
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from app.services import knowledge
from app.services import llm_agent


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


def _keyword_embed(texts, input_type):
    """Deterministic fake embedder: vector = keyword counts over a fixed vocab.
    Lets cosine similarity work without calling Voyage."""
    vocab = ["kale", "lettuce", "tomato", "ec"]
    rows = []
    for t in texts:
        low = t.lower()
        rows.append([float(low.count(w)) for w in vocab])
    return np.asarray(rows, dtype=np.float32)


class TestBuildAndRetrieve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.seed = os.path.join(self.tmp, "crops_seed.json")
        self.index = os.path.join(self.tmp, "knowledge_index.npz")
        with open(self.seed, "w", encoding="utf-8") as f:
            json.dump([
                {"crop": "Kale", "stages": [
                    {"name": "Growing", "duration_days": 28,
                     "targets": {"EC": {"min": 1.4, "max": 2.0}}}],
                 "notes": "hardy brassica"},
                {"crop": "Lettuce", "stages": [
                    {"name": "Growing", "duration_days": 21,
                     "targets": {"EC": {"min": 1.2, "max": 1.8}}}],
                 "notes": "cool leafy green"},
            ], f)
        self._patchers = [
            mock.patch.object(knowledge, "_SEED", self.seed),
            mock.patch.object(knowledge, "_INDEX", self.index),
            mock.patch.object(knowledge, "_KNOWLEDGE_DIR", self.tmp),
            mock.patch.object(knowledge, "_embed", _keyword_embed),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def test_build_then_retrieve_ranks_kale_first(self):
        n = knowledge.build_index()
        self.assertEqual(n, 2)
        self.assertTrue(os.path.exists(self.index))
        hits = knowledge.retrieve("kale EC target", k=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("Kale", hits[0]["text"])
        self.assertIn("score", hits[0])

    def test_retrieve_without_index_returns_empty(self):
        # index not built in this test
        self.assertEqual(knowledge.retrieve("kale", k=3), [])

    def test_build_with_no_knowledge_raises(self):
        os.remove(self.seed)
        with self.assertRaises(RuntimeError):
            knowledge.build_index()


class TestLLMInjection(unittest.TestCase):
    def test_knowledge_block_empty_when_no_hits(self):
        with mock.patch.object(llm_agent.knowledge, "retrieve", return_value=[]):
            self.assertEqual(llm_agent._knowledge_block("kale"), "")

    def test_knowledge_block_includes_text_and_source(self):
        hits = [{"text": "Crop: Kale\nEC 1.4-2.0", "source": "seed:Kale", "score": 0.9}]
        with mock.patch.object(llm_agent.knowledge, "retrieve", return_value=hits):
            block = llm_agent._knowledge_block("kale EC")
        self.assertIn("Kale", block)
        self.assertIn("seed:Kale", block)
        self.assertIn("Reference knowledge", block)

    def test_last_user_text_from_string_and_blocks(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": [
                {"type": "text", "text": "second"},
                {"type": "image", "source": {}},
            ]},
        ]
        self.assertEqual(llm_agent._last_user_text(history), "second")


if __name__ == "__main__":
    unittest.main()
