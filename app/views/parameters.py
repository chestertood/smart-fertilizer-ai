import copy
import flet as ft

from app import theme
from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState
from config.sensors import SENSORS, get_status
from config.i18n import t

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
        "water_tank": copy.deepcopy(state.water_tank),
        "growth": copy.deepcopy(state.growth),
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

    def revert_on_blur(field: ft.TextField, get_current: callable) -> callable:
        """On_blur handler: if the field was left empty/invalid, restore the
        last committed numeric value so it never displays blank."""
        def handler(e):
            try:
                float(field.value)
            except (TypeError, ValueError):
                field.value = str(get_current())
                field.update()
        return handler

    # -- section: Setpoints -------------------------------------------------

    def section_setpoints() -> ft.Control:
        rows = []
        targets = state.targets  # active profile's editable dict

        for name, meta in _SENSOR_META.items():
            tgt = targets.setdefault(name, {"min": meta["min"], "max": meta["max"]})
            unit = meta["unit"]
            dot = ft.Icon(ft.Icons.CIRCLE, size=12, color="#BDBDBD")
            reading_txt = ft.Text("", size=11, color=theme.TEXT_MUTED)

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
            range_error = ft.Text("", size=10, color="#C62828")

            def apply_validation(n=name, minf=min_field, maxf=max_field, err=range_error):
                """Set border/error state from data. No .update() here — safe
                to call before the row is mounted (initial build) too."""
                lo, hi = state.targets[n]["min"], state.targets[n]["max"]
                invalid = lo >= hi
                minf.border_color = "#C62828" if invalid else None
                maxf.border_color = "#C62828" if invalid else None
                err.value = "min must be less than max" if invalid else ""
                return not invalid

            def on_min(e, n=name, f=min_field, rs=refresh_status):
                state.targets[n]["min"] = parse_float(f, state.targets[n]["min"])
                rs(); dot.update(); reading_txt.update()
                apply_validation()
                min_field.update(); max_field.update(); range_error.update()
                mark_dirty()

            def on_max(e, n=name, f=max_field, rs=refresh_status):
                state.targets[n]["max"] = parse_float(f, state.targets[n]["max"])
                rs(); dot.update(); reading_txt.update()
                apply_validation()
                min_field.update(); max_field.update(); range_error.update()
                mark_dirty()

            min_field.on_change = on_min
            max_field.on_change = on_max
            min_field.on_blur = revert_on_blur(min_field, lambda n=name: state.targets[n]["min"])
            max_field.on_blur = revert_on_blur(max_field, lambda n=name: state.targets[n]["max"])
            apply_validation()  # catch any pre-existing invalid data on open (no .update, unmounted)

            rows.append(
                ft.Container(
                    bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                    border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
                    content=ft.Column(
                        spacing=2,
                        controls=[
                            ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Container(
                                        bgcolor=meta["color"], border_radius=10, padding=8,
                                        content=ft.Icon(meta["icon"], color="#FFFFFF", size=20),
                                    ),
                                    ft.Column(
                                        spacing=0, expand=True,
                                        controls=[
                                            ft.Text(
                                                f"{t(f'sensor.name.{name}', state.language)} ({unit})",
                                                size=14, weight=ft.FontWeight.W_600, color=theme.TEXT,
                                            ),
                                            ft.Row(spacing=4, controls=[dot, reading_txt]),
                                        ],
                                    ),
                                    min_field,
                                    max_field,
                                ],
                            ),
                            ft.Row(alignment=ft.MainAxisAlignment.END, controls=[range_error]),
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
                        size=12, color=theme.TEXT_SECONDARY),
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
                value=rule.get("op", "<"), width=110, label="is",
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
                bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
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
                        size=12, color=theme.TEXT_SECONDARY),
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
                try:
                    dispensed = actuator_hub.dose(n, amount)
                except RuntimeError as exc:  # includes CooldownError
                    feedback.value = str(exc); feedback.color = "#C62828"
                    feedback.update(); return
                db.log_dose(n, dispensed, source="manual")
                feedback.value = f"Dispensed {dispensed:.1f} ml from {n}"; feedback.color = "#2E7D32"
                feedback.update()

            return ft.Container(
                bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.OPACITY, color="#1976D2"),
                        ft.Column(
                            spacing=0, expand=True,
                            controls=[
                                ft.Text(name, size=15, weight=ft.FontWeight.W_600),
                                ft.Text(f"max {pump.max_dose:.0f} ml", size=11, color=theme.TEXT_MUTED),
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
                        size=12, color=theme.TEXT_SECONDARY),
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
                    bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                    border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
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

        width_f = ft.TextField(
            label="Tank width (cm)", value=str(state.water_tank["width_cm"]),
            width=160, height=46, text_size=14, keyboard_type=ft.KeyboardType.NUMBER,
        )
        length_f = ft.TextField(
            label="Tank length (cm)", value=str(state.water_tank["length_cm"]),
            width=160, height=46, text_size=14, keyboard_type=ft.KeyboardType.NUMBER,
        )
        height_f = ft.TextField(
            label="Tank height (cm)", value=str(state.water_tank["height_cm"]),
            width=160, height=46, text_size=14, keyboard_type=ft.KeyboardType.NUMBER,
        )
        volume_text = ft.Text("", size=11, color=theme.TEXT_SECONDARY)

        def refresh_volume():
            volume_text.value = f"Capacity ~{state.tank_capacity_liters():.1f} L"

        refresh_volume()

        def on_tank_height(e):
            state.water_tank["height_cm"] = parse_float(height_f, state.water_tank["height_cm"])
            refresh_volume(); volume_text.update(); mark_dirty()

        def on_tank_width(e):
            state.water_tank["width_cm"] = parse_float(width_f, state.water_tank["width_cm"])
            refresh_volume(); volume_text.update(); mark_dirty()

        def on_tank_length(e):
            state.water_tank["length_cm"] = parse_float(length_f, state.water_tank["length_cm"])
            refresh_volume(); volume_text.update(); mark_dirty()

        height_f.on_change = on_tank_height
        width_f.on_change = on_tank_width
        length_f.on_change = on_tank_length

        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Pump throughput and sensor calibration offsets.", size=12, color=theme.TEXT_SECONDARY),
                ft.Text("Pumps", size=14, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
                *pump_cards,
                ft.Divider(),
                ft.Text("Sensor offsets", size=14, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
                ft.Container(
                    bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                    border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
                    content=ft.Row(wrap=True, spacing=10, run_spacing=10, controls=offset_fields),
                ),
                ft.Divider(),
                ft.Text("Reservoir tank", size=14, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
                ft.Container(
                    bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                    border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            ft.Text(
                                "Enter the reservoir's inner dimensions. Capacity feeds "
                                "the chat assistant so it sizes EC dosing to your tank.",
                                size=11, color=theme.TEXT_MUTED,
                            ),
                            ft.Row(wrap=True, spacing=10, run_spacing=10,
                                   controls=[width_f, length_f, height_f]),
                            volume_text,
                        ],
                    ),
                ),
            ],
        )

    # -- section: Growth stages ---------------------------------------------

    def section_growth() -> ft.Control:
        g = state.growth_config()
        stage_rows = ft.Column(spacing=8)

        def render_stages():
            stage_rows.controls = [
                stage_card(i, s) for i, s in enumerate(g["stages"])
            ]

        def stage_card(idx: int, stage: dict) -> ft.Control:
            name_f = ft.TextField(
                label="Stage name", value=stage["name"], width=160, height=46,
                text_size=14,
            )
            days_f = ft.TextField(
                label="Duration (days)", value=str(stage["duration_days"]),
                width=140, height=46, text_size=14,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def on_name(e, i=idx, f=name_f):
                g["stages"][i]["name"] = f.value or g["stages"][i]["name"]
                mark_dirty()

            def on_days(e, i=idx, f=days_f):
                try:
                    g["stages"][i]["duration_days"] = max(1, int(float(f.value)))
                except (TypeError, ValueError):
                    f.value = str(g["stages"][i]["duration_days"])
                    f.update()
                mark_dirty()

            name_f.on_change = on_name
            days_f.on_change = on_days

            def delete(e, i=idx):
                state.delete_stage(i)
                mark_dirty()
                render_stages()
                stage_rows.update()

            target_fields = []
            for sname, meta in _SENSOR_META.items():
                tgt = stage["targets"].setdefault(
                    sname, {"min": meta["min"], "max": meta["max"]}
                )
                min_f = ft.TextField(
                    label=f"{sname} min", value=str(tgt["min"]), width=110,
                    height=44, text_size=13, keyboard_type=ft.KeyboardType.NUMBER,
                )
                max_f = ft.TextField(
                    label=f"{sname} max", value=str(tgt["max"]), width=110,
                    height=44, text_size=13, keyboard_type=ft.KeyboardType.NUMBER,
                )

                def on_min(e, i=idx, s=sname, f=min_f):
                    g["stages"][i]["targets"][s]["min"] = parse_float(
                        f, g["stages"][i]["targets"][s]["min"]
                    )
                    mark_dirty()

                def on_max(e, i=idx, s=sname, f=max_f):
                    g["stages"][i]["targets"][s]["max"] = parse_float(
                        f, g["stages"][i]["targets"][s]["max"]
                    )
                    mark_dirty()

                min_f.on_change = on_min
                max_f.on_change = on_max
                target_fields += [min_f, max_f]

            return ft.Container(
                bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    bgcolor=theme.PRIMARY, border_radius=12,
                                    padding=ft.Padding(left=8, right=8, top=2, bottom=2),
                                    content=ft.Text(f"Stage {idx + 1}", size=11,
                                                     color="#FFFFFF", weight=ft.FontWeight.BOLD),
                                ),
                                name_f, days_f,
                                ft.Container(expand=True),
                                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#C62828",
                                              tooltip="Delete stage", on_click=delete),
                            ],
                        ),
                        ft.Row(wrap=True, spacing=8, run_spacing=8, controls=target_fields),
                    ],
                ),
            )

        render_stages()

        # -- add stage ---
        new_name_f = ft.TextField(label="Name", width=160, height=46, text_size=14)
        new_days_f = ft.TextField(label="Duration (days)", value="7", width=140,
                                   height=46, text_size=14,
                                   keyboard_type=ft.KeyboardType.NUMBER)

        def add_stage(e):
            try:
                days = max(1, int(float(new_days_f.value)))
            except (TypeError, ValueError):
                days = 7
            state.add_stage(new_name_f.value or f"Stage {len(g['stages']) + 1}", days)
            new_name_f.value = ""
            mark_dirty()
            render_stages()
            stage_rows.update()

        # -- planting date controls ---
        status_text = ft.Text(size=12, color="#424242")

        def refresh_status():
            info = state.current_stage_info()
            if info is None:
                planted = g.get("planting_date")
                status_text.value = (
                    "Not tracking a grow cycle. Add stages below, then start planting."
                    if not g["stages"] else
                    f"Stages defined but not tracking (planted: {planted or 'never'})."
                )
                status_text.color = "#9E9E9E"
            else:
                status_text.value = (
                    f"Day {info['elapsed_days']} of {info['total_days']} "
                    f"({info['overall_pct']:.0f}%) — Stage {info['stage_index'] + 1}: "
                    f"{info['stage']['name']} (day {info['day_in_stage']}/"
                    f"{info['stage']['duration_days']})"
                )
                status_text.color = "#2E7D32"

        refresh_status()

        def start_today(e):
            state.start_planting()
            state.save()  # immediate action, like the dosing buttons — don't
            # wait on the page-level Save button or this is lost on restart.
            snapshot["growth"] = copy.deepcopy(state.growth)  # keep Reset in sync
            refresh_status(); status_text.update()
            _show_snack("Planting started today", "#2E7D32")

        def stop_tracking(e):
            state.stop_planting()
            state.save()
            snapshot["growth"] = copy.deepcopy(state.growth)
            refresh_status(); status_text.update()
            _show_snack("Growth tracking stopped", "#757575")

        return ft.Column(
            spacing=10,
            controls=[
                ft.Text(
                    "Define growth stages (e.g. seedling / growing / mature) with "
                    "their own target ranges and duration. While tracking, the "
                    "active stage's targets are used everywhere automatically.",
                    size=12, color=theme.TEXT_SECONDARY,
                ),
                ft.Container(
                    bgcolor=theme.PRIMARY_LIGHT, border_radius=theme.RADIUS, padding=14,
                    content=ft.Column(
                        spacing=8,
                        controls=[
                            status_text,
                            ft.Row(
                                wrap=True, spacing=8,
                                controls=[
                                    ft.FilledButton("Start planting today", icon=ft.Icons.PLAY_ARROW,
                                                     on_click=start_today),
                                    ft.OutlinedButton("Stop tracking", icon=ft.Icons.STOP,
                                                       on_click=stop_tracking),
                                ],
                            ),
                        ],
                    ),
                ),
                ft.Text("Stages", size=14, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
                stage_rows,
                ft.Container(
                    bgcolor=theme.SURFACE, border_radius=theme.RADIUS, padding=14,
                    border=ft.Border.all(1, theme.BORDER), shadow=theme.shadow(),
                    content=ft.Row(
                        wrap=True, spacing=8, run_spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            new_name_f, new_days_f,
                            ft.FilledButton("Add stage", icon=ft.Icons.ADD, on_click=add_stage),
                        ],
                    ),
                ),
            ],
        )

    _SECTIONS = {
        "Setpoints": section_setpoints,
        "Growth stages": section_growth,
        "Auto-dose rules": section_rules,
        "Manual dosing": section_dosing,
        "Calibration": section_calibration,
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

    # -- section switcher ---------------------------------------------------

    switcher = ft.Row(wrap=True, spacing=8)

    def swap(name: str):
        current["name"] = name
        section_host.content = _SECTIONS[name]()
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
    section_host.content = section_setpoints()

    # -- save bar -----------------------------------------------------------

    def invalid_target_sensors() -> list[str]:
        """Pure data check across the active profile's targets — works no
        matter which section is currently on screen (unlike the per-row
        border/error UI in Setpoints, which only exists while that section's
        controls are mounted)."""
        bad = []
        for sensor_name, rng in state.targets.items():
            if rng.get("min", 0) >= rng.get("max", 0):
                bad.append(sensor_name)
        return bad

    def do_save(e):
        bad = invalid_target_sensors()
        if bad:
            _show_snack(
                f"Fix min/max first: {', '.join(bad)} (min must be less than max)",
                "#C62828",
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
        _show_snack("Saved", "#2E7D32")

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

    save_bar.bgcolor = "#FFF8E1"
    save_bar.padding = ft.Padding(left=14, right=14, top=10, bottom=10)
    save_bar.border_radius = theme.RADIUS
    save_bar.border = ft.Border.all(1, "#F0E6C8")
    save_bar.shadow = theme.shadow()
    save_bar.content = ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Icon(ft.Icons.EDIT_NOTE, color="#F57F17"),
            ft.Text(t("parameters.unsaved", state.language), size=13, color="#F57F17",
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
