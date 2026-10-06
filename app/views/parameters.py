import copy
import flet as ft

from app import theme
from app.services.actuators import ActuatorHub
from app.services.database import Database
from app.views.parameters_common import (
    SectionCtx, invalid_target_sensors, is_number, num_field,
)
from app.views.parameters_sections import (
    calibration, dosing, growth, rules, setpoints,
)
from config.profiles import AppState
from config.i18n import t

# Re-exported so callers (and tests) can keep importing them from this module.
__all__ = ["build_parameters", "invalid_target_sensors", "is_number", "num_field"]

# Sensor display metadata, keyed by name (reused from the dashboard config).







def build_parameters(
    page: ft.Page,
    actuator_hub: ActuatorHub,
    db: Database,
    state: AppState,
) -> ft.Container:
    """Manual setup: setpoints, auto-dose rules, manual dosing, calibration.

    Edits write straight into `state` (live) but are only persisted when the
    user presses Save; Reset restores the snapshot taken when the page opened.
    """

    pump_names = list(actuator_hub.pumps.keys())

    # Snapshot of editable state for Reset.
    snapshot = {
        "targets": copy.deepcopy(state._targets),
        "auto_rules": copy.deepcopy(state.auto_rules),
        "pumps": copy.deepcopy(state.pumps),
        "offsets": copy.deepcopy(state.offsets),
        "water_tank": copy.deepcopy(state.water_tank),
        "growth": copy.deepcopy(state.growth),
    }

    dirty = {"v": False}
    save_bar = ft.Container(visible=False)  # filled in below
    section_host = ft.Container(expand=True)  # holds the active section
    current = {"name": "Setpoints"}

    # Numeric fields belonging to the section currently on screen. Only one
    # section is mounted at a time (swap() rebuilds section_host), so this is
    # cleared and repopulated per swap.
    #
    # do_save() needs these because `state` alone cannot see bad input:
    # parse_float() deliberately keeps the last good value when the text won't
    # parse, so a box showing "abc" leaves state perfectly valid and Save would
    # sail through. Checking the field text is the only way to catch it.
    live_num_fields: list[ft.TextField] = []

    def nf(signed: bool = False, **kwargs) -> ft.TextField:
        """num_field() that registers itself for the save-time text check."""
        field = num_field(signed=signed, **kwargs)
        live_num_fields.append(field)
        return field

    def mark_dirty():
        if not dirty["v"]:
            dirty["v"] = True
            save_bar.visible = True
            save_bar.update()

    def _show_snack(msg: str, color: str) -> None:
        # This Flet build has no page.open()/show_snack_bar(); drive the
        # SnackBar via page.overlay instead.
        sb = ft.SnackBar(content=ft.Text(msg), bgcolor=color)
        page.overlay.append(sb)
        sb.open = True
        page.update()

    def parse_float(field: ft.TextField, fallback: float) -> float:
        # Never rewrite field.value here — this runs on every keystroke
        # (on_change). Snapping the text back mid-edit made it impossible to
        # clear a field to type a new number (deleting the last digit always
        # bounced back to the old value). Just fall back the underlying
        # state value silently; the field keeps whatever the user is typing,
        # including empty, until it parses again.
        try:
            return float(field.value)
        except (TypeError, ValueError):
            return fallback

    # -- section: Setpoints -------------------------------------------------


    # -- section: Auto-dose rules ------------------------------------------


    # -- section: Manual dosing --------------------------------------------


    # -- section: Calibration ----------------------------------------------


    # -- section: Growth stages ---------------------------------------------


    _SECTIONS = {
        "Setpoints": setpoints.build,
        "Growth stages": growth.build,
        "Auto-dose rules": rules.build,
        "Manual dosing": dosing.build,
        "Calibration": calibration.build,
    }
    # Internal section key (also used for swap()/current["name"]) -> i18n key
    # for the displayed switcher button label.
    _SECTION_I18N_KEYS = {
        "Setpoints": "parameters.section.setpoints",
        "Growth stages": "parameters.section.growth",
        "Auto-dose rules": "parameters.section.rules",
        "Manual dosing": "parameters.section.dosing",
        "Calibration": "parameters.section.calibration",
    }

    ctx = SectionCtx(
        page=page, state=state, db=db, actuator_hub=actuator_hub,
        pump_names=pump_names, nf=nf, mark_dirty=mark_dirty,
        parse_float=parse_float, show_snack=_show_snack,
        swap=lambda name: swap(name),   # defined just below
        live_num_fields=live_num_fields, snapshot=snapshot,
    )

    # -- section switcher ---------------------------------------------------

    switcher = ft.Row(wrap=True, spacing=8)

    def swap(name: str):
        current["name"] = name
        # The outgoing section's fields are about to be discarded; only the
        # incoming ones can be checked at save time.
        live_num_fields.clear()
        section_host.content = _SECTIONS[name](ctx)
        for btn in switcher.controls:
            selected = btn.data == name
            btn.style = ft.ButtonStyle(
                bgcolor=theme.PRIMARY if selected else theme.SURFACE,
                color="#FFFFFF" if selected else theme.PRIMARY,
            )
        section_host.update()
        switcher.update()

    for sec_name in _SECTIONS:
        switcher.controls.append(
            ft.OutlinedButton(
                t(_SECTION_I18N_KEYS[sec_name], state.language),
                data=sec_name,
                on_click=lambda e, n=sec_name: swap(n),
                style=ft.ButtonStyle(
                    bgcolor=theme.PRIMARY if sec_name == "Setpoints" else theme.SURFACE,
                    color="#FFFFFF" if sec_name == "Setpoints" else theme.PRIMARY,
                ),
            )
        )
    section_host.content = setpoints.build(ctx)

    # -- save bar -----------------------------------------------------------

    def do_save(e):
        # Text check first: a box reading "abc" leaves state valid (parse_float
        # keeps the last good number), so this is the only guard that sees it.
        not_numbers = [f for f in live_num_fields if not is_number(f.value)]
        for f in live_num_fields:
            f.border_color = theme.DANGER if f in not_numbers else None
            f.update()
        if not_numbers:
            _show_snack(t("parameters.numbers_only", state.language), theme.DANGER)
            return

        bad = invalid_target_sensors(state.targets)
        if bad:
            _show_snack(
                f"Fix min/max first: {', '.join(bad)} (min must be less than max)",
                theme.DANGER,
            )
            return
        state.save()
        actuator_hub.apply_config(state)
        # refresh snapshot to current
        snapshot["targets"] = copy.deepcopy(state._targets)
        snapshot["auto_rules"] = copy.deepcopy(state.auto_rules)
        snapshot["pumps"] = copy.deepcopy(state.pumps)
        snapshot["offsets"] = copy.deepcopy(state.offsets)
        snapshot["water_tank"] = copy.deepcopy(state.water_tank)
        snapshot["growth"] = copy.deepcopy(state.growth)
        dirty["v"] = False
        save_bar.visible = False
        save_bar.update()
        _show_snack(t("parameters.saved", state.language), theme.SUCCESS)

    def do_reset(e):
        state._targets = copy.deepcopy(snapshot["targets"])
        state.auto_rules = copy.deepcopy(snapshot["auto_rules"])
        state.pumps = copy.deepcopy(snapshot["pumps"])
        state.offsets = copy.deepcopy(snapshot["offsets"])
        state.water_tank = copy.deepcopy(snapshot["water_tank"])
        state.growth = copy.deepcopy(snapshot["growth"])
        dirty["v"] = False
        save_bar.visible = False
        save_bar.update()
        swap(current["name"])

    save_bar.bgcolor = theme.WARN_SURFACE
    save_bar.padding = ft.Padding(left=14, right=14, top=10, bottom=10)
    save_bar.border_radius = theme.RADIUS
    save_bar.border = ft.Border.all(1, theme.WARN_BORDER)
    save_bar.shadow = theme.shadow()
    save_bar.content = ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.EDIT_NOTE, color="#F57F17"),
            ft.Text(t("parameters.unsaved", state.language), size=theme.FONT_SM, color="#F57F17",
                    weight=ft.FontWeight.W_600, expand=True),
            ft.OutlinedButton(t("parameters.reset", state.language), icon=ft.Icons.UNDO, on_click=do_reset),
            ft.FilledButton(t("parameters.save", state.language), icon=ft.Icons.SAVE, on_click=do_save),
        ],
    )

    return ft.Container(
        expand=True,
        padding=theme.PAGE_PADDING,
        content=ft.Column(
            spacing=10,
            controls=[
                theme.page_header(
                    t("parameters.title", state.language),
                    t("parameters.subtitle", state.language),
                ),
                switcher,
                ft.Divider(height=1),
                ft.Column(
                    expand=True, scroll=ft.ScrollMode.AUTO,
                    controls=[section_host],
                ),
                save_bar,
            ],
        ),
    )
