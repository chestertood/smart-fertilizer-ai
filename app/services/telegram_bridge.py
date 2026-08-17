"""Telegram DM bridge — lets the operator ask the same Claude-backed
fertilizer assistant the in-app chat panel provides, from Telegram.

v1 scope (see docs/superpowers/specs/2026-08-17-telegram-bridge-design.md):
DM only, Q&A only. No remote approval of proposals, no proactive alerts,
no persistence across restarts.
"""
import asyncio
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


def _get_updates_url(token: str, offset: int | None) -> str:
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=30"
    if offset is not None:
        url += f"&offset={offset}"
    return url


def _send_message_url(token: str) -> str:
    return f"https://api.telegram.org/bot{token}/sendMessage"


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
                        json={"chat_id": chat_id, "text": reply_text},
                    )
            except Exception:
                logger.exception("Telegram poll iteration failed")
                await asyncio.sleep(5)
