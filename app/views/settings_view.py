import os
import flet as ft

from app import theme
from app.services.database import Database
from config.profiles import AppState, DEFAULT_PROFILE
from config.i18n import t, LANGUAGES

_NEW_PROFILE_KEY = "__new__"
_LANG_LABELS = {"en": "English", "th": "ไทย (Thai)"}


def build_settings(
    page: ft.Page, state: AppState, db: Database | None = None,
    on_language_changed: callable = None, on_mode_changed: callable = None,
    on_theme_changed: callable = None,
) -> ft.Container:
    """View/adjust crop profile, UI language, LLM dosing mode, check
    API-key status, and see estimated LLM token usage/cost (from the local
    llm_usage ledger — the regular API key can't query Anthropic billing).

    `on_language_changed`, if given, is called after the language is saved so
    the caller can refresh the nav rail / currently visible view (see
    app.app.main). `on_mode_changed` is called after llm_mode is saved so
    the caller can sync the app bar's lock/bolt badge (same state, second
    place it's shown — see app.app.main's mode_setter). `on_theme_changed`
    receives "light"/"dark" and is expected to repaint the window (colors
    are baked into controls at build time — see app.app.main's
    set_theme_mode)."""

    feedback = ft.Text("", size=theme.FONT_SM, color=theme.SUCCESS)
    profile_dropdown = ft.Dropdown(label=t("settings.crop_profile", state.language), width=260)

    def refresh_dropdown():
        profile_dropdown.value = state.active_profile
        profile_dropdown.options = [
            ft.dropdown.Option(key=name, text=name) for name in state.profile_names
        ] + [
            ft.dropdown.Option(key=_NEW_PROFILE_KEY, text="+ Create new profile…"),
        ]

    # -- create-new-profile dialog -------------------------------------------
    name_field = ft.TextField(label=t("settings.profile_name", state.language), autofocus=True, width=280)
    dialog_error = ft.Text("", size=theme.FONT_SM, color=theme.DANGER)

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
        title=ft.Text(t("settings.new_profile", state.language)),
        content=ft.Column(
            tight=True,
            controls=[
                name_field,
                dialog_error,
                ft.Text(
                    t("settings.new_profile_hint", state.language),
                    size=theme.FONT_XS, color=theme.TEXT_SECONDARY,
                ),
            ],
        ),
        actions=[
            ft.TextButton(t("common.cancel", state.language), on_click=lambda e: close_dialog()),
            ft.FilledButton(t("common.create", state.language), on_click=confirm_create),
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
        delete_btn.disabled = state.active_profile == DEFAULT_PROFILE
        delete_btn.update()
        feedback.value = (
            f"Active profile saved: {state.active_profile}. "
            "Edit its setpoints on the Parameters page."
        )
        feedback.update()

    profile_dropdown.on_select = on_profile_change
    refresh_dropdown()

    # -- delete-profile confirm dialog ---------------------------------------
    delete_error = ft.Text("", size=theme.FONT_SM, color=theme.DANGER)

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
            delete_error.value = (
                f"The '{DEFAULT_PROFILE}' profile can't be deleted — it's the "
                "fallback the app always keeps."
            )
            delete_error.update()

    delete_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("settings.delete_profile_q", state.language)),
        content=ft.Column(
            tight=True,
            controls=[
                ft.Text(
                    t("settings.delete_profile_body", state.language),
                    size=theme.FONT_SM,
                ),
                delete_error,
            ],
        ),
        actions=[
            ft.TextButton(t("common.cancel", state.language), on_click=lambda e: close_delete_dialog()),
            ft.FilledButton(
                t("common.delete", state.language), on_click=confirm_delete,
                style=ft.ButtonStyle(bgcolor=theme.DANGER, color="#FFFFFF"),
            ),
        ],
    )

    def open_delete_dialog(e):
        delete_error.value = ""
        delete_dialog.title = ft.Text(f"Delete '{state.active_profile}'?")
        page.show_dialog(delete_dialog)

    delete_btn = ft.IconButton(
        ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER,
        tooltip=t("settings.delete_profile_tip", state.language),
        on_click=open_delete_dialog,
        # Greyed out on the permanent fallback profile rather than opening a
        # dialog that could only ever refuse. Kept in sync by on_profile_change.
        disabled=state.active_profile == DEFAULT_PROFILE,
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

    # -- appearance -----------------------------------------------------------
    # Dark mode exists for the greenhouse at night: a full-screen white kiosk
    # is blinding in the dark and ruins night vision around the tanks.
    def on_theme_change(e):
        new_mode = "dark" if e.control.value else "light"
        if on_theme_changed is not None:
            # Repaints (and persists) the whole window; this view is rebuilt
            # as part of that, so there's nothing to update here afterwards.
            on_theme_changed(new_mode)
        else:  # standalone preview without a host to repaint
            state.theme_mode = new_mode
            state.save()

    theme_switch = ft.Switch(value=state.theme_mode == "dark", on_change=on_theme_change)
    theme_label_text = ft.Text(
        t("settings.theme_dark" if state.theme_mode == "dark" else "settings.theme_light",
          state.language),
        size=theme.FONT_SM, weight=ft.FontWeight.W_600, color=theme.TEXT,
    )

    # -- LLM dosing mode --------------------------------------------------------
    # Same state.llm_mode the app bar's lock/bolt badge and the Telegram
    # mode button toggle — this is a third view onto one shared switch.
    def _mode_label(mode: str) -> str:
        return t("settings.mode_auto" if mode == "auto" else "settings.mode_approval",
                  state.language)

    mode_switch = ft.Switch(value=state.llm_mode == "auto")
    mode_label_text = ft.Text(_mode_label(state.llm_mode), size=theme.FONT_SM,
                               weight=ft.FontWeight.W_600, color=theme.TEXT)

    def _apply_mode_toggle():
        new_mode = state.toggle_llm_mode()
        state.save()
        mode_switch.value = new_mode == "auto"
        mode_label_text.value = _mode_label(new_mode)
        mode_switch.update()
        mode_label_text.update()
        if on_mode_changed is not None:
            on_mode_changed()

    def _cancel_mode_dialog(e):
        mode_confirm_dialog.open = False
        # Switch already flipped visually on tap — snap it back since the
        # change was cancelled.
        mode_switch.value = state.llm_mode == "auto"
        page.update()

    def _confirm_mode_dialog(e):
        mode_confirm_dialog.open = False
        page.update()
        _apply_mode_toggle()

    mode_confirm_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("mode.enable_title", state.language)),
        content=ft.Text(t("mode.enable_body", state.language)),
        actions=[
            ft.TextButton(t("common.cancel", state.language), on_click=_cancel_mode_dialog),
            ft.FilledButton(
                t("mode.enable_confirm", state.language), on_click=_confirm_mode_dialog,
                style=ft.ButtonStyle(bgcolor="#F57F17", color="#FFFFFF"),
            ),
        ],
    )

    def on_mode_switch(e):
        if state.llm_mode == "approval":
            # Turning ON auto-dose — confirm first, this is the direction
            # that can fire a pump with nobody watching.
            page.show_dialog(mode_confirm_dialog)
        else:
            _apply_mode_toggle()

    mode_switch.on_change = on_mode_switch

    # -- API key status -----------------------------------------------------
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    key_status = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.CHECK_CIRCLE if has_key else ft.Icons.ERROR,
                color=theme.SUCCESS if has_key else "#C62828",
                size=18,
            ),
            ft.Text(
                "ANTHROPIC_API_KEY found" if has_key
                else "ANTHROPIC_API_KEY missing — add it to .env",
                size=theme.FONT_SM,
                color=theme.SUCCESS if has_key else "#C62828",
            ),
        ]
    )

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
                card(t("settings.appearance", state.language),
                     ft.Row(
                         vertical_alignment=ft.CrossAxisAlignment.CENTER,
                         controls=[theme_switch, theme_label_text],
                     ),
                     ft.Text(t("settings.theme_hint", state.language),
                             size=theme.FONT_XS, color=theme.TEXT_MUTED)),
                card(t("settings.llm_mode", state.language),
                     ft.Row(
                         vertical_alignment=ft.CrossAxisAlignment.CENTER,
                         controls=[mode_switch, mode_label_text],
                     ),
                     ft.Text(t("settings.mode_hint", state.language),
                             size=theme.FONT_SM, color=theme.TEXT_MUTED)),
                card(t("settings.crop_profile", state.language),
                     ft.Row(
                         vertical_alignment=ft.CrossAxisAlignment.CENTER,
                         controls=[profile_dropdown, delete_btn],
                     ),
                     ft.Text(t("settings.profile_hint", state.language),
                             size=theme.FONT_SM, color=theme.TEXT_MUTED)),
                card(t("settings.llm_connection", state.language), key_status),
                feedback,
            ],
        ),
    )
