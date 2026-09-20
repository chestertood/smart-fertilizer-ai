import flet as ft

from app import theme
from config.i18n import t, t_status
from config.sensors import get_status, sensor_icon


# A single dropped Modbus frame shouldn't flash "No signal" on the card, so
# a reading is only called stale after this many consecutive failed polls
# (hub.read_all() returns NaN per failed sensor). Poll is 2s -> ~4s to show.
_STALE_AFTER_FAILS = 2


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
        t_status(label, lang), size=theme.FONT_XS, color=badge_fg, weight=ft.FontWeight.BOLD
    )
    status_badge = ft.Container(
        bgcolor=badge_bg,
        border_radius=20,
        padding=ft.Padding(left=10, right=10, top=4, bottom=4),
        content=status_text,
    )
    value_text = ft.Text(
        f"{value:.1f}", size=theme.FONT_XXL, weight=ft.FontWeight.BOLD, color=badge_fg
    )
    # Reserved width for the big number: Roboto's digits aren't fixed-width,
    # so "8.8" -> "10.1" re-flowed the row on every poll and the unit label
    # beside it visibly jittered. Flet 0.85's TextStyle has no font_features,
    # so tabular figures aren't available — a fixed box is the stable fix.
    # ponytail: 104px fits "100.0" at size 32; a 4-digit reading would clip.
    value_box = ft.Container(
        width=104, alignment=ft.Alignment.CENTER_LEFT, content=value_text
    )
    progress_bar = ft.ProgressBar(
        value=progress, color=s_color, bgcolor=theme.BORDER, height=8, border_radius=4
    )
    range_text = ft.Text(
        f"{t('sensor.target', lang)} {lo}–{hi} {sensor['unit']}",
        size=theme.FONT_XS, color=theme.TEXT_MUTED,
    )

    container = theme.card(
        col={"xs": 12, "sm": 6},
        padding=12,
        content=ft.Column(
            spacing=8,
            tight=True,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    controls=[
                        ft.Container(
                            bgcolor=sensor["color"],
                            border_radius=8,
                            width=40,
                            height=40,
                            alignment=ft.Alignment.CENTER,
                            content=sensor_icon(sensor, size=22),
                        ),
                        ft.Text(
                            t(f"sensor.name.{sensor['name']}", lang),
                            size=theme.FONT_MD,
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
                        value_box,
                        ft.Text(sensor["unit"], size=theme.FONT_SM, color=theme.TEXT_MUTED),
                    ],
                ),
                progress_bar,
                ft.Row(
                    controls=[
                        ft.Text(str(lo), size=theme.FONT_XS, color=theme.TEXT_MUTED),
                        ft.Container(expand=True),
                        range_text,
                        ft.Container(expand=True),
                        ft.Text(str(hi), size=theme.FONT_XS, color=theme.TEXT_MUTED),
                    ],
                ),
            ],
        ),
    )

    fails = 0

    def update(new_value: float) -> None:
        """Called every poll with the latest reading. NaN means the sensor
        read failed: the last number stays on screen but goes grey with a
        "No signal" badge, so a frozen value can't be mistaken for a live
        one. A good reading clears the state immediately."""
        nonlocal fails
        if new_value != new_value:  # NaN
            fails += 1
            if fails >= _STALE_AFTER_FAILS:
                value_text.color = theme.TEXT_MUTED
                status_text.value = t("sensor.no_signal", lang)
                status_text.color = theme.TEXT_SECONDARY
                status_badge.bgcolor = theme.NEUTRAL_BG
                progress_bar.color = theme.TEXT_MUTED
                container.update()
            return
        fails = 0
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
