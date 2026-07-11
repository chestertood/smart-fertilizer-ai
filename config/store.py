"""JSON-backed persistence for user-editable config.

Holds editable setpoints, auto-dose rules, pump calibration and sensor offsets
so they survive a restart. Stdlib-only (json). Lives next to the SQLite DB in
data/app_config.json.

Imports of CROP_PROFILES / _PUMP_CONFIG are done lazily inside functions to
avoid a circular import with config.profiles.
"""

import os
import sys
import copy
import json
import logging

logger = logging.getLogger(__name__)

# Writable data dir. When frozen by `flet pack`, __file__ is inside the temp
# _MEIPASS extraction dir (wiped on exit) — use the exe's folder instead so
# config survives a restart.
if getattr(sys, "frozen", False):
    _DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    _DATA_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
    )
_CONFIG_PATH = os.path.join(_DATA_DIR, "app_config.json")


def _defaults() -> dict:
    """Build a fresh config from the hardcoded defaults."""
    from config.profiles import CROP_PROFILES, DEFAULT_PROFILE
    from app.services.actuators import _PUMP_CONFIG

    pumps = {
        name: {"max_dose": max_dose, "ml_per_s": 1.0}
        for name, max_dose, _pin in _PUMP_CONFIG
    }
    return {
        "active_profile": DEFAULT_PROFILE,
        "targets": copy.deepcopy(CROP_PROFILES),
        "auto_rules": [],
        "pumps": pumps,
        "offsets": {"EC": 0.0, "PH": 0.0, "Temperature": 0.0, "Humidity": 0.0},
        # Built-in profile names the operator deleted — CROP_PROFILES is a
        # hardcoded constant, so "deleting" a built-in just hides it here.
        "hidden_profiles": [],
        # Reservoir dimensions (cm). Used to compute tank capacity (liters),
        # which the LLM advisor uses to size EC dosing amounts correctly.
        "water_tank": {"width_cm": 30.0, "length_cm": 30.0, "height_cm": 40.0},
        # Growth-stage tracking, keyed by profile name:
        #   {"planting_date": "YYYY-MM-DD" | None,
        #    "stages": [{"name","duration_days","targets": {sensor:{min,max}}}]}
        # Empty/no planting_date means that profile isn't tracking a grow
        # cycle — targets fall back to the flat per-profile range as before.
        "growth": {},
        # UI language: "en" or "th" (see config.i18n).
        "language": "en",
        # Claude model used by the chat assistant / advisor. Selectable from
        # the chat panel; must be one of llm_agent.AVAILABLE_MODELS.
        "llm_model": "claude-opus-4-8",
    }


def _merge(defaults: dict, loaded: dict) -> dict:
    """Shallow-merge loaded values over defaults so new keys added in code
    still appear for users with an older config file."""
    cfg = copy.deepcopy(defaults)
    for key, val in loaded.items():
        cfg[key] = val
    return cfg


def load() -> dict:
    """Load config, seeding defaults on first run or on a corrupt file."""
    defaults = _defaults()
    if not os.path.exists(_CONFIG_PATH):
        save(defaults)
        return defaults
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        return _merge(defaults, loaded)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("config load failed (%s); using defaults", exc)
        return defaults


def save(cfg: dict) -> None:
    """Persist config to disk (pretty-printed)."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    logger.info("config saved to %s", _CONFIG_PATH)
