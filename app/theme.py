"""Central design tokens and small UI helpers shared by every view.

One place to change the app's look: palette, radii, shadow, page padding and
the standard card / page-header builders. Views import from here instead of
hardcoding hex values, so the whole app stays visually consistent.
"""

import flet as ft

# -- palette -----------------------------------------------------------------
PRIMARY = "#2E7D32"        # brand green: app bar, selected controls, accents
PRIMARY_DARK = "#1B5E20"
PRIMARY_LIGHT = "#E8F5E9"  # tinted fills: badges, bot bubbles, selected chips
NAV_BG = "#F1F8E9"

BG = "#F4F6F4"             # page background behind cards
SURFACE = "#FFFFFF"        # card background
BORDER = "#E4E9E4"         # hairline card border

TEXT = "#212121"
TEXT_SECONDARY = "#5F6368"
TEXT_MUTED = "#80868B"

SUCCESS = "#2E7D32"
WARNING = "#E65100"
DANGER = "#C62828"
SUCCESS_BG = "#E8F5E9"
WARNING_BG = "#FFF3E0"
DANGER_BG = "#FDECEA"

RADIUS = 14
PAGE_PADDING = ft.Padding(left=16, right=16, top=12, bottom=16)

# get_status() raw color -> (tint background, readable foreground). Tinted
# badges (light bg + dark text) are far more legible than white text on a
# fully saturated fill, especially on the Pi's small screen.
_STATUS_STYLES = {
    "#F44336": (DANGER_BG, DANGER),
    "#FF9800": (WARNING_BG, WARNING),
    "#4CAF50": (SUCCESS_BG, SUCCESS),
}


def status_style(raw_color: str) -> tuple[str, str]:
    """Map a get_status() color to a (badge background, foreground) pair."""
    return _STATUS_STYLES.get(raw_color, ("#EEEEEE", TEXT_SECONDARY))


def shadow() -> ft.BoxShadow:
    return ft.BoxShadow(blur_radius=10, offset=ft.Offset(0, 2), color="#14000000")


def card(content: ft.Control, padding=14, **kwargs) -> ft.Container:
    """Standard surface card: white, rounded, hairline border, soft shadow."""
    return ft.Container(
        bgcolor=SURFACE,
        border_radius=RADIUS,
        padding=padding,
        border=ft.Border.all(1, BORDER),
        shadow=shadow(),
        content=content,
        **kwargs,
    )


def page_header(
    title: str,
    subtitle: str | None = None,
    trailing: list[ft.Control] | None = None,
) -> ft.Row:
    """Uniform page header: bold title + optional secondary line, with
    optional right-aligned controls (clock, status badge, ...)."""
    text_col: list[ft.Control] = [
        ft.Text(title, size=20, weight=ft.FontWeight.BOLD, color=TEXT)
    ]
    if subtitle:
        text_col.append(ft.Text(subtitle, size=12, color=TEXT_SECONDARY))
    return ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Column(spacing=2, expand=True, controls=text_col),
            *(trailing or []),
        ],
    )


def section_title(text: str) -> ft.Text:
    return ft.Text(text, size=14, weight=ft.FontWeight.W_600, color=TEXT_SECONDARY)
