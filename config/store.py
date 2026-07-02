"""JSON-backed persistence for user-editable config.

Holds editable setpoints, auto-dose rules, pump calibration and sensor offsets
so they survive a restart. Stdlib-only (json). Lives next to the SQLite DB in
data/app_config.json.

Imports of CROP_PROFILES / _PUMP_CONFIG are done lazily inside functions to
avoid a circular import with config.profiles.
"""

import os
import copy
import json
import logging

logger = logging.getLogger(__name__)

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
        "control_mode": "Manual",
        "targets": copy.deepcopy(CROP_PROFILES),
        "auto_rules": [],
        "pumps": pumps,
        "offsets": {"EC": 0.0, "PH": 0.0, "Temperature": 0.0, "Humidity": 0.0},
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
