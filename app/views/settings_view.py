import os
import flet as ft

from config.profiles import AppState, CROP_PROFILES


def build_settings(state: AppState) -> ft.Container:
    """View/adjust crop profile, control mode, and check API-key status."""

    feedback = ft.Text("", size=12, color="#2E7D32")

    # -- control mode -------------------------------------------------------
    def on_mode_change(e):
        state.control_mode = e.control.value
        state.save()
        feedback.value = f"Control mode saved: {state.control_mode}"
        feedback.update()

    mode_group = ft.RadioGroup(
        value=state.control_mode,
        on_change=on_mode_change,
        content=ft.Row(
            controls=[
                ft.Radio(value="Manual", label="Manual"),
                ft.Radio(value="Advisor", label="Advisor (LLM)"),
            ]
        ),
    )

    # -- crop profile -------------------------------------------------------
    def on_profile_change(e):
        state.active_profile = e.control.value
        state.save()
        feedback.value = (
            f"Active profile saved: {state.active_profile}. "
            "Edit its setpoints on the Parameters page."
        )
        feedback.update()

    profile_dropdown = ft.Dropdown(
        label="Crop profile",
        value=state.active_profile,
        options=[ft.dropdown.Option(key=name, text=name) for name in CROP_PROFILES],
        on_select=on_profile_change,
        width=260,
    )

    # -- API key status -----------------------------------------------------
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    key_status = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.CHECK_CIRCLE if has_key else ft.Icons.ERROR,
                color="#2E7D32" if has_key else "#C62828",
                size=18,
            ),
            ft.Text(
                "ANTHROPIC_API_KEY found" if has_key
                else "ANTHROPIC_API_KEY missing — add it to .env",
                size=12,
                color="#2E7D32" if has_key else "#C62828",
            ),
        ]
    )

    def card(title: str, *content: ft.Control) -> ft.Control:
        return ft.Container(
            bgcolor="#FFFFFF",
            border_radius=12,
            padding=14,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Text(title, size=14, weight=ft.FontWeight.W_600, color="#424242"),
                    *content,
                ],
            ),
        )

    return ft.Container(
        expand=True,
        padding=ft.Padding(left=12, right=12, top=8, bottom=12),
        content=ft.Column(
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("Settings", size=18, weight=ft.FontWeight.BOLD, color="#212121"),
                card("Control mode", mode_group),
                card("Crop profile", profile_dropdown,
                     ft.Text("Setpoints for this profile are edited on the Parameters page.",
                             size=12, color="#9E9E9E")),
                card("LLM connection", key_status),
                feedback,
            ],
        ),
    )
