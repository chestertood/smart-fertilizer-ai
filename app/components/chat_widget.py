import asyncio
import flet as ft

from app import theme
from app.services import llm_agent
from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState
from config.sensors import get_status

# Chat colors come from the shared theme so the assistant matches the rest
# of the app instead of using its own vivid green.
_PRIMARY = theme.PRIMARY
_PRIMARY_DARK = theme.PRIMARY_DARK
_PANEL_BG = theme.SURFACE
_USER_BUBBLE = theme.PRIMARY
_BOT_BUBBLE = theme.PRIMARY_LIGHT   # light green so bot text pops
_UNITS = {"EC": "mS/cm", "PH": "pH", "Temperature": "°C", "Humidity": "%"}

# File types the attach button accepts — must stay in sync with what
# llm_agent.build_user_content() can encode (images/pdf/plain text).
_ATTACH_EXTS = ["png", "jpg", "jpeg", "gif", "webp",
                "pdf", "txt", "md", "csv", "json", "log"]
_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
# Per-file guard; keeps a single request comfortably under the API's 32MB cap.
_MAX_ATTACH_BYTES = 5 * 1024 * 1024


def build_chat_widget(
    page: ft.Page,
    state: AppState,
    actuator_hub: ActuatorHub,
    db: Database,
) -> ft.Container:
    """Floating chat assistant pinned to the bottom-right corner.

    Quick-action chips answer common requests (status check / dosing
    recommendation); dosing recommendations render with inline Approve
    buttons that drive ActuatorHub directly — no separate Advisor page.
    """

    # Conversation history in Anthropic format: [{"role", "content"}, ...].
    # User content is a plain string, or content blocks when files are attached
    # (see llm_agent.build_user_content).
    history: list[dict] = []
    # Files staged for the next message: [{"name": str, "data": bytes}, ...]
    pending_attachments: list[dict] = []

    messages_col = ft.ListView(spacing=10, auto_scroll=True, expand=True)
    input_field = ft.TextField(
        hint_text="Ask anything…",
        expand=True,
        text_size=13,
        border=ft.InputBorder.NONE,
        shift_enter=True,
        on_submit=lambda e: page.run_task(send_typed),
    )

    # Native file dialog; a service, not a control, in flet ≥0.70.
    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    def bubble(text: str, is_user: bool,
               attachments: list[dict] | None = None) -> ft.Control:
        inner: list[ft.Control] = []
        for att in attachments or []:
            ext = att["name"].rsplit(".", 1)[-1].lower()
            if ext in _IMAGE_EXTS:
                inner.append(ft.Image(
                    src=att["data"], width=180, height=120,
                    fit=ft.BoxFit.COVER, border_radius=8,
                ))
            else:
                inner.append(ft.Row(
                    spacing=4,
                    controls=[
                        ft.Icon(ft.Icons.DESCRIPTION, size=14, color="#FFFFFF"),
                        ft.Text(att["name"], size=11, color="#FFFFFF",
                                italic=True),
                    ],
                ))
        if text:
            inner.append(ft.Text(
                text, size=13,
                color="#FFFFFF" if is_user else "#1B5E20",
                selectable=True,
            ))
        return ft.Row(
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
            controls=[
                ft.Container(
                    bgcolor=_USER_BUBBLE if is_user else _BOT_BUBBLE,
                    border_radius=12,
                    padding=ft.Padding(left=12, right=12, top=8, bottom=8),
                    content=ft.Column(spacing=6, tight=True, controls=inner),
                    width=250,
                )
            ],
        )

    def approve_control():
        """Approve button that, on success, scales out and a green check
        scales in — so an approved card shows only the checkmark. Returns
        (status_text, button, switcher, done_fn, fail_fn); shared by all cards."""
        status = ft.Text("", size=11, color=_PRIMARY_DARK)
        btn = ft.FilledButton(
            "Approve", icon=ft.Icons.CHECK,
            style=ft.ButtonStyle(bgcolor=_PRIMARY, color="#FFFFFF"),
        )
        switcher = ft.AnimatedSwitcher(
            btn,
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=0, reverse_duration=0,
        )

        def done(msg: str):
            status.value = msg
            status.color = _PRIMARY_DARK
            switcher.content = ft.Icon(ft.Icons.CHECK_CIRCLE, color=_PRIMARY, size=26)
            page.update()

        def fail(msg: str):
            status.value = msg
            status.color = "#C62828"
            page.update()

        return status, btn, switcher, done, fail

    def action_card(action: dict) -> ft.Control:
        """A dosing action recommended by the LLM, approvable inline."""
        pump = action.get("pump", "?")
        amount = float(action.get("amount_ml", 0) or 0)
        reason = action.get("reason", "")

        status, approve_btn, switcher, done, fail = approve_control()

        def approve(e):
            try:
                dispensed = actuator_hub.dose(pump, amount)
            except RuntimeError as exc:  # includes CooldownError
                fail(str(exc))
                return
            db.log_dose(pump, dispensed, source="llm")
            done(f"Dispensed {dispensed:.1f} ml")

        approve_btn.on_click = approve

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.Border.all(1, _PRIMARY),
            border_radius=12,
            padding=10,
            width=270,
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.OPACITY, color=_PRIMARY, size=16),
                            ft.Text(pump, size=13, weight=ft.FontWeight.BOLD,
                                    color="#1B5E20", expand=True),
                            ft.Text(f"{amount:.1f} ml", size=13,
                                    weight=ft.FontWeight.BOLD, color=_PRIMARY_DARK),
                        ],
                    ),
                    ft.Text(reason, size=11, color="#33691E"),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[status, switcher],
                    ),
                ],
            ),
        )

    def param_card(proposal: dict) -> ft.Control:
        """Parameter setup proposed by the LLM (crop min/max), approvable inline."""
        crop = proposal.get("crop", "?")
        targets_prop = proposal.get("targets", {})

        status, approve_btn, switcher, done, fail = approve_control()

        rows = []
        for name in ("EC", "PH", "Temperature", "Humidity"):
            rng = targets_prop.get(name)
            if not rng:
                continue
            rows.append(
                ft.Row(
                    controls=[
                        ft.Text(name, size=12, weight=ft.FontWeight.W_600,
                                color="#1B5E20", expand=True),
                        ft.Text(f"{rng['min']} – {rng['max']} {_UNITS.get(name,'')}",
                                size=12, color=_PRIMARY_DARK),
                    ],
                )
            )

        def approve(e):
            applied = []
            for name, rng in targets_prop.items():
                try:
                    lo, hi = float(rng["min"]), float(rng["max"])
                except (KeyError, TypeError, ValueError):
                    continue
                if lo >= hi:  # reject nonsense ranges
                    continue
                state.targets[name] = {"min": lo, "max": hi}
                applied.append(name)
            state.save()
            done(f"Saved ({', '.join(applied)})")

        approve_btn.on_click = approve

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.Border.all(1, _PRIMARY),
            border_radius=12,
            padding=10,
            width=270,
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.TUNE, color=_PRIMARY, size=16),
                            ft.Text(f"Setup for: {crop}", size=13,
                                    weight=ft.FontWeight.BOLD, color="#1B5E20",
                                    expand=True),
                        ],
                    ),
                    *rows,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[status, switcher],
                    ),
                ],
            ),
        )

    def growth_card(proposal: dict) -> ft.Control:
        """Growth-stage plan proposed by the LLM (name/duration/targets per
        stage), approvable inline. On approve: creates the stages on the
        active profile and starts planting today."""
        crop = proposal.get("crop", "?")
        stages_prop = proposal.get("stages", [])

        status, approve_btn, switcher, done, fail = approve_control()

        stage_rows = []
        for s in stages_prop:
            name = s.get("name", "?")
            days = s.get("duration_days", "?")
            tgt = s.get("targets", {})
            ec = tgt.get("EC")
            ec_str = f"EC {ec['min']}–{ec['max']}" if ec else ""
            stage_rows.append(
                ft.Row(
                    controls=[
                        ft.Text(f"{name}", size=12, weight=ft.FontWeight.W_600,
                                color="#1B5E20", expand=True),
                        ft.Text(f"{days} days · {ec_str}", size=11, color=_PRIMARY_DARK),
                    ],
                )
            )

        def approve(e):
            count = state.set_stages(stages_prop)
            if count == 0:
                fail("No usable stages")
            else:
                state.start_planting()
                state.save()
                done(f"Set {count} stages — planting starts today")

        approve_btn.on_click = approve

        return ft.Container(
            bgcolor="#FFFFFF",
            border=ft.Border.all(1, _PRIMARY),
            border_radius=12,
            padding=10,
            width=280,
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.TIMELINE, color=_PRIMARY, size=16),
                            ft.Text(f"Grow plan: {crop}", size=13,
                                    weight=ft.FontWeight.BOLD, color="#1B5E20",
                                    expand=True),
                        ],
                    ),
                    *stage_rows,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[status, switcher],
                    ),
                ],
            ),
        )

    send_btn = ft.IconButton(
        ft.Icons.ARROW_UPWARD, icon_size=16, icon_color="#FFFFFF",
        tooltip="Send",
        style=ft.ButtonStyle(bgcolor=_PRIMARY),
    )
    attach_btn = ft.IconButton(
        ft.Icons.ADD, icon_size=18, icon_color=_PRIMARY_DARK,
        tooltip="Attach file or image",
    )
    thinking = ft.Text("Thinking…", size=11, color="#9E9E9E", visible=False)

    def busy(on: bool) -> None:
        thinking.visible = on
        send_btn.disabled = on
        attach_btn.disabled = on
        page.update()

    # -- model picker ---------------------------------------------------------
    # Compact, Claude-style: sits in the input bar, persists to app config.

    def on_model_select(e) -> None:
        state.llm_model = e.control.value
        state.save()

    model_dd = ft.Dropdown(
        value=state.llm_model,
        options=[
            ft.dropdown.Option(key=mid, text=label)
            for mid, label, _desc in llm_agent.AVAILABLE_MODELS
        ],
        on_select=on_model_select,
        width=130,
        dense=True,
        text_size=11,
        border=ft.InputBorder.NONE,
        content_padding=ft.Padding(left=8, right=0, top=0, bottom=0),
    )
    # Saved model no longer offered (e.g. renamed in an update) — fall back.
    if state.llm_model not in {m[0] for m in llm_agent.AVAILABLE_MODELS}:
        state.llm_model = llm_agent.DEFAULT_MODEL
        model_dd.value = state.llm_model

    # -- attachments ----------------------------------------------------------

    attach_row = ft.Row(wrap=True, spacing=6, run_spacing=6, visible=False)

    def render_attachments() -> None:
        attach_row.controls.clear()
        for i, att in enumerate(pending_attachments):
            ext = att["name"].rsplit(".", 1)[-1].lower()
            icon = ft.Icons.IMAGE if ext in _IMAGE_EXTS else ft.Icons.DESCRIPTION
            name = att["name"]
            if len(name) > 18:
                name = name[:15] + "…"

            def remove(e, index=i):
                pending_attachments.pop(index)
                render_attachments()
                page.update()

            attach_row.controls.append(ft.Container(
                bgcolor=theme.PRIMARY_LIGHT,
                border_radius=8,
                padding=ft.Padding(left=8, right=2, top=2, bottom=2),
                content=ft.Row(
                    spacing=2, tight=True,
                    controls=[
                        ft.Icon(icon, size=13, color=_PRIMARY_DARK),
                        ft.Text(name, size=11, color=_PRIMARY_DARK),
                        ft.IconButton(
                            ft.Icons.CLOSE, icon_size=12,
                            icon_color=_PRIMARY_DARK,
                            padding=0, on_click=remove,
                        ),
                    ],
                ),
            ))
        attach_row.visible = bool(pending_attachments)

    async def pick_attachments() -> None:
        files = await file_picker.pick_files(
            allow_multiple=True,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=_ATTACH_EXTS,
            with_data=True,  # bytes work in desktop and web mode alike
        )
        for f in files:
            if not f.bytes:
                continue
            if f.size > _MAX_ATTACH_BYTES:
                messages_col.controls.append(
                    bubble(f"⚠ {f.name} is over 5MB — skipped", is_user=False)
                )
                continue
            pending_attachments.append({"name": f.name, "data": f.bytes})
        render_attachments()
        page.update()

    attach_btn.on_click = lambda e: page.run_task(pick_attachments)

    # -- quick actions --------------------------------------------------------

    def do_status(e) -> None:
        """Local, instant status summary — no API call needed."""
        messages_col.controls.append(bubble("Check status", is_user=True))
        readings = state.last_readings
        targets = state.targets
        if not readings:
            messages_col.controls.append(bubble("No sensor data yet", is_user=False))
            page.update()
            return
        lines = []
        for name in ("EC", "PH", "Temperature", "Humidity"):
            val = readings.get(name)
            if not isinstance(val, (int, float)) or val != val:
                lines.append(f"{name}: no data")
                continue
            tgt = targets.get(name, {})
            if tgt:
                label, _ = get_status(val, tgt["min"], tgt["max"])
                lines.append(f"{name}: {val:.2f} {_UNITS.get(name,'')} — {label}")
            else:
                lines.append(f"{name}: {val:.2f} {_UNITS.get(name,'')}")
        lines.append(f"Tank ~{state.tank_capacity_liters():.1f} L")
        messages_col.controls.append(bubble("\n".join(lines), is_user=False))
        page.update()

    async def do_recommend() -> None:
        """Ask Claude for dosing actions; render inline Approve cards."""
        messages_col.controls.append(bubble("Recommend dosing", is_user=True))
        busy(True)
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, llm_agent.recommend,
                dict(state.last_readings), state.targets, state.active_profile,
                state.tank_capacity_liters(), state.language, state.llm_model,
            )
        except llm_agent.LLMError as exc:
            messages_col.controls.append(bubble(f"⚠ {exc}", is_user=False))
        except Exception as exc:  # noqa: BLE001
            messages_col.controls.append(bubble(f"⚠ Unexpected error: {exc}", is_user=False))
        else:
            if result.get("usage"):
                db.log_llm_usage(**result["usage"])
            if result.get("summary"):
                messages_col.controls.append(bubble(result["summary"], is_user=False))
            actions = result.get("actions", [])
            if actions:
                for a in actions:
                    messages_col.controls.append(
                        ft.Row(
                            alignment=ft.MainAxisAlignment.START,
                            controls=[action_card(a)],
                        )
                    )
            else:
                messages_col.controls.append(
                    bubble("All values within target — no dosing needed", is_user=False)
                )
        finally:
            busy(False)

    chips = ft.Row(
        wrap=True,
        spacing=6,
        run_spacing=6,
        controls=[
            ft.OutlinedButton(
                "📊 Check status",
                on_click=do_status,
                style=ft.ButtonStyle(color=_PRIMARY_DARK),
            ),
            ft.OutlinedButton(
                "💧 Recommend dosing",
                on_click=lambda e: page.run_task(do_recommend),
                style=ft.ButtonStyle(color=_PRIMARY_DARK),
            ),
        ],
    )

    # -- free-form chat -------------------------------------------------------

    async def send_typed():
        text = (input_field.value or "").strip()
        if not text and not pending_attachments:
            return
        attachments = list(pending_attachments)
        pending_attachments.clear()
        render_attachments()
        input_field.value = ""
        messages_col.controls.append(
            bubble(text, is_user=True, attachments=attachments)
        )
        history.append({
            "role": "user",
            "content": llm_agent.build_user_content(text, attachments),
        })
        busy(True)
        proposal = None
        growth_proposal = None
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, llm_agent.chat, list(history),
                dict(state.last_readings), state.targets, state.active_profile,
                state.tank_capacity_liters(), state.language, state.llm_model,
                list(state.growth_config()["stages"]),
            )
        except llm_agent.LLMError as exc:
            reply = f"⚠ {exc}"
        except Exception as exc:  # noqa: BLE001
            reply = f"⚠ Unexpected error: {exc}"
        else:
            reply = result["text"]
            proposal = result.get("param_proposal")
            growth_proposal = result.get("growth_proposal")
            if result.get("usage"):
                db.log_llm_usage(**result["usage"])
            history.append({"role": "assistant", "content": reply})
        messages_col.controls.append(bubble(reply, is_user=False))
        if proposal:
            messages_col.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    controls=[param_card(proposal)],
                )
            )
        if growth_proposal:
            messages_col.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    controls=[growth_card(growth_proposal)],
                )
            )
        busy(False)

    send_btn.on_click = lambda e: page.run_task(send_typed)

    panel = ft.Container(
        width=370,
        height=560,
        bgcolor=_PANEL_BG,
        border_radius=16,
        padding=0,
        visible=False,
        shadow=ft.BoxShadow(blur_radius=20, color="#33000000"),
        content=ft.Column(
            spacing=0,
            controls=[
                # header — bright green, leaf logo
                ft.Container(
                    bgcolor=_PRIMARY,
                    border_radius=ft.BorderRadius(
                        top_left=16, top_right=16, bottom_left=0, bottom_right=0
                    ),
                    padding=ft.Padding(left=14, right=8, top=10, bottom=10),
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                bgcolor="#FFFFFF",
                                border_radius=20,
                                padding=6,
                                content=ft.Icon(ft.Icons.ECO, color=_PRIMARY, size=18),
                            ),
                            ft.Text("Farm Assistant", color="#FFFFFF",
                                    weight=ft.FontWeight.BOLD, size=15, expand=True),
                        ],
                    ),
                ),
                # messages
                ft.Container(expand=True, padding=12, content=messages_col),
                thinking,
                # quick-action chips
                ft.Container(
                    padding=ft.Padding(left=10, right=10, top=4, bottom=4),
                    content=chips,
                ),
                # composer — Claude-style: staged attachments above a rounded
                # input card; attach button + model picker + send inside it.
                ft.Container(
                    padding=ft.Padding(left=10, right=10, top=4, bottom=10),
                    content=ft.Column(
                        spacing=6,
                        controls=[
                            attach_row,
                            ft.Container(
                                bgcolor=theme.BG,
                                border=ft.Border.all(1, theme.BORDER),
                                border_radius=14,
                                padding=ft.Padding(left=10, right=6, top=2, bottom=4),
                                content=ft.Column(
                                    spacing=0,
                                    controls=[
                                        input_field,
                                        ft.Row(
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                            controls=[
                                                attach_btn,
                                                model_dd,
                                                ft.Container(expand=True),
                                                send_btn,
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        ),
    )

    def toggle(e=None):
        panel.visible = not panel.visible
        if panel.visible and not messages_col.controls:
            messages_col.controls.append(
                bubble("Hi! Tap a button below or ask me anything", is_user=False)
            )
        page.update()

    # Fixed overlay anchored below the top app bar on the right. The trigger
    # button lives in the app bar (see app_bar.build_app_bar); this returns
    # (overlay, toggle) so app.py can wire that button to toggle().
    overlay = ft.Container(top=56, right=16, content=panel)
    return overlay, toggle
