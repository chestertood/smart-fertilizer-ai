"""Telegram DM bridge — lets the operator ask the same Claude-backed
fertilizer assistant the in-app chat panel provides, from Telegram.

v1 scope (see docs/superpowers/specs/2026-08-17-telegram-bridge-design.md):
DM only, Q&A only. No remote approval of proposals, no proactive alerts,
no persistence across restarts.
"""
import logging
import os

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
