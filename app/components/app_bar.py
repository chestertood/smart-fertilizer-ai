import flet as ft


def build_app_bar(state=None) -> ft.Container:
    """Slim title bar. Navigation now lives in the side rail, so there's no
    hamburger button. Shows a control-mode chip when `state` is provided."""
    controls = [
        ft.Icon(ft.Icons.GRASS, color="#FFFFFF", size=24),
        ft.Container(width=8),
        ft.Text(
            "Smart Fertilizer",
            size=17,
            weight=ft.FontWeight.BOLD,
            color="#FFFFFF",
            expand=True,
        ),
    ]

    if state is not None:
        mode = getattr(state, "control_mode", "Manual")
        controls.append(
            ft.Container(
                bgcolor="#FFFFFF",
                border_radius=20,
                padding=ft.Padding(left=12, right=12, top=4, bottom=4),
                content=ft.Row(
                    spacing=6,
                    tight=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(
                            ft.Icons.PAN_TOOL if mode == "Manual" else ft.Icons.SMART_TOY,
                            color="#388E3C",
                            size=16,
                        ),
                        ft.Text(mode, size=12, weight=ft.FontWeight.BOLD, color="#388E3C"),
                    ],
                ),
            )
        )

    return ft.Container(
        bgcolor="#388E3C",
        padding=ft.Padding(left=12, right=12, top=8, bottom=8),
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        ),
    )
