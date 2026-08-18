"""Telegram DM bridge — lets the operator ask the same Claude-backed
fertilizer assistant the in-app chat panel provides, from Telegram, and
approve any proposed dosing/parameter/growth change with inline buttons
without opening the app.

v1 scope (see docs/superpowers/specs/2026-08-17-telegram-bridge-design.md):
DM only. Remote approval added 2026-08-18 — supersedes that spec's
"approval stays in-app" decision. Still no proactive alerts, no
persistence of chat history or pending proposals across restarts.
"""
import asyncio
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)


def parse_allowed_ids(raw: str | None) -> set[int]:
    """Parse TELEGRAM_ALLOWED_IDS ("123,456") into a set of ints. Empty/None
    -> empty set, which is a fail-closed allowlist (nobody is allowed)."""
    if not raw:
        return set()
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def is_allowed(sender_id: int, allowed: set[int]) -> bool:
    """True only if sender_id is explicitly in the allowlist. An empty
    allowlist denies everyone — there is no "open" fallback."""
    return sender_id in allowed


class ChatHistory:
    """In-memory, per-chat message history. Resets on app restart — v1
    doesn't persist Telegram conversations (see design spec, Scope)."""

    def __init__(self, max_messages: int = 20) -> None:
        self._max = max_messages
        self._by_chat: dict[int, list[dict]] = {}

    def append(self, chat_id: int, role: str, content) -> None:
        messages = self._by_chat.setdefault(chat_id, [])
        messages.append({"role": role, "content": content})
        if len(messages) > self._max:
            del messages[: len(messages) - self._max]

    def get(self, chat_id: int) -> list[dict]:
        return list(self._by_chat.get(chat_id, []))


class PendingProposals:
    """In-memory store of dosing/parameter/growth proposals awaiting a
    Telegram inline-button tap. Lost on app restart, same as ChatHistory —
    a stale proposal from before a restart just gets "already handled"
    instead of resurrecting and possibly applying against changed state."""

    def __init__(self) -> None:
        self._next_id = 1
        self._by_id: dict[str, dict] = {}

    def register(self, kind: str, data: dict, chat_id: int) -> str:
        pid = format(self._next_id, "x")
        self._next_id += 1
        self._by_id[pid] = {"kind": kind, "data": data, "chat_id": chat_id}
        return pid

    def get(self, pid: str) -> dict | None:
        return self._by_id.get(pid)

    def pop(self, pid: str) -> dict | None:
        """Removes the record — first tap wins. A second tap, or a tap
        after a restart, finds nothing and the caller reports it as
        already handled instead of applying it twice."""
        return self._by_id.pop(pid, None)


def approval_keyboard(pid: str) -> dict:
    """Telegram inline keyboard for one pending proposal."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve:{pid}"},
                {"text": "❌ Reject", "callback_data": f"reject:{pid}"},
            ]
        ]
    }


_UNITS = {"EC": "mS/cm", "PH": "pH", "Temperature": "°C", "Humidity": "%"}


def format_dose_proposal(action: dict) -> str:
    """One dosing action, as shown before the operator taps Approve/Reject.
    Mirrors chat_widget.py's action_card."""
    pump = action.get("pump", "?")
    amount = float(action.get("amount_ml", 0) or 0)
    reason = action.get("reason", "")
    lines = [f"💧 {pump}: {amount:.1f} ml"]
    if reason:
        lines.append(reason)
    return "\n".join(lines)


def format_param_proposal(proposal: dict) -> str:
    """A crop parameter setup proposal, as shown before approval. Mirrors
    chat_widget.py's param_card."""
    crop = proposal.get("crop", "?")
    targets_prop = proposal.get("targets", {})
    lines = [f"⚙ Setup for: {crop}"]
    for name in ("EC", "PH", "Temperature", "Humidity"):
        rng = targets_prop.get(name)
        if not rng:
            continue
        lines.append(f"{name}: {rng['min']} – {rng['max']} {_UNITS.get(name, '')}")
    return "\n".join(lines)


