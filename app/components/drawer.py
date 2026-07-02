from typing import Callable
import flet as ft

_NAV_ITEMS = [
    ("Dashboard", ft.Icons.DASHBOARD),
    ("Manual Control", ft.Icons.TUNE),
    ("LLM Advisor", ft.Icons.SMART_TOY),
    ("History", ft.Icons.HISTORY),
    ("Settings", ft.Icons.SETTINGS),
]


def build_drawer(on_navigate: Callable[[str], None]) -> ft.NavigationDrawer:
    def make_tile(name: str, icon) -> ft.ListTile:
        return ft.ListTile(
            leading=ft.Icon(icon, size=26),
            title=ft.Text(name, size=16),
            on_click=lambda e, n=name: on_navigate(n),
        )

    return ft.NavigationDrawer(
        controls=[
            ft.Container(height=16),
            ft.ListTile(
                leading=ft.Icon(ft.Icons.GRASS, color="#388E3C", size=28),
                title=ft.Text("Smart Fertilizer", weight=ft.FontWeight.BOLD, size=18),
            ),
            ft.Divider(),
            *[make_tile(name, icon) for name, icon in _NAV_ITEMS],
        ],
    )
