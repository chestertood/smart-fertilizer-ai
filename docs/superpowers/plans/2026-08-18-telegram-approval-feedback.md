# Telegram Approval Feedback (Loading + Refresh) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an operator taps ✅ Approve on a Telegram proposal, show a
"working" state and then a result on both Telegram and the running kiosk
app, and refresh whatever view is currently on screen so changed values
appear without manual navigation.

**Architecture:** `poll_telegram()` gains `page` and `refresh_view` params
passed in from `app.py`. Its `handle_callback` closure edits the Telegram
message twice (loading, then result — unchanged path already does the
second edit) and fires a matching in-app `SnackBar` toast via
`page.overlay`, then calls `refresh_view()` to rebuild the current view.
`app.py` extracts its existing rebuild-current-view lines out of
`refresh_language()` into a reusable `refresh_current_view()` closure.

**Tech Stack:** Python, Flet (`ft.SnackBar`, `page.overlay`), httpx
(Telegram Bot API), existing `app/theme.py` color constants.

## Global Constraints

- Only the **approve** path gets loading/toast/refresh — reject makes no
  state change, so it stays as-is (spec: "Out of scope: Reject taps").
- Always rebuild the *current* view, no per-proposal-type view mapping
  (spec: "Approaches considered", #1 chosen).
- No new automated tests — this wiring is I/O/Flet-page-driven, same
  category as the rest of `handle_callback`, verified manually (spec:
  "Testing").
- Toast colors: `theme.TEXT_MUTED` for the applying state,
  `theme.SUCCESS` for a result that doesn't start with `⚠`,
  `theme.DANGER` for one that does.

---

### Task 1: Extract `refresh_current_view()` in app.py and wire it into `poll_telegram`

**Files:**
- Modify: `app/app.py:134-146` (`refresh_language()`), `app/app.py:310`
  (the `poll_telegram` call site)
- Modify: `app/services/telegram_bridge.py:188` (`poll_telegram` signature)
  and `app/services/telegram_bridge.py:1-7` (module docstring — no change
  needed, already updated) — this task only widens the signature so the
  app doesn't crash on the new call; Task 2 fills in the behavior.

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `refresh_current_view() -> None` in `app.py`'s `main()` scope
  (closes over `body`, `views`, `current_view_name`, `page` — all already
  defined above it). `poll_telegram(state, actuator_hub, db, page,
  refresh_view) -> None` — the two new trailing params, both required
  (matches the existing style: `state`/`actuator_hub`/`db` are already
  required, not optional).

- [ ] **Step 1: Read the current `refresh_language()` to confirm line numbers**

Run: read `app/app.py` lines 134-146. It currently reads:

```python
    def refresh_language() -> None:
        """Re-render the nav rail labels, the app-bar flag, and the currently
        visible view after a language switch (from the flag shortcut or the
        Settings dropdown), so it takes effect without an app restart."""
        set_nav_language(rail, state.language)
        rail.update()
        exit_button.tooltip = t("nav.exit", state.language)
        if KIOSK:
            exit_button.update()
        if flag_setter[0] is not None:
            flag_setter[0](state.language)
        body.controls = [views[current_view_name[0]]()]
        page.update()
```

If the lines have drifted, locate `def refresh_language()` by name instead
of by line number before editing.

- [ ] **Step 2: Extract `refresh_current_view()` and call it from `refresh_language()`**

Replace the block above with:

```python
    def refresh_current_view() -> None:
        """Rebuild whichever view is currently on screen from live state —
        used after a language switch and after a Telegram approval applies
        a change, so the operator never has to navigate away and back to
        see it."""
        body.controls = [views[current_view_name[0]]()]
        page.update()

    def refresh_language() -> None:
        """Re-render the nav rail labels, the app-bar flag, and the currently
        visible view after a language switch (from the flag shortcut or the
        Settings dropdown), so it takes effect without an app restart."""
        set_nav_language(rail, state.language)
        rail.update()
        exit_button.tooltip = t("nav.exit", state.language)
        if KIOSK:
            exit_button.update()
        if flag_setter[0] is not None:
            flag_setter[0](state.language)
        refresh_current_view()
```

- [ ] **Step 3: Widen `poll_telegram`'s signature (behavior comes in Task 2)**

In `app/services/telegram_bridge.py`, change:

```python
async def poll_telegram(state, actuator_hub, db) -> None:
```

to:

```python
async def poll_telegram(state, actuator_hub, db, page, refresh_view) -> None:
```

Leave the docstring and body untouched in this step — Task 2 uses `page`
and `refresh_view`. This step alone makes them unused-but-accepted
parameters, which is fine as an intermediate state within this plan (Task
2 lands in the same PR/session).

- [ ] **Step 4: Update the call site in `app/app.py`**

Change:

```python
    page.run_task(telegram_bridge.poll_telegram, state, actuator_hub, db)
```

to:

```python
    page.run_task(
        telegram_bridge.poll_telegram, state, actuator_hub, db,
        page, refresh_current_view,
    )
```

This line is currently after `refresh_current_view` is defined (it's
defined inside `main()` earlier, alongside `refresh_language()`, well
before `page.run_task(...)` near the end of `main()`) — confirm by reading
`app/app.py` around the `page.run_task(poll_sensors)` /
`page.run_task(poll_connectivity)` block before editing; `refresh_current_view`
must already be in scope at that point.

- [ ] **Step 5: Syntax-check both files**

Run:
```bash
python -c "import ast; ast.parse(open('app/app.py', encoding='utf-8').read())"
python -c "import ast; ast.parse(open('app/services/telegram_bridge.py', encoding='utf-8').read())"
```
Expected: no output, exit code 0 (both parse cleanly).

- [ ] **Step 6: Run the existing Telegram bridge unit tests (regression)**

Run: `python -m unittest tests.test_telegram_bridge -v`
Expected: all tests still PASS (this task doesn't change any tested
function — `poll_telegram` itself has no unit tests, per the plan's Global
Constraints).

- [ ] **Step 7: Commit**

```bash
git add app/app.py app/services/telegram_bridge.py
git commit -m "refactor: extract refresh_current_view, widen poll_telegram signature"
```

---

### Task 2: Loading edit, in-app toast, and refresh on approve

**Files:**
- Modify: `app/services/telegram_bridge.py` — add `from app import theme`
  import, add `_toast()`, edit `handle_callback`'s approve path.

**Interfaces:**
- Consumes: `page` and `refresh_view` params added to `poll_telegram` in
  Task 1 (available inside `handle_callback`, which is defined as a nested
  closure inside `poll_telegram` and already closes over `client`, `token`,
  `allowed`, `pending`, `state`, `actuator_hub`, `db`).
- Produces: `_toast(page, msg: str, color: str) -> None` (module-level
  function, no other task depends on it).

- [ ] **Step 1: Add the `theme` import**

At the top of `app/services/telegram_bridge.py`, alongside the existing
imports:

```python
import httpx

from app import theme
```

- [ ] **Step 2: Add `_toast()` — a module-level function, placed after `approval_keyboard()`**

```python
def _toast(page, msg: str, color: str) -> None:
    """In-app feedback for a Telegram-triggered change. Mirrors
    app/views/parameters.py's _show_snack — this Flet build has no
    page.open()/show_snack_bar(), so the SnackBar is driven via
    page.overlay directly."""
    sb = ft.SnackBar(content=ft.Text(msg), bgcolor=color)
    page.overlay.append(sb)
    sb.open = True
    page.update()
```

This needs `import flet as ft` at module level — check first with:
```bash
grep -n "^import flet" app/services/telegram_bridge.py
```
If it's missing, add `import flet as ft` next to the `from app import theme`
import added in Step 1.

- [ ] **Step 3: Read the current `handle_callback` approve path to confirm exact text**

Run: read `app/services/telegram_bridge.py`, locate the `async def
handle_callback` closure inside `poll_telegram`. Confirm the section
between `record = pending.pop(pid)` and the final
`await client.post(_edit_message_url(token), ...)` / `await answer()`
still matches this shape (it was written in the prior session's build):

```python
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
                    ...
                elif kind == "param":
                    ...
                elif kind == "growth":
                    ...
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
```

If it has drifted, adapt the insertion points below to the actual text —
the anchors are "right after the reject branch returns" (insert loading
step) and "right after the final `editMessageText` call" (insert toast +
refresh), not exact line numbers.

- [ ] **Step 4: Insert the loading edit + toast right after the reject branch, before the apply-by-kind logic**

Insert this block immediately after the `if action == "reject": ... return`
block and before `kind, data = record["kind"], record["data"]`:

```python
            # Approve path only (reject makes no state change, handled
            # above). Give immediate feedback on both ends before the
            # apply logic runs, so a tap never looks like nothing happened.
            await client.post(
                _edit_message_url(token),
                json={"chat_id": chat_id, "message_id": message_id,
                      "text": "⏳ Applying…"},
            )
            _toast(page, "Telegram: applying…", theme.TEXT_MUTED)

            kind, data = record["kind"], record["data"]
```

(This replaces the old bare `kind, data = record["kind"], record["data"]`
line — don't duplicate it.)

- [ ] **Step 5: Insert the result toast + view refresh right after the final `editMessageText`, before `await answer()`**

Change:

```python
            await client.post(
                _edit_message_url(token),
                json={"chat_id": chat_id, "message_id": message_id,
                      "text": result_text},
            )
            await answer()
```

to:

```python
            await client.post(
                _edit_message_url(token),
                json={"chat_id": chat_id, "message_id": message_id,
                      "text": result_text},
            )
            _toast(
                page, f"Telegram: {result_text}",
                theme.DANGER if result_text.startswith("⚠") else theme.SUCCESS,
            )
            refresh_view()
            await answer()
```

- [ ] **Step 6: Syntax-check**

Run:
```bash
python -c "import ast; ast.parse(open('app/services/telegram_bridge.py', encoding='utf-8').read())"
```
Expected: no output, exit code 0.

- [ ] **Step 7: Run the existing Telegram bridge unit tests (regression)**

Run: `python -m unittest tests.test_telegram_bridge -v`
Expected: all tests still PASS — none of them exercise `handle_callback`,
so this is a regression check on the pure-function tests, not new
coverage.

- [ ] **Step 8: Commit**

```bash
git add app/services/telegram_bridge.py
git commit -m "feat: Telegram approval loading state, toast, and live view refresh"
```

- [ ] **Step 9: Manual verification (do this yourself — not automatable)**

1. `python main.py`, open the kiosk app to the **Parameters** view.
2. From Telegram, send a message that yields a param proposal, e.g. "set
   me up for lettuce", and tap ✅ Approve on the proposal message that
   appears.
3. Confirm the Telegram message shows `⏳ Applying…` briefly, then
   `✅ Saved (...)`.
4. Confirm a green toast appears in the kiosk app with the same text.
5. Confirm the Parameters view on screen shows the new target ranges
   without you touching it.
6. Repeat with `Recommend dosing` → Approve one action, kiosk app on
   **Dashboard** — same toast/edit sequence, dashboard/history reflect the
   dose.
7. Tap ❌ Reject on a proposal — confirm no `⏳ Applying…` edit, no toast,
   no view rebuild; only the existing `❌ Rejected` edit happens.
