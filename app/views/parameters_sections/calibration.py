"""Parameters page — "calibration" section.

Split out of parameters.py: each section owns one screenful of controls and
talks to the rest of the page only through SectionCtx.
"""

import flet as ft

from app import theme
from app.views.parameters_common import SectionCtx, _SENSOR_META
from config.i18n import t


def build(ctx: SectionCtx) -> ft.Control:
    pump_cards = []
    for name in ctx.pump_names:
        cfg = ctx.state.pumps.setdefault(name, {"max_dose": ctx.actuator_hub.pumps[name].max_dose, "ml_per_s": 1.0})
        max_f = ctx.nf(label="max dose (ml)", value=str(cfg["max_dose"]),
                          width=140, height=46, text_size=14)
        mls_f = ctx.nf(label="ml / second", value=str(cfg.get("ml_per_s", 1.0)),
                          width=140, height=46, text_size=14)

        def on_max(e, n=name, f=max_f):
            ctx.state.pumps[n]["max_dose"] = ctx.parse_float(f, ctx.state.pumps[n]["max_dose"]); ctx.mark_dirty()

        def on_mls(e, n=name, f=mls_f):
            ctx.state.pumps[n]["ml_per_s"] = ctx.parse_float(f, ctx.state.pumps[n].get("ml_per_s", 1.0)); ctx.mark_dirty()

        max_f.on_change = on_max
        mls_f.on_change = on_mls
        pump_cards.append(
            theme.card(
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10,
                    controls=[
                        ft.Icon(ft.Icons.SETTINGS_INPUT_COMPONENT, color="#6A1B9A"),
                        ft.Text(name, size=theme.FONT_MD, weight=ft.FontWeight.W_600, expand=True),
                        max_f, mls_f,
                    ],
                ),
            )
        )

    offset_fields = []
    for name, meta in _SENSOR_META.items():
        off = ctx.state.offsets.setdefault(name, 0.0)
        # Offsets are the one field that routinely goes negative — a probe
        # reading 0.3 high is corrected with -0.3.
        f = ctx.nf(signed=True,
                      label=f"{name} offset ({meta['unit']})", value=str(off),
                      width=180, height=46, text_size=14)

        def on_off(e, n=name, fld=f):
            ctx.state.offsets[n] = ctx.parse_float(fld, ctx.state.offsets[n]); ctx.mark_dirty()

        f.on_change = on_off
        offset_fields.append(f)

    width_f = ctx.nf(
        label="Tank width (cm)", value=str(ctx.state.water_tank["width_cm"]),
        width=160, height=46, text_size=14,
    )
    length_f = ctx.nf(
        label="Tank length (cm)", value=str(ctx.state.water_tank["length_cm"]),
        width=160, height=46, text_size=14,
    )
    height_f = ctx.nf(
        label="Tank height (cm)", value=str(ctx.state.water_tank["height_cm"]),
        width=160, height=46, text_size=14,
    )
    volume_text = ft.Text("", size=theme.FONT_XS, color=theme.TEXT_SECONDARY)

    def refresh_volume():
        volume_text.value = f"Capacity ~{ctx.state.tank_capacity_liters():.1f} L"

    refresh_volume()

    def on_tank_height(e):
        ctx.state.water_tank["height_cm"] = ctx.parse_float(height_f, ctx.state.water_tank["height_cm"])
        refresh_volume(); volume_text.update(); ctx.mark_dirty()

    def on_tank_width(e):
        ctx.state.water_tank["width_cm"] = ctx.parse_float(width_f, ctx.state.water_tank["width_cm"])
        refresh_volume(); volume_text.update(); ctx.mark_dirty()

    def on_tank_length(e):
        ctx.state.water_tank["length_cm"] = ctx.parse_float(length_f, ctx.state.water_tank["length_cm"])
        refresh_volume(); volume_text.update(); ctx.mark_dirty()

    height_f.on_change = on_tank_height
    width_f.on_change = on_tank_width
    length_f.on_change = on_tank_length

    return ft.Column(
        spacing=10,
        controls=[
            ft.Text(t("parameters.calib_hint", ctx.state.language), size=theme.FONT_SM, color=theme.TEXT_SECONDARY),
            ft.Text(t("parameters.pumps", ctx.state.language), size=theme.FONT_SM, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
            *pump_cards,
            ft.Divider(),
            ft.Text(t("parameters.sensor_offsets", ctx.state.language), size=theme.FONT_SM, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
            theme.card(
                content=ft.Row(wrap=True, spacing=10, run_spacing=10, controls=offset_fields),
            ),
            ft.Divider(),
            ft.Text(t("parameters.reservoir", ctx.state.language), size=theme.FONT_SM, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
            theme.card(
                content=ft.Column(
                    spacing=6,
                    controls=[
                        ft.Text(
                            t("parameters.tank_hint", ctx.state.language),
                            size=theme.FONT_XS, color=theme.TEXT_MUTED,
                        ),
                        ft.Row(wrap=True, spacing=10, run_spacing=10,
                               controls=[width_f, length_f, height_f]),
                        volume_text,
                    ],
                ),
            ),
        ],
    )
