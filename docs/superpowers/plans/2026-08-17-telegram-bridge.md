# Telegram Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the operator DM `smart_fert_bot` on Telegram and get the same Claude-backed fertilizer Q&A the in-app chat panel provides, using live sensor/profile state.

**Architecture:** A single new module, `app/services/telegram_bridge.py`, exposes a `poll_telegram(state, page)` async function with the same shape as `app/app.py`'s existing `poll_sensors`/`poll_connectivity` tasks. `app/app.py` starts it via `page.run_task` alongside the others. It long-polls Telegram's `getUpdates`, filters by an ID allowlist, calls the existing `llm_agent.chat()` (identical call shape to `chat_widget.py`), and replies via `sendMessage`. No new process, no new hardware access, no persistence.

**Tech Stack:** `httpx` (already a transitive dependency via `anthropic`/`fastapi` — verified in Task 1), Python stdlib `asyncio`, existing `app.services.llm_agent`, existing `config.profiles.AppState`.

## Global Constraints

- No new pip dependency — use `httpx`, already installed transitively (spec: "Library" decision).
- Bridge is DM-only; group chats unsupported (spec: "Scope").
- Unrecognized sender IDs are dropped silently, no reply sent, logged at INFO only (spec: "Access").
- If `param_proposal` or `growth_proposal` comes back from `llm_agent.chat()`, append a fixed pointer-back-to-app string to the reply text — never apply the proposal (spec: "Scope" — approval stays in-app for v1).
- If `TELEGRAM_BOT_TOKEN` is unset/empty, the bridge task must log once and return immediately — rest of the app must be unaffected (spec: "Configuration").
- Runs inside `main.py`'s existing asyncio loop via `page.run_task`, not a separate process (spec: "Process").
- Per-chat history is in-memory only, capped length, resets on restart (spec: "Memory").
- `TELEGRAM_ALLOWED_IDS` is a comma-separated list of ints in `.env` (already set by the user — confirmed via smoke test, id `8901185566` replied to successfully).

---

## File Structure

- **Create:** `app/services/telegram_bridge.py` — all Telegram HTTP calls (`getUpdates`, `sendMessage`), allowlist filtering, per-chat history, and the `poll_telegram` task loop. One file, one responsibility: adapt the existing `llm_agent.chat()` to Telegram's transport.
- **Modify:** `app/app.py` — construct and start the bridge task next to `poll_sensors`/`poll_connectivity`/`poll_clock`.
- **Test:** `tests/test_telegram_bridge.py` — pure-function unit tests (allowlist filter, reply-text formatting, history capping) with the two HTTP calls mocked. No real network calls, matching how `tests/test_llm_agent.py` avoids hitting the Anthropic API.

---

### Task 1: Allowlist parsing + filter function

**Files:**
- Create: `app/services/telegram_bridge.py`
- Test: `tests/test_telegram_bridge.py`

**Interfaces:**
- Consumes: nothing (pure stdlib + env var).
- Produces: `parse_allowed_ids(raw: str) -> set[int]`, `is_allowed(sender_id: int, allowed: set[int]) -> bool` — used by Task 4's poll loop.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_telegram_bridge.py`:

```python
"""Telegram bridge unit tests — no real network calls."""
import unittest

from app.services import telegram_bridge


class TestParseAllowedIds(unittest.TestCase):
    def test_single_id(self):
        self.assertEqual(telegram_bridge.parse_allowed_ids("123"), {123})

    def test_multiple_ids(self):
        self.assertEqual(
            telegram_bridge.parse_allowed_ids("123,456, 789"), {123, 456, 789}
        )

    def test_empty_string(self):
        self.assertEqual(telegram_bridge.parse_allowed_ids(""), set())

    def test_none_treated_as_empty(self):
        self.assertEqual(telegram_bridge.parse_allowed_ids(None), set())


class TestIsAllowed(unittest.TestCase):
    def test_id_in_set(self):
        self.assertTrue(telegram_bridge.is_allowed(123, {123, 456}))

    def test_id_not_in_set(self):
        self.assertFalse(telegram_bridge.is_allowed(999, {123, 456}))

    def test_empty_allowlist_denies_everyone(self):
        # An unset TELEGRAM_ALLOWED_IDS must fail closed, not open.
        self.assertFalse(telegram_bridge.is_allowed(123, set()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.telegram_bridge'`

- [ ] **Step 3: Write minimal implementation**

Create `app/services/telegram_bridge.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/telegram_bridge.py tests/test_telegram_bridge.py
git commit -m "feat: Telegram bridge allowlist parsing"
```

---

### Task 2: Reply-text formatting (proposal pointer-back)

**Files:**
- Modify: `app/services/telegram_bridge.py`
- Test: `tests/test_telegram_bridge.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `format_reply(result: dict) -> str` — used by Task 4's poll loop. `result` has the same shape `llm_agent.chat()` returns: `{"text": str, "param_proposal": dict | None, "growth_proposal": dict | None, "usage": dict}`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_telegram_bridge.py` (new class, keep existing ones):

