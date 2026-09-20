"""Parameters page — "setpoints" section.

Split out of parameters.py: each section owns one screenful of controls and
talks to the rest of the page only through SectionCtx.
"""

import flet as ft

from app import theme
from app.views.parameters_common import SectionCtx, _SENSOR_META, is_number
from config.i18n import t
from config.sensors import get_status, sensor_icon


def build(ctx: SectionCtx) -> ft.Control:
    rows = []
    targets = ctx.state.targets  # active profile's editable dict

    for name, meta in _SENSOR_META.items():
        tgt = targets.setdefault(name, {"min": meta["min"], "max": meta["max"]})
        unit = meta["unit"]
        dot = ft.Icon(ft.Icons.CIRCLE, size=12, color=theme.TEXT_MUTED)
        reading_txt = ft.Text("", size=theme.FONT_XS, color=theme.TEXT_MUTED)

        def refresh_status(n=name, d=dot, rt=reading_txt):
            val = ctx.state.last_readings.get(n)
            t = ctx.state.targets.get(n, {})
            if isinstance(val, (int, float)) and val == val and t:
                _, color = get_status(val, t["min"], t["max"])
                d.color = color
                rt.value = f"now {val:.2f}"
            else:
                d.color = theme.TEXT_MUTED
                rt.value = "no reading"

        refresh_status()

        min_field = ctx.nf(
            signed=True,
            label="min", value=str(tgt["min"]), width=90, height=46, text_size=14,
        )
        max_field = ctx.nf(
            signed=True,
            label="max", value=str(tgt["max"]), width=90, height=46, text_size=14,
        )
        range_error = ft.Text("", size=theme.FONT_XS, color=theme.DANGER)

        def apply_validation(n=name, minf=min_field, maxf=max_field, err=range_error):
            """Set border/error ctx.state from the field text and the data. No
            .update() here — safe to call before the row is mounted
            (initial build) too.

            Text is checked before ctx.state because ctx.state can't show the
            problem: ctx.parse_float() keeps the last good number when the box
            won't parse, so "abc" leaves ctx.state looking perfectly valid."""
            not_numbers = [f for f in (minf, maxf) if not is_number(f.value)]
            if not_numbers:
                for f in (minf, maxf):
                    f.border_color = theme.DANGER if f in not_numbers else None
                err.value = "numbers only"
                return False
            lo, hi = ctx.state.targets[n]["min"], ctx.state.targets[n]["max"]
            invalid = lo >= hi
            minf.border_color = theme.DANGER if invalid else None
            maxf.border_color = theme.DANGER if invalid else None
            err.value = "min must be less than max" if invalid else ""
            return not invalid

        # Everything these handlers touch is bound as a default argument:
        # a bare `min_field` here is a free variable resolved at call time,
        # so every row ended up updating the last row's controls.
        def on_min(e, n=name, f=min_field, rs=refresh_status, d=dot,
                   rt=reading_txt, minf=min_field, maxf=max_field,
                   err=range_error, validate=apply_validation):
            ctx.state.targets[n]["min"] = ctx.parse_float(f, ctx.state.targets[n]["min"])
            rs(); d.update(); rt.update()
            validate()
            minf.update(); maxf.update(); err.update()
            ctx.mark_dirty()

        def on_max(e, n=name, f=max_field, rs=refresh_status, d=dot,
                   rt=reading_txt, minf=min_field, maxf=max_field,
                   err=range_error, validate=apply_validation):
            ctx.state.targets[n]["max"] = ctx.parse_float(f, ctx.state.targets[n]["max"])
            rs(); d.update(); rt.update()
            validate()
            minf.update(); maxf.update(); err.update()
            ctx.mark_dirty()

        min_field.on_change = on_min
        max_field.on_change = on_max
        apply_validation()  # catch any pre-existing invalid data on open (no .update, unmounted)

        rows.append(
            theme.card(
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Row(
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    bgcolor=meta["color"], border_radius=10,
                                    width=44, height=44,
                                    alignment=ft.Alignment.CENTER,
                                    content=sensor_icon(meta, size=24),
                                ),
                                ft.Column(
                                    spacing=0, expand=True,
                                    controls=[
                                        ft.Text(
                                            f"{t(f'sensor.name.{name}', ctx.state.language)} ({unit})",
                                            size=theme.FONT_SM, weight=ft.FontWeight.W_600, color=theme.TEXT,
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
        ctx.state.reset_targets_to_default()
        ctx.mark_dirty()
        ctx.swap("Setpoints")

    return ft.Column(
        spacing=10,
        controls=[
            ft.Text(t("parameters.setpoints_hint", ctx.state.language),
                    size=theme.FONT_SM, color=theme.TEXT_SECONDARY),
            *rows,
            ft.TextButton(
                t("parameters.reset_defaults", ctx.state.language),
                icon=ft.Icons.RESTART_ALT,
                on_click=reset_defaults,
            ),
        ],
    )
