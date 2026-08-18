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


class TestChatHistory(unittest.TestCase):
    def test_get_unknown_chat_is_empty(self):
        history = telegram_bridge.ChatHistory(max_messages=10)
        self.assertEqual(history.get(999), [])

    def test_append_and_get(self):
        history = telegram_bridge.ChatHistory(max_messages=10)
        history.append(1, "user", "hi")
        history.append(1, "assistant", "hello")
        self.assertEqual(
            history.get(1),
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        )

    def test_chats_are_isolated(self):
        history = telegram_bridge.ChatHistory(max_messages=10)
        history.append(1, "user", "chat one")
        history.append(2, "user", "chat two")
        self.assertEqual(history.get(1), [{"role": "user", "content": "chat one"}])
        self.assertEqual(history.get(2), [{"role": "user", "content": "chat two"}])

    def test_caps_at_max_messages(self):
        history = telegram_bridge.ChatHistory(max_messages=4)
        for i in range(6):
            history.append(1, "user", f"msg{i}")
        # Oldest messages drop first; only the most recent 4 remain.
        self.assertEqual(
            [m["content"] for m in history.get(1)], ["msg2", "msg3", "msg4", "msg5"]
        )


class TestBuildRequests(unittest.TestCase):
    def test_get_updates_url(self):
        url = telegram_bridge._get_updates_url("TOKEN123", offset=42)
        self.assertEqual(
            url,
            "https://api.telegram.org/botTOKEN123/getUpdates"
            "?timeout=30&offset=42",
        )

    def test_get_updates_url_no_offset(self):
        url = telegram_bridge._get_updates_url("TOKEN123", offset=None)
        self.assertEqual(
            url, "https://api.telegram.org/botTOKEN123/getUpdates?timeout=30"
        )

    def test_send_message_url(self):
        url = telegram_bridge._send_message_url("TOKEN123")
        self.assertEqual(
            url, "https://api.telegram.org/botTOKEN123/sendMessage"
        )


class TestStatusSummary(unittest.TestCase):
    def test_no_readings_yet(self):
        self.assertEqual(
            telegram_bridge.status_summary({}, {}, 10.0), "No sensor data yet"
        )

    def test_formats_known_sensors_with_target_status(self):
        readings = {"EC": 2.1, "PH": 6.2, "Temperature": 24.5, "Humidity": 65.0}
        targets = {
            "EC": {"min": 1.5, "max": 2.5},
            "PH": {"min": 5.5, "max": 6.5},
            "Temperature": {"min": 18.0, "max": 28.0},
            "Humidity": {"min": 40.0, "max": 80.0},
        }
        out = telegram_bridge.status_summary(readings, targets, 40.0)
        self.assertIn("EC: 2.10 mS/cm", out)
        self.assertIn("PH: 6.20 pH", out)
        self.assertIn("Tank ~40.0 L", out)

    def test_missing_value_reported_as_no_data(self):
        out = telegram_bridge.status_summary({"EC": 2.1}, {}, 10.0)
        self.assertIn("Temperature: no data", out)


class TestReplyKeyboard(unittest.TestCase):
    def test_contains_both_buttons(self):
        kb = telegram_bridge.reply_keyboard()
        buttons = [b for row in kb["keyboard"] for b in row]
        self.assertIn("Check status", buttons)
        self.assertIn("Recommend dosing", buttons)
        self.assertTrue(kb["resize_keyboard"])


class TestFormatRecommendation(unittest.TestCase):
    def test_no_actions_needed(self):
        result = {"summary": "All good.", "actions": []}
        out = telegram_bridge.format_recommendation(result)
        self.assertIn("All good.", out)
        self.assertIn("no dosing needed", out.lower())

    def test_actions_omitted_detail_goes_to_separate_messages(self):
        # Per-action detail now lives in format_dose_proposal, sent as its
        # own approval message — the summary line stays action-free.
        result = {
            "summary": "EC is low.",
            "actions": [{"pump": "Nutrient A", "amount_ml": 12.5, "reason": "raise EC"}],
        }
        out = telegram_bridge.format_recommendation(result)
        self.assertIn("EC is low.", out)
        self.assertNotIn("Nutrient A", out)
        self.assertNotIn("no dosing needed", out.lower())


