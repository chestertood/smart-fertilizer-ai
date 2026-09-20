"""Parameters page — "growth" section.

Split out of parameters.py: each section owns one screenful of controls and
talks to the rest of the page only through SectionCtx.
"""

import copy

import flet as ft

from app import theme
from app.views.parameters_common import SectionCtx, _SENSOR_META
from config.i18n import t


def build(ctx: SectionCtx) -> ft.Control:
    g = ctx.state.growth_config()
    stage_rows = ft.Column(spacing=8)
    # ctx.nf() fields from stages deleted/rebuilt by render_stages() (below)
    # linger in ctx.live_num_fields otherwise — do_save() then calls
    # .update() on a TextField no longer in the ctx.page tree and Flet
    # raises "Control must be added to the ctx.page first".
    stage_fields: list[ft.TextField] = []

    def render_stages():
        for f in stage_fields:
            if f in ctx.live_num_fields:
                ctx.live_num_fields.remove(f)
        stage_fields.clear()
        cards = []
        for i, s in enumerate(g["stages"]):
            start = len(ctx.live_num_fields)
            cards.append(stage_card(i, s))
            stage_fields.extend(ctx.live_num_fields[start:])
        stage_rows.controls = cards

    def stage_card(idx: int, stage: dict) -> ft.Control:
        name_f = ft.TextField(
            label=t("parameters.stage_name", ctx.state.language), value=stage["name"], width=160, height=46,
            text_size=14,
        )
        days_f = ctx.nf(
            label="Duration (days)", value=str(stage["duration_days"]),
            width=140, height=46, text_size=14,
        )

        def on_name(e, i=idx, f=name_f):
            g["stages"][i]["name"] = f.value or g["stages"][i]["name"]
            ctx.mark_dirty()

        def on_days(e, i=idx, f=days_f):
            try:
                g["stages"][i]["duration_days"] = max(1, int(float(f.value)))
            except (TypeError, ValueError):
                f.value = str(g["stages"][i]["duration_days"])
                f.update()
            ctx.mark_dirty()

        name_f.on_change = on_name
        days_f.on_change = on_days

        def delete(e, i=idx):
            ctx.state.delete_stage(i)
            ctx.mark_dirty()
            render_stages()
            stage_rows.update()

        target_fields = []
        for sname, meta in _SENSOR_META.items():
            tgt = stage["targets"].setdefault(
                sname, {"min": meta["min"], "max": meta["max"]}
            )
            min_f = ctx.nf(
                signed=True,
                label=f"{sname} min", value=str(tgt["min"]), width=110,
                height=44, text_size=13,
            )
            max_f = ctx.nf(
                signed=True,
                label=f"{sname} max", value=str(tgt["max"]), width=110,
                height=44, text_size=13,
            )

            def on_min(e, i=idx, s=sname, f=min_f):
                g["stages"][i]["targets"][s]["min"] = ctx.parse_float(
                    f, g["stages"][i]["targets"][s]["min"]
                )
                ctx.mark_dirty()

            def on_max(e, i=idx, s=sname, f=max_f):
                g["stages"][i]["targets"][s]["max"] = ctx.parse_float(
                    f, g["stages"][i]["targets"][s]["max"]
                )
                ctx.mark_dirty()

            min_f.on_change = on_min
            max_f.on_change = on_max
            target_fields += [min_f, max_f]

        return theme.card(
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                bgcolor=theme.PRIMARY, border_radius=12,
                                padding=ft.Padding(left=8, right=8, top=2, bottom=2),
                                content=ft.Text(f"Stage {idx + 1}", size=theme.FONT_XS,
                                                 color="#FFFFFF", weight=ft.FontWeight.BOLD),
                            ),
                            name_f, days_f,
                            ft.Container(expand=True),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER,
                                          tooltip=t("parameters.delete_stage", ctx.state.language), on_click=delete),
                        ],
                    ),
                    ft.Row(wrap=True, spacing=8, run_spacing=8, controls=target_fields),
                ],
            ),
        )

    render_stages()

    # -- add stage ---
    new_name_f = ft.TextField(label=t("common.name", ctx.state.language), width=160, height=46, text_size=14)
    new_days_f = ctx.nf(label=t("parameters.duration_days", ctx.state.language), value="7", width=140,
                            height=46, text_size=14)

    def add_stage(e):
        try:
            days = max(1, int(float(new_days_f.value)))
        except (TypeError, ValueError):
            days = 7
        ctx.state.add_stage(new_name_f.value or f"Stage {len(g['stages']) + 1}", days)
        new_name_f.value = ""
        ctx.mark_dirty()
        render_stages()
        stage_rows.update()

    # -- planting date controls ---
    status_text = ft.Text(size=theme.FONT_SM, color=theme.TEXT)

    def refresh_status():
        info = ctx.state.current_stage_info()
        if info is None:
            planted = g.get("planting_date")
            status_text.value = (
                "Not tracking a grow cycle. Add stages below, then start planting."
                if not g["stages"] else
                f"Stages defined but not tracking (planted: {planted or 'never'})."
            )
            status_text.color = theme.TEXT_MUTED
        else:
            status_text.value = (
                f"Day {info['elapsed_days']} of {info['total_days']} "
                f"({info['overall_pct']:.0f}%) — Stage {info['stage_index'] + 1}: "
                f"{info['stage']['name']} (day {info['day_in_stage']}/"
                f"{info['stage']['duration_days']})"
            )
            status_text.color = theme.SUCCESS

    refresh_status()

    def start_today(e):
        ctx.state.start_planting()
        ctx.state.save()  # immediate action, like the dosing buttons — don't
        # wait on the ctx.page-level Save button or this is lost on restart.
        ctx.snapshot["growth"] = copy.deepcopy(ctx.state.growth)  # keep Reset in sync
        refresh_status(); status_text.update()
        ctx.show_snack(t("parameters.planting_started", ctx.state.language), theme.SUCCESS)

    def stop_tracking(e):
        ctx.state.stop_planting()
        ctx.state.save()
        ctx.snapshot["growth"] = copy.deepcopy(ctx.state.growth)
        refresh_status(); status_text.update()
        ctx.show_snack(t("parameters.tracking_stopped", ctx.state.language), theme.TEXT_SECONDARY)

    return ft.Column(
        spacing=10,
        controls=[
            ft.Text(
                t("parameters.growth_hint", ctx.state.language),
                size=theme.FONT_SM, color=theme.TEXT_SECONDARY,
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
                                ft.FilledButton(t("parameters.start_planting", ctx.state.language), icon=ft.Icons.PLAY_ARROW,
                                                 on_click=start_today),
                                ft.OutlinedButton(t("parameters.stop_tracking", ctx.state.language), icon=ft.Icons.STOP,
                                                   on_click=stop_tracking),
                            ],
                        ),
                    ],
                ),
            ),
            ft.Text(t("parameters.stages", ctx.state.language), size=theme.FONT_SM, weight=ft.FontWeight.W_600, color=theme.TEXT_SECONDARY),
            stage_rows,
            theme.card(
                content=ft.Row(
                    wrap=True, spacing=8, run_spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        new_name_f, new_days_f,
                        ft.FilledButton(t("parameters.add_stage", ctx.state.language), icon=ft.Icons.ADD, on_click=add_stage),
                    ],
                ),
            ),
        ],
    )