def format_growth_proposal(proposal: dict) -> str:
    """A growth-stage plan proposal, as shown before approval. Mirrors
    chat_widget.py's growth_card."""
    crop = proposal.get("crop", "?")
    stages_prop = proposal.get("stages", [])
    lines = [f"🌱 Grow plan: {crop}"]
    for s in stages_prop:
        name = s.get("name", "?")
        days = s.get("duration_days", "?")
        tgt = s.get("targets", {})
        ec = tgt.get("EC")
        ec_str = f" · EC {ec['min']}–{ec['max']}" if ec else ""
        lines.append(f"{name}: {days} days{ec_str}")
    return "\n".join(lines)


def status_summary(readings: dict, targets: dict, tank_liters: float) -> str:
    """Instant, local sensor summary — no LLM call, mirrors chat_widget.py's
    "Check status" quick action so the Telegram button behaves identically."""
    from config.sensors import get_status

    if not readings:
        return "No sensor data yet"
    lines = []
    for name in ("EC", "PH", "Temperature", "Humidity"):
        val = readings.get(name)
        if not isinstance(val, (int, float)) or val != val:
            lines.append(f"{name}: no data")
            continue
        tgt = targets.get(name, {})
        if tgt:
            label, _ = get_status(val, tgt["min"], tgt["max"])
            lines.append(f"{name}: {val:.2f} {_UNITS.get(name, '')} — {label}")
        else:
            lines.append(f"{name}: {val:.2f} {_UNITS.get(name, '')}")
    lines.append(f"Tank ~{tank_liters:.1f} L")
    return "\n".join(lines)


def status_image(readings: dict, targets: dict) -> bytes:
    """Render the 4 sensors as a card-grid PNG for Telegram's sendPhoto.
    Pure function — no I/O — so it's testable without hitting the network."""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont
    from config.sensors import get_status

    CARD_W, CARD_H, GAP, PAD = 380, 200, 24, 24
    W = PAD * 2 + CARD_W * 2 + GAP
    H = PAD * 2 + CARD_H * 2 + GAP
    BG = "#E4E9E4"
    SURFACE = "#FFFFFF"
    TEXT = "#212121"
    TEXT_MUTED = "#80868B"

    font_name = ImageFont.load_default(size=28)
    font_value = ImageFont.load_default(size=48)
    font_status = ImageFont.load_default(size=24)

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    for i, name in enumerate(("EC", "PH", "Temperature", "Humidity")):
        col, row = i % 2, i // 2
        x0 = PAD + col * (CARD_W + GAP)
        y0 = PAD + row * (CARD_H + GAP)
        x1, y1 = x0 + CARD_W, y0 + CARD_H

        draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=SURFACE)

        val = readings.get(name)
        has_val = isinstance(val, (int, float)) and val == val  # not NaN
        unit = _UNITS.get(name, "")
        tgt = targets.get(name, {})
        if has_val and tgt:
            label, color = get_status(val, tgt["min"], tgt["max"])
        elif has_val:
            label, color = "", TEXT_MUTED
        else:
            label, color = "No data", TEXT_MUTED

        # 8px colored left accent bar = status color, doubles as the
        # "icon" — Flet's ft.Icons.* constants aren't drawable in Pillow,
        # and a shape-per-sensor icon set is unrequested scope.
        draw.rounded_rectangle([x0, y0, x0 + 8, y1], radius=4, fill=color)

        tx = x0 + 32
        draw.text((tx, y0 + 24), name, font=font_name, fill=TEXT)
        value_text = f"{val:.2f} {unit}" if has_val else "—"
        draw.text((tx, y0 + 70), value_text, font=font_value, fill=TEXT)
        if label:
            draw.text((tx, y0 + 145), label, font=font_status, fill=color)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def format_recommendation(result: dict) -> str:
    """Render an llm_agent.recommend() result's summary line. Per-action
    detail is sent as separate, individually-approvable messages
    (format_dose_proposal) instead of an inert bullet list here."""
    lines = [result.get("summary", "")]
    if not result.get("actions"):
        lines.append("All values within target — no dosing needed")
    return "\n".join(line for line in lines if line)


def reply_keyboard() -> dict:
    """Telegram reply_markup: a persistent 2-button keyboard under the text
    field, mirroring chat_widget.py's "Check status" / "Recommend dosing"
    quick-action chips."""
    return {
        "keyboard": [["Check status", "Recommend dosing"]],
        "resize_keyboard": True,
    }


