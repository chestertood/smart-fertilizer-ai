"""Unit tests for the safety-critical core logic.

Run with:  python -m unittest discover tests -v
Stdlib unittest only — no extra dependencies.
"""

import datetime
import os
import tempfile
import unittest

# Point the config store at a temp dir before anything imports it, so tests
# never touch the real data/app_config.json.
import config.store as store

_TMP = tempfile.mkdtemp()
store._DATA_DIR = _TMP
store._CONFIG_PATH = os.path.join(_TMP, "app_config.json")

from config.sensors import get_status  # noqa: E402
from config.profiles import AppState  # noqa: E402
from app.components.sensor_card import _bar_fraction  # noqa: E402
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

    def test_cannot_delete_last_profile(self):
        s = AppState()
        for name in list(s.profile_names)[:-1]:
            s.delete_profile(name)
        self.assertFalse(s.delete_profile(s.profile_names[0]))

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


if __name__ == "__main__":
    unittest.main()
