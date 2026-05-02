# Full-File Code Review Report — DesktopOCR Working Changes

**Date:** 2026-05-02  
**Scope:** All 5 files with staged changes, plus cross-file dependencies (`logic/anki_card_builder.py`). Reviewed line-by-line, not diff-only.  
**Method:** Static analysis focused on logic errors, edge cases, null derefs, race conditions, resource leaks, API contract violations, and pattern violations.

---

## Executive Summary

- **Staged changes are clean and correct.** The 5 items in the working-changes diff (bool guards, `sys.stdout` guard, Anki `last_error` fixes, task tracking, `_anki_timer` GC fix, status safety) are all well-justified and low-risk.
- **5 pre-existing issues found** (none introduced by the diff). None are release-blocking. Three are dead-code / unreachable branches; two are missing `hasattr` guards or unprotected `print()` calls.
- **No Critical or High severity issues.**

| Severity | Count | Categories |
|----------|-------|------------|
| Critical | 0 | — |
| High | 0 | — |
| Medium | 2 | Dead code, un-tracked async task |
| Low | 3 | Missing guards, unreachable branches |

---

## Medium Severity

### M1 — Dead code: `cached_translation` is always `None` at usage site

**File:** `main.py:1028`  
**Lines:**
```python
ocr_translation = cached_translation or None   # cached_translation is always None here
```
`cached_translation` is initialized to `None` on line 1011 and never reassigned before line 1028. The `or None` is therefore a no-op. This is leftover from an earlier iteration that cached translation results.

**Recommendation:** Remove `or None`; set `ocr_translation = None` directly.

---

### M2 — Pre-existing: `engine_changed` signal uses bare `asyncio.create_task()` without tracking

**File:** `main.py:403-405`  
**Lines:**
```python
window.engine_changed.connect(
    lambda eid: asyncio.create_task(_on_engine_changed(eid))
)
```
The working changes fixed the same pattern for Anki signals (`anki_requested`, `anki_test_requested`) by introducing `_safe_task()` and a `_anki_tasks` set. The engine-changed signal was left untouched. While `_on_engine_changed` has its own `try/except`, a failed task could still emit an unhandled exception warning and the Task object is not held, making it inconsistent with the Phase 3.4 cleanup.

**Recommendation:** Apply the same `_safe_task()` wrapper to `engine_changed.connect` for consistency.

---

## Low Severity

### L1 — Unprotected `print()` calls in GUI mode may fail under `pythonw.exe`

**Files & lines:**
- `main.py:1341` — `print(f"\n[{timestamp}] ...")` inside `_ocr_task`
- `main.py:1464` — `print("\nCleaning up resources...")` in `finally` block

`core/win_utils.py` was recently fixed (Phase 2.12) with a `sys.stdout is None` guard because PyInstaller `--windowed` or `pythonw.exe` can leave `sys.stdout` as `None`. The same risk applies to these `print()` calls, which are in the GUI event-loop path. In practice PyInstaller redirects stdout, so the realistic risk is very low.

**Recommendation:** Optional — guard with `if sys.stdout is not None:` for parity with `list_windows()`.

---

### L2 — Unreachable `else` branch in Anki card front-html fallback

**File:** `logic/anki_card_builder.py:133-134`  
**Lines:**
```python
if target_text:
    front_html = "<div class='target'>{TargetText}</div>"
else:
    front_html = "<div class='context'>{ContextText}</div>"  # unreachable
```
An empty-text guard at lines 86-89 returns `False` before this code is reached, guaranteeing `target_text` is truthy. The `else` branch is dead code.

**Recommendation:** Remove the `else` branch or replace the `if/else` with a direct assignment, since `target_text` is always truthy here.

---

### L3 — `window.side_menu.update_openai_usage` lacks `hasattr` guard

**File:** `main.py:1348`  
**Line:**
```python
window.side_menu.update_openai_usage(openai_validator.cost_estimate_chars)
```
Every other `window.side_menu.*` call in the same function is wrapped in `hasattr(window.side_menu, "...")`. This one is not. If a future UI refactor removes or renames the method, this line will raise `AttributeError` inside the OCR loop.

**Recommendation:** Wrap in `if hasattr(window.side_menu, "update_openai_usage"):`.

---

## Verified-OK Patterns (No Issues Found)

The following high-risk areas were examined and found correct:

1. **Anki `last_error` clobbering** — Fixed in working changes. `is_available` now only sets "Anki is not running" when `last_error` is already `None`, preventing transport-error messages from being overwritten.
2. **Task GC hygiene (`_anki_tasks` set)** — Correctly implemented. `_safe_check_anki()` and `_safe_task()` both add tasks to the set and use `add_done_callback(_anki_tasks.discard)`.
3. **`_anki_timer` stored on `window`** — Correct. `window._anki_timer = QTimer(window)` prevents the Python wrapper from being collected while C++ object survives.
4. **`_safe_clear_status` RuntimeError guard** — Correct. Catches the `RuntimeError` raised by calling a method on a destroyed `QObject`.
5. **`add_note` unexpected-result diagnostic** — Correct. `_set_error("addNote returned unexpected result type")` now fires before returning `None`.
6. **`_capture_gen` generation tracking in OCR loop** — Correct. Stale results are discarded when `this_gen != _capture_gen`.
7. **Settings boolean type guards** — Correct. All 15 boolean settings are guarded against non-bool values (including the `bool` subclass-of-`int` trap).
8. **Anki card builder API contract** — `build_and_send_card` correctly checks `note_id is not None` and propagates `False` on failure. `ensure_deck` and `ensure_note_type` are called sequentially (safe for AnkiConnect).
9. **Translation sequentiality** — `_translate` is called sequentially inside `_on_anki_requested`, matching the documented TranslationManager per-call lock behavior.
10. **Signal handler closures** — All lambda signal connections that capture `window` are safe; `window` is never reassigned inside the closure scopes.

---

## Files Examined

| File | Lines | Coverage |
|------|-------|----------|
| `main.py` | 1-1564 | Full |
| `logic/anki_connect.py` | 1-304 | Full |
| `logic/anki_card_builder.py` | 1-297 | Full |
| `core/win_utils.py` | 1-42 | Full |
| `plans/final-pre-release-plan.md` | N/A | Reviewed for accuracy |
| `settings.json` | N/A | Verified structure |
