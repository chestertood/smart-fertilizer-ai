"""Telegram DM bridge — lets the operator ask the same Claude-backed
fertilizer assistant the in-app chat panel provides, from Telegram.

v1 scope (see docs/superpowers/specs/2026-08-17-telegram-bridge-design.md):
DM only, Q&A only. No remote approval of proposals, no proactive alerts,
no persistence across restarts.
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


_PROPOSAL_NOTE = "\n\n(Proposed change — open the app to review and approve.)"


def format_reply(result: dict) -> str:
    """Turn an llm_agent.chat() result into the text sent back over
    Telegram. If Claude proposed a parameter or growth change, the
    proposal itself is never applied here (v1 is Q&A-only) — just point
    the operator back to the app to approve it."""
    text = result["text"]
    if result.get("param_proposal") or result.get("growth_proposal"):
        text += _PROPOSAL_NOTE
    return text


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


_UNITS = {"EC": "mS/cm", "PH": "pH", "Temperature": "°C", "Humidity": "%"}


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
    """Render an llm_agent.recommend() result as plain text. Telegram v1 has
    no approve/reject UI (spec: approval stays in-app), so a proposed dose
    is listed as text with a pointer back to the app — never applied here."""
    lines = [result.get("summary", "")]
    actions = result.get("actions", [])
    if not actions:
        lines.append("All values within target — no dosing needed")
    else:
        for a in actions:
            lines.append(f"• {a['pump']}: {a['amount_ml']} ml — {a['reason']}")
        lines.append(_PROPOSAL_NOTE.strip())
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


async def poll_telegram(state) -> None:
    """Background task: long-poll Telegram for DMs, answer them with the
    same llm_agent.chat() the in-app chat panel uses. Mirrors the shape of
    app.app.poll_sensors — runs forever, one bad iteration must not kill
    the task or the app around it.

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
    offset: int | None = None

    async with httpx.AsyncClient(timeout=35) as client:
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
                            reply_text = format_recommendation(result)
                        except llm_agent.LLMError as exc:
                            reply_text = f"⚠ {exc}"
                        except Exception:
                            logger.exception("Telegram recommend() call failed")
                            reply_text = "⚠ Unexpected error handling your message."
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
                            reply_text = format_reply(result)
                        except llm_agent.LLMError as exc:
                            reply_text = f"⚠ {exc}"
                        except Exception:
                            logger.exception("Telegram chat() call failed")
                            reply_text = "⚠ Unexpected error handling your message."
                        else:
                            history.append(chat_id, "assistant", result["text"])

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
