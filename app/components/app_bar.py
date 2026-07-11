import flet as ft

from app import theme

# Tiny hand-drawn flags (24x16) instead of emoji — flag emoji don't render on
# Windows desktop (they degrade to "TH"/"US" letters). Drawn flags look the
# same on Windows dev and the Raspberry Pi.
_FLAG_W = 24
_FLAG_H = 16


def _thai_flag() -> ft.Control:
    # Red / white / blue(double) / white / red horizontal stripes.
    def stripe(color, h):
        return ft.Container(bgcolor=color, height=h, width=_FLAG_W)
    return ft.Column(
        spacing=0, tight=True,
        controls=[
            stripe("#A51931", 3), stripe("#F4F5F8", 2),
            stripe("#2D2A4A", 6),
            stripe("#F4F5F8", 2), stripe("#A51931", 3),
        ],
    )


def _usa_flag() -> ft.Control:
    # 7 red/white stripes with a blue canton over the top-left.
    stripes = ft.Column(
        spacing=0, tight=True,
        controls=[
            ft.Container(bgcolor=c, height=h, width=_FLAG_W)
            for c, h in [
                ("#B22234", 2), ("#FFFFFF", 2), ("#B22234", 2), ("#FFFFFF", 2),
                ("#B22234", 3), ("#FFFFFF", 3), ("#B22234", 2),
            ]
        ],
    )
    canton = ft.Container(bgcolor="#3C3B6E", width=11, height=9)
    return ft.Stack(width=_FLAG_W, height=_FLAG_H, controls=[stripes, canton])


def _flag_for(lang: str) -> ft.Control:
    return _thai_flag() if lang == "th" else _usa_flag()


def build_app_bar(state=None, on_chat=None, on_flag=None):
    """Slim title bar. Returns (container, set_flag) where set_flag(lang)
    updates the language-shortcut flag after a language switch. `on_flag` is
    called when the flag is clicked (to toggle language)."""
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

    lang = getattr(state, "language", "en") if state is not None else "en"
    flag_holder = ft.Container(
        content=_flag_for(lang),
        border_radius=3,
        border=ft.Border.all(1, "#FFFFFF"),
        ink=True,
        tooltip="ไทย" if lang == "th" else "English",
        on_click=on_flag,
        padding=0,
    )
    if on_flag is not None:
        controls.append(flag_holder)
        controls.append(ft.Container(width=4))

    if on_chat is not None:
        controls.append(
            ft.IconButton(
                icon=ft.Icons.CHAT_BUBBLE,
                icon_color="#FFFFFF",
                tooltip="Farm Assistant",
                on_click=on_chat,
            )
        )

    container = ft.Container(
        gradient=ft.LinearGradient(
            begin=ft.Alignment.CENTER_LEFT,
            end=ft.Alignment.CENTER_RIGHT,
            colors=[theme.PRIMARY_DARK, theme.PRIMARY],
        ),
        padding=ft.Padding(left=16, right=8, top=10, bottom=10),
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        ),
    )

    def set_flag(new_lang: str) -> None:
        flag_holder.content = _flag_for(new_lang)
        flag_holder.tooltip = "ไทย" if new_lang == "th" else "English"
        flag_holder.update()

    return container, set_flag
