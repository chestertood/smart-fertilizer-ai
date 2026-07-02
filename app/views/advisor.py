import asyncio
import flet as ft

from app.services.actuators import ActuatorHub
from app.services.database import Database
from app.services import llm_agent
from config.profiles import AppState


def build_advisor(
    page: ft.Page,
    actuator_hub: ActuatorHub,
    db: Database,
    state: AppState,
) -> ft.Container:
    """Ask Claude for dosing recommendations, then approve each action."""

    summary = ft.Text("", size=13, color="#424242")
    actions_column = ft.Column(spacing=8)
    spinner = ft.ProgressRing(width=20, height=20, visible=False)
    get_button = ft.FilledButton("Get recommendation", icon=ft.Icons.SMART_TOY)

    def make_action_card(action: dict) -> ft.Control:
        pump = action.get("pump", "?")
        amount = float(action.get("amount_ml", 0) or 0)
        reason = action.get("reason", "")

        status = ft.Text("", size=12, color="#2E7D32")
        approve_btn = ft.FilledButton("Approve", icon=ft.Icons.CHECK)

        def approve(e):
            dispensed = actuator_hub.dose(pump, amount)
            db.log_dose(pump, dispensed, source="llm")
            status.value = f"Approved — dispensed {dispensed:.1f} ml"
            approve_btn.disabled = True
            approve_btn.text = "Done"
            e.page.update()

        approve_btn.on_click = approve

        return ft.Container(
            bgcolor="#FFFFFF",
            border_radius=12,
            padding=12,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(ft.Icons.OPACITY, color="#1976D2"),
                            ft.Text(f"{pump}", size=15, weight=ft.FontWeight.W_600, expand=True),
                            ft.Text(f"{amount:.1f} ml", size=15, weight=ft.FontWeight.BOLD, color="#1976D2"),
                            approve_btn,
                        ],
                    ),
                    ft.Text(reason, size=12, color="#616161"),
                    status,
                ],
            ),
        )

    async def get_recommendation(e):
        spinner.visible = True
        get_button.disabled = True
        summary.value = ""
        actions_column.controls = []
        page.update()

        readings = dict(state.last_readings)
        targets = state.targets
        profile = state.active_profile

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, llm_agent.recommend, readings, targets, profile
            )
        except llm_agent.LLMError as exc:
            summary.value = f"⚠ {exc}"
            summary.color = "#C62828"
        except Exception as exc:  # noqa: BLE001 - surface anything to the user
            summary.value = f"⚠ Unexpected error: {exc}"
            summary.color = "#C62828"
        else:
            summary.value = result.get("summary", "")
            summary.color = "#424242"
            actions = result.get("actions", [])
            if actions:
                actions_column.controls = [make_action_card(a) for a in actions]
            else:
                actions_column.controls = [
                    ft.Text("All readings within target — no dosing needed.",
                            size=12, color="#2E7D32")
                ]
        finally:
            spinner.visible = False
            get_button.disabled = False
            page.update()

    get_button.on_click = get_recommendation

    return ft.Container(
        expand=True,
        padding=ft.Padding(left=12, right=12, top=8, bottom=12),
        content=ft.Column(
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=0,
                            expand=True,
                            controls=[
                                ft.Text("LLM Advisor", size=18, weight=ft.FontWeight.BOLD, color="#212121"),
                                ft.Text("Claude recommends dosing; you approve.", size=11, color="#757575"),
                            ],
                        ),
                        spinner,
                    ],
                ),
                get_button,
                summary,
                actions_column,
            ],
        ),
    )
