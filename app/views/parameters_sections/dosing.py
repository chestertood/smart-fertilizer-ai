"""Parameters page — "dosing" section.

Split out of parameters.py: each section owns one screenful of controls and
talks to the rest of the page only through SectionCtx.
"""

import flet as ft

from app import theme
from app.views.parameters_common import SectionCtx
from config.i18n import t


def build(ctx: SectionCtx) -> ft.Control:
    feedback = ft.Text("", size=theme.FONT_SM, color=theme.SUCCESS)

    def pump_row(name: str) -> ft.Control:
        pump = ctx.actuator_hub.pumps[name]
        amount_field = ctx.nf(
            value="10", width=100, height=44, text_size=14,
            suffix=ft.Text("ml"),
        )

        def dose(e, n=name, fld=amount_field):
            try:
                amount = float(fld.value)
            except (TypeError, ValueError):
                feedback.value = t("parameters.bad_number", ctx.state.language).format(pump=n); feedback.color = theme.DANGER
                feedback.update(); return
            try:
                dispensed = ctx.actuator_hub.dose(n, amount)
            except RuntimeError as exc:  # includes CooldownError
                feedback.value = str(exc); feedback.color = theme.DANGER
                feedback.update(); return
            ctx.db.log_dose(n, dispensed, source="manual")
            feedback.value = t("parameters.dispensed", ctx.state.language).format(amount=dispensed, pump=n); feedback.color = theme.SUCCESS
            feedback.update()

        return theme.card(
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.OPACITY, color="#1976D2"),
                    ft.Column(
                        spacing=0, expand=True,
                        controls=[
                            ft.Text(name, size=theme.FONT_MD, weight=ft.FontWeight.W_600),
                            ft.Text(f"max {pump.max_dose:.0f} ml", size=theme.FONT_XS, color=theme.TEXT_MUTED),
                        ],
                    ),
                    amount_field,
                    ft.FilledButton(t("parameters.dose", ctx.state.language), icon=ft.Icons.PLAY_ARROW, on_click=dose),
                ],
            ),
        )

    return ft.Column(
        spacing=10,
        controls=[
            ft.Text(t("parameters.dose_hint", ctx.state.language),
                    size=theme.FONT_SM, color=theme.TEXT_SECONDARY),
            *[pump_row(n) for n in ctx.pump_names],
            feedback,
        ],
    )
