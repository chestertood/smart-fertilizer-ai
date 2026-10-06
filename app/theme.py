"""Central design tokens and small UI helpers shared by every view.

One place to change the app's look: palette, type scale, radii, shadow, page
padding and the standard card / page-header builders. Views import from here
instead of hardcoding hex values, so the whole app stays visually consistent.

Two palettes live here — light (daytime, the default) and dark (a greenhouse
at night, where a white kiosk screen is blinding). `apply(mode)` rebinds the
module-level color names to the chosen palette; views read them as
`theme.SURFACE` at build time, so a theme switch takes effect by rebuilding
the visible controls (see app.py's remount()).
"""

import flet as ft

# -- type scale --------------------------------------------------------------
# Five steps, nothing in between: meta/caption, body, card title, page title,
# hero number. Every ft.Text in the app picks one of these instead of an
# ad-hoc size, so type hierarchy reads the same on every page.
FONT_XS = 11    # captions, units, axis labels, range hints
FONT_SM = 13    # body text, field labels, section headers (weight carries it)
FONT_MD = 16    # card titles
FONT_LG = 20    # page titles
FONT_XXL = 32   # the hero sensor reading

# -- palette -----------------------------------------------------------------
# Brand green and the status hues are shared by both modes: they're the
# app's identity and its safety signals, and they stay legible on either
# background. Only surfaces, text and tints flip.
PRIMARY = "#2E7D32"        # brand green: app bar, selected controls, accents
PRIMARY_DARK = "#1B5E20"

SUCCESS = "#2E7D32"
WARNING = "#E65100"
DANGER = "#C62828"

LIGHT = {
    "BG": "#E4E9E4",            # page background behind cards
    "SURFACE": "#FFFFFF",       # card background
    "SURFACE_ALT": "#F4F6F4",   # inset areas: chat transcript, progress track
    "BORDER": "#E4E9E4",        # hairline card border
    "NAV_BG": "#F1F8E9",
    "PRIMARY_LIGHT": "#E8F5E9",  # tinted fills: badges, bot bubbles, chips
    "TEXT": "#212121",
    "TEXT_SECONDARY": "#5F6368",
    "TEXT_MUTED": "#80868B",
    "SUCCESS_BG": "#E8F5E9",
    "WARNING_BG": "#FFF3E0",
    "DANGER_BG": "#FDECEA",
    "NEUTRAL_BG": "#EEEEEE",    # "no signal" badge, disabled chips
    "ACCENT_TEXT": "#1B5E20",   # green text ON a surface (proposal cards)
    "WARN_SURFACE": "#FFF8E1",  # unsaved-changes bar
    "WARN_BORDER": "#F0E6C8",
    "SHADOW": "#14000000",
}

# Dark surfaces are near-black greens rather than pure grey, so the brand
# green still looks at home on them. Text steps down in three levels exactly
# like the light palette, so contrast relationships survive the flip.
DARK = {
    "BG": "#121712",
    "SURFACE": "#1C231C",
    "SURFACE_ALT": "#161C16",
    "BORDER": "#2C352C",
    "NAV_BG": "#182018",
    "PRIMARY_LIGHT": "#24402A",
    "TEXT": "#E8EDE8",
    "TEXT_SECONDARY": "#B3BDB3",
    "TEXT_MUTED": "#8A948A",
    "SUCCESS_BG": "#1E3A22",
    "WARNING_BG": "#3A2A12",
    "DANGER_BG": "#3A1E1E",
    "NEUTRAL_BG": "#2A322A",
    "ACCENT_TEXT": "#9CCC9F",   # dark-mode green has to lift off the surface
    "WARN_SURFACE": "#33290F",
    "WARN_BORDER": "#4A3C16",
    "SHADOW": "#40000000",
}

MODES = ("light", "dark")

# Bound by apply() below; declared here so linters and readers see them.
BG = SURFACE = SURFACE_ALT = BORDER = NAV_BG = PRIMARY_LIGHT = ""
TEXT = TEXT_SECONDARY = TEXT_MUTED = ACCENT_TEXT = ""
SUCCESS_BG = WARNING_BG = DANGER_BG = NEUTRAL_BG = SHADOW = ""
WARN_SURFACE = WARN_BORDER = ""

RADIUS = 14
PAGE_PADDING = ft.Padding(left=16, right=16, top=12, bottom=16)

mode = "light"

# get_status() raw color -> (tint background, readable foreground). Tinted
# badges (light bg + dark text) are far more legible than white text on a
# fully saturated fill, especially on the Pi's small screen. Rebuilt by
# apply() because the tints differ per mode.
_STATUS_STYLES: dict[str, tuple[str, str]] = {}


def apply(new_mode: str) -> None:
    """Rebind the palette tokens to `new_mode` ("light" / "dark").

    Only affects controls built *after* the call — Flet controls copy the
    colors they were given. Callers rebuild the visible tree afterwards.
    """
    global mode, _STATUS_STYLES
    palette = DARK if new_mode == "dark" else LIGHT
    mode = new_mode if new_mode in MODES else "light"
    globals().update(palette)
    _STATUS_STYLES = {
        "#F44336": (palette["DANGER_BG"], DANGER),
        "#FF9800": (palette["WARNING_BG"], WARNING),
        "#4CAF50": (palette["SUCCESS_BG"], SUCCESS),
    }


apply("light")


def flet_theme_mode() -> ft.ThemeMode:
    """page.theme_mode matching the active palette, so Flet's own widgets
    (dialogs, dropdowns, text fields) follow the app's cards."""
    return ft.ThemeMode.DARK if mode == "dark" else ft.ThemeMode.LIGHT


def status_style(raw_color: str) -> tuple[str, str]:
    """Map a get_status() color to a (badge background, foreground) pair."""
    return _STATUS_STYLES.get(raw_color, (NEUTRAL_BG, TEXT_SECONDARY))


def shadow() -> ft.BoxShadow:
    return ft.BoxShadow(blur_radius=10, offset=ft.Offset(0, 2), color=SHADOW)


def card(content: ft.Control, padding=14, **kwargs) -> ft.Container:
    """Standard surface card: rounded, hairline border, soft shadow."""
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
        ft.Text(title, size=FONT_LG, weight=ft.FontWeight.BOLD, color=TEXT)
    ]
    if subtitle:
        text_col.append(ft.Text(subtitle, size=FONT_XS, color=TEXT_SECONDARY))
    return ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Column(spacing=2, expand=True, controls=text_col),
            *(trailing or []),
        ],
    )


def section_title(text: str) -> ft.Text:
    return ft.Text(text, size=FONT_SM, weight=ft.FontWeight.W_600, color=TEXT_SECONDARY)
