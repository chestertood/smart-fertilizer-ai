"""Parameters page — "rules" section.

Split out of parameters.py: each section owns one screenful of controls and
talks to the rest of the page only through SectionCtx.
"""

import flet as ft

from app import theme
from app.views.parameters_common import SectionCtx, _OPS, _SENSOR_META
from config.i18n import t


def build(ctx: SectionCtx) -> ft.Control:
    rule_rows = ft.Column(spacing=8)
    # ctx.nf() fields from rows deleted/rebuilt by render_rules() (below)
    # linger in ctx.live_num_fields otherwise — do_save() then calls
    # .update() on a TextField no longer in the ctx.page tree and Flet
    # raises "Control must be added to the ctx.page first".
    rule_fields: list[ft.TextField] = []

    def render_rules():
        for f in rule_fields:
            if f in ctx.live_num_fields:
                ctx.live_num_fields.remove(f)
        rule_fields.clear()
        rows = []
        for i, r in enumerate(ctx.state.auto_rules):
            start = len(ctx.live_num_fields)
            rows.append(rule_row(i, r))
            rule_fields.extend(ctx.live_num_fields[start:])
        rule_rows.controls = rows

    def rule_row(idx: int, rule: dict) -> ft.Control:
        sensor_dd = ft.Dropdown(
            value=rule.get("sensor", "EC"), width=140, label=t("parameters.rule_if", ctx.state.language),
            options=[ft.dropdown.Option(key=n, text=n) for n in _SENSOR_META],
        )
        op_dd = ft.Dropdown(
            value=rule.get("op", "<"), width=110, label=t("parameters.rule_is", ctx.state.language),
            options=[ft.dropdown.Option(key=o, text=o) for o in _OPS],
        )
        thr_field = ctx.nf(
            signed=True,  # a rule can trigger on a sub-zero temperature
            value=str(rule.get("threshold", 0)), width=90, height=46, label=t("parameters.rule_value", ctx.state.language),
            text_size=14,
        )
        pump_dd = ft.Dropdown(
            value=rule.get("pump", ctx.pump_names[0]), width=150, label=t("parameters.rule_then", ctx.state.language),
            options=[ft.dropdown.Option(key=p, text=p) for p in ctx.pump_names],
        )
        amt_field = ctx.nf(
            value=str(rule.get("amount", 10)), width=90, height=46, label="ml",
            text_size=14,
        )
        enabled_sw = ft.Switch(value=rule.get("enabled", True))

        def upd(_=None, i=idx, s=sensor_dd, o=op_dd, t=thr_field, p=pump_dd, a=amt_field, sw=enabled_sw):
            ctx.state.auto_rules[i] = {
                "sensor": s.value, "op": o.value,
                "threshold": ctx.parse_float(t, ctx.state.auto_rules[i].get("threshold", 0)),
                "pump": p.value,
                "amount": ctx.parse_float(a, ctx.state.auto_rules[i].get("amount", 10)),
                "enabled": sw.value,
            }
            ctx.mark_dirty()

        for c in (sensor_dd, op_dd, pump_dd):
            c.on_select = upd
        thr_field.on_change = upd
        amt_field.on_change = upd
        enabled_sw.on_change = upd

        def delete(e, i=idx):
            ctx.state.auto_rules.pop(i)
            ctx.mark_dirty()
            render_rules()
            rule_rows.update()

        return theme.card(
            content=ft.Row(
                wrap=True, spacing=8, run_spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    sensor_dd, op_dd, thr_field, pump_dd, amt_field, enabled_sw,
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER,
                                  tooltip=t("parameters.delete_rule", ctx.state.language), on_click=delete),
                ],
            ),
        )

    def add_rule(e):
        ctx.state.auto_rules.append({
            "sensor": "EC", "op": "<", "threshold": 1.8,
            "pump": ctx.pump_names[0], "amount": 10, "enabled": True,
        })
        ctx.mark_dirty()
        render_rules()
        rule_rows.update()

    render_rules()
    return ft.Column(
        spacing=10,
        controls=[
            ft.Text(t("parameters.rules_hint", ctx.state.language),
                    size=theme.FONT_SM, color=theme.TEXT_SECONDARY),
            rule_rows,
            ft.FilledButton(t("parameters.add_rule", ctx.state.language), icon=ft.Icons.ADD, on_click=add_rule),
        ],
    )
