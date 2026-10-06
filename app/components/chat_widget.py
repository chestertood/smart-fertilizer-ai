import asyncio
import copy
from datetime import datetime
import flet as ft

from app import theme
from app.services import llm_agent
from app.services.actuators import ActuatorHub
from app.services.database import Database
from config.profiles import AppState
from config.i18n import t
from config.sensors import get_status

# Chat colors come from the shared theme so the assistant's header/panel
# chrome matches the rest of the app; bubbles themselves follow Telegram's
# convention (sent = tinted, received = plain surface) rather than the app's
# green-on-green, which made the two hard to tell apart at a glance.
#
# These are read fresh on every build (not captured at import) because
# theme.apply() rebinds them when the operator switches to dark mode.
_PRIMARY = theme.PRIMARY          # brand green is the same in both palettes
_PRIMARY_DARK = theme.PRIMARY_DARK
_UNITS = {"EC": "mS/cm", "PH": "pH", "Temperature": "°C", "Humidity": "%"}

# ponytail: char-count width heuristic, not real text measurement — this flet
# version's Container has no shrink-to-content/max-width constraint to size
# bubbles the way Telegram does natively. Upgrade path: swap for real
# intrinsic sizing if/when flet exposes Container(constraints=...).
_BUBBLE_MIN_WIDTH = 110
_BUBBLE_MAX_WIDTH = 270
_PX_PER_CHAR = 7.5  # was 7 — underestimated real text width, so short
                     # labels like "Recommend dosing" wrapped to 2 lines
                     # instead of fitting the one line the bubble had room for


def _bubble_width(text: str, has_attachment: bool) -> int:
    if has_attachment:
        return _BUBBLE_MAX_WIDTH
    longest_line = max((len(line) for line in text.splitlines()), default=0)
    return max(_BUBBLE_MIN_WIDTH, min(_BUBBLE_MAX_WIDTH, int(longest_line * _PX_PER_CHAR) + 28))


