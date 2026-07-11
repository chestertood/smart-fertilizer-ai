import flet as ft

from app import theme
from config.i18n import t, t_status
from config.sensors import get_status


def _bar_fraction(value: float, lo: float, hi: float) -> float:
    """Bar fill = position of value within [lo, hi]. Out of range in EITHER
    direction fills the bar completely — previously Too High clamped to a
    full red bar while Too Low clamped to an empty one, so a dangerously low
    reading was far less visible than a high one."""
    span = hi - lo
    if span <= 0:
        return 0.0
    if value < lo or value > hi:
        return 1.0
    return (value - lo) / span


def sensor_card(sensor: dict, target: dict | None = None, lang: str = "en"):
    """`target` = {"min", "max"} for this sensor from the active crop
    profile (state.targets). Falls back to sensor's own default range if
    not given, so callers that don't care about profiles still work."""
    lo = target["min"] if target else sensor["min"]
    hi = target["max"] if target else sensor["max"]

    value = sensor["value"]
    label, s_color = get_status(value, lo, hi)
    badge_bg, badge_fg = theme.status_style(s_color)
    progress = _bar_fraction(value, lo, hi)

    status_text = ft.Text(
        t_status(label, lang), size=11, color=badge_fg, weight=ft.FontWeight.BOLD
    )
    status_badge = ft.Container(
        bgcolor=badge_bg,
        border_radius=20,
        padding=ft.Padding(left=10, right=10, top=4, bottom=4),
        content=status_text,
    )
    value_text = ft.Text(
        f"{value:.1f}", size=36, weight=ft.FontWeight.BOLD, color=badge_fg
    )
    progress_bar = ft.ProgressBar(
        value=progress, color=s_color, bgcolor="#ECEFEC", height=8, border_radius=4
    )
    range_text = ft.Text(
        f"{t('sensor.target', lang)} {lo}–{hi} {sensor['unit']}",
        size=11, color=theme.TEXT_MUTED,
    )

    container = theme.card(
        col={"xs": 12, "sm": 6},
        content=ft.Column(
            spacing=10,
            tight=True,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Container(
                            bgcolor=sensor["color"],
                            border_radius=10,
                            padding=8,
                            content=ft.Icon(sensor["icon"], color="#FFFFFF", size=22),
                        ),
                        ft.Text(
                            t(f"sensor.name.{sensor['name']}", lang),
                            size=14,
                            weight=ft.FontWeight.W_600,
                            color=theme.TEXT,
                            expand=True,
                        ),
                        status_badge,
                    ],
                ),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.END,
                    spacing=4,
                    controls=[
                        value_text,
                        ft.Text(sensor["unit"], size=13, color=theme.TEXT_MUTED),
                    ],
                ),
                progress_bar,
                ft.Row(
                    controls=[
                        ft.Text(str(lo), size=11, color=theme.TEXT_MUTED),
                        ft.Container(expand=True),
                        range_text,
                        ft.Container(expand=True),
                        ft.Text(str(hi), size=11, color=theme.TEXT_MUTED),
                    ],
                ),
            ],
        ),
    )

    def update(new_value: float) -> None:
        new_label, new_color = get_status(new_value, lo, hi)
        new_bg, new_fg = theme.status_style(new_color)
        value_text.value = f"{new_value:.1f}"
        value_text.color = new_fg
        status_text.value = t_status(new_label, lang)
        status_text.color = new_fg
        status_badge.bgcolor = new_bg
        progress_bar.value = _bar_fraction(new_value, lo, hi)
        progress_bar.color = new_color
        container.update()

    return container, update
