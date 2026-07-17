"""Unit tests for the safety-critical core logic.

Run with:  python -m unittest discover tests -v
Stdlib unittest only — no extra dependencies.
"""

import datetime
import os
import re
import tempfile
import unittest
from unittest import mock

# Point the config store at a temp dir before anything imports it, so tests
# never touch the real data/app_config.json.
import config.store as store

_TMP = tempfile.mkdtemp()
store._DATA_DIR = _TMP
store._CONFIG_PATH = os.path.join(_TMP, "app_config.json")

from config.sensors import get_status  # noqa: E402
from config.profiles import AppState, DEFAULT_PROFILE  # noqa: E402
from app.components.sensor_card import _bar_fraction  # noqa: E402
from app.views.parameters import (  # noqa: E402
    invalid_target_sensors, is_number, num_field,
)
from app.services.actuators import (  # noqa: E402
    ActuatorHub, CooldownError, DOSE_COOLDOWN_S,
)
from app.services.database import Database  # noqa: E402


class TestGetStatus(unittest.TestCase):
    def test_below_min_is_too_low(self):
        label, color = get_status(1.0, 1.4, 2.0)
        self.assertEqual(label, "Too Low")
        self.assertEqual(color, "#F44336")

    def test_above_max_is_too_high(self):
        label, color = get_status(2.5, 1.4, 2.0)
        self.assertEqual(label, "Too High")

    def test_mid_range_is_normal(self):
        label, _ = get_status(1.7, 1.4, 2.0)
        self.assertEqual(label, "Normal")

    def test_edge_of_range_is_warning(self):
        label, _ = get_status(1.41, 1.4, 2.0)
        self.assertEqual(label, "Warning")


class TestBarFraction(unittest.TestCase):
    def test_too_low_fills_bar_like_too_high(self):
        # Symmetry: out of range in either direction = full bar.
        self.assertEqual(_bar_fraction(0.5, 1.4, 2.0), 1.0)
        self.assertEqual(_bar_fraction(3.0, 1.4, 2.0), 1.0)

    def test_in_range_proportional(self):
        self.assertAlmostEqual(_bar_fraction(1.7, 1.4, 2.0), 0.5)

    def test_degenerate_range(self):
        self.assertEqual(_bar_fraction(1.0, 2.0, 2.0), 0.0)


class TestDoseSafety(unittest.TestCase):
    def setUp(self):
        self.hub = ActuatorHub()
        self.hub.connect_all()

    def test_dose_clamped_to_max(self):
        dispensed = self.hub.dose("pH Up", 999)
        self.assertEqual(dispensed, self.hub.pumps["pH Up"].max_dose)

    def test_cooldown_blocks_second_dose(self):
        self.hub.dose("Nutrient A", 5)
        with self.assertRaises(CooldownError):
            self.hub.dose("Nutrient A", 5)

    def test_cooldown_is_per_pump(self):
        self.hub.dose("Nutrient A", 5)
        # A different pump is not affected by Nutrient A's cooldown.
        self.assertEqual(self.hub.dose("Nutrient B", 5), 5.0)

    def test_cooldown_expires(self):
        pump = self.hub.pumps["Water"]
        self.hub.dose("Water", 10)
        # Simulate the cooldown having elapsed.
        pump._last_dose_at -= DOSE_COOLDOWN_S + 1
        self.assertEqual(self.hub.dose("Water", 10), 10.0)

    def test_unknown_pump_raises(self):
        with self.assertRaises(KeyError):
            self.hub.dose("Nope", 1)