def _proposal_card(icon: str, title: str, rows: list[ft.Control],
                    status: ft.Control, switcher: ft.Control, *,
                    header_extra: ft.Control | None = None,
                    width: int = 280) -> ft.Control:
    """Shared shell for every LLM-proposal card (dose/params/growth/rules/
    calibration): icon+title header, body rows, approve-button footer.
    `header_extra` is one more control tacked onto the header row (action_card
    uses it for the ml amount, right-aligned next to the pump name)."""
    header = [
        ft.Icon(icon, color=_PRIMARY, size=16),
        ft.Text(title, size=theme.FONT_SM, weight=ft.FontWeight.BOLD, color=theme.ACCENT_TEXT, expand=True),
    ]
    if header_extra is not None:
        header.append(header_extra)
    return ft.Container(
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, _PRIMARY),
        border_radius=12,
        padding=10,
        width=width,
        content=ft.Column(
            spacing=4,
            controls=[
                ft.Row(controls=header),
                *rows,
                ft.Row(alignment=ft.MainAxisAlignment.END, controls=[status, switcher]),
            ],
        ),
    )

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
        hint_text=t("chat.placeholder", state.language),
        expand=True,
        text_size=13,
        border=ft.InputBorder.NONE,
        shift_enter=True,
        autofocus=True,
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
                        ft.Text(att["name"], size=theme.FONT_XS, color="#FFFFFF",
                                italic=True),
                    ],
                ))
        if text:
            inner.append(ft.Text(
                text, size=theme.FONT_SM,
                color=theme.TEXT if is_user else theme.TEXT,
                selectable=True,
            ))
        inner.append(ft.Row(
            alignment=ft.MainAxisAlignment.END,
            controls=[ft.Text(
                datetime.now().strftime("%H:%M"), size=theme.FONT_XS,
                color=theme.TEXT_MUTED if is_user else theme.TEXT_MUTED,
            )],
        ))
        # Sharp corner on the pointing side — a cheap stand-in for a real
        # speech-bubble tail, same asymmetric-radius trick as the panel
        # header below.
        radius = (
            ft.BorderRadius(top_left=12, top_right=12, bottom_left=12, bottom_right=2)
            if is_user else
            ft.BorderRadius(top_left=12, top_right=12, bottom_left=2, bottom_right=12)
        )
        return ft.Row(
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START,
            controls=[
                ft.Container(
                    bgcolor=theme.PRIMARY_LIGHT if is_user else theme.SURFACE,
                    border=ft.Border.all(0.8, theme.BORDER),
                    border_radius=radius,
                    padding=ft.Padding(left=12, right=12, top=8, bottom=4),
                    content=ft.Column(spacing=4, tight=True, controls=inner),
                    width=_bubble_width(text, bool(attachments)),
                )
            ],
        )

    def approve_control():
        """Approve button that, on success, scales out and a green check
        scales in — so an approved card shows only the checkmark. Returns
        (status_text, button, switcher, done_fn, fail_fn); shared by all cards."""
        status = ft.Text("", size=theme.FONT_XS, color=_PRIMARY_DARK)
        btn = ft.FilledButton(
            t("chat.approve", state.language), icon=ft.Icons.CHECK,
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
            status.color = theme.DANGER
            page.update()

        return status, btn, switcher, done, fail

    def apply_dose(pump: str, amount: float) -> tuple[bool, str]:
        """Actually dispense + log one dosing action. Shared by
        action_card's approve button and llm_mode=="auto", which skips
        the card and calls this directly — one place doses+logs so the
        two paths can't drift apart."""
        try:
            dispensed = actuator_hub.dose(pump, amount)
        except RuntimeError as exc:  # includes CooldownError
            return False, str(exc)
        db.log_dose(pump, dispensed, source="llm")
        return True, f"Dispensed {dispensed:.1f} ml"

    def action_card(action: dict) -> ft.Control:
        """A dosing action recommended by the LLM, approvable inline."""
        pump = action.get("pump", "?")
        amount = float(action.get("amount_ml", 0) or 0)
        reason = action.get("reason", "")

        status, approve_btn, switcher, done, fail = approve_control()

        def approve(e):
            ok, msg = apply_dose(pump, amount)
            (done if ok else fail)(msg)

        approve_btn.on_click = approve

        return _proposal_card(
            ft.Icons.OPACITY, pump, [ft.Text(reason, size=theme.FONT_XS, color=theme.ACCENT_TEXT)],
            status, switcher, width=270,
            header_extra=ft.Text(f"{amount:.1f} ml", size=theme.FONT_SM,
                                  weight=ft.FontWeight.BOLD, color=_PRIMARY_DARK),
        )

    def render_dose_action(action: dict) -> ft.Control:
        """One dosing action, either as an approval card (default) or,
        in llm_mode=="auto", dispensed immediately with a bubble in its
        place — shared by the "Recommend dosing" chip and free-text
        dose_proposal below."""
        if state.llm_mode == "auto":
            pump = action.get("pump", "?")
            amount = float(action.get("amount_ml", 0) or 0)
            _ok, msg = apply_dose(pump, amount)
            return bubble(f"Auto-dosed {pump}: {msg}", is_user=False)
        return ft.Row(
            alignment=ft.MainAxisAlignment.START,
            controls=[action_card(action)],
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
                        ft.Text(name, size=theme.FONT_SM, weight=ft.FontWeight.W_600,
                                color=theme.ACCENT_TEXT, expand=True),
                        ft.Text(f"{rng['min']} – {rng['max']} {_UNITS.get(name,'')}",
                                size=theme.FONT_SM, color=_PRIMARY_DARK),
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

        return _proposal_card(ft.Icons.TUNE, f"Setup for: {crop}", rows,
                               status, switcher, width=270)

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
                        ft.Text(f"{name}", size=theme.FONT_SM, weight=ft.FontWeight.W_600,
                                color=theme.ACCENT_TEXT, expand=True),
                        ft.Text(f"{days} days · {ec_str}", size=theme.FONT_XS, color=_PRIMARY_DARK),
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

        return _proposal_card(ft.Icons.TIMELINE, f"Grow plan: {crop}",
                               stage_rows, status, switcher)

    def rules_card(proposal: dict) -> ft.Control:
        """Auto-dose rule set proposed by the LLM, approvable inline. On
        approve: replaces the profile's whole auto-dose rule list."""
        rules_prop = proposal.get("rules", [])

        status, approve_btn, switcher, done, fail = approve_control()

        rule_rows = []
        for r in rules_prop:
            state_str = "" if r.get("enabled", True) else " (disabled)"
            rule_rows.append(
                ft.Text(
                    f"if {r.get('sensor')} {r.get('op')} {r.get('threshold')} "
                    f"→ {r.get('amount')}ml {r.get('pump')}{state_str}",
                    size=theme.FONT_XS, color=theme.ACCENT_TEXT,
                )
            )

        def approve(e):
            count = state.set_auto_rules(rules_prop)
            if count == 0:
                fail("No usable rules")
            else:
                state.save()
                done(f"Set {count} auto-dose rule(s)")

        approve_btn.on_click = approve

        return _proposal_card(ft.Icons.REPEAT, "Auto-dose rules", rule_rows,
                               status, switcher)

    def calibration_card(proposal: dict) -> ft.Control:
        """Partial calibration change (pump rate/max, sensor offset, tank
        size) proposed by the LLM, approvable inline. On approve: merges
        just the proposed fields into state — leaves everything else."""
        status, approve_btn, switcher, done, fail = approve_control()

        change_rows = []
        for name, cfg in (proposal.get("pumps") or {}).items():
            if "max_dose" in cfg:
                change_rows.append(ft.Text(f"{name}: max dose → {cfg['max_dose']}ml",
                                            size=theme.FONT_XS, color=theme.ACCENT_TEXT))
            if "ml_per_s" in cfg:
                change_rows.append(ft.Text(f"{name}: flow rate → {cfg['ml_per_s']}ml/s",
                                            size=theme.FONT_XS, color=theme.ACCENT_TEXT))
        for sensor, value in (proposal.get("offsets") or {}).items():
            change_rows.append(ft.Text(f"{sensor} offset → {value:+g}",
                                        size=theme.FONT_XS, color=theme.ACCENT_TEXT))
        tank = proposal.get("water_tank") or {}
        if tank:
            dims = ", ".join(f"{k.replace('_cm','')} {v}cm" for k, v in tank.items())
            change_rows.append(ft.Text(f"Tank: {dims}", size=theme.FONT_XS, color=theme.ACCENT_TEXT))

        def approve(e):
            applied = state.apply_calibration(proposal)
            if not applied:
                fail("No valid fields to apply")
            else:
                state.save()
                done(f"Saved ({', '.join(applied)})")

        approve_btn.on_click = approve

        return _proposal_card(ft.Icons.TUNE, "Calibration change", change_rows,
                               status, switcher)

    send_btn = ft.IconButton(
        ft.Icons.ARROW_UPWARD, icon_size=16, icon_color="#FFFFFF",
        tooltip=t("chat.send", state.language),
        style=ft.ButtonStyle(bgcolor=_PRIMARY),
    )
    attach_btn = ft.IconButton(
        ft.Icons.ADD, icon_size=18, icon_color=_PRIMARY_DARK,
        tooltip=t("chat.attach", state.language),
    )
    thinking = ft.Text(t("chat.thinking", state.language), size=theme.FONT_XS, color=theme.TEXT_MUTED, visible=False)

    def busy(on: bool) -> None:
        thinking.visible = on
        send_btn.disabled = on
        attach_btn.disabled = on
        page.update()

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
                        ft.Text(name, size=theme.FONT_XS, color=_PRIMARY_DARK),
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
        messages_col.controls.append(bubble(t("chat.check_status", state.language), is_user=True))
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
        messages_col.controls.append(bubble(t("chat.recommend", state.language), is_user=True))
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
                    messages_col.controls.append(render_dose_action(a))
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
            # Material icons instead of emoji glyphs: they ship inside Flutter,
            # so they render on the Pi, which has no color-emoji font by default.
            ft.OutlinedButton(
                t("chat.check_status", state.language),
                icon=ft.Icons.CHECKLIST_OUTLINED,
                on_click=do_status,
                style=ft.ButtonStyle(color=_PRIMARY_DARK),
            ),
            ft.OutlinedButton(
                t("chat.recommend", state.language),
                icon=ft.Icons.THUMB_UP_OUTLINED,
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
        rules_proposal = None
        dose_proposal = None
        calibration_proposal = None
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, llm_agent.chat, list(history),
                dict(state.last_readings), state.targets, state.active_profile,
                state.tank_capacity_liters(), state.language, state.llm_model,
                list(state.growth_config()["stages"]), list(state.auto_rules),
                copy.deepcopy(state.pumps), dict(state.offsets), dict(state.water_tank),
            )
        except llm_agent.LLMError as exc:
            reply = f"⚠ {exc}"
        except Exception as exc:  # noqa: BLE001
            reply = f"⚠ Unexpected error: {exc}"
        else:
            reply = result["text"]
            proposal = result.get("param_proposal")
            growth_proposal = result.get("growth_proposal")
            rules_proposal = result.get("rules_proposal")
            dose_proposal = result.get("dose_proposal")
            calibration_proposal = result.get("calibration_proposal")
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
        if rules_proposal:
            messages_col.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    controls=[rules_card(rules_proposal)],
                )
            )
        # One card/bubble per action, not one for the whole proposal —
        # matches the "Recommend dosing" quick action.
        for dose_action in (dose_proposal or {}).get("actions", []):
            messages_col.controls.append(render_dose_action(dose_action))
        if calibration_proposal:
            messages_col.controls.append(
                ft.Row(
                    alignment=ft.MainAxisAlignment.START,
                    controls=[calibration_card(calibration_proposal)],
                )
            )
        busy(False)

    send_btn.on_click = lambda e: page.run_task(send_typed)

    _POP_ANIM = ft.Animation(180, ft.AnimationCurve.EASE_OUT)
    panel = ft.Container(
        width=370,
        height=560,
        bgcolor=theme.SURFACE,
        border_radius=16,
        padding=0,
        visible=False,
        opacity=0,
        scale=0.92,
        animate_opacity=_POP_ANIM,
        animate_scale=_POP_ANIM,
        shadow=ft.BoxShadow(blur_radius=20, color="#33000000"),
        content=ft.Column(
            spacing=0,
            controls=[
                # header — same gradient as the app bar, so the popup reads
                # as a continuation of it instead of a separate flat green.
                ft.Container(
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.CENTER_LEFT,
                        end=ft.Alignment.CENTER_RIGHT,
                        colors=[theme.PRIMARY_DARK, theme.PRIMARY],
                    ),
                    border_radius=ft.BorderRadius(
                        top_left=16, top_right=16, bottom_left=0, bottom_right=0
                    ),
                    padding=ft.Padding(left=14, right=8, top=10, bottom=10),
                    content=ft.Row(
                        controls=[
                            ft.Container(
                                bgcolor="#FFFFFF",
                                border_radius=20,
                                width=30,
                                height=30,
                                alignment=ft.Alignment.CENTER,
                                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                                content=ft.Image(
                                    src="telegram_bot_avatar.png",
                                    width=30, height=30,
                                    fit=ft.BoxFit.COVER,
                                    border_radius=15,
                                ),
                            ),
                            ft.Text(t("chat.title", state.language), color="#FFFFFF",
                                    weight=ft.FontWeight.BOLD, size=theme.FONT_MD, expand=True),
                        ],
                    ),
                ),
                # messages — gray backdrop, like Telegram's chat wallpaper,
                # so bubbles read as bubbles instead of floating on the
                # panel's own white background.
                ft.Container(expand=True, padding=12, bgcolor=theme.SURFACE_ALT,
                             content=messages_col),
                thinking,
                # quick-action chips
                ft.Container(
                    padding=ft.Padding(left=10, right=10, top=4, bottom=4),
                    content=chips,
                ),
                # composer — Claude-style: staged attachments above a rounded
                # input card; attach button + send inside it.
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

    want_open = [False]  # mutable flag: closing target for on_animation_end below

    def _on_panel_anim_end(e):
        # Fires after both open and close transitions — only hide-for-real
        # once the close animation (opacity/scale → 0) has actually landed.
        if not want_open[0]:
            panel.visible = False
            page.update()

    panel.on_animation_end = _on_panel_anim_end

    def toggle(e=None):
        want_open[0] = not want_open[0]
        opening = want_open[0]
        if opening and not messages_col.controls:
            messages_col.controls.append(
                bubble("Hi! Tap a button below or ask me anything", is_user=False)
            )
        if opening:
            panel.visible = True
            # Force a render at the closed (opacity 0 / scaled down) state
            # before animating to the open one — same two-update trick as
            # the autofocus flip below, otherwise flet nets no visible change
            # and there's nothing to animate from.
            panel.opacity = 0
            panel.scale = 0.92
            page.update()
            panel.opacity = 1
            panel.scale = 1
            page.update()
            # TextField.autofocus only fires once, on first mount — this
            # control mounted long ago with the panel hidden, so it never
            # got the chance. Flip it off then on as two separate updates so
            # flet actually diffs+patches the client twice (setting both
            # before one update nets no change — client never sees it).
            # (The imperative RPC .focus() call — even awaited, even with a
            # render-frame delay — never landed here; this route does.)
            input_field.autofocus = False
            page.update()
            input_field.autofocus = True
            page.update()
        else:
            panel.opacity = 0
            panel.scale = 0.92
            page.update()
            # panel.visible flips to False in _on_panel_anim_end once the
            # fade-out actually finishes.

    # Fixed overlay anchored below the top app bar on the right. The trigger
    # button lives in the app bar (see app_bar.build_app_bar); this returns
    # (overlay, toggle) so app.py can wire that button to toggle().
    overlay = ft.Container(top=56, right=16, content=panel)
    return overlay, toggle
