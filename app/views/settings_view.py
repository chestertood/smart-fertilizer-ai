import os
import flet as ft

from app import theme
from app.services import llm_agent
from app.services.database import Database
from config.profiles import AppState
from config.i18n import t, LANGUAGES

_NEW_PROFILE_KEY = "__new__"
_LANG_LABELS = {"en": "English", "th": "ไทย (Thai)"}

_MODEL_LABELS = {mid: label for mid, label, _ in llm_agent.AVAILABLE_MODELS}


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def build_settings(
    page: ft.Page, state: AppState, db: Database | None = None,
    on_language_changed: callable = None,
) -> ft.Container:
    """View/adjust crop profile, UI language, check API-key status, and see
    estimated LLM token usage/cost (from the local llm_usage ledger — the
    regular API key can't query Anthropic billing).

    `on_language_changed`, if given, is called after the language is saved so
    the caller can refresh the nav rail / currently visible view (see
    app.app.main)."""

    feedback = ft.Text("", size=12, color="#2E7D32")
    profile_dropdown = ft.Dropdown(label=t("settings.crop_profile", state.language), width=260)

    def refresh_dropdown():
        profile_dropdown.value = state.active_profile
        profile_dropdown.options = [
            ft.dropdown.Option(key=name, text=name) for name in state.profile_names
        ] + [
            ft.dropdown.Option(key=_NEW_PROFILE_KEY, text="+ Create new profile…"),
        ]

    # -- create-new-profile dialog -------------------------------------------
    name_field = ft.TextField(label="Profile name", autofocus=True, width=280)
    dialog_error = ft.Text("", size=12, color="#C62828")

    def close_dialog():
        dialog.open = False
        page.update()

    def confirm_create(e):
        name = (name_field.value or "").strip()
        if state.create_profile(name):
            state.save()
            profile_dropdown.value = state.active_profile
            refresh_dropdown()
            profile_dropdown.update()
            feedback.value = (
                f"Created profile '{name}' with generic default ranges. "
                "Edit its setpoints on the Parameters page."
            )
            feedback.update()
            close_dialog()
        else:
            dialog_error.value = (
                "Enter a name that isn't blank or already used."
            )
            dialog_error.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("New crop profile"),
        content=ft.Column(
            tight=True,
            controls=[
                name_field,
                dialog_error,
                ft.Text(
                    "Starts with generic EC/pH/Temperature/Humidity ranges — "
                    "adjust them on the Parameters page after creating.",
                    size=11, color="#757575",
                ),
            ],
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_dialog()),
            ft.FilledButton("Create", on_click=confirm_create),
        ],
    )

    # -- crop profile ---------------------------------------------------------
    def on_profile_change(e):
        if e.control.value == _NEW_PROFILE_KEY:
            # Revert the dropdown display until the dialog resolves.
            profile_dropdown.value = state.active_profile
            profile_dropdown.update()
            name_field.value = ""
            dialog_error.value = ""
            page.show_dialog(dialog)
            return
        state.active_profile = e.control.value
        state.save()
        feedback.value = (
            f"Active profile saved: {state.active_profile}. "
            "Edit its setpoints on the Parameters page."
        )
        feedback.update()

    profile_dropdown.on_select = on_profile_change
    refresh_dropdown()

    # -- delete-profile confirm dialog ---------------------------------------
    delete_error = ft.Text("", size=12, color="#C62828")

    def close_delete_dialog():
        delete_dialog.open = False
        page.update()

    def confirm_delete(e):
        name = state.active_profile
        if state.delete_profile(name):
            state.save()
            refresh_dropdown()
            profile_dropdown.update()
            feedback.value = f"Deleted profile '{name}'. Now on '{state.active_profile}'."
            feedback.update()
            close_delete_dialog()
        else:
            delete_error.value = "Can't delete the last remaining profile."
            delete_error.update()

    delete_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Delete profile?"),
        content=ft.Column(
            tight=True,
            controls=[
                ft.Text(
                    "This permanently deletes the profile and its saved "
                    "setpoints. This can't be undone.",
                    size=12,
                ),
                delete_error,
            ],
        ),
        actions=[
            ft.TextButton("Cancel", on_click=lambda e: close_delete_dialog()),
            ft.FilledButton(
                "Delete", on_click=confirm_delete,
                style=ft.ButtonStyle(bgcolor="#C62828", color="#FFFFFF"),
            ),
        ],
    )

    def open_delete_dialog(e):
        delete_error.value = ""
        delete_dialog.title = ft.Text(f"Delete '{state.active_profile}'?")
        page.show_dialog(delete_dialog)

    delete_btn = ft.IconButton(
        ft.Icons.DELETE_OUTLINE, icon_color="#C62828",
        tooltip="Delete this profile",
        on_click=open_delete_dialog,
    )

    # -- language -------------------------------------------------------------
    def on_language_change(e):
        state.language = e.control.value
        state.save()
        feedback.value = f"Language: {_LANG_LABELS.get(state.language, state.language)}"
        feedback.update()
        if on_language_changed is not None:
            on_language_changed()

    language_dropdown = ft.Dropdown(
        label=t("settings.language", state.language),
        value=state.language,
        options=[ft.dropdown.Option(key=code, text=_LANG_LABELS[code]) for code in LANGUAGES],
        on_select=on_language_change,
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

    # -- LLM usage & estimated cost ------------------------------------------

    def usage_rows() -> list[ft.Control]:
        if db is None:
            return [ft.Text("Usage log unavailable.", size=12, color=theme.TEXT_MUTED)]
        summary = db.llm_usage_summary()

        def period_row(label: str, rows: list[dict]) -> ft.Row:
            calls = sum(r["calls"] for r in rows)
            inp = sum(r["input"] for r in rows)
            out = sum(r["output"] for r in rows)
            cost = sum(
                llm_agent.estimate_cost_usd(r["model"], r["input"], r["output"])
                for r in rows
            )
            return ft.Row(
                controls=[
                    ft.Text(label, size=12, weight=ft.FontWeight.W_600,
                            color=theme.TEXT, width=90),
                    ft.Text(f"{calls} calls", size=12,
                            color=theme.TEXT_SECONDARY, width=70),
                    ft.Text(f"in {_fmt_tokens(inp)} / out {_fmt_tokens(out)} tok",
                            size=12, color=theme.TEXT_SECONDARY, expand=True),
                    ft.Text(f"~${cost:.2f}" if cost >= 0.005 else "<$0.01",
                            size=12, weight=ft.FontWeight.W_600,
                            color=theme.PRIMARY_DARK),
                ],
            )

        controls: list[ft.Control] = [
            period_row("Today", summary["today"]),
            period_row("This month", summary["month"]),
            period_row("All time", summary["all"]),
        ]
        if summary["all"]:
            model_bits = []
            for r in summary["all"]:
                cost = llm_agent.estimate_cost_usd(r["model"], r["input"], r["output"])
                label = _MODEL_LABELS.get(r["model"], r["model"])
                model_bits.append(f"{label}: {r['calls']} calls · ~${cost:.2f}")
            controls.append(ft.Text("  ·  ".join(model_bits), size=11,
                                    color=theme.TEXT_MUTED))
        controls.append(ft.Text(
            "Estimated from this app's local log only. Remaining credit and "
            "exact billing: console.anthropic.com → Billing.",
            size=11, color=theme.TEXT_MUTED,
        ))
        return controls

    def card(title: str, *content: ft.Control) -> ft.Control:
        return theme.card(
            ft.Column(
                spacing=10,
                controls=[theme.section_title(title), *content],
            ),
        )

    return ft.Container(
        expand=True,
        padding=theme.PAGE_PADDING,
        content=ft.Column(
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                theme.page_header(
                    t("settings.title", state.language),
                    t("settings.subtitle", state.language),
                ),
                card(t("settings.language", state.language), language_dropdown),
                card(t("settings.crop_profile", state.language),
                     ft.Row(
                         vertical_alignment=ft.CrossAxisAlignment.CENTER,
                         controls=[profile_dropdown, delete_btn],
                     ),
                     ft.Text(t("settings.profile_hint", state.language),
                             size=12, color=theme.TEXT_MUTED)),
                card(t("settings.llm_connection", state.language), key_status),
                card("LLM usage & cost (estimated)", *usage_rows()),
                feedback,
            ],
        ),
    )