class TestGrowthStages(unittest.TestCase):
    def _fresh_state(self) -> AppState:
        s = AppState()
        s.growth = {}
        return s

    def _add_stages(self, s: AppState):
        s.add_stage("Seedling", 5)
        s.add_stage("Growing", 10)
        s.add_stage("Mature", 15)

    def test_no_tracking_returns_none(self):
        s = self._fresh_state()
        self.assertIsNone(s.current_stage_info())

    def _plan(self, *names):
        return [
            {"name": n, "duration_days": 7,
             "targets": {"EC": {"min": 1.0, "max": 1.6}}}
            for n in names
        ]

    def test_set_stages_replaces_instead_of_appending(self):
        s = self._fresh_state()
        s.set_stages(self._plan("Seedling", "Growing"))
        s.set_stages(self._plan("Seedling", "Growing", "Mature"))
        self.assertEqual(
            [st["name"] for st in s.growth_config()["stages"]],
            ["Seedling", "Growing", "Mature"],
        )

    def test_set_stages_applies_proposed_targets(self):
        s = self._fresh_state()
        self.assertEqual(s.set_stages(self._plan("Seedling")), 1)
        self.assertEqual(
            s.growth_config()["stages"][0]["targets"]["EC"],
            {"min": 1.0, "max": 1.6},
        )

    def test_set_stages_skips_bad_entries_and_ranges(self):
        s = self._fresh_state()
        count = s.set_stages([
            {"name": "Ok", "duration_days": 5, "targets": {"EC": {"min": 2.0, "max": 1.0}}},
            {"name": "No days"},
        ])
        self.assertEqual(count, 1)
        self.assertNotEqual(
            s.growth_config()["stages"][0]["targets"]["EC"], {"min": 2.0, "max": 1.0}
        )

    def test_set_stages_keeps_existing_when_nothing_usable(self):
        s = self._fresh_state()
        self._add_stages(s)
        self.assertEqual(s.set_stages([{"bogus": 1}]), 0)
        self.assertEqual(len(s.growth_config()["stages"]), 3)

    def test_stage_progression(self):
        s = self._fresh_state()
        self._add_stages(s)
        past = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        s.start_planting(past)
        info = s.current_stage_info()
        self.assertEqual(info["stage_index"], 1)  # day 7 -> Growing
        self.assertEqual(info["day_in_stage"], 3)

    def test_clamps_to_last_stage_after_end(self):
        s = self._fresh_state()
        self._add_stages(s)
        past = (datetime.date.today() - datetime.timedelta(days=100)).isoformat()
        s.start_planting(past)
        info = s.current_stage_info()
        self.assertEqual(info["stage_index"], 2)
        self.assertEqual(info["overall_pct"], 100.0)

    def test_targets_route_to_current_stage(self):
        s = self._fresh_state()
        self._add_stages(s)
        s.growth_config()["stages"][0]["targets"]["EC"] = {"min": 0.8, "max": 1.2}
        s.start_planting()  # today -> stage 0
        self.assertEqual(s.targets["EC"], {"min": 0.8, "max": 1.2})

    def test_stop_planting_falls_back_to_flat(self):
        s = self._fresh_state()
        self._add_stages(s)
        s.start_planting()
        s.stop_planting()
        self.assertIsNone(s.current_stage_info())

    def test_invalid_planting_date_returns_none(self):
        s = self._fresh_state()
        self._add_stages(s)
        s.growth_config()["planting_date"] = "not-a-date"
        self.assertIsNone(s.current_stage_info())


class TestProfiles(unittest.TestCase):
    def test_create_and_delete_profile(self):
        s = AppState()
        self.assertTrue(s.create_profile("TestCrop"))
        self.assertIn("TestCrop", s.profile_names)
        self.assertFalse(s.create_profile("TestCrop"))  # duplicate
        self.assertFalse(s.create_profile("  "))        # blank
        self.assertTrue(s.delete_profile("TestCrop"))
        self.assertNotIn("TestCrop", s.profile_names)

    def test_default_profile_always_present_and_undeletable(self):
        s = AppState()
        self.assertIn(DEFAULT_PROFILE, s.profile_names)
        self.assertFalse(s.delete_profile(DEFAULT_PROFILE))
        self.assertIn(DEFAULT_PROFILE, s.profile_names)

    def test_default_survives_deleting_everything_else(self):
        s = AppState()
        s.create_profile("TestCrop")
        for name in list(s.profile_names):
            s.delete_profile(name)
        self.assertEqual(s.profile_names, [DEFAULT_PROFILE])
        self.assertEqual(s.active_profile, DEFAULT_PROFILE)

    def test_default_cannot_be_hidden_by_saved_config(self):
        # A config written before Default became permanent (or hand-edited)
        # must not be able to hide it.
        with mock.patch.object(
            store, "load", return_value={"hidden_profiles": [DEFAULT_PROFILE]}
        ):
            s = AppState()
        self.assertIn(DEFAULT_PROFILE, s.profile_names)

    def test_tank_capacity(self):
        s = AppState()
        s.water_tank = {"width_cm": 30.0, "length_cm": 30.0, "height_cm": 40.0}
        self.assertEqual(s.tank_capacity_liters(), 36.0)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(tempfile.mkdtemp(), "t.db"))

    def test_reading_roundtrip_with_stage(self):
        self.db.log_reading(
            {"EC": 2.1, "PH": 6.2, "Temperature": 24.5, "Humidity": 65.0},
            stage="Seedling",
        )
        row = self.db.recent_readings(1)[0]
        self.assertEqual(row["ec"], 2.1)
        self.assertEqual(row["stage"], "Seedling")

    def test_nan_stored_as_null(self):
        self.db.log_reading({"EC": float("nan"), "PH": 6.0})
        row = self.db.recent_readings(1)[0]
        self.assertIsNone(row["ec"])
        self.assertEqual(row["ph"], 6.0)

    def test_dose_roundtrip(self):
        self.db.log_dose("Nutrient A", 10.0, "manual")
        row = self.db.recent_doses(1)[0]
        self.assertEqual(row["pump"], "Nutrient A")
        self.assertEqual(row["source"], "manual")


