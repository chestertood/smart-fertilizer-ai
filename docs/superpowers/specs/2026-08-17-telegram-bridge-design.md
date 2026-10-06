# Telegram Bridge — Design (v1: Q&A only)

## Purpose

Let the operator ask the same Claude-backed fertilizer assistant that lives
in the in-app chat panel (`app/components/chat_widget.py`) from Telegram
instead of standing in front of the kiosk screen. v1 is DM-only,
read/reply — no remote approval of dosing or parameter changes, no
proactive alerts.

## Scope (v1)

In scope:
- One-on-one Telegram DM with a single bot (`@smart_fert_bot`).
- Free-form Q&A against live sensor readings, target ranges, active crop
  profile, and reservoir volume — same context the in-app chat already
  builds.
- Multi-turn memory per chat, in-process only (resets on app restart).
- Allowlist by numeric Telegram user ID — unrecognized senders are
  silently ignored.

**Superseded 2026-08-18:** the "approving proposals from Telegram" item
below was reversed — proposals are now approvable inline from Telegram
(`PendingProposals`, inline Approve/Reject buttons). See
`[[telegram-approval-plan-pending]]` for the reversal design; original
v1 text kept as the historical record of the decision it replaced.

Out of scope (deferred, not designed here):
- ~~Approving parameter/growth/dosing proposals from Telegram. If Claude
  proposes a change, the reply says so and points the operator back to the
  app.~~ Reversed — see note above.
- Group chats. Bot works in DM only; inviting it to a group is unsupported
  for v1 (privacy-mode + "who can see replies" concerns deferred).
- Proactive/background alerts (e.g. EC out of range) pushed without being
  asked.
- Persisting chat history across app restarts.

## Architecture

Runs as a background `asyncio` task inside the existing `main.py` process
(via `page.run_task`, same mechanism as `poll_sensors` in `app/app.py`) —
not a separate process. This avoids two processes both touching the same
I2C/GPIO sensor and pump hardware.

New module: `app/services/telegram_bridge.py`.

```
long-poll GET https://api.telegram.org/bot<token>/getUpdates
  (httpx.AsyncClient, timeout=30 — long-poll, not a tight loop)
    → for each update:
        sender_id not in TELEGRAM_ALLOWED_IDS?
          → log at INFO, drop the update, no reply sent
        else:
          → append to that chat_id's in-memory history (list, capped length)
          → call llm_agent.chat(history, state.last_readings, state.targets,
                state.active_profile, state.tank_capacity_liters(),
                state.language, state.llm_model,
                state.growth_config()["stages"])
            (identical call shape to chat_widget.py's send_typed — no new
            LLM logic, this module only adapts transport)
          → reply_text = result["text"]
          → if result["param_proposal"] or result["growth_proposal"]:
                append "\n\n(Proposed change — open the app to review and
                approve.)"
          → POST https://api.telegram.org/bot<token>/sendMessage
        → advance the update offset so getUpdates doesn't redeliver it
```

`httpx` is already a transitive dependency (pulled in by `anthropic` /
`fastapi`) — no new package needed.

## Configuration

`.env` (git-ignored, same file as `ANTHROPIC_API_KEY`):

- `TELEGRAM_BOT_TOKEN` — from BotFather.
- `TELEGRAM_ALLOWED_IDS` — comma-separated numeric Telegram user IDs
  permitted to use the bot.

If `TELEGRAM_BOT_TOKEN` is unset, the bridge task logs once and exits
immediately — the rest of the app runs unaffected. No hard dependency on
Telegram being configured.

## Error handling

- Unrecognized sender → ignored silently (no reply), logged at INFO. A
  stranger who finds the bot's username gets no confirmation it's even
  responsive to anyone.
- `llm_agent.LLMError` / any exception from the `chat()` call → reply with
  `⚠ ...`, same pattern the in-app chat already uses. Never let an LLM
  failure kill the poll loop.
- `getUpdates` network failure → log, short backoff, retry. Must not crash
  the poll task (and by extension must not crash the Flet app, since it
  shares the event loop).

## Data flow / state reuse

No new state store. Reuses:
- `state.last_readings` (already populated by `poll_sensors` in `app.py`)
- `state.targets`, `state.active_profile`, `state.tank_capacity_liters()`,
  `state.growth_config()["stages"]`, `state.language`, `state.llm_model`

Telegram-side state is scoped to `telegram_bridge.py` alone: an in-memory
`dict[chat_id, list[message]]` for per-chat history, and the `getUpdates`
offset. Neither persists across restarts (acceptable for v1 — see Scope).

## Testing

- Unit-testable: the allowlist filter (id in/out of `TELEGRAM_ALLOWED_IDS`)
  and the reply-formatting logic (plain text vs. proposal-appended text)
  are pure functions, testable without hitting the network.
- The `getUpdates`/`sendMessage` HTTP calls themselves are integration-level
  — verified by manual smoke test (send a real DM, confirm a reply lands)
  rather than mocked unit tests, consistent with how the rest of this
  codebase treats hardware/network I/O.