```python
class TestFormatReply(unittest.TestCase):
    def test_plain_text_passthrough(self):
        result = {"text": "EC looks fine.", "param_proposal": None, "growth_proposal": None}
        self.assertEqual(telegram_bridge.format_reply(result), "EC looks fine.")

    def test_param_proposal_appends_pointer(self):
        result = {
            "text": "I'd suggest tightening the EC range.",
            "param_proposal": {"crop": "lettuce"},
            "growth_proposal": None,
        }
        out = telegram_bridge.format_reply(result)
        self.assertIn("I'd suggest tightening the EC range.", out)
        self.assertIn("open the app", out.lower())

    def test_growth_proposal_appends_pointer(self):
        result = {
            "text": "Here's a 4-stage plan.",
            "param_proposal": None,
            "growth_proposal": {"crop": "lettuce", "stages": []},
        }
        out = telegram_bridge.format_reply(result)
        self.assertIn("Here's a 4-stage plan.", out)
        self.assertIn("open the app", out.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'format_reply'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/services/telegram_bridge.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/telegram_bridge.py tests/test_telegram_bridge.py
git commit -m "feat: Telegram bridge reply formatting for proposals"
```

---

### Task 3: Per-chat history store with capped length

**Files:**
- Modify: `app/services/telegram_bridge.py`
- Test: `tests/test_telegram_bridge.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ChatHistory` class with `.append(chat_id: int, role: str, content) -> None` and `.get(chat_id: int) -> list[dict]` — used by Task 4's poll loop. `content` matches what `llm_agent.chat()`'s `history` param expects: a plain string or the content-blocks shape from `llm_agent.build_user_content()`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_telegram_bridge.py`:

```python
class TestChatHistory(unittest.TestCase):
    def test_get_unknown_chat_is_empty(self):
        history = telegram_bridge.ChatHistory(max_messages=10)
        self.assertEqual(history.get(999), [])

    def test_append_and_get(self):
        history = telegram_bridge.ChatHistory(max_messages=10)
        history.append(1, "user", "hi")
        history.append(1, "assistant", "hello")
        self.assertEqual(
            history.get(1),
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        )

    def test_chats_are_isolated(self):
        history = telegram_bridge.ChatHistory(max_messages=10)
        history.append(1, "user", "chat one")
        history.append(2, "user", "chat two")
        self.assertEqual(history.get(1), [{"role": "user", "content": "chat one"}])
        self.assertEqual(history.get(2), [{"role": "user", "content": "chat two"}])

    def test_caps_at_max_messages(self):
        history = telegram_bridge.ChatHistory(max_messages=4)
        for i in range(6):
            history.append(1, "user", f"msg{i}")
        # Oldest messages drop first; only the most recent 4 remain.
        self.assertEqual(
            [m["content"] for m in history.get(1)], ["msg2", "msg3", "msg4", "msg5"]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'ChatHistory'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/services/telegram_bridge.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/telegram_bridge.py tests/test_telegram_bridge.py
git commit -m "feat: Telegram bridge per-chat history with cap"
```

---

### Task 4: Telegram HTTP calls + poll loop wiring

**Files:**
- Modify: `app/services/telegram_bridge.py`
- Modify: `app/app.py`
- Test: `tests/test_telegram_bridge.py`

**Interfaces:**
- Consumes:
  - `parse_allowed_ids`, `is_allowed` (Task 1)
  - `format_reply` (Task 2)
  - `ChatHistory` (Task 3)
  - `app.services.llm_agent.chat(history, readings, targets, profile_name, volume_liters, lang, model, stages) -> dict` (existing, unchanged — exact signature verified against `app/components/chat_widget.py`'s `send_typed`)
  - `config.profiles.AppState` fields used: `state.last_readings`, `state.targets`, `state.active_profile`, `state.tank_capacity_liters()`, `state.language`, `state.llm_model`, `state.growth_config()["stages"]`
- Produces: `async def poll_telegram(state) -> None` — the task `app/app.py` starts via `page.run_task(poll_telegram, state)`. Runs forever (like `poll_sensors`); returns immediately (without looping) if `TELEGRAM_BOT_TOKEN` is unset.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_telegram_bridge.py`. These test the two request-building helpers in isolation (no real network — `httpx` calls themselves are exercised manually in Task 5's smoke test, matching how the rest of the codebase treats hardware/network I/O per the spec's Testing section):

```python
class TestBuildRequests(unittest.TestCase):
    def test_get_updates_url(self):
        url = telegram_bridge._get_updates_url("TOKEN123", offset=42)
        self.assertEqual(
            url,
            "https://api.telegram.org/botTOKEN123/getUpdates"
            "?timeout=30&offset=42",
        )

    def test_get_updates_url_no_offset(self):
        url = telegram_bridge._get_updates_url("TOKEN123", offset=None)
        self.assertEqual(
            url, "https://api.telegram.org/botTOKEN123/getUpdates?timeout=30"
        )

    def test_send_message_url(self):
        url = telegram_bridge._send_message_url("TOKEN123")
        self.assertEqual(
            url, "https://api.telegram.org/botTOKEN123/sendMessage"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_get_updates_url'`

- [ ] **Step 3: Write minimal implementation**

Append to `app/services/telegram_bridge.py` (add `import asyncio`, `import httpx` at the top of the file alongside the existing imports):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_telegram_bridge.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Wire the task into `app/app.py`**

In `app/app.py`, find the block:

```python
    page.run_task(poll_sensors)
    page.run_task(poll_connectivity)
    page.run_task(poll_clock)
```

Replace with:

```python
    page.run_task(poll_sensors)
    page.run_task(poll_connectivity)
    page.run_task(poll_clock)
    page.run_task(telegram_bridge.poll_telegram, state)
```

And add the import near the other `app.services` imports at the top of `app/app.py`:

```python
from app.services import telegram_bridge
```

- [ ] **Step 6: Confirm the app still starts cleanly**

Run: `python main.py` (let it run ~10s, then close the window)
Expected: same log lines as before (`SimulatedSensor[...]: ready`, `Database ready...`) plus either:
- `Telegram bridge disabled` (if `TELEGRAM_BOT_TOKEN` unset in this shell), or
- no new errors/tracebacks (if it is set — the poll loop starts silently)

No exceptions, no crash.

- [ ] **Step 7: Commit**

```bash
git add app/services/telegram_bridge.py app/app.py tests/test_telegram_bridge.py
git commit -m "feat: wire Telegram bridge poll loop into main.py"
```

---

### Task 5: Manual end-to-end smoke test

**Files:** none (verification only — no code changes)

**Interfaces:** none.

- [ ] **Step 1: Confirm `.env` has both variables set**

Run: `python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(bool(os.environ.get('TELEGRAM_BOT_TOKEN'))); print(bool(os.environ.get('TELEGRAM_ALLOWED_IDS')))"`
Expected: `True` then `True` (already confirmed set earlier in this session).

- [ ] **Step 2: Run the app**

Run: `python main.py`
Expected: normal startup log lines, app window opens, no tracebacks.

- [ ] **Step 3: Send the bot a DM in Telegram**

In the Telegram app, open the chat with `smart_fert_bot`, send: `what's the current EC reading?`

Expected: within a few seconds, the bot replies in Telegram with a real answer referencing the live simulated EC value (matching what the Dashboard/app shows at that moment).

- [ ] **Step 4: Send a follow-up to confirm multi-turn memory**

Send: `and the pH?`

Expected: bot answers about pH specifically, without you having to restate "current pH reading" — confirms `ChatHistory` is carrying context.

- [ ] **Step 5: Confirm the allowlist actually blocks (optional but recommended)**

Temporarily set `TELEGRAM_ALLOWED_IDS` in `.env` to a bogus id (e.g. `TELEGRAM_ALLOWED_IDS=1`), restart `python main.py`, send the bot another DM from your real account.

Expected: no reply arrives in Telegram; app log shows `Telegram message from unallowed id=<your real id> ignored.`

Restore `TELEGRAM_ALLOWED_IDS` to your real id afterward and restart.

- [ ] **Step 6: Close the app**

No commit for this task — it's verification of Task 4's work, not new code.

---

## Self-Review

**Spec coverage:**
- DM-only Q&A ✓ (Task 4 — no group handling, no approval logic)
- Multi-turn memory, in-process only ✓ (Task 3)
- Allowlist by numeric ID, silent drop ✓ (Task 1, Task 4 step 3's `is_allowed` check)
- No new dependency (httpx already transitive) ✓ (Global Constraints; verified via existing `anthropic`/`fastapi` deps, not re-verified here since `httpx` import will simply fail loudly at Task 4 if somehow absent — acceptable, existing test suite would catch it via CI)
- Reuses `llm_agent.chat()` unchanged, same call shape as `chat_widget.py` ✓ (Task 4)
- Proposal pointer-back, never auto-applies ✓ (Task 2)
- `TELEGRAM_BOT_TOKEN` unset → no-op, rest of app unaffected ✓ (Task 4, poll_telegram's early return)
- Runs in main.py's asyncio loop via `page.run_task` ✓ (Task 4 step 5)
- Error handling: LLMError, generic exception, network failure all caught, loop never dies ✓ (Task 4 implementation)

**Placeholder scan:** none found — every step has real code or exact commands with expected output.

**Type consistency:** `poll_telegram(state)` takes `AppState` (matches `app/app.py`'s existing `state` variable); `llm_agent.chat(...)` call args match the exact positional order used in `chat_widget.py:509-514` (verified against that file during design). `ChatHistory.get()` returns `list[dict]` with `{"role", "content"}` keys — matches what `llm_agent.chat()`'s `history` parameter expects (per its docstring).
