import flet as ft

from app import theme
from config.i18n import t

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


# A person icon for both modes — auto mode pins a small "AI" tag on its
# corner (same purple accent as the AI badge on dosing-log entries, see
# history.py) so "manual vs AI" reads the same everywhere. White like the
# chat shortcut, so the mode toggle reads as one of the app bar's own icon
# buttons instead of a separate badge style.
_AI_ACCENT = "#7E57C2"
_MODE_TOOLTIPS = {
    "approval": "Mode: Approval — dosing waits for your tap",
    "auto":     "Mode: Auto-dose — dosing applies immediately",
}


def _mode_content(mode: str) -> ft.Control:
    person = ft.Icon(ft.Icons.PERSON, color="#FFFFFF", size=22)
    if mode != "auto":
        return person
    return ft.Stack(
        width=36,
        height=28,
        controls=[
            ft.Container(bottom=0, left=2, width=18, height=18,
                         alignment=ft.Alignment.CENTER,
                         content=ft.Icon(ft.Icons.PERSON, color="#FFFFFF", size=16)),
            ft.Container(
                top=0,
                right=0,
                bgcolor="#FFFFFF",
                border_radius=8,
                padding=ft.Padding(left=5, right=5, top=2, bottom=2),
                content=ft.Text("AI", size=theme.FONT_XS, weight=ft.FontWeight.BOLD, color=_AI_ACCENT),
            ),
        ],
    )


def build_app_bar(state=None, on_chat=None, on_flag=None, on_mode=None):
    """Slim title bar. Returns (container, set_flag, set_mode) where
    set_flag(lang)/set_mode(mode) update the language flag / mode badge
    after a change. `on_flag`/`on_mode` fire when their control is tapped
    (to toggle language / llm_mode)."""
    controls = [
        ft.Image(src="logo.png", width=34, height=34, fit=ft.BoxFit.CONTAIN),
        ft.Container(width=3),
        ft.Container(
            margin=ft.Margin(top=6, left=0, right=0, bottom=0),
            expand=True,
            content=ft.Text(
                "Smart Fertilizer Dosing",
                size=theme.FONT_MD,
                font_family="PixelFont",
                color="#FFFFFF",
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
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

    mode = getattr(state, "llm_mode", "approval") if state is not None else "approval"
    mode_button = ft.Container(
        width=40,
        height=40,
        border_radius=20,
        ink=True,
        alignment=ft.Alignment.CENTER,
        tooltip=_MODE_TOOLTIPS.get(mode, _MODE_TOOLTIPS["approval"]),
        on_click=on_mode,
        content=_mode_content(mode),
    )
    if on_mode is not None:
        controls.append(mode_button)

    if on_chat is not None:
        controls.append(
            ft.IconButton(
                icon=ft.Icons.CHAT_BUBBLE,
                icon_color="#FFFFFF",
                tooltip=t("chat.title", lang),
                on_click=on_chat,
            )
        )

    container = ft.Container(
        gradient=ft.LinearGradient(
            begin=ft.Alignment.CENTER_LEFT,
            end=ft.Alignment.CENTER_RIGHT,
            colors=[theme.PRIMARY_DARK, theme.PRIMARY],
        ),
        padding=ft.Padding(left=30, right=8, top=10, bottom=10),
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        ),
    )

    def set_flag(new_lang: str) -> None:
        flag_holder.content = _flag_for(new_lang)
        flag_holder.tooltip = "ไทย" if new_lang == "th" else "English"
        flag_holder.update()

    def set_mode(new_mode: str) -> None:
        mode_button.content = _mode_content(new_mode)
        mode_button.tooltip = _MODE_TOOLTIPS.get(new_mode, _MODE_TOOLTIPS["approval"])
        mode_button.update()

    return container, set_flag, set_mode
