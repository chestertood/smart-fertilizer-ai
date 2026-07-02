import flet as ft
from config.sensors import SENSORS
from app.components.sensor_card import sensor_card


def build_dashboard(updaters: dict | None = None) -> tuple[ft.Container, callable]:
    card_controls = []
    for s in SENSORS:
        card, update = sensor_card(s)
        card_controls.append(card)
        if updaters is not None:
            updaters[s["name"]] = update

    cards = ft.ResponsiveRow(
        spacing=10,
        run_spacing=10,
        controls=card_controls,
    )

    status_dot = ft.Icon(ft.Icons.CIRCLE, color="#4CAF50", size=10)
    status_text = ft.Text(
        "Online",
        size=11,
        color="#2E7D32",
        weight=ft.FontWeight.BOLD,
    )
    status_badge = ft.Container(
        bgcolor="#E8F5E9",
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
            status_text.value = "Online"
            status_text.color = "#2E7D32"
            status_badge.bgcolor = "#E8F5E9"
        else:
            status_dot.color = "#F44336"
            status_text.value = "Offline"
            status_text.color = "#C62828"
            status_badge.bgcolor = "#FFEBEE"

    container = ft.Container(
        expand=True,
        padding=ft.Padding(left=12, right=12, top=8, bottom=12),
        content=ft.Column(
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            expand=True,
                            controls=[
                                ft.Text(
                                    "Sensor Dashboard",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color="#212121",
                                ),
                                ft.Text(
                                    "Real-time monitoring",
                                    size=11,
                                    color="#757575",
                                ),
                            ],
                        ),
                        status_badge,
                    ],
                ),
                cards,
            ],
        ),
    )

    return container, update_connection_status
