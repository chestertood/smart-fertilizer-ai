"""Telegram bridge unit tests — no real network calls."""
import unittest

from app.services import telegram_bridge


class TestParseAllowedIds(unittest.TestCase):
    def test_single_id(self):
        self.assertEqual(telegram_bridge.parse_allowed_ids("123"), {123})

    def test_multiple_ids(self):
        self.assertEqual(
            telegram_bridge.parse_allowed_ids("123,456, 789"), {123, 456, 789}
        )

    def test_empty_string(self):
        self.assertEqual(telegram_bridge.parse_allowed_ids(""), set())

    def test_none_treated_as_empty(self):
        self.assertEqual(telegram_bridge.parse_allowed_ids(None), set())


class TestIsAllowed(unittest.TestCase):
    def test_id_in_set(self):
        self.assertTrue(telegram_bridge.is_allowed(123, {123, 456}))

    def test_id_not_in_set(self):
        self.assertFalse(telegram_bridge.is_allowed(999, {123, 456}))

    def test_empty_allowlist_denies_everyone(self):
        # An unset TELEGRAM_ALLOWED_IDS must fail closed, not open.
        self.assertFalse(telegram_bridge.is_allowed(123, set()))


class TestFormatReply(unittest.TestCase):
    def test_plain_text_passthrough(self):
        result = {"text": "EC looks fine.", "param_proposal": None, "growth_proposal": None}
        self.assertEqual(telegram_bridge.format_reply(result), "EC looks fine.")

    def test_param_proposal_appends_pointer(self):
        result = {
            "text": "I'd suggest tightening the EC range.",
            "param_proposal": {"crop": "lettuce"},
            "growth_proposal": None,
        }
        out = telegram_bridge.format_reply(result)
        self.assertIn("I'd suggest tightening the EC range.", out)
        self.assertIn("open the app", out.lower())

    def test_growth_proposal_appends_pointer(self):
        result = {
            "text": "Here's a 4-stage plan.",
            "param_proposal": None,
            "growth_proposal": {"crop": "lettuce", "stages": []},
        }
        out = telegram_bridge.format_reply(result)
        self.assertIn("Here's a 4-stage plan.", out)
        self.assertIn("open the app", out.lower())


if __name__ == "__main__":
    unittest.main()
