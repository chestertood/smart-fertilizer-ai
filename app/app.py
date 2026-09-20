import asyncio
import datetime
import logging
import os
import socket
import flet as ft

logger = logging.getLogger(__name__)

from app import theme
from app.components.app_bar import build_app_bar
from app.components.nav_rail import build_nav_rail, set_nav_language, NAV_NAMES
from app.components.chat_widget import build_chat_widget
from app.views.dashboard import build_dashboard
from app.views.history import build_history
from app.views.parameters import build_parameters
from app.views.settings_view import build_settings
from app.services import telegram_bridge
from app.services.hardware import SensorHub
from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.i18n import t
from config.profiles import AppState

# Kiosk is the normal way this app runs, on the Pi's touch screen and on
# Windows: borderless full-screen with no title bar, so the window can't be
# moved, resized or closed by a stray touch. The app carries its own Exit
# button at the bottom of the nav rail instead.
# Set KIOSK=0 for an ordinary resizable window (handy while developing).
KIOSK = os.environ.get("KIOSK", "1") != "0"

POLL_INTERVAL_S = 2.0
CONNECTIVITY_INTERVAL_S = 5.0
CLOCK_INTERVAL_S = 1.0
# Persist a reading every Nth poll so the DB isn't hammered every 2s.
LOG_EVERY_N_POLLS = 15


def check_internet() -> bool:
    # Port 443 (HTTPS), not 53 (DNS) — cafe/hotel/office WiFi commonly blocks
    # direct DNS-port TCP as an anti-tunneling measure while browsing works
    # fine, which made this check falsely report Offline. 443 is effectively
    # always open (the network is unusable for the web otherwise).
    try:
        with socket.create_connection(("8.8.8.8", 443), timeout=3):
            return True
    except OSError:
        return False


