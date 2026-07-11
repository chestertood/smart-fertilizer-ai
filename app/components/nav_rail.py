from typing import Callable
import flet as ft

from app import theme
from config.i18n import t

# (internal key, icon, selected icon) — order defines the rail + index
# mapping. The key is also used as the views-dict lookup in app.py, so it
# stays a fixed English identifier; only the displayed label is translated.
NAV_ITEMS = [
    ("Dashboard",   ft.Icons.DASHBOARD_OUTLINED,  ft.Icons.DASHBOARD),
    ("Parameters",  ft.Icons.TUNE_OUTLINED,       ft.Icons.TUNE),
    ("History",     ft.Icons.HISTORY_OUTLINED,    ft.Icons.HISTORY),
    ("Settings",    ft.Icons.SETTINGS_OUTLINED,   ft.Icons.SETTINGS),
]

NAV_NAMES = [name for name, _, _ in NAV_ITEMS]


def build_nav_rail(
    on_navigate: Callable[[int], None],
    selected_index: int = 0,
    lang: str = "en",
) -> ft.NavigationRail:
    """Always-visible side rail. `on_navigate` receives the destination index."""
    return ft.NavigationRail(
        selected_index=selected_index,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=72,
        bgcolor=theme.NAV_BG,
        indicator_color="#A5D6A7",
        leading=ft.Container(
            padding=ft.Padding(left=0, right=0, top=8, bottom=8),
            content=ft.Icon(ft.Icons.GRASS, color=theme.PRIMARY, size=30),
        ),
        destinations=[
            ft.NavigationRailDestination(
                icon=icon,
                selected_icon=sel_icon,
                label=t(f"nav.{name.lower()}", lang),
            )
            for name, icon, sel_icon in NAV_ITEMS
        ],
        on_change=lambda e: on_navigate(e.control.selected_index),
    )


def set_nav_language(rail: ft.NavigationRail, lang: str) -> None:
    """Update destination labels in place after a language switch. Caller
    must call rail.update() afterward."""
    for (name, _, _), dest in zip(NAV_ITEMS, rail.destinations):
        dest.label = t(f"nav.{name.lower()}", lang)
