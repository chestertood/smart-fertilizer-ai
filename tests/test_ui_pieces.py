"""Checks for the UI plumbing that isn't covered by the view-agnostic tests:
the type scale / palette switch, the chart crosshair math, and the Parameters
page's split section modules.
"""
import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock

# Point the config store at a temp dir before AppState reads it, so tests
# never touch the real data/app_config.json (same trick as test_core).
import config.store as store
_TMP = tempfile.mkdtemp()
store._DATA_DIR = _TMP
store._CONFIG_PATH = os.path.join(_TMP, "app_config.json")

import flet as ft  # noqa: E402

from app import theme  # noqa: E402
from app.views.history import _nearest_index, _PAD_L, _PAD_R  # noqa: E402
from app.views.parameters_common import SectionCtx, num_field  # noqa: E402
from app.views.parameters_sections import (  # noqa: E402
    calibration, dosing, growth, rules, setpoints,
)
from app.services.actuators import ActuatorHub  # noqa: E402
from app.services.database import Database  # noqa: E402
from config.profiles import AppState  # noqa: E402


class TestThemePalettes(unittest.TestCase):
    def tearDown(self):
        theme.apply("light")

    def test_apply_switches_surfaces_and_status_tints(self):
        theme.apply("light")
        light_surface = theme.SURFACE
        light_ok_bg, _ = theme.status_style("#4CAF50")
        theme.apply("dark")
        self.assertNotEqual(theme.SURFACE, light_surface)
        self.assertNotEqual(theme.status_style("#4CAF50")[0], light_ok_bg)
        self.assertEqual(theme.flet_theme_mode(), ft.ThemeMode.DARK)

    def test_unknown_mode_falls_back_to_light(self):
        theme.apply("solarized")
        self.assertEqual(theme.mode, "light")
        self.assertEqual(theme.SURFACE, theme.LIGHT["SURFACE"])

    def test_both_palettes_define_the_same_tokens(self):
        self.assertEqual(set(theme.LIGHT), set(theme.DARK))


class TestChartCrosshair(unittest.TestCase):
    """Tapping the chart has to land on the sample under the finger."""

    def setUp(self):
        t0 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        self.points = [(t0 + datetime.timedelta(minutes=i), float(i))
                       for i in range(11)]
        self.width = 100 + _PAD_L + _PAD_R  # 100px of plot area

    def test_left_edge_picks_first_sample(self):
        self.assertEqual(_nearest_index(self.points, _PAD_L, self.width), 0)

    def test_right_edge_picks_last_sample(self):
        self.assertEqual(
            _nearest_index(self.points, _PAD_L + 100, self.width),
            len(self.points) - 1,
        )

    def test_middle_picks_middle_sample(self):
        self.assertEqual(_nearest_index(self.points, _PAD_L + 50, self.width), 5)

    def test_touch_outside_the_plot_clamps_to_an_end(self):
        self.assertEqual(_nearest_index(self.points, -500, self.width), 0)
        self.assertEqual(_nearest_index(self.points, 5_000, self.width),
                         len(self.points) - 1)


class TestParameterSections(unittest.TestCase):
    """Every section was moved out of parameters.py into its own module; they
    must still build from nothing but a SectionCtx."""

    def setUp(self):
        self.state = AppState()
        self.db = Database(os.path.join(tempfile.mkdtemp(), "sec.db"))
        self.hub = ActuatorHub()
        self.hub.connect_all()
        self.fields = []

        def nf(signed=False, **kwargs):
            field = num_field(signed=signed, **kwargs)
            self.fields.append(field)
            return field

        self.ctx = SectionCtx(
            page=MagicMock(), state=self.state, db=self.db,
            actuator_hub=self.hub, pump_names=list(self.hub.pumps), nf=nf,
            mark_dirty=lambda: None, parse_float=lambda f, d: d,
            show_snack=lambda m, c: None, swap=lambda n: None,
            live_num_fields=self.fields,
            snapshot={"growth": {}, "targets": {}},
        )

    def test_every_section_builds(self):
        for module in (setpoints, rules, dosing, calibration, growth):
            with self.subTest(section=module.__name__):
                self.fields.clear()
                self.assertIsInstance(module.build(self.ctx), ft.Control)


if __name__ == "__main__":
    unittest.main()