def main(page: ft.Page) -> None:
    page.title = "Smart Fertilizer Dosing"
    page.update()
    page.bgcolor = theme.BG
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    # Seed Material widgets (buttons, text fields, switches, dialogs) from the
    # brand green so built-in controls match the hand-styled cards.
    page.theme = ft.Theme(color_scheme_seed=theme.PRIMARY)
    # Pixel font for the app-bar title, matching the pixel-art logo. Bundled
    # locally (OFL) so it still works offline on the Pi.
    page.fonts = {"PixelFont": "fonts/PressStart2P-Regular.ttf"}

    if os.environ.get("FLET_VIEW") != "web":
        page.window.width = 1280
        page.window.height = 720
        page.window.min_width = 480
        page.window.min_height = 320
        # Replace the default Flet window/taskbar icon with the app logo
        # (served from assets_dir configured in main.py).
        page.window.icon = "icon.ico"
        if KIOSK:
            page.window.full_screen = True
            page.window.frameless = True

    state = AppState()

    # Palette first: Flet controls copy their colors at construction time, so
    # the saved light/dark choice has to be applied before the splash, let
    # alone the views.
    theme.apply(state.theme_mode)
    page.bgcolor = theme.BG
    page.theme_mode = theme.flet_theme_mode()

    # connect_all() on the sensor/actuator hubs is a blocking Modbus round
    # trip per device (with retries/timeouts on anything unplugged or slow
    # to wake) — on a kiosk with no title bar that showed as a blank white
    # screen, indistinguishable from a hang. A splash makes the wait legible.
    splash = ft.Column(
        expand=True,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Image(src="logo.png", width=96, height=96, fit=ft.BoxFit.CONTAIN),
            ft.Container(height=24),
            ft.ProgressRing(width=28, height=28, stroke_width=3, color=theme.PRIMARY),
            ft.Container(height=12),
            ft.Text(
                t("startup.connecting", state.language),
                size=theme.FONT_SM, color=theme.TEXT_SECONDARY,
            ),
        ],
    )
    page.add(ft.Container(expand=True, bgcolor=theme.BG, content=splash))
    page.update()

    hub = SensorHub()
    hub.connect_all()

    actuator_hub = ActuatorHub()
    actuator_hub.connect_all()

    db = Database()

    page.controls.clear()

    # Maps sensor name -> updater fn for the cards currently on screen.
    # Cleared and repopulated whenever the Dashboard view is (re)built.
    updaters: dict = {}
    # Holds the connection status updater for the currently visible dashboard.
    connection_updater = None
    # Holds the clock-text updater for the currently visible dashboard.
    clock_updater = None
    # Tracks which view is currently showing, so a language switch can
    # re-render it in place (see refresh_language below).
    current_view_name = "Dashboard"

    def build_dash():
        nonlocal connection_updater, clock_updater
        dashboard, update_conn, update_clock = build_dashboard(state, updaters)
        connection_updater = update_conn
        clock_updater = update_clock
        return dashboard

    # Every control below carries palette colors baked in at construction
    # time, so a theme switch rebuilds them as a group — see build_shell().
    # They're declared here because the handlers defined next close over them.
    chat_overlay = chat_toggle = None
    app_bar = flag_setter = mode_setter = None
    rail = exit_button = None

    def on_flag(e=None) -> None:
        # Flag shortcut in the app bar toggles between the two languages;
        # refresh_language() re-renders nav, flag, and the current view.
        state.language = "th" if state.language == "en" else "en"
        state.save()
        refresh_language()

    # Mode badge in the app bar toggles llm_mode. Turning Auto-dose ON gets
    # a confirm dialog first — it's the direction that can fire a pump with
    # nobody watching; turning it back OFF (the safe direction) doesn't.
    def _apply_mode_change() -> None:
        state.toggle_llm_mode()
        state.save()
        # Not just the app-bar badge: rebuild whatever view is on screen too
        # (e.g. Settings' own mode switch) — otherwise toggling from the app
        # bar while Settings is open leaves its switch showing the old mode
        # until the operator navigates away and back.
        refresh_current_view()

    def on_mode(e=None) -> None:
        if state.llm_mode != "approval":
            _apply_mode_change()
            return

        # Built fresh on open so it speaks the currently selected language.
        lang = state.language

        def close(_=None) -> None:
            dlg.open = False
            page.update()

        def confirm(_=None) -> None:
            close()
            _apply_mode_change()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("mode.enable_title", lang)),
            content=ft.Text(t("mode.enable_body", lang)),
            actions=[
                ft.TextButton(t("common.cancel", lang), on_click=close),
                ft.FilledButton(
                    t("mode.enable_confirm", lang), on_click=confirm,
                    style=ft.ButtonStyle(bgcolor="#F57F17", color="#FFFFFF"),
                ),
            ],
        )
        page.show_dialog(dlg)

    def sync_mode_badge() -> None:
        # Settings toggles state.llm_mode itself (own confirm dialog, same
        # as the app bar's) — this just re-paints the badge to match after
        # the fact, so the two views of one switch don't go stale.
        mode_setter(state.llm_mode)

    views = {
        "Dashboard": build_dash,
        "Parameters": lambda: build_parameters(page, actuator_hub, db, state),
        "History": lambda: build_history(db, state),
        "Settings": lambda: build_settings(
            page, state, db, on_language_changed=refresh_language,
            on_mode_changed=sync_mode_badge,
            on_theme_changed=lambda m: set_theme_mode(m),
        ),
    }

    # Filled by build_shell(); the nav swaps its single child on navigate().
    body = ft.Column(expand=True, spacing=0)

    def navigate(index: int) -> None:
        nonlocal connection_updater, clock_updater, current_view_name
        updaters.clear()
        connection_updater = None
        clock_updater = None
        current_view_name = NAV_NAMES[index]
        body.controls = [views[current_view_name]()]
        page.update()

    def refresh_current_view() -> None:
        """Rebuild whichever view is currently on screen from live state —
        used after a language switch and after a Telegram approval applies
        a change, so the operator never has to navigate away and back to
        see it. Also re-syncs the app bar's mode icon: it's outside `body`
        so rebuilding the view alone wouldn't catch a mode flip made from
        Telegram (the "Mode: …" button toggles state.llm_mode directly,
        with no other way back into this process to repaint the badge)."""
        body.controls = [views[current_view_name]()]
        mode_setter(state.llm_mode)
        page.update()

    def refresh_language() -> None:
        """Re-render the nav rail labels, the app-bar flag, and the currently
        visible view after a language switch (from the flag shortcut or the
        Settings dropdown), so it takes effect without an app restart."""
        set_nav_language(rail, state.language)
        rail.update()
        exit_button.tooltip = t("nav.exit", state.language)
        if KIOSK:
            exit_button.update()
        flag_setter(state.language)
        refresh_current_view()

    def open_exit_dialog(e=None) -> None:
        # Built fresh on each open so it picks up the current language, and
        # confirmed because a stray touch on a kiosk would otherwise stop
        # monitoring until someone restarts the app by hand.
        lang = state.language

        def close(_=None) -> None:
            dlg.open = False
            page.update()

        # page.window.close() is a coroutine in Flet 0.85 — a sync handler
        # would build it and drop it un-awaited, leaving the button dead.
        async def do_exit(_=None) -> None:
            await page.window.close()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(t("exit.title", lang)),
            content=ft.Text(t("exit.body", lang), size=theme.FONT_SM),
            actions=[
                ft.TextButton(t("exit.cancel", lang), on_click=close),
                ft.FilledButton(
                    t("exit.confirm", lang),
                    on_click=do_exit,
                    style=ft.ButtonStyle(bgcolor=theme.DANGER, color="#FFFFFF"),
                ),
            ],
        )
        page.show_dialog(dlg)

    def build_shell() -> ft.Control:
        """Build every palette-carrying control and return the window's root.

        Called once at startup and again on a theme switch: Flet controls
        copy their colors when they're constructed, so repainting the app
        means rebuilding it rather than poking at the existing tree.
        """
        nonlocal chat_overlay, chat_toggle, app_bar, flag_setter, mode_setter
        nonlocal rail, exit_button

        # Chat assistant overlay + its toggle; the toggle is wired to a
        # button in the top app bar, so it's built before the app bar.
        # ponytail: a rebuild drops the current chat transcript (it lives in
        # the widget's own closure). Fine for a theme switch; if the
        # transcript has to survive, move it onto AppState.
        chat_overlay, chat_toggle = build_chat_widget(page, state, actuator_hub, db)

        app_bar, flag_setter, mode_setter = build_app_bar(
            state, on_chat=chat_toggle, on_flag=on_flag, on_mode=on_mode,
        )

        rail = build_nav_rail(
            navigate,
            selected_index=NAV_NAMES.index(current_view_name),
            lang=state.language,
        )

        # Kiosk has no title bar, so the app carries its own Exit button,
        # pinned below the rail at the bottom-left. Windowed builds keep
        # their native close button and don't need it.
        exit_button = ft.IconButton(
            icon=ft.Icons.POWER_SETTINGS_NEW,
            icon_color=theme.DANGER,
            tooltip=t("nav.exit", state.language),
            on_click=open_exit_dialog,
            style=ft.ButtonStyle(side=ft.BorderSide(0, "transparent")),
        )
        # 10px gap between the app bar and the rail's own top padding —
        # NavigationRail has no padding of its own, so a Container wraps it.
        rail_top_pad = ft.Container(
            expand=True,
            bgcolor=theme.NAV_BG,
            padding=ft.Padding(left=0, right=0, top=12, bottom=0),
            content=rail,
        )
        if KIOSK:
            rail.expand = True
            rail_width = 96  # NavigationRail's rendered width in ALL-label mode
            nav_side: ft.Control = ft.Column(
                width=rail_width,
                spacing=0,
                controls=[
                    rail_top_pad,
                    ft.Container(
                        width=rail_width,
                        bgcolor=theme.NAV_BG,
                        padding=ft.Padding(left=0, right=0, top=4, bottom=15),
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[exit_button],
                        ),
                    ),
                ],
            )
        else:
            nav_side = rail_top_pad

        # The visible view is rebuilt too, so it picks up the new palette.
        body.controls = [views[current_view_name]()]

        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                app_bar,
                ft.Row(
                    expand=True,
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        nav_side,
                        ft.VerticalDivider(width=1),
                        ft.Container(expand=True, content=body),
                    ],
                ),
            ],
        )

    def mount() -> None:
        """Put a freshly built shell on the page, replacing what's there."""
        page.controls.clear()
        page.overlay.clear()
        page.add(build_shell())
        # Chat panel overlay (opened from the app-bar button, top-right).
        page.overlay.append(chat_overlay)
        page.update()

    def set_theme_mode(new_mode: str) -> None:
        """Switch palette and repaint the whole window (Settings calls this).
        Persisted, so the kiosk comes back up in the mode it was left in."""
        if new_mode == state.theme_mode:
            return
        state.theme_mode = new_mode
        state.save()
        theme.apply(new_mode)
        page.bgcolor = theme.BG
        page.theme_mode = theme.flet_theme_mode()
        mount()

    mount()

    async def poll_sensors() -> None:
        poll_count = 0
        while True:
            # One transient failure (sqlite lock, a card mid-teardown during
            # navigation, …) must not kill this task silently — that froze
            # the whole dashboard until restart.
            try:
                readings = hub.read_all()
                # Apply the operator's calibration offsets here, at the single
                # entry point — so the UI, the chat assistant, and the DB log
                # all see corrected values. (The offsets were previously
                # stored by the Calibration page but never used anywhere.)
                for name, off in state.offsets.items():
                    val = readings.get(name)
                    if isinstance(val, (int, float)) and val == val and off:
                        readings[name] = round(val + off, 2)
                # Keep shared state fresh so any view / the LLM can read it.
                state.last_readings = readings
                for name, value in readings.items():
                    update = updaters.get(name)
                    if update:
                        # NaN is passed through, not skipped: the card needs
                        # to know a read failed so it can grey out and show
                        # "No signal" instead of holding a stale number that
                        # still looks live.
                        update(value)
                poll_count += 1
                if poll_count % LOG_EVERY_N_POLLS == 0:
                    info = state.current_stage_info()
                    stage_name = info["stage"]["name"] if info else None
                    db.log_reading(readings, stage_name)
                page.update()
            except Exception:
                logger.exception("poll_sensors iteration failed")
            await asyncio.sleep(POLL_INTERVAL_S)

    async def poll_connectivity() -> None:
        # Require 2 consecutive failures before reporting Offline — a single
        # dropped probe (WiFi jitter, transient DNS block) shouldn't flip the
        # badge. Recovery reports Online immediately on the first success.
        consecutive_failures = 0
        while True:
            is_online = await asyncio.get_event_loop().run_in_executor(
                None, check_internet
            )
            if is_online:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
            if connection_updater is not None:
                connection_updater(is_online or consecutive_failures < 2)
                page.update()
            await asyncio.sleep(CONNECTIVITY_INTERVAL_S)

    async def poll_clock() -> None:
        last_date = datetime.date.today()
        while True:
            try:
                if clock_updater is not None:
                    clock_updater()
                    page.update()
                # Growth-stage progress is computed at view build time, so a
                # kiosk left running overnight would show yesterday's stage
                # forever. Re-render the current view when the date rolls.
                today = datetime.date.today()
                if today != last_date:
                    last_date = today
                    body.controls = [views[current_view_name]()]
                    page.update()
            except Exception:
                logger.exception("poll_clock iteration failed")
            await asyncio.sleep(CLOCK_INTERVAL_S)

    page.run_task(poll_sensors)
    page.run_task(poll_connectivity)
    page.run_task(poll_clock)
    page.run_task(
        telegram_bridge.poll_telegram, state, actuator_hub, db,
        page, refresh_current_view,
    )
    
