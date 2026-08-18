# Telegram approval feedback — loading + refresh — Design

## Context

The Telegram approval flow (`[[telegram-approval-plan-pending]]`, built
2026-08-18) lets the operator tap ✅ Approve on a dosing/parameter/growth
proposal from Telegram, and it applies for real (`Actuator.dose()`,
`state.targets[...] = ...`, `state.set_stages(...)`). Two gaps observed in
manual testing:

1. **No feedback that a tap is being processed** — the Telegram message
   sits unchanged until the apply finishes, and there's nothing in the
   running kiosk app to show a Telegram-triggered change is happening.
2. **No live refresh** — if the operator has the Parameters (or Dashboard,
   or Settings) view open on the kiosk screen when a Telegram approval
   lands, that view keeps showing stale values until they manually
   navigate away and back, because Flet views here are built once on
   `navigate()` and don't re-render on background state changes.

This adds a "loading → result" feedback step on both sides (Telegram
message edit + in-app toast) and a live rebuild of whatever view is
currently on screen after an approve.

## Scope

In scope:
- Telegram message shows `⏳ Applying…` immediately after an approve tap,
  before the existing final-result edit.
- In-app SnackBar toast mirrors the same two states (applying → result),
  colored by outcome.
- Whatever view is currently displayed in the kiosk app rebuilds itself
  after an approve, so changed values (targets, growth stages, dose
  history) show without the operator navigating away and back.

Out of scope:
- Reject taps — no state changes, so no loading/toast/refresh needed.
- Per-proposal-type targeted refresh (e.g. skip refresh if operator is on
  History during a param approval) — always rebuilding the current view is
  simpler and cheap; see Approaches below.
- Any change to the dosing/param/growth apply logic itself (unchanged from
  the existing `handle_callback`).

## Approaches considered

1. **Always rebuild the current view (chosen).** Reuses the exact
   rebuild-and-`page.update()` pattern `refresh_language()` already uses
   after a language switch. One code path, no type→view mapping to keep in
   sync as views/proposal kinds evolve.
2. Targeted per-proposal-type refresh (only rebuild views known to show
   that data). More precise, but adds a maintenance burden (a mapping that
   silently goes stale when a new view starts showing dose/target/growth
   data) for a rebuild that's already cheap. Rejected — YAGNI.

## Design

**`app/app.py`**
- Extract the rebuild lines currently inline in `refresh_language()`
  (`body.controls = [views[current_view_name[0]]()]; page.update()`) into
  a small `refresh_current_view() -> None` closure, defined alongside
  `refresh_language()` (same scope, same free variables: `body`, `views`,
  `current_view_name`, `page`). `refresh_language()` calls it instead of
  repeating the lines.
- `page.run_task(telegram_bridge.poll_telegram, state, actuator_hub, db)`
  → `page.run_task(telegram_bridge.poll_telegram, state, actuator_hub, db,
  page, refresh_current_view)`.

**`app/services/telegram_bridge.py`**
- `poll_telegram(state, actuator_hub, db, page, refresh_view)` — two new
  params. `poll_telegram` already runs as a `page.run_task` coroutine, the
  same execution context `poll_sensors` calls bare `page.update()` from —
  calling `page.overlay.append(...)` / `page.update()` directly from
  `handle_callback` (itself a closure inside `poll_telegram`) is the same
  pattern, not a new threading concern.
- New `_toast(page, msg: str, color: str) -> None` — mirrors
  `app/views/parameters.py`'s existing `_show_snack`: builds an
  `ft.SnackBar(content=ft.Text(msg), bgcolor=color)`, appends to
  `page.overlay`, sets `.open = True`, calls `page.update()`.
- In `handle_callback`, only on the **approve** path (after
  `pending.pop(pid)` succeeds, before the existing kind-dispatch apply
  logic):
  1. `await client.post(_edit_message_url(token), json={..., "text": "⏳ Applying…"})`
  2. `_toast(page, "Telegram: applying…", theme.TEXT_MUTED)`
  3. existing apply-by-kind logic (unchanged) → produces `result_text`
  4. existing final `editMessageText` with `result_text` (unchanged)
  5. `_toast(page, f"Telegram: {result_text}", theme.DANGER if result_text.startswith("⚠") else theme.SUCCESS)`
  6. `refresh_view()`
- Reject path unchanged — no loading edit, no toast, no refresh.
- New import: `from app import theme` (module-level, alongside the
  existing `httpx`/`json`/`os` imports — no local-import guard needed,
  `theme.py` has no hardware/optional dependencies).

## Testing

The new behavior is I/O- and Flet-page-driven (Telegram HTTP calls,
`page.overlay`/`page.update()`), same category as the rest of
`handle_callback` and `poll_telegram` — already outside the pure-function
unit tests in `tests/test_telegram_bridge.py` and verified manually
instead. No new automated tests; manual verification steps below.

## Verification

1. `python -m unittest tests.test_telegram_bridge -v` — still all pass
   (no existing test touches `poll_telegram`/`handle_callback` directly).
2. `python main.py`, open the kiosk app to the Parameters view, then from
   Telegram send a message that yields a param proposal (e.g. "set me up
   for lettuce") and tap Approve:
   - Telegram message shows `⏳ Applying…` then the final `✅ Saved (...)`.
   - Kiosk app shows a green toast with the same result text.
   - Parameters view on screen updates to the new target ranges without
     the operator touching it.
3. Same test with a dosing approval (`Recommend dosing` → Approve one
   action) while Dashboard is open — toast + message-edit sequence as
   above; Dashboard rebuilds (readings/history reflect the dose).
4. Tap Reject on a proposal — confirm no toast, no `⏳ Applying…` edit, no
   view rebuild; only the existing `❌ Rejected` edit.
