"""Shared pieces of the Parameters page: numeric fields, validation, and the
context object each section is handed.

Lives in its own module so `parameters.py` (the page shell) and
`parameters_sections/*` (one file per section) can both import it without a
circular import.
"""

from dataclasses import dataclass
from typing import Callable

import flet as ft

from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState
from config.sensors import SENSORS

# Sensor display metadata, keyed by name (reused from the dashboard config).
_SENSOR_META = {s["name"]: s for s in SENSORS}
_OPS = ["<", ">"]


@dataclass
class SectionCtx:
    """Everything a section needs from the page around it.

    Sections are built fresh on every swap, so they hold no state of their
    own: they read and write `state`, register their numeric fields through
    `nf` (so Save can re-check the raw text), and report edits via
    `mark_dirty`.
    """

    page: ft.Page
    state: AppState
    db: Database
    actuator_hub: ActuatorHub
    pump_names: list[str]
    nf: Callable[..., ft.TextField]
    mark_dirty: Callable[[], None]
    parse_float: Callable[[ft.TextField, float], float]
    show_snack: Callable[[str, str], None]
    swap: Callable[[str], None]
    # Numeric fields of the section currently mounted, in registration order;
    # sections that rebuild rows slice it to drop the fields they discarded.
    live_num_fields: list[ft.TextField]
    # The page's Reset snapshot, so a section can restore its own slice.
    snapshot: dict


def is_number(text) -> bool:
    """Does this field's text parse as a number? Blank and "1.2.3" don't."""
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True


def invalid_target_sensors(targets: dict) -> list[str]:
    """Sensors whose range can't be saved: not a number, or min >= max.

    Pure data check — works no matter which section is currently on screen
    (unlike the per-row border/error UI in Setpoints, which only exists while
    that section's controls are mounted).

    Non-numeric only reaches here from a hand-edited app_config.json: the
    fields filter letters out (see num_field) and parse_float() never writes a
    non-float into state. Comparing a str to a float raises TypeError, so this
    has to coerce rather than compare raw.
    """
    bad = []
    for name, rng in targets.items():
        try:
            lo, hi = float(rng["min"]), float(rng["max"])
        except (KeyError, TypeError, ValueError):
            bad.append(name)
        else:
            if lo >= hi:
                bad.append(name)
    return bad


def num_field(signed: bool = False, **kwargs) -> ft.TextField:
    """TextField that only accepts numeric characters.

    `signed=True` also allows a minus sign, for values that can legitimately
    go below zero: sensor calibration offsets and temperature targets. Volumes
    (ml), durations and tank dimensions stay unsigned.

    keyboard_type only picks which on-screen keyboard appears — it doesn't stop
    a physical keyboard (or a paste) from entering "abc". input_filter is what
    blocks characters, and it is not trusted on its own: do_save() re-checks
    every mounted field's text, so a filter that fails to apply can't get bad
    input saved.
    """
    return ft.TextField(
        keyboard_type=ft.KeyboardType.NUMBER,
        # Built per field rather than shared: a single InputFilter instance
        # reused across every TextField is exactly the kind of thing Flet's
        # control tree mishandles, and the object is cheap.
        input_filter=ft.InputFilter(
            regex_string=r"[0-9.\-]" if signed else r"[0-9.]"
        ),
        **kwargs,
    )
