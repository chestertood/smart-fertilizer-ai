import copy
import flet as ft

from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState
from config.sensors import SENSORS, get_status

# Sensor display metadata, keyed by name (reused from the dashboard config).
_SENSOR_META = {s["name"]: s for s in SENSORS}
_OPS = ["<", ">"]


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
    }

    dirty = {"v": False}
    save_bar = ft.Container(visible=False)  # filled in below
    section_host = ft.Container(expand=True)  # holds the active section
    current = {"name": "Setpoints"}

    def mark_dirty():
        if not dirty["v"]:
            dirty["v"] = True
            save_bar.visible = True
            save_bar.update()

    def parse_float(field: ft.TextField, fallback: float) -> float:
        try:
            return float(field.value)
        except (TypeError, ValueError):
            field.value = str(fallback)
            field.update()
            return fallback

    # -- section: Setpoints -------------------------------------------------

    def section_setpoints() -> ft.Control:
        rows = []
        targets = state.targets  # active profile's editable dict

        for name, meta in _SENSOR_META.items():
            tgt = targets.setdefault(name, {"min": meta["min"], "max": meta["max"]})
            unit = meta["unit"]
            dot = ft.Icon(ft.Icons.CIRCLE, size=12, color="#BDBDBD")
            reading_txt = ft.Text("", size=11, color="#9E9E9E")

            def refresh_status(n=name, d=dot, rt=reading_txt):
                val = state.last_readings.get(n)
                t = state.targets.get(n, {})
                if isinstance(val, (int, float)) and val == val and t:
                    _, color = get_status(val, t["min"], t["max"])
                    d.color = color
                    rt.value = f"now {val:.2f}"
                else:
                    d.color = "#BDBDBD"
                    rt.value = "no reading"

            refresh_status()

            min_field = ft.TextField(
                label="min", value=str(tgt["min"]), width=90, height=46, text_size=14,
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            max_field = ft.TextField(
                label="max", value=str(tgt["max"]), width=90, height=46, text_size=14,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def on_min(e, n=name, f=min_field, rs=refresh_status):
                state.targets[n]["min"] = parse_float(f, state.targets[n]["min"])
                rs(); dot.update(); reading_txt.update(); mark_dirty()

            def on_max(e, n=name, f=max_field, rs=refresh_status):
                state.targets[n]["max"] = parse_float(f, state.targets[n]["max"])
                rs(); dot.update(); reading_txt.update(); mark_dirty()

            min_field.on_change = on_min
            max_field.on_change = on_max

            rows.append(
                ft.Container(
                    bgcolor="#FFFFFF", border_radius=12, padding=12,
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                bgcolor=meta["color"], border_radius=10, padding=8,
                                content=ft.Icon(meta["icon"], color="#FFFFFF", size=20),
                            ),
                            ft.Column(
                                spacing=0, expand=True,
                                controls=[
                                    ft.Text(f"{name} ({unit})", size=14, weight=ft.FontWeight.W_600),
                                    ft.Row(spacing=4, controls=[dot, reading_txt]),
                                ],
                            ),
                            min_field,
                            max_field,
                        ],
                    ),
                )
            )

        def reset_defaults(e):
            state.reset_targets_to_default()
            mark_dirty()
            swap("Setpoints")

        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Normal range per sensor. The dot shows the live status against your range.",
                        size=12, color="#757575"),
                *rows,
                ft.TextButton(
                    "Reset to profile defaults",
                    icon=ft.Icons.RESTART_ALT,
                    on_click=reset_defaults,
                ),
            ],
        )

    # -- section: Auto-dose rules ------------------------------------------

    def section_rules() -> ft.Control:
        rule_rows = ft.Column(spacing=8)

        def render_rules():
            rule_rows.controls = [rule_row(i, r) for i, r in enumerate(state.auto_rules)]

        def rule_row(idx: int, rule: dict) -> ft.Control:
            sensor_dd = ft.Dropdown(
                value=rule.get("sensor", "EC"), width=140, label="if sensor",
                options=[ft.dropdown.Option(key=n, text=n) for n in _SENSOR_META],
            )
            op_dd = ft.Dropdown(
                value=rule.get("op", "<"), width=70, label="is",
                options=[ft.dropdown.Option(key=o, text=o) for o in _OPS],
            )
            thr_field = ft.TextField(
                value=str(rule.get("threshold", 0)), width=90, height=46, label="value",
                text_size=14, keyboard_type=ft.KeyboardType.NUMBER,
            )
            pump_dd = ft.Dropdown(
                value=rule.get("pump", pump_names[0]), width=150, label="then dose",
                options=[ft.dropdown.Option(key=p, text=p) for p in pump_names],
            )
            amt_field = ft.TextField(
                value=str(rule.get("amount", 10)), width=90, height=46, label="ml",
                text_size=14, keyboard_type=ft.KeyboardType.NUMBER,
            )
            enabled_sw = ft.Switch(value=rule.get("enabled", True))

            def upd(_=None, i=idx, s=sensor_dd, o=op_dd, t=thr_field, p=pump_dd, a=amt_field, sw=enabled_sw):
                state.auto_rules[i] = {
                    "sensor": s.value, "op": o.value,
                    "threshold": parse_float(t, state.auto_rules[i].get("threshold", 0)),
                    "pump": p.value,
                    "amount": parse_float(a, state.auto_rules[i].get("amount", 10)),
                    "enabled": sw.value,
                }
                mark_dirty()

            for c in (sensor_dd, op_dd, pump_dd):
                c.on_select = upd
            thr_field.on_change = upd
            amt_field.on_change = upd
            enabled_sw.on_change = upd

            def delete(e, i=idx):
                state.auto_rules.pop(i)
                mark_dirty()
                render_rules()
                rule_rows.update()

            return ft.Container(
                bgcolor="#FFFFFF", border_radius=12, padding=12,
                content=ft.Row(
                    wrap=True, spacing=8, run_spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        sensor_dd, op_dd, thr_field, pump_dd, amt_field, enabled_sw,
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#C62828",
                                      tooltip="Delete rule", on_click=delete),
                    ],
                ),
            )

        def add_rule(e):
            state.auto_rules.append({
                "sensor": "EC", "op": "<", "threshold": 1.8,
                "pump": pump_names[0], "amount": 10, "enabled": True,
            })
            mark_dirty()
            render_rules()
            rule_rows.update()

        render_rules()
        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Rules are saved now; automatic execution is a later phase. "
                        "For now they document your intended logic.",
                        size=12, color="#757575"),
                rule_rows,
                ft.FilledButton("Add rule", icon=ft.Icons.ADD, on_click=add_rule),
            ],
        )

    # -- section: Manual dosing --------------------------------------------

    def section_dosing() -> ft.Control:
        feedback = ft.Text("", size=12, color="#2E7D32")

        def pump_row(name: str) -> ft.Control:
            pump = actuator_hub.pumps[name]
            amount_field = ft.TextField(
                value="10", width=100, height=44, text_size=14,
                suffix=ft.Text("ml"), keyboard_type=ft.KeyboardType.NUMBER,
            )

            def dose(e, n=name, fld=amount_field):
                try:
                    amount = float(fld.value)
                except (TypeError, ValueError):
                    feedback.value = f"{n}: enter a valid number"; feedback.color = "#C62828"
                    feedback.update(); return
                dispensed = actuator_hub.dose(n, amount)
                db.log_dose(n, dispensed, source="manual")
                feedback.value = f"Dispensed {dispensed:.1f} ml from {n}"; feedback.color = "#2E7D32"
                feedback.update()

            return ft.Container(
                bgcolor="#FFFFFF", border_radius=12, padding=12,
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.OPACITY, color="#1976D2"),
                        ft.Column(
                            spacing=0, expand=True,
                            controls=[
                                ft.Text(name, size=15, weight=ft.FontWeight.W_600),
                                ft.Text(f"max {pump.max_dose:.0f} ml", size=11, color="#9E9E9E"),
                            ],
                        ),
                        amount_field,
                        ft.FilledButton("Dose", icon=ft.Icons.PLAY_ARROW, on_click=dose),
                    ],
                ),
            )

        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Trigger a pump by hand. Dispensing is logged to History.",
                        size=12, color="#757575"),
                *[pump_row(n) for n in pump_names],
                feedback,
            ],
        )

    # -- section: Calibration ----------------------------------------------

    def section_calibration() -> ft.Control:
        pump_cards = []
        for name in pump_names:
            cfg = state.pumps.setdefault(name, {"max_dose": actuator_hub.pumps[name].max_dose, "ml_per_s": 1.0})
            max_f = ft.TextField(label="max dose (ml)", value=str(cfg["max_dose"]),
                                 width=140, height=46, text_size=14,
                                 keyboard_type=ft.KeyboardType.NUMBER)
            mls_f = ft.TextField(label="ml / second", value=str(cfg.get("ml_per_s", 1.0)),
                                 width=140, height=46, text_size=14,
                                 keyboard_type=ft.KeyboardType.NUMBER)

            def on_max(e, n=name, f=max_f):
                state.pumps[n]["max_dose"] = parse_float(f, state.pumps[n]["max_dose"]); mark_dirty()

            def on_mls(e, n=name, f=mls_f):
                state.pumps[n]["ml_per_s"] = parse_float(f, state.pumps[n].get("ml_per_s", 1.0)); mark_dirty()

            max_f.on_change = on_max
            mls_f.on_change = on_mls
            pump_cards.append(
                ft.Container(
                    bgcolor="#FFFFFF", border_radius=12, padding=12,
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10,
                        controls=[
                            ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="#6A1B9A"),
                            ft.Text(name, size=15, weight=ft.FontWeight.W_600, expand=True),
                            max_f, mls_f,
                        ],
                    ),
                )
            )

        offset_fields = []
        for name, meta in _SENSOR_META.items():
            off = state.offsets.setdefault(name, 0.0)
            f = ft.TextField(label=f"{name} offset ({meta['unit']})", value=str(off),
                             width=180, height=46, text_size=14,
                             keyboard_type=ft.KeyboardType.NUMBER)

            def on_off(e, n=name, fld=f):
                state.offsets[n] = parse_float(fld, state.offsets[n]); mark_dirty()

            f.on_change = on_off
            offset_fields.append(f)

        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Pump throughput and sensor calibration offsets.", size=12, color="#757575"),
                ft.Text("Pumps", size=14, weight=ft.FontWeight.W_600, color="#424242"),
                *pump_cards,
                ft.Divider(),
                ft.Text("Sensor offsets", size=14, weight=ft.FontWeight.W_600, color="#424242"),
                ft.Container(
                    bgcolor="#FFFFFF", border_radius=12, padding=12,
                    content=ft.Row(wrap=True, spacing=10, run_spacing=10, controls=offset_fields),
                ),
            ],
        )

    _SECTIONS = {
        "Setpoints": section_setpoints,
        "Auto-dose rules": section_rules,
        "Manual dosing": section_dosing,
        "Calibration": section_calibration,
    }

    # -- section switcher ---------------------------------------------------

    switcher = ft.Row(wrap=True, spacing=8)

    def swap(name: str):
        current["name"] = name
        section_host.content = _SECTIONS[name]()
        for btn in switcher.controls:
            selected = btn.data == name
            btn.style = ft.ButtonStyle(
                bgcolor="#388E3C" if selected else "#FFFFFF",
                color="#FFFFFF" if selected else "#388E3C",
            )
        section_host.update()
        switcher.update()

    for sec_name in _SECTIONS:
        switcher.controls.append(
            ft.OutlinedButton(
                sec_name,
                data=sec_name,
                on_click=lambda e, n=sec_name: swap(n),
                style=ft.ButtonStyle(
                    bgcolor="#388E3C" if sec_name == "Setpoints" else "#FFFFFF",
                    color="#FFFFFF" if sec_name == "Setpoints" else "#388E3C",
                ),
            )
        )
    section_host.content = section_setpoints()

    # -- save bar -----------------------------------------------------------

    def do_save(e):
        state.save()
        actuator_hub.apply_config(state)
        # refresh snapshot to current
        snapshot["targets"] = copy.deepcopy(state._targets)
        snapshot["auto_rules"] = copy.deepcopy(state.auto_rules)
        snapshot["pumps"] = copy.deepcopy(state.pumps)
        snapshot["offsets"] = copy.deepcopy(state.offsets)
        dirty["v"] = False
        save_bar.visible = False
        save_bar.update()
        page.open(ft.SnackBar(content=ft.Text("Saved"), bgcolor="#2E7D32"))

    def do_reset(e):
        state._targets = copy.deepcopy(snapshot["targets"])
        state.auto_rules = copy.deepcopy(snapshot["auto_rules"])
        state.pumps = copy.deepcopy(snapshot["pumps"])
        state.offsets = copy.deepcopy(snapshot["offsets"])
        dirty["v"] = False
        save_bar.visible = False
        save_bar.update()
        swap(current["name"])

    save_bar.bgcolor = "#FFF8E1"
    save_bar.padding = ft.Padding(left=12, right=12, top=10, bottom=10)
    save_bar.border_radius = 12
    save_bar.content = ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.EDIT_NOTE, color="#F57F17"),
            ft.Text("You have unsaved changes", size=13, color="#F57F17",
                    weight=ft.FontWeight.W_600, expand=True),
            ft.OutlinedButton("Reset", icon=ft.Icons.UNDO, on_click=do_reset),
            ft.FilledButton("Save", icon=ft.Icons.SAVE, on_click=do_save),
        ],
    )

    return ft.Container(
        expand=True,
        padding=ft.Padding(left=12, right=12, top=8, bottom=12),
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Text("Parameters", size=18, weight=ft.FontWeight.BOLD, color="#212121"),
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
