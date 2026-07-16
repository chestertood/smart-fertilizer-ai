"""LLM request-shaping tests — no API calls, no network."""
import unittest

from app.services import llm_agent


class TestThinkingGate(unittest.TestCase):
    def test_adaptive_models_get_thinking(self):
        for model in ("claude-opus-4-8", "claude-sonnet-5"):
            self.assertEqual(
                llm_agent._thinking(model), {"thinking": {"type": "adaptive"}}
            )

    def test_haiku_gets_no_thinking(self):
        # Haiku 4.5 errors on adaptive; it must be omitted, not disabled.
        self.assertEqual(llm_agent._thinking("claude-haiku-4-5"), {})

    def test_unknown_model_gets_no_thinking(self):
        self.assertEqual(llm_agent._thinking("some-future-model"), {})

    def test_gate_does_not_drift_from_model_picker(self):
        # Every adaptive model must still be offered; a rename in
        # AVAILABLE_MODELS would otherwise silently drop thinking.
        offered = {m[0] for m in llm_agent.AVAILABLE_MODELS}
        self.assertTrue(llm_agent._ADAPTIVE_MODELS <= offered)


class TestKnowledgeBlock(unittest.TestCase):
    def test_seed_is_injected(self):
        block = llm_agent._knowledge_block()
        self.assertIn("Morning Glory", block)
        self.assertIn("ผักบุ้ง", block)  # Thai survives ensure_ascii=False


if __name__ == "__main__":
    unittest.main()
