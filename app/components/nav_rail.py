from typing import Callable
import flet as ft

# (view name, icon, selected icon) — order defines the rail + index mapping.
NAV_ITEMS = [
    ("Dashboard",   ft.Icons.DASHBOARD_OUTLINED,  ft.Icons.DASHBOARD),
    ("Parameters",  ft.Icons.TUNE_OUTLINED,       ft.Icons.TUNE),
    ("LLM Advisor", ft.Icons.SMART_TOY_OUTLINED,  ft.Icons.SMART_TOY),
    ("History",     ft.Icons.HISTORY_OUTLINED,    ft.Icons.HISTORY),
    ("Settings",    ft.Icons.SETTINGS_OUTLINED,   ft.Icons.SETTINGS),
]

NAV_NAMES = [name for name, _, _ in NAV_ITEMS]


def build_nav_rail(
    on_navigate: Callable[[int], None],
    selected_index: int = 0,
) -> ft.NavigationRail:
    """Always-visible side rail. `on_navigate` receives the destination index."""
    return ft.NavigationRail(
        selected_index=selected_index,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=72,
        bgcolor="#F1F8E9",
        indicator_color="#A5D6A7",
        leading=ft.Container(
            padding=ft.Padding(left=0, right=0, top=8, bottom=8),
            content=ft.Icon(ft.Icons.GRASS, color="#388E3C", size=30),
        ),
        destinations=[
            ft.NavigationRailDestination(
                icon=icon,
                selected_icon=sel_icon,
                label=name,
            )
            for name, icon, sel_icon in NAV_ITEMS
        ],
        on_change=lambda e: on_navigate(e.control.selected_index),
    )