class TestNumericInputFilter(unittest.TestCase):
    """The Parameters page must not accept letters in fields that have to
    parse as numbers — keyboard_type alone doesn't stop a physical keyboard
    or a paste."""

    @staticmethod
    def _typed(field, text: str) -> str:
        """What survives the filter: Flet maps InputFilter onto Flutter's
        allow-formatter, which keeps every character the regex matches and
        drops the rest."""
        return "".join(re.findall(field.input_filter.regex_string, text))

    def test_letters_are_dropped(self):
        self.assertEqual(self._typed(num_field(), "12abc3"), "123")
        self.assertEqual(self._typed(num_field(), "ABC"), "")
        self.assertEqual(self._typed(num_field(signed=True), "-4a2"), "-42")

    def test_real_numbers_pass_through(self):
        for text in ("2.5", "0", "100", "6.20"):
            self.assertEqual(self._typed(num_field(), text), text)

    def test_signed_allows_minus_unsigned_strips_it(self):
        # Calibration offsets legitimately go negative; millilitres don't.
        self.assertEqual(self._typed(num_field(signed=True), "-0.3"), "-0.3")
        self.assertEqual(self._typed(num_field(), "-5"), "5")

    def test_partial_input_survives(self):
        # parse_float()/revert_on_blur() rely on being able to clear a field
        # and type through intermediate states.
        for text in ("", "2.", "."):
            self.assertEqual(self._typed(num_field(), text), text)


class TestSaveBlocksNonNumericText(unittest.TestCase):
    """do_save() refuses while any mounted numeric box holds non-numeric text.

    This is the guard that catches letters: parse_float() keeps the last good
    value when the text won't parse, so state stays valid and every
    state-based check passes while the box still reads "abc".
    """

    def test_letters_are_not_numbers(self):
        for text in ("abc", "12abc", "1.2.3", "--5", "", None, "."):
            self.assertFalse(is_number(text), text)

    def test_real_numbers_are(self):
        for text in ("0", "2.5", "-0.3", "100", "6.20"):
            self.assertTrue(is_number(text), text)

    def test_save_blocked_when_a_box_holds_letters(self):
        # Mirrors do_save()'s condition against a stand-in for the mounted
        # fields, including the case that matters: state is still valid.
        fields = [num_field(value="2.5"), num_field(value="abc")]
        not_numbers = [f for f in fields if not is_number(f.value)]
        self.assertEqual(len(not_numbers), 1)
        self.assertEqual(invalid_target_sensors({"EC": {"min": 0.5, "max": 4.0}}), [])

    def test_save_allowed_when_every_box_is_numeric(self):
        fields = [num_field(value="2.5"), num_field(signed=True, value="-0.3")]
        self.assertEqual([f for f in fields if not is_number(f.value)], [])

    def test_letters_survive_until_save_sees_them(self):
        # Setpoints used to wire an on_blur that rewrote an unparseable box
        # back to the last good number. Clicking Save blurs the field first,
        # so the guard only ever saw the reverted value and saved happily.
        # Nothing may quietly repair the text before do_save() reads it.
        field = num_field(value="2.5")
        field.value = "abc"          # what the operator typed
        self.assertIsNone(field.on_blur)
        self.assertFalse(is_number(field.value))


class TestSaveGuard(unittest.TestCase):
    """do_save() refuses when invalid_target_sensors() reports anything."""

    def test_good_range_saves(self):
        self.assertEqual(invalid_target_sensors({"EC": {"min": 0.5, "max": 4.0}}), [])

    def test_min_not_below_max_blocks(self):
        self.assertEqual(invalid_target_sensors({"EC": {"min": 4.0, "max": 4.0}}), ["EC"])
        self.assertEqual(invalid_target_sensors({"EC": {"min": 9.0, "max": 1.0}}), ["EC"])

    def test_letters_block_instead_of_crashing(self):
        # Only reachable via a hand-edited app_config.json. Comparing "abc"
        # to a float used to raise TypeError straight out of do_save.
        self.assertEqual(invalid_target_sensors({"EC": {"min": "abc", "max": 4.0}}), ["EC"])
        self.assertEqual(invalid_target_sensors({"PH": {"min": 1.0, "max": "x"}}), ["PH"])

    def test_numeric_strings_are_fine(self):
        # json only ever holds numbers here, but a "2.5" shouldn't block save.
        self.assertEqual(invalid_target_sensors({"EC": {"min": "0.5", "max": "4.0"}}), [])

    def test_missing_and_none_block(self):
        self.assertEqual(invalid_target_sensors({"EC": {"min": 0.5}}), ["EC"])
        self.assertEqual(invalid_target_sensors({"EC": {"min": None, "max": 4.0}}), ["EC"])


if __name__ == "__main__":
    unittest.main()