class TestPendingProposals(unittest.TestCase):
    def test_register_returns_unique_ids(self):
        pending = telegram_bridge.PendingProposals()
        pid1 = pending.register("dose", {"pump": "A"}, chat_id=1)
        pid2 = pending.register("dose", {"pump": "B"}, chat_id=1)
        self.assertNotEqual(pid1, pid2)

    def test_get_returns_registered_record(self):
        pending = telegram_bridge.PendingProposals()
        pid = pending.register("param", {"crop": "lettuce"}, chat_id=42)
        record = pending.get(pid)
        self.assertEqual(record["kind"], "param")
        self.assertEqual(record["data"], {"crop": "lettuce"})
        self.assertEqual(record["chat_id"], 42)

    def test_get_unknown_id_is_none(self):
        pending = telegram_bridge.PendingProposals()
        self.assertIsNone(pending.get("nope"))

    def test_pop_removes_record(self):
        pending = telegram_bridge.PendingProposals()
        pid = pending.register("dose", {"pump": "A"}, chat_id=1)
        first = pending.pop(pid)
        second = pending.pop(pid)
        self.assertIsNotNone(first)
        self.assertIsNone(second)  # second tap: already handled


class TestApprovalKeyboard(unittest.TestCase):
    def test_has_approve_and_reject_with_matching_pid(self):
        kb = telegram_bridge.approval_keyboard("7")
        buttons = kb["inline_keyboard"][0]
        self.assertEqual(buttons[0]["callback_data"], "approve:7")
        self.assertEqual(buttons[1]["callback_data"], "reject:7")


class TestFormatDoseProposal(unittest.TestCase):
    def test_includes_pump_amount_and_reason(self):
        out = telegram_bridge.format_dose_proposal(
            {"pump": "Nutrient A", "amount_ml": 12.5, "reason": "raise EC"}
        )
        self.assertIn("Nutrient A", out)
        self.assertIn("12.5", out)
        self.assertIn("raise EC", out)


class TestFormatParamProposal(unittest.TestCase):
    def test_includes_crop_and_ranges(self):
        proposal = {
            "crop": "lettuce",
            "targets": {"EC": {"min": 1.5, "max": 2.5}, "PH": {"min": 5.5, "max": 6.5}},
        }
        out = telegram_bridge.format_param_proposal(proposal)
        self.assertIn("lettuce", out)
        self.assertIn("1.5", out)
        self.assertIn("2.5", out)
        self.assertIn("mS/cm", out)

    def test_missing_sensor_omitted(self):
        proposal = {"crop": "lettuce", "targets": {"EC": {"min": 1.5, "max": 2.5}}}
        out = telegram_bridge.format_param_proposal(proposal)
        self.assertNotIn("Temperature", out)


class TestFormatGrowthProposal(unittest.TestCase):
    def test_includes_crop_and_stage_names(self):
        proposal = {
            "crop": "lettuce",
            "stages": [
                {"name": "Seedling", "duration_days": 10,
                 "targets": {"EC": {"min": 0.8, "max": 1.2}}},
                {"name": "Vegetative", "duration_days": 20, "targets": {}},
            ],
        }
        out = telegram_bridge.format_growth_proposal(proposal)
        self.assertIn("lettuce", out)
        self.assertIn("Seedling", out)
        self.assertIn("10 days", out)
        self.assertIn("Vegetative", out)


class TestStatusImage(unittest.TestCase):
    def _readings(self):
        return {"EC": 2.1, "PH": 6.0, "Temperature": 24.5, "Humidity": 65.0}

    def _targets(self):
        return {
            "EC": {"min": 1.5, "max": 2.5},
            "PH": {"min": 5.5, "max": 6.5},
            "Temperature": {"min": 18.0, "max": 28.0},
            "Humidity": {"min": 40.0, "max": 80.0},
        }

    def test_returns_valid_png(self):
        from io import BytesIO
        from PIL import Image
        png_bytes = telegram_bridge.status_image(self._readings(), self._targets())
        self.assertGreater(len(png_bytes), 0)
        img = Image.open(BytesIO(png_bytes))
        self.assertEqual(img.format, "PNG")

    def test_dimensions_are_2x2_grid(self):
        from io import BytesIO
        from PIL import Image
        png_bytes = telegram_bridge.status_image(self._readings(), self._targets())
        img = Image.open(BytesIO(png_bytes))
        self.assertEqual(img.size, (832, 472))

    def test_missing_reading_does_not_crash(self):
        from io import BytesIO
        from PIL import Image
        readings = {"EC": 2.1, "PH": 6.0}  # Temperature/Humidity absent
        png_bytes = telegram_bridge.status_image(readings, self._targets())
        Image.open(BytesIO(png_bytes)).load()  # round-trips without error

    def test_empty_readings_still_renders(self):
        from io import BytesIO
        from PIL import Image
        png_bytes = telegram_bridge.status_image({}, {})
        img = Image.open(BytesIO(png_bytes))
        self.assertEqual(img.size, (832, 472))


if __name__ == "__main__":
    unittest.main()
