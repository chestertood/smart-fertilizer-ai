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
from app.services.hardware import SensorHub
from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState

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
    page.title = "Smart Fertilizer"
    page.bgcolor = theme.BG
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    # Seed Material widgets (buttons, text fields, switches, dialogs) from the
    # brand green so built-in controls match the hand-styled cards.
    page.theme = ft.Theme(color_scheme_seed=theme.PRIMARY)

    if os.environ.get("FLET_VIEW") != "web":
        page.window.width = 1280
        page.window.height = 720
        page.window.min_width = 480
        page.window.min_height = 320
        # Replace the default Flet window/taskbar icon with the app logo
        # (served from assets_dir configured in main.py).
        page.window.icon = "icon.ico"

    hub = SensorHub()
    hub.connect_all()

    actuator_hub = ActuatorHub()
    actuator_hub.connect_all()

    db = Database()
    state = AppState()

    # Maps sensor name -> updater fn for the cards currently on screen.
    # Cleared and repopulated whenever the Dashboard view is (re)built.
    updaters: dict = {}
    # Holds the connection status updater for the currently visible dashboard.
    connection_updater: list = [None]
    # Holds the clock-text updater for the currently visible dashboard.
    clock_updater: list = [None]
    # Tracks which view is currently showing, so a language switch can
    # re-render it in place (see refresh_language below).
    current_view_name: list = ["Dashboard"]

    def build_dash():
        dashboard, update_conn, update_clock = build_dashboard(state, updaters)
        connection_updater[0] = update_conn
        clock_updater[0] = update_clock
        return dashboard

    # Chat assistant overlay + its toggle; the toggle is wired to a button in
    # the top app bar. Built before the app bar so the callback exists.
    chat_overlay, chat_toggle = build_chat_widget(page, state, actuator_hub, db)

    flag_setter: list = [None]

    def on_flag(e=None) -> None:
        # Flag shortcut in the app bar toggles between the two languages;
        # refresh_language() re-renders nav, flag, and the current view.
        state.language = "th" if state.language == "en" else "en"
        state.save()
        refresh_language()

    app_bar, set_flag = build_app_bar(state, on_chat=chat_toggle, on_flag=on_flag)
    flag_setter[0] = set_flag

    views = {
        "Dashboard": build_dash,
        "Parameters": lambda: build_parameters(page, actuator_hub, db, state),
        "History": lambda: build_history(db, state),
        "Settings": lambda: build_settings(page, state, db, on_language_changed=refresh_language),
    }

    body = ft.Column(expand=True, spacing=0)
    body.controls = [build_dash()]

    def navigate(index: int) -> None:
        updaters.clear()
        connection_updater[0] = None
        clock_updater[0] = None
        name = NAV_NAMES[index]
        current_view_name[0] = name
        body.controls = [views[name]()]
        page.update()

    def refresh_language() -> None:
        """Re-render the nav rail labels, the app-bar flag, and the currently
        visible view after a language switch (from the flag shortcut or the
        Settings dropdown), so it takes effect without an app restart."""
        set_nav_language(rail, state.language)
        rail.update()
        if flag_setter[0] is not None:
            flag_setter[0](state.language)
        body.controls = [views[current_view_name[0]]()]
        page.update()

    rail = build_nav_rail(navigate, selected_index=0, lang=state.language)

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                app_bar,
                ft.Row(
                    expand=True,
                    spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    controls=[
                        rail,
                        ft.VerticalDivider(width=1),
                        ft.Container(expand=True, content=body),
                    ],
                ),
            ],
        )
    )

    # Chat panel overlay (opened from the app-bar button, top-right).
    page.overlay.append(chat_overlay)
    page.update()

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
                    if update and value == value:  # skip NaN
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
            fn = connection_updater[0]
            if fn is not None:
                fn(is_online or consecutive_failures < 2)
                page.update()
            await asyncio.sleep(CONNECTIVITY_INTERVAL_S)

    async def poll_clock() -> None:
        last_date = datetime.date.today()
        while True:
            try:
                fn = clock_updater[0]
                if fn is not None:
                    fn()
                    page.update()
                # Growth-stage progress is computed at view build time, so a
                # kiosk left running overnight would show yesterday's stage
                # forever. Re-render the current view when the date rolls.
                today = datetime.date.today()
                if today != last_date:
                    last_date = today
                    body.controls = [views[current_view_name[0]]()]
                    page.update()
            except Exception:
                logger.exception("poll_clock iteration failed")
            await asyncio.sleep(CLOCK_INTERVAL_S)

    page.run_task(poll_sensors)
    page.run_task(poll_connectivity)
    page.run_task(poll_clock)
    
