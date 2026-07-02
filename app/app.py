import asyncio
import os
import socket
import flet as ft

from app.components.app_bar import build_app_bar
from app.components.nav_rail import build_nav_rail, NAV_NAMES
from app.views.dashboard import build_dashboard
from app.views.history import build_history
from app.views.advisor import build_advisor
from app.views.parameters import build_parameters
from app.views.settings_view import build_settings
from app.services.hardware import SensorHub
from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState

POLL_INTERVAL_S = 2.0
CONNECTIVITY_INTERVAL_S = 5.0
# Persist a reading every Nth poll so the DB isn't hammered every 2s.
LOG_EVERY_N_POLLS = 15


def check_internet() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False


def main(page: ft.Page) -> None:
    page.title = "Smart Fertilizer"
    page.bgcolor = "#F5F5F5"
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT

    if os.environ.get("FLET_VIEW") != "web":
        page.window.width = 1280
        page.window.height = 720
        page.window.min_width = 480
        page.window.min_height = 320

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

    def build_dash():
        dashboard, update_conn = build_dashboard(updaters)
        connection_updater[0] = update_conn
        return dashboard

    views = {
        "Dashboard": build_dash,
        "Parameters": lambda: build_parameters(page, actuator_hub, db, state),
        "LLM Advisor": lambda: build_advisor(page, actuator_hub, db, state),
        "History": lambda: build_history(db),
        "Settings": lambda: build_settings(state),
    }

    body = ft.Column(expand=True, spacing=0)
    body.controls = [build_dash()]

    def navigate(index: int) -> None:
        updaters.clear()
        connection_updater[0] = None
        name = NAV_NAMES[index]
        body.controls = [views[name]()]
        page.update()

    rail = build_nav_rail(navigate, selected_index=0)

    page.add(
        ft.Column(
            expand=True,
            spacing=0,
            controls=[
                build_app_bar(state),
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

    async def poll_sensors() -> None:
        poll_count = 0
        while True:
            readings = hub.read_all()
            # Keep shared state fresh so any view / the LLM advisor can read it.
            state.last_readings = readings
            for name, value in readings.items():
                update = updaters.get(name)
                if update and value == value:  # skip NaN
                    update(value)
            poll_count += 1
            if poll_count % LOG_EVERY_N_POLLS == 0:
                db.log_reading(readings)
            page.update()
            await asyncio.sleep(POLL_INTERVAL_S)

    async def poll_connectivity() -> None:
        while True:
            is_online = await asyncio.get_event_loop().run_in_executor(
                None, check_internet
            )
            fn = connection_updater[0]
            if fn is not None:
                fn(is_online)
                page.update()
            await asyncio.sleep(CONNECTIVITY_INTERVAL_S)

    page.run_task(poll_sensors)
    page.run_task(poll_connectivity)
    
