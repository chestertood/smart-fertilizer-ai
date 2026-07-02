import flet as ft

from app.services.database import Database

# Series to plot: (db column, label, color)
_SERIES = [
    ("ec", "EC", "#2196F3"),
    ("ph", "PH", "#9C27B0"),
    ("temp", "Temp", "#FF9800"),
    ("humidity", "Humidity", "#009688"),
]


def build_history(db: Database) -> ft.Container:
    rows = list(reversed(db.recent_readings(limit=60)))  # oldest -> newest
    doses = db.recent_doses(limit=30)

    _BAR_AREA = 90  # px height the sparkline occupies

    def _sparkline(values: list[float], color: str) -> ft.Control:
        """A bar sparkline built from thin Containers (no chart dependency)."""
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0
        bars = [
            ft.Container(
                expand=True,
                height=8 + (v - lo) / span * (_BAR_AREA - 8),
                bgcolor=color,
                border_radius=2,
            )
            for v in values
        ]
        return ft.Container(
            height=_BAR_AREA,
            content=ft.Row(
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=bars,
            ),
        )

    def chart_for(col: str, label: str, color: str) -> ft.Control:
        values = [r[col] for r in rows if r[col] is not None]
        if len(values) < 2:
            body = ft.Container(
                height=_BAR_AREA,
                alignment=ft.Alignment.CENTER,
                content=ft.Text("Not enough data yet", size=12, color="#9E9E9E"),
            )
            latest = ft.Text("")
        else:
            body = _sparkline(values, color)
            latest = ft.Text(
                f"now {values[-1]:.2f}   (min {min(values):.2f} / max {max(values):.2f})",
                size=11, color="#9E9E9E",
            )
        return ft.Container(
            col={"xs": 12, "md": 6},
            bgcolor="#FFFFFF",
            border_radius=12,
            padding=12,
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=color),
                    body,
                    latest,
                ],
            ),
        )

    charts = ft.ResponsiveRow(
        spacing=10,
        run_spacing=10,
        controls=[chart_for(c, lbl, clr) for c, lbl, clr in _SERIES],
    )

    if doses:
        dose_items = [
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.SMART_TOY if d["source"] == "llm" else ft.Icons.PAN_TOOL,
                        size=16,
                        color="#7E57C2" if d["source"] == "llm" else "#1976D2",
                    ),
                    ft.Text(f"{d['pump']}", size=12, weight=ft.FontWeight.W_600, expand=True),
                    ft.Text(f"{d['amount']:.1f} ml", size=12, color="#1976D2"),
                    ft.Text(d["ts"].replace("T", " "), size=10, color="#9E9E9E"),
                ],
            )
            for d in doses
        ]
    else:
        dose_items = [ft.Text("No dosing events yet.", size=12, color="#9E9E9E")]

    dose_log = ft.Container(
        bgcolor="#FFFFFF",
        border_radius=12,
        padding=12,
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Text("Recent dosing events", size=14, weight=ft.FontWeight.W_600, color="#424242"),
                *dose_items,
            ],
        ),
    )

    return ft.Container(
        expand=True,
        padding=ft.Padding(left=12, right=12, top=8, bottom=12),
        content=ft.Column(
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("History", size=18, weight=ft.FontWeight.BOLD, color="#212121"),
                ft.Text("Logged readings and dosing events.", size=11, color="#757575"),
                charts,
                dose_log,
            ],
        ),
    )
