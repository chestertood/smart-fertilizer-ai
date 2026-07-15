"""Seed knowledge sanity checks — no API, no dependencies beyond stdlib."""
import json
import os
import unittest

_SEED = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge", "crops_seed.json",
)
_SENSORS = {"EC", "PH", "Temperature", "Humidity"}


class TestSeed(unittest.TestCase):
    def setUp(self):
        with open(_SEED, encoding="utf-8") as f:
            self.crops = json.load(f)

    def test_seed_is_nonempty_list(self):
        self.assertIsInstance(self.crops, list)
        self.assertGreaterEqual(len(self.crops), 5)

    def test_every_crop_has_valid_stages(self):
        for crop in self.crops:
            self.assertTrue(crop.get("crop"))
            self.assertTrue(crop.get("stages"))
            for st in crop["stages"]:
                self.assertTrue(st.get("name"))
                self.assertIsInstance(st.get("duration_days"), int)
                for sensor, rng in st.get("targets", {}).items():
                    self.assertIn(sensor, _SENSORS)
                    self.assertLess(rng["min"], rng["max"])


if __name__ == "__main__":
    unittest.main()
