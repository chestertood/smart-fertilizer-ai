import datetime
import flet as ft

from app import theme
from app.components.sensor_card import sensor_card
from config.i18n import t
from config.profiles import AppState
from config.sensors import SENSORS


def _greeting(lang: str) -> str:
    hour = datetime.datetime.now().hour
    if hour < 12:
        key = "greeting.morning"
    elif hour < 17:
        key = "greeting.afternoon"
    else:
        key = "greeting.evening"
    return t(key, lang)


def build_dashboard(
    state: AppState, updaters: dict | None = None
) -> tuple[ft.Container, callable, callable]:
    lang = state.language

    card_controls = []
    for s in SENSORS:
        target = state.targets.get(s["name"])
        card, update = sensor_card(s, target, lang)
        card_controls.append(card)
        if updaters is not None:
            updaters[s["name"]] = update

    cards = ft.ResponsiveRow(
        spacing=12,
        run_spacing=12,
        controls=card_controls,
    )

    status_dot = ft.Icon(ft.Icons.CIRCLE, color="#4CAF50", size=10)
    status_text = ft.Text(
        t("dashboard.online", lang),
        size=12,
        color=theme.SUCCESS,
        weight=ft.FontWeight.BOLD,
    )
    status_badge = ft.Container(
        bgcolor=theme.SUCCESS_BG,
        border_radius=20,
        padding=ft.Padding(left=10, right=10, top=4, bottom=4),
        content=ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[status_dot, status_text],
        ),
    )

    def update_connection_status(is_online: bool) -> None:
        if is_online:
            status_dot.color = "#4CAF50"
            status_text.value = t("dashboard.online", lang)
            status_text.color = theme.SUCCESS
            status_badge.bgcolor = theme.SUCCESS_BG
        else:
            status_dot.color = "#F44336"
            status_text.value = t("dashboard.offline", lang)
            status_text.color = theme.DANGER
            status_badge.bgcolor = theme.DANGER_BG

    clock_text = ft.Text(
        datetime.datetime.now().strftime("%a %d %b %Y  %H:%M:%S"),
        size=12, color=theme.TEXT_SECONDARY,
    )

    def update_clock() -> None:
        clock_text.value = datetime.datetime.now().strftime("%a %d %b %Y  %H:%M:%S")

    def build_growth_bar() -> ft.Control | None:
        """Segmented progress bar across the active profile's growth stages,
        filled up to today's position. None if that profile isn't tracking
        a grow cycle (see AppState.current_stage_info)."""
        info = state.current_stage_info()
        if info is None:
            return None
        stages = state.growth_config()["stages"]

        segments = []
        for i, s in enumerate(stages):
            if i < info["stage_index"]:
                fraction = 1.0  # fully completed stage
            elif i == info["stage_index"]:
                fraction = min(1.0, info["day_in_stage"] / s["duration_days"])
            else:
                fraction = 0.0  # upcoming stage
            # Container.expand only accepts bool/int (no float flex weight),
            # so the fill fraction is scaled into an integer ratio here.
            filled = round(fraction * 1000)
            remaining = 1000 - filled
            segments.append(
                ft.Container(
                    expand=max(1, s["duration_days"]),
                    height=14,
                    bgcolor="#E4E9E4",
                    border_radius=4,
                    padding=1,
                    content=ft.Row(
                        spacing=0,
                        controls=[
                            ft.Container(expand=filled, bgcolor=theme.PRIMARY, border_radius=3),
                            ft.Container(expand=remaining),
                        ],
                    ),
                )
            )

        bar_row = ft.Row(spacing=3, controls=segments)
        labels_row = ft.Row(
            controls=[
                ft.Text(
                    s["name"], size=10,
                    color=theme.PRIMARY if i <= info["stage_index"] else theme.TEXT_MUTED,
                    weight=ft.FontWeight.BOLD if i == info["stage_index"] else None,
                    expand=max(1, s["duration_days"]),
                )
                for i, s in enumerate(stages)
            ],
        )
        summary = ft.Text(
            f"Day {info['elapsed_days']} of {info['total_days']} "
            f"({info['overall_pct']:.0f}%) — {info['stage']['name']} "
            f"(day {info['day_in_stage']}/{info['stage']['duration_days']})",
            size=12, color=theme.TEXT_SECONDARY,
        )
        return theme.card(
            ft.Column(
                spacing=6,
                controls=[summary, bar_row, labels_row],
            ),
        )

    growth_bar = build_growth_bar()

    container = ft.Container(
        expand=True,
        padding=theme.PAGE_PADDING,
        content=ft.Column(
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                theme.page_header(
                    t("dashboard.title", lang),
                    f"{_greeting(lang)} · {t('dashboard.subtitle', lang)}",
                    trailing=[clock_text, ft.Container(width=12), status_badge],
                ),
                *([growth_bar] if growth_bar else []),
                cards,
            ],
        ),
    )

    return container, update_connection_status, update_clock
