import flet as ft
from config.sensors import get_status


def sensor_card(sensor: dict):
    value = sensor["value"]
    label, s_color = get_status(value, sensor["min"], sensor["max"])
    progress = min(1.0, max(0.0, value / sensor["abs_max"]))

    status_text = ft.Text(
        label, size=11, color="#FFFFFF", weight=ft.FontWeight.BOLD
    )
    status_badge = ft.Container(
        bgcolor=s_color,
        border_radius=20,
        padding=ft.Padding(left=10, right=10, top=4, bottom=4),
        content=status_text,
    )
    value_text = ft.Text(
        f"{value:.1f}", size=34, weight=ft.FontWeight.BOLD, color=s_color
    )
    progress_bar = ft.ProgressBar(
        value=progress, color=s_color, bgcolor="#EEEEEE", height=10, border_radius=5
    )

    container = ft.Container(
        col={"xs": 12, "sm": 6},
        bgcolor="#FFFFFF",
        border_radius=14,
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
                            border_radius=10,
                            padding=8,
                            content=ft.Icon(sensor["icon"], color="#FFFFFF", size=22),
                        ),
                        ft.Text(
                            sensor["name"],
                            size=15,
                            weight=ft.FontWeight.W_600,
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
                        ft.Text(sensor["unit"], size=13, color="#9E9E9E"),
                    ],
                ),
                progress_bar,
                ft.Row(
                    controls=[
                        ft.Text("0", size=10, color="#BDBDBD"),
                        ft.Container(expand=True),
                        ft.Text(
                            f"Normal {sensor['min']}-{sensor['max']} {sensor['unit']}",
                            size=10,
                            color="#9E9E9E",
                        ),
                        ft.Container(expand=True),
                        ft.Text(str(int(sensor["abs_max"])), size=10, color="#BDBDBD"),
                    ],
                ),
            ],
        ),
    )

    def update(new_value: float) -> None:
        new_label, new_color = get_status(new_value, sensor["min"], sensor["max"])
        value_text.value = f"{new_value:.1f}"
        value_text.color = new_color
        status_text.value = new_label
        status_badge.bgcolor = new_color
        progress_bar.value = min(1.0, max(0.0, new_value / sensor["abs_max"]))
        progress_bar.color = new_color
        container.update()

    return container, update