def _get_updates_url(token: str, offset: int | None) -> str:
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=30"
    if offset is not None:
        url += f"&offset={offset}"
    return url


def _send_message_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}/sendMessage"


def _send_photo_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}/sendPhoto"


def _answer_callback_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}/answerCallbackQuery"


def _edit_message_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}/editMessageText"


async def poll_telegram(state, actuator_hub, db, page, refresh_view) -> None:
    """Background task: long-poll Telegram for DMs, answer them with the
    same llm_agent.chat() the in-app chat panel uses, and handle inline
    Approve/Reject taps on proposed changes. Mirrors the shape of
    app.app.poll_sensors — runs forever, one bad iteration must not kill
    the task or the app around it.

    actuator_hub/db are the same instances the in-app chat's action_card
    uses to dose and log — a Telegram approval goes through the identical
    Actuator.dose() cooldown/clamp, no separate safety net.

    No-ops (logs once, returns) if TELEGRAM_BOT_TOKEN isn't set, so dev
    machines without a bot configured are unaffected."""
    from app.services import llm_agent  # local import avoids a hard
    # dependency at module load for code paths that never touch Telegram

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set — Telegram bridge disabled.")
        return

    allowed = parse_allowed_ids(os.environ.get("TELEGRAM_ALLOWED_IDS"))
    history = ChatHistory()
    pending = PendingProposals()
    offset: int | None = None

    async with httpx.AsyncClient(timeout=35) as client:

        async def handle_callback(callback: dict) -> None:
            """Approve/Reject button tap. Re-checks the allowlist on the
            tapper's own id — never assumes the button is safe just
            because it was shown in an allowed chat."""
            sender_id = callback.get("from", {}).get("id")
            cq_id = callback["id"]
            message = callback.get("message") or {}
            chat_id = message.get("chat", {}).get("id")
            message_id = message.get("message_id")

            async def answer(text: str = "") -> None:
                # Required or the button spins forever on the operator's phone.
                await client.post(
                    _answer_callback_url(token),
                    json={"callback_query_id": cq_id, "text": text},
                )

            if not is_allowed(sender_id, allowed):
                logger.info(
                    "Telegram callback from unallowed id=%s ignored.", sender_id
                )
                await answer("Not authorized")
                return

            try:
                action, pid = callback.get("data", "").split(":", 1)
            except ValueError:
                await answer()
                return

            record = pending.pop(pid)
            if record is None:
                await answer("Already handled")
                return

            if action == "reject":
                await client.post(
                    _edit_message_url(token),
                    json={"chat_id": chat_id, "message_id": message_id,
                          "text": "❌ Rejected"},
                )
                await answer("Rejected")
                return

            kind, data = record["kind"], record["data"]
            try:
                if kind == "dose":
                    pump = data.get("pump", "?")
                    amount = float(data.get("amount_ml", 0) or 0)
                    try:
                        dispensed = actuator_hub.dose(pump, amount)
                    except RuntimeError as exc:  # includes CooldownError
                        result_text = f"⚠ {exc}"
                    else:
                        db.log_dose(pump, dispensed, source="llm")
                        result_text = f"✅ Dispensed {dispensed:.1f} ml"
                elif kind == "param":
                    applied = []
                    for name, rng in data.get("targets", {}).items():
                        try:
                            lo, hi = float(rng["min"]), float(rng["max"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        if lo >= hi:  # reject nonsense ranges
                            continue
                        state.targets[name] = {"min": lo, "max": hi}
                        applied.append(name)
                    if applied:
                        state.save()
                        result_text = f"✅ Saved ({', '.join(applied)})"
                    else:
                        result_text = "⚠ No valid ranges to apply"
                elif kind == "growth":
                    count = state.set_stages(data.get("stages", []))
                    if count == 0:
                        result_text = "⚠ No usable stages"
                    else:
                        state.start_planting()
                        state.save()
                        result_text = f"✅ Set {count} stages — planting starts today"
                else:
                    result_text = "⚠ Unknown proposal type"
            except Exception:
                logger.exception("Telegram callback approval failed")
                result_text = "⚠ Unexpected error applying change."

            await client.post(
                _edit_message_url(token),
                json={"chat_id": chat_id, "message_id": message_id,
                      "text": result_text},
            )
            await answer()

        while True:
            try:
                resp = await client.get(_get_updates_url(token, offset))
                data = resp.json()
                if not data.get("ok"):
                    logger.warning("Telegram getUpdates failed: %s", data)
                    await asyncio.sleep(5)
                    continue

                for update in data["result"]:
                    offset = update["update_id"] + 1

                    callback = update.get("callback_query")
                    if callback:
                        await handle_callback(callback)
                        continue

                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                    sender_id = message.get("from", {}).get("id")
                    chat_id = message["chat"]["id"]
                    text = message["text"]

                    if not is_allowed(sender_id, allowed):
                        logger.info(
                            "Telegram message from unallowed id=%s ignored.",
                            sender_id,
                        )
                        continue

                    if text == "/start":
                        # Welcome + menu only — no LLM call, matches the
                        # in-app chat's opening bubble.
                        reply_text = "Hi! Tap a button below or ask me anything."
                    elif text == "Check status":
                        # Instant, local — no LLM call. Sends a PNG card
                        # grid instead of text, easier to scan on a phone.
                        png_bytes = status_image(
                            dict(state.last_readings), state.targets
                        )
                        await client.post(
                            _send_photo_url(token),
                            data={
                                "chat_id": chat_id,
                                "reply_markup": json.dumps(reply_keyboard()),
                            },
                            files={"photo": ("status.png", png_bytes, "image/png")},
                        )
                        continue
                    elif text == "Recommend dosing":
                        try:
                            result = await asyncio.get_event_loop().run_in_executor(
                                None, llm_agent.recommend,
                                dict(state.last_readings), state.targets,
                                state.active_profile, state.tank_capacity_liters(),
                                state.language, state.llm_model,
                            )
                        except llm_agent.LLMError as exc:
                            reply_text = f"⚠ {exc}"
                        except Exception:
                            logger.exception("Telegram recommend() call failed")
                            reply_text = "⚠ Unexpected error handling your message."
                        else:
                            await client.post(
                                _send_message_url(token),
                                json={"chat_id": chat_id,
                                      "text": format_recommendation(result),
                                      "reply_markup": reply_keyboard()},
                            )
                            for action in result.get("actions", []):
                                pid = pending.register("dose", action, chat_id)
                                await client.post(
                                    _send_message_url(token),
                                    json={"chat_id": chat_id,
                                          "text": format_dose_proposal(action),
                                          "reply_markup": approval_keyboard(pid)},
                                )
                            continue
                    else:
                        history.append(chat_id, "user", text)
                        try:
                            result = await asyncio.get_event_loop().run_in_executor(
                                None, llm_agent.chat, history.get(chat_id),
                                dict(state.last_readings), state.targets,
                                state.active_profile, state.tank_capacity_liters(),
                                state.language, state.llm_model,
                                list(state.growth_config()["stages"]),
                            )
                        except llm_agent.LLMError as exc:
                            reply_text = f"⚠ {exc}"
                        except Exception:
                            logger.exception("Telegram chat() call failed")
                            reply_text = "⚠ Unexpected error handling your message."
                        else:
                            history.append(chat_id, "assistant", result["text"])
                            await client.post(
                                _send_message_url(token),
                                json={"chat_id": chat_id, "text": result["text"],
                                      "reply_markup": reply_keyboard()},
                            )
                            for kind, key, fmt in (
                                ("param", "param_proposal", format_param_proposal),
                                ("growth", "growth_proposal", format_growth_proposal),
                            ):
                                proposal = result.get(key)
                                if not proposal:
                                    continue
                                pid = pending.register(kind, proposal, chat_id)
                                await client.post(
                                    _send_message_url(token),
                                    json={"chat_id": chat_id, "text": fmt(proposal),
                                          "reply_markup": approval_keyboard(pid)},
                                )
                            continue

                    await client.post(
                        _send_message_url(token),
                        json={
                            "chat_id": chat_id,
                            "text": reply_text,
                            "reply_markup": reply_keyboard(),
                        },
                    )
            except Exception:
                logger.exception("Telegram poll iteration failed")
                await asyncio.sleep(5)
