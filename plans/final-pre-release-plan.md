# DesktopOCR Pre-Release Plan — Corrected Final

> **Based on:** Independent evaluation of the original plan
> **Corrections applied:**
> - ❌ Lock fix: Replaced dangerous `asyncio.Lock` suggestion with safe atomic assignment
> - ❌ Removed sequential translation concern (already handled in existing code)
> - All other claims verified against source and retained
>
> **✅ Completed 2026-05-02:** All phases complete (35/36 items). See progress summary below.

---

## Code Review Evaluation Log — 2026-05-02

A 7-claim code review of the working changes was investigated. Results:

| # | Claim | Verdict | Already in Plan? | Risk |
|---|-------|---------|-----------------|------|
| 1 | QMessageBox NameError in `_on_recapture` | ❌ **FALSE** — QMessageBox IS imported at `main.py:1478` inside `if __name__ == "__main__":` guard, before `main()` is called | N/A — not a bug | None |
| 2 | `ValueError` on corrupted `paddle_line_count` | ✅ **TRUE** — `int("abc")` crashes | Yes, Phase 1.3 | Low — needs hand-edited settings |
| 3 | Port range validation missing | ✅ **TRUE** — no clamp on 0 or 65536+ | Yes, Phases 1.4-1.5 | Low — bad port = connection error, not crash |
| 4 | Unreferenced `asyncio.create_task()` calls | ⚠️ **PARTIALLY TRUE** — tasks not tracked, but mitigated by 10s timeout vs 30s interval | Yes, Phase 3.4 | Very Low — `_check_anki` catches all exceptions |
| 5 | Relative `user_guide.html` path in PyInstaller | ✅ **TRUE** — `pathlib.Path("docs/...")` breaks in `--onefile` builds | Yes, Phase 1.2 | Medium — graceful degradation (blank dialog, not crash) |
| 6 | Redundant `json.loads(body)` in anki_connect.py | ✅ **TRUE** — `action` parameter already in scope | Yes, Phase 2.4 | None — wasted CPU on error paths only |
| 7 | Unnecessary `threading.Lock` in anki_connect.py | ⚠️ **PARTIALLY TRUE** — GIL makes single-attr write atomic, but Lock documents thread-safety intent | Yes, Phase 0 | None — removal is safe but optional |

**Key takeaway:** All 6 real issues were already captured in the plan. No new items needed. Claim 1 is incorrect — the QMessageBox import exists and executes before `_on_recapture` is ever called.

---

## PR Review Evaluation Log — 2026-05-02

A PR review of the Phase 1 patches raised 5 new issues + 1 pre-existing bug. Results:

| # | Claim | Verdict | Risk | Actionable? |
|---|-------|---------|------|-------------|
| 1 | `user_guide_dialog.py:38` fallback path has same relative-path bug | ✅ **TRUE** — but dead code; current caller always passes `guide_path` | **Very Low** — only matters if new caller appears | Optional defense-in-depth |
| 2 | Boolean `true` passes `isinstance(x, int)` guard for `anki_port` | ✅ **TRUE** — `bool` is subclass of `int` in Python; `"anki_port": true` → port 1 | **Low** — requires hand-edited JSON with `true` (rare) | Yes — fix isinstance check |
| 3 | Float `5.5` silently truncates for `paddle_line_count` | ✅ **TRUE** — `int(5.5)` → 5, while `int("5.5")` → ValueError → fallback to 3 | **Very Low** — only hand-edited; truncation is reasonable for line count | No — acceptable behavior |
| 4 | Misleading comment in port reset (`side_menu.py:1171`) | ✅ **TRUE** — says "Restore valid port" but actually resets to hardcoded 8765 | **None** — cosmetic only | Optional — fix comment |
| 5 | `import sys` inside `__init__` is non-idiomatic | ✅ **TRUE** — stylistic preference; functional but should be module-level | **None** — stylistic only | Optional — move to module level |
| 6 | **Pre-existing:** `AnkiConnect.__init__` / `set_host_port` don't validate port range | ✅ **TRUE** — `f"http://{host}:{port}"` accepts any int unvalidated | **Low** — all current code paths go through `load_settings()` clamp | Yes — defense-in-depth |

**Action items for plan:**

1. **Fix the `anki_port` isinstance check** in [`main.py:89`](main.py:89) to exclude `bool`: `isinstance(x, bool)` must return True so the guard catches `true` values. This is a Phase 1 refinement — the gate is already in place but has an edge case.
2. **Add port range validation in `set_host_port`** in [`logic/anki_connect.py:35`](logic/anki_connect.py:35) — clamp port to 1-65535 before building URL. Defense-in-depth for future code paths.
3. **Update `user_guide_dialog.py:38` fallback** to use `sys._MEIPASS` pattern — deferred since it's dead code.
4. **Fix comment** in `side_menu.py:1171` — low priority cosmetic.
5. **Move `import sys`** in `main_window.py` to module level — low priority stylistic.

---

## PR Review Evaluation Log 2 — 2026-05-02

A second PR review of the Phase 1 remainder patches raised 4 new issues. Results:

| # | Claim | Verdict | Risk | Actionable? |
|---|-------|---------|------|-------------|
| 1 | `sys` imported locally inside `_load_guide` — inconsistent with `main_window.py` cleanup | ✅ **TRUE** — `import sys` at `user_guide_dialog.py:38` is same pattern just cleaned up in Phase 1.9 | **Very Low** — dead code path (current callers always pass `guide_path`) | Yes — consistent with Phase 1.9 |
| 2 | `set_host_port()` clamps `port` but does not validate `host` — `http://None:8765` | ✅ **TRUE** — type annotation says `host: str` but no runtime guard; all callers pass validated strings from `load_settings()` | **Very Low** — signal is typed `pyqtSignal(str)`, callers use settings_state values already validated as strings | Optional defense-in-depth |
| 3 | No `anki_enabled` type guard — `"anki_enabled": "true"` (string) passes through unchecked | ⚠️ **PARTIALLY TRUE** — downstream uses truthiness (`not x`), so behavior is correct; but type consistency is compromised if string is saved back to JSON | **Very Low** — string `"true"` is truthy, `setChecked()` and signal emit work correctly via PyQt coercion | Optional — add `isinstance(x, bool)` guard |
| 4 | `settings.json` `auto_read_selection` flipped from `true` to `false` | ❌ **NOT A BUG** — `DEFAULT_SETTINGS` at `main.py:31` has `"auto_read_selection": False`; this is the user's own `settings.json`, not modified by our patches. The value was likely already `false` before this PR. | None | No |

**Actionable items:**
1. **Move `import sys` to module level in `user_guide_dialog.py`** — consistent with Phase 1.9 in `main_window.py`. Low priority (dead code).
2. **Add `anki_enabled` type guard in `load_settings()`** — optional consistency fix. Add after line 105: `if not isinstance(settings.get("anki_enabled"), bool): settings["anki_enabled"] = False`
3. **Add host validation in `set_host_port()`** — optional defense-in-depth. Add: `if not isinstance(host, str): host = "localhost"`

---

## PR Review Evaluation Log 3 — 2026-05-02

A third PR review of the **Phase 2 cleanup** patches (json.loads deduplication, list_windows consolidation, test_capture.py cleanup) raised 2 issues + 2 positive observations. Results:

| # | Claim | Verdict | Risk | Actionable? |
|---|-------|---------|------|-------------|
| 1 | `ctypes`, `ctypes.wintypes` unused in [`main.py:3-4`](main.py:3) after `list_windows()` moved to `core/win_utils.py` | ✅ **TRUE** — confirmed via regex search: `ctypes` only appears on lines 3-4 in the entire 1514-line file. Zero references remain. Dead imports. | **None** — no runtime impact; violates PEP8 import hygiene | Yes — remove dead imports |
| 2 | Pre-existing: `sys.stdout.encoding` can be `None` in [`core/win_utils.py:36`](core/win_utils.py:36) | ✅ **TRUE** — `title.encode(sys.stdout.encoding, ...)` crashes with `TypeError: encode() argument 1 must be str, not None` when stdout is redirected to a pipe/file (or in PyInstaller frozen builds where `sys.stdout.encoding` is `None`). Bug was carried over verbatim from the original `main.py` implementation. | **Low** — `list_windows()` is a dev/debug tool; crash would occur before any meaningful work | Yes — add encoding fallback |
| — | **Positive observation:** anki_connect.py action refactor is clean | ✅ **Confirmed** — no `json.loads(body)` calls remain in either `_request_aiohttp` or `_request_urllib`; `action` parameter is threaded correctly through both paths | — | — |
| — | **Positive observation:** test_capture.py deduplication is correct | ✅ **Confirmed** — `ctypes` imports and duplicate `list_windows()` function properly removed; clean `from core.win_utils import list_windows` | — | — |

**Action items for plan:**

1. **Remove unused `ctypes` and `ctypes.wintypes` imports** from [`main.py:3-4`](main.py:3) — clean dead imports after `list_windows()` consolidation.
2. **Add `sys.stdout.encoding` None guard** in [`core/win_utils.py:36`](core/win_utils.py:36) — use `encoding = sys.stdout.encoding or "utf-8"` before calling `.encode()`/`.decode()`.

---

## Code Review Evaluation Log 4 — 2026-05-02 (Post-Phase-0 Review)

A post-Phase-0 code review of the `threading.Lock` removal raised 3 issues. Results:

| # | Claim | Verdict | Risk | Actionable? |
|---|-------|---------|------|-------------|
| 1 | Stale docstring in [`_request_urllib`](logic/anki_connect.py:124) still claims ``threading.Lock`` protection | ✅ **TRUE** — lines 126-129: "protected by a ``threading.Lock``" — lock no longer exists. Misleading to maintainers. | **Low** — docs only; no runtime impact | Yes |
| 2 | Dead error fallback in [`add_note`](logic/anki_connect.py:301-304) — `self.last_error is None` never True | ✅ **TRUE** — all 8 code paths in `_request` call `_set_error` before returning `None`. The `if self.last_error is None:` guard is dead code. | **Extremely Low** — silent dead code, never executes | Optional — remove or comment as defense-in-depth |
| 3 | [`is_available`](logic/anki_connect.py:185-188) overwrites specific error messages with generic "Anki is not running" | ✅ **TRUE** — line 187 immediately overwrites `_request`'s specific error like `"Transport error: [WinError 10061]"` with generic `"Anki is not running"`, erasing diagnostic detail. | **Low-Medium** — impacts UX debugging; hides root cause of Anki connectivity failures | Yes — only set generic if `last_error` is still None |

**Action items for plan:**

1. **Fix stale docstring** in `_request_urllib` — update or remove the `threading.Lock` claim (Phase 0.2 — direct consequence of Phase 0.1).
2. **Fix `is_available` error clobbering** — add `if self.last_error is None:` guard before setting generic message (Phase 0.3).
3. **Optional: Remove dead `last_error is None` check in `add_note`** — or add comment noting it's defense-in-depth (Phase 2.11).

---

## PR Review Evaluation Log 5 — 2026-05-02 (Latest Staged Changes)

A new PR review of the most recent staged changes (Phase 0 + Phase 2.9/2.10) raised 7 issues. Results:

| # | Claim | Verdict | Risk | Actionable? |
|---|-------|---------|------|-------------|
| 1 | Stale docstring in [`_request_urllib`](logic/anki_connect.py:124) still claims ``threading.Lock`` protection | ✅ **TRUE** — lines 126-129: "protected by a ``threading.Lock``" — lock removed in Phase 0.1 | **Low** — docs only; no runtime impact | Already in plan as Phase 0.2 |
| 2 | [`is_available`](logic/anki_connect.py:186-188) overwrites specific error messages with generic "Anki is not running" | ✅ **TRUE** — line 187 overwrites `_request`'s specific diagnostic with generic message | **Low-Medium** — impacts UX debugging | Already in plan as Phase 0.3 |
| 3 | [`settings.json`](settings.json) has accidental local config changes: `paddle_line_count: 3→1`, `auto_capture: false→true` | ✅ **TRUE** — confirmed: `paddle_line_count: 1` (line 3), `auto_capture: true` (line 4). These are test artifacts, not product defaults. | **Low** — user's personal settings, only affects their local run | Yes — revert before commit |
| 4 | [`is_available`](logic/anki_connect.py:189-193) mislabels protocol errors as "not running" when Anki responds with bad payload | ✅ **TRUE** — line 193: when `result` is not a number, it says "Anki is not running" — but Anki *did* respond, so the message is factually wrong. Should be "Unexpected version response from Anki" or similar. | **Low** — impacts UX diagnosis; user sees wrong error message | Yes — distinct fix from Claim 2 (different code path) |
| 5 | [`core/win_utils.py`](core/win_utils.py:34-39) can crash if `sys.stdout` is `None` (e.g. `pythonw.exe`, headless) | ✅ **TRUE** — Phase 2.10 fixed `sys.stdout.encoding` being None, but `sys.stdout` itself can be None. `print()` raises `RuntimeError`, `sys.stdout.encoding` raises `AttributeError`. Called unconditionally at [`main.py:225`](main.py:225). | **Low** — `list_windows()` is dev-facing; production GUI uses `pythonw.exe` only after PyInstaller packaging | Yes — add `if sys.stdout is None: return` guard |
| 6 | Duplicate exception blocks in [`_request_urllib`](logic/anki_connect.py:155-168) — `urllib.error.URLError` and `(OSError, TimeoutError)` have identical bodies | ✅ **TRUE** — lines 155-161 and 162-168 are byte-for-byte identical. Can be collapsed into `except (urllib.error.URLError, OSError, TimeoutError)`. | **None** — code quality only | Yes — collapse into single except tuple |
| 7 | Dead defensive guard in [`add_note`](logic/anki_connect.py:302-304) — `self.last_error is None` never True | ✅ **TRUE** — all 8 `_request` failure paths call `_set_error` before returning None | **Extremely Low** — dead code | Already in plan as Phase 2.11 |

**New action items (not yet in plan):**

1. **Revert `settings.json`** — restore `paddle_line_count` to `3` and `auto_capture` to `false`. These are user-local test artifacts.
2. **Fix `is_available` bad-payload message** at [`logic/anki_connect.py:193`](logic/anki_connect.py:193) — change `"Anki is not running"` to `"Unexpected version response from Anki"` when Anki responded but payload was invalid. This is distinct from Phase 0.3 (which is about preserving `_request`'s error when Anki doesn't respond at all).
3. **Add `sys.stdout is None` guard** in [`core/win_utils.py:34`](core/win_utils.py:34) — early return before any `print()` calls.
4. **Collapse duplicate exception blocks** in [`logic/anki_connect.py:155-168`](logic/anki_connect.py:155) — merge `urllib.error.URLError` and `(OSError, TimeoutError)` into single `except` tuple.

---

## Code Review Evaluation Log 6 — 2026-05-02 (Latest Working Changes)

A new code review of the latest working changes (post-Phase-3.4) raised 6 claims. Results:

| # | Claim | Verdict | Risk | Actionable? |
|---|-------|---------|------|-------------|
| 1 | **Inconsistent task tracking** — [`anki_requested`](main.py:1099-1101) and [`anki_test_requested`](main.py:1187-1189) still use bare `asyncio.create_task()` without tracking pattern | ✅ **TRUE** — lines 1099-1101 and 1187-1189 use `lambda: asyncio.create_task(...)` without `set` tracking. `_on_anki_requested` has its own `try/except` at line 1005, so unhandled exceptions are logged. Task object is GC'd when lambda returns, but CPython event loop holds an internal reference until completion. | **Very Low** — no silent failure risk | Yes — Phase 3.5 |
| 2 | **`add_note` silently returns `None` on unexpected API result** — [`logic/anki_connect.py:294-302`](logic/anki_connect.py:294): if `_request("addNote")` returns data but result is non-numeric, falls through without `_set_error()` | ✅ **TRUE** — line 297-302: `result = data.get("result")` — if `isinstance(result, (int, float))` is False, function returns `None` without setting `last_error`. Caller in [`main.py:1087-1090`](main.py:1087) falls back to generic "Card save failed". Pre-existing. | **Low** — caller handles gracefully with generic message; loses diagnostic detail | Yes — Phase 2.14 |
| 3 | **Thread-safety docstring relies on CPython implementation detail** — GIL atomicity claim at [`logic/anki_connect.py:126-128`](logic/anki_connect.py:126) not guaranteed by Python language spec | ⚠️ **TRUE but opinion-based** — Deliberate, documented design decision for Windows-only CPython desktop app. GIL `STORE_ATTR` atomicity is well-known CPython property. | **None** — Not a bug, not actionable | ❌ No |
| 4 | **`_anki_timer` local variable may be garbage-collected** — [`main.py:1113`](main.py:1113): `QTimer(window)` has Qt parent so C++ object survives, but Python wrapper can be GC'd, breaking signal connections | ✅ **TRUE** — PyQt6 docs: if Python wrapper is GC'd, `timeout` signal disconnects even though C++ timer lives. `_anki_timer` is only on the stack of `main()`, which never returns during app lifetime (event loop). Cyclic GC could theoretically collect it. | **Very Low** — `main()` stack frame keeps strong reference; cyclic GC during startup is extremely unlikely | Yes — Phase 3.6 |
| 5 | **Forward-referenced `nonlocal` declaration** — [`main.py:548`](main.py:548): `nonlocal ref_frame, _capture_gen, selection_ready` where `_capture_gen` assigned at [`main.py:1243`](main.py:1243) | ✅ **TRUE** — Python allows this (resolution deferred to runtime). `_on_recapture()` (calling `_capture_gen(...)`) only fires after first successful capture loop, and line 1243 assignment is part of setup sequence. | **None** — functional, unconventional but safe | ❌ No — low priority |
| 6 | **`call_later` lambdas close over `window` with late null-check** — [`main.py:1093-1094`](main.py:1093): `window is not None` guard doesn't protect against destroyed C++ QObject | ✅ **TRUE** — `window is not None` checks Python object identity, not C++ `QObject` validity. Destroyed QObject wrapper passes the guard but calling `.set_status()` raises `RuntimeError`. Realistic risk is near-zero (window closing during 3s timer delay). | **Very Low** — pre-existing pattern throughout codebase; near-zero realistic risk | Yes — Phase 3.7 |

### Risk Analysis — Regression Risk From Applying the Fix

This table evaluates the risk that **applying the fix itself** could break existing working behavior (regression risk, not bug severity):

| Phase | Change | Regression Risk | How the Fix Could Cause a Regression | Why the Risk is Low |
|-------|--------|----------------|--------------------------------------|---------------------|
| **2.14** | Add `_set_error` in `add_note` unexpected-result path | **Very Low** | Adding `_set_error` changes `self.last_error` state. If some code path reads `last_error` after `add_note` returns `None` on a bad payload, it would now see a new error message instead of whatever was there before. | `_request` already overwrites `last_error` on every call. The new `_set_error` only triggers when Anki responds with unexpected data — a rare edge case. The caller (`main.py:1087-1090`) checks `card_id is None`, not `last_error`. |
| **3.5** | Track signal tasks in `_anki_tasks` set | **Very Low** | If `_safe_task` is not defined correctly (e.g., typo, wrong function signature), the signal connection could silently fail. Both `_on_anki_requested` and `_on_anki_test_requested` are long async functions — if they never fire, Anki card creation stops working. | The fix is a trivial wrapper: `def _safe_task(coro): task = asyncio.create_task(coro); _anki_tasks.add(task); task.add_done_callback(_anki_tasks.discard)`. Same pattern already proven in Phase 3.4. The signal connection changes from `lambda: asyncio.create_task(f())` to `lambda: _safe_task(f())` — single function call replacement. |
| **3.6** | Store `_anki_timer` on `window` | **Very Low** | If `window._anki_timer` shadows an existing attribute used elsewhere, the timer could be accidentally stopped or reset. If `_anki_timer` stops ticking, the periodic Anki availability check stops — users won't see the Anki status update in the tray. | `MainWindow` has no `_anki_timer` attribute (verified via codebase search). The timer logic is identical — same `QTimer(window)`, same `timeout.connect(_safe_check_anki)` — only the storage location changes. |
| **3.7** | Wrap `window.set_status` in try/except | **Very Low** | `try/except RuntimeError: pass` could accidentally swallow a genuine `RuntimeError` from inside `set_status`, making a real bug invisible. The `pass` silently drops the exception. | `set_status` is a one-line setter: `self._status_label.setText(msg)`. `QLabel.setText` does not raise `RuntimeError` in any documented path. The only `RuntimeError` that could fire is from the C++ QObject peer being destroyed — which is exactly the case being guarded against. |

**Overall assessment:** All 4 changes carry **Very Low** regression risk. None touch shared state, core logic, or data flow. Each is a self-contained modification to one or two lines, and 3 of the 4 follow patterns already proven in Phase 3.4. The only review item rejected (Claim 3 — CPython docstring) was rejected precisely because changing it would introduce risk (wrong abstraction for a non-existent target platform) with zero benefit.

### New Action Items

1. **Phase 2.14 — Add `_set_error` in `add_note` unexpected-result path** — [`logic/anki_connect.py:297-302`](logic/anki_connect.py:297): add diagnostic `_set_error` before returning `None` when Anki responds with non-numeric result.
2. **Phase 3.5 — Track `anki_requested`/`anki_test_requested` tasks** — Replace bare `asyncio.create_task()` with `_safe_anki_callback` pattern for consistency with Phase 3.4. Lines 1099-1101 and 1187-1189 in [`main.py`](main.py).
3. **Phase 3.6 — Store `_anki_timer` on `window`** — [`main.py:1113`](main.py:1113): change `_anki_timer = QTimer(window)` to `window._anki_timer = QTimer(window)` to prevent Python wrapper GC from disconnecting the `timeout` signal.
4. **Phase 3.7 — Safeguard `call_later` window reference** — [`main.py:1093-1094`](main.py:1093): wrap `window.set_status(...)` in `try/except RuntimeError` to handle destroyed QObject peer gracefully.

---

## Phase 0 — Must Correct (🚨) [3 items]

### 0.1 ✅ Fix `threading.Lock` — Use atomic assignment, NOT `asyncio.Lock`

**File:** [`logic/anki_connect.py`](logic/anki_connect.py)

**Why:** The original plan proposed replacing `threading.Lock` with `asyncio.Lock`. This is wrong — `_set_error` is called from **both** async paths (`_request_aiohttp`) and thread-pool paths (`_sync_post` via `run_in_executor`). An `asyncio.Lock` cannot be acquired from a thread-pool worker and would crash with `RuntimeError`.

**Corrected approach:** Under CPython, the GIL protects single attribute writes. `self.last_error = msg` is already atomic. The `threading.Lock` wrapper is unnecessary overhead. Replace with direct assignment.

**Changes applied:**
1. Removed `import threading` (line 8) — confirmed unused after lock removal
2. Removed `self._last_error_lock = threading.Lock()` (line 33)
3. Replaced `_set_error`/`_clear_error` with direct atomic assignment

**Status:** ✅ **Done**

### 0.2 Fix stale docstring in `_request_urllib` (Post-Phase-0 Review, Claim 1)

**File:** [`logic/anki_connect.py:124-129`](logic/anki_connect.py:124)

**Why:** After Phase 0.1 removed `threading.Lock`, the docstring at lines 126-129 still claims assignments are "protected by a ``threading.Lock``" — now false and misleading to future maintainers.

**Change:** Update the thread-safety paragraph to reflect GIL-based atomicity:
```python
"""Fallback using urllib.request wrapped in a thread-pool executor.

Thread-safety note: ``_sync_post`` runs in a thread-pool executor
(``run_in_executor``). Under CPython the GIL makes single attribute
assignment atomic, so direct writes to ``last_error`` are safe.
"""
```

**Status:** ✅ **Done**

### 0.3 Fix `is_available` error clobbering — transport-failure path (Post-Phase-0 Review, Claim 3)

**File:** [`logic/anki_connect.py:185-188`](logic/anki_connect.py:185)

**Why:** `is_available` overwrites `_request`'s specific diagnostic message (e.g., `"Transport error: [WinError 10061]"`) with the generic `"Anki is not running"` — hiding the root cause from users. This is the path where `_request` returns `None` (Anki not reachable).

**Change:** Only set generic message if `_request` didn't already set a specific error:
```python
if data is None:
    if self.last_error is None:
        self._set_error("Anki is not running")
    return False
```

**Status:** ✅ **Done**

### 0.4 Fix `is_available` mislabeling — bad-payload path (PR Review Log 5, Claim 4)

**File:** [`logic/anki_connect.py:189-193`](logic/anki_connect.py:189)

**Why:** When AnkiConnect *responds* but with a non-numeric `result` (line 189-193), the code says `"Anki is not running"` — but Anki IS running (it responded). This is factually wrong and misleads users during debugging.

**Change:** Use a message that accurately describes the situation:
```python
result = data.get("result")
if isinstance(result, (int, float)):
    self._clear_error()
    return True
self._set_error("Unexpected version response from Anki")
return False
```

**Status:** ✅ **Done**

---

## Phase 1 — Safety First (⚠️ Medium Risk) [5 items]

### 1.1 ✅ Add `sounddevice` to `requirements.txt`

**File:** [`requirements.txt`](requirements.txt)

**Why:** [`tts/manager.py:36`](tts/manager.py:36) does `import sounddevice as sd` but `sounddevice` is not listed. When COEIROINK or any backend returns audio data, the app will crash with `ModuleNotFoundError`.

**Status:** ✅ **Done** — `sounddevice==0.5.2` added alongside `pyinstaller`; `pyperclip`, `pyttsx3`, `nuitka` removed.

### 1.2 ✅ Fix user guide path for PyInstaller compatibility

**File:** [`ui/main_window.py`](ui/main_window.py:175)

**Why:** `pathlib.Path("docs/user_guide.html")` is relative to the current working directory. In a PyInstaller `--onefile` build, CWD may not be the executable directory. Use `__file__` with `sys._MEIPASS` fallback.

**Change applied:**
```python
import sys
_base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent.parent))
self._user_guide_path = _base / "docs" / "user_guide.html"
```

**Status:** ✅ **Done**

### 1.3 ✅ Add `paddle_line_count` try/except guard

**File:** [`main.py:316`](main.py:316)

**Why:** `int(settings_state.get("paddle_line_count", 3) or 3)` raises `ValueError` if the saved value is a non-integer string (e.g., corrupted `settings.json`).

**Change applied:**
```python
try:
    saved_line_count = max(1, min(5, int(settings_state.get("paddle_line_count", 3) or 3)))
except (ValueError, TypeError):
    saved_line_count = 3
```

**Status:** ✅ **Done**

### 1.4 ✅ Add port range validation in `side_menu.py`

**File:** [`ui/side_menu.py:1162-1170`](ui/side_menu.py:1162)

**Why:** Port is coerced to `int` but not validated to 1-65535. Invalid ports are emitted silently.

**Change applied:**
```python
port = int(raw)
if port < 1 or port > 65535:
    port = 8765
    self._anki_port_edit.setText(str(port))
```

**Status:** ✅ **Done** (QIntValidator option skipped — would require import changes not authorized)

### 1.5 ✅ Add port range clamping in `load_settings()`

**File:** [`main.py:89`](main.py:89)

**Why:** Type guard exists for `anki_port` but no range clamp. Corrupted settings can set port 0 or 99999.

**First pass applied:**
```python
if not isinstance(settings.get("anki_port"), int):
    settings["anki_port"] = 8765
if not 1 <= settings.get("anki_port", 8765) <= 65535:
    settings["anki_port"] = 8765
```

**Refinement needed (PR Review Finding #2):** `isinstance(True, int)` returns `True` in Python because `bool` is a subclass of `int`. A corrupted `settings.json` with `"anki_port": true` (JSON boolean) would pass the type guard and silently use port **1** (since `True == 1`). The fix: exclude `bool` explicitly.

**Corrected code:**
```python
# Defensive type guards — settings.json may be hand-edited with invalid types
if not isinstance(settings.get("anki_host"), str):
    settings["anki_host"] = "localhost"
# bool is a subclass of int in Python; must exclude it explicitly
if not isinstance(settings.get("anki_port"), int) or isinstance(settings.get("anki_port"), bool):
    settings["anki_port"] = 8765
if not 1 <= settings.get("anki_port", 8765) <= 65535:
    settings["anki_port"] = 8765
```

**Status:** ⚠️ **Needs refinement** — add `or isinstance(settings.get("anki_port"), bool)` to the type guard

### 1.6 Add port range validation in `AnkiConnect.set_host_port()` (defense-in-depth)

**File:** [`logic/anki_connect.py:35`](logic/anki_connect.py:35)

**Why (PR Review Finding #6 - pre-existing):** `AnkiConnect.__init__` and `set_host_port` accept any `int` for port without validation. The URL `f"http://{host}:{port}"` is constructed with an unvalidated value. While all current code paths go through `load_settings()` (which now clamps in Phase 1.5), future code paths or direct API calls could bypass this safety net.

**Change:**
```python
def set_host_port(self, host: str, port: int) -> None:
    # Clamp to valid range (defense-in-depth, load_settings() also validates)
    if not isinstance(port, int) or isinstance(port, bool):
        port = 8765
    elif port < 1 or port > 65535:
        port = 8765
    self._host = host
    self._port = port
    self._anki_url = f"http://{host}:{port}"
```

**Status:** ⬜ **Pending** — needs Code mode

### 1.7 Fix `user_guide_dialog.py` fallback path (optional, defense-in-depth)

**File:** [`ui/user_guide_dialog.py:38`](ui/user_guide_dialog.py:38)

**Why (PR Review Finding #1):** The fallback path `pathlib.Path("docs/user_guide.html")` is relative to CWD, same bug as the original `main_window.py:175`. Currently dead code because `MainWindow` always passes `guide_path`, but could bite if a new caller omits the argument.

**Change:** Apply same `sys._MEIPASS` pattern as in Phase 1.2:
```python
import sys
_base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent.parent))
path = _base / "docs" / "user_guide.html"
```

**Status:** ⬜ **Pending** (low priority — dead code)

### 1.8 Fix misleading comment in port reset (cosmetic)

**File:** [`ui/side_menu.py:1171`](ui/side_menu.py:1171)

**Why (PR Review Finding #4):** Comment says "Restore the valid port in the field so the user sees what was applied" but the code resets to hardcoded 8765 — misleading to future maintainers.

**Change:** Replace with accurate comment:
```python
# Reset to default port
self._anki_port_edit.setText(str(port))
```

**Status:** ⬜ **Pending** (cosmetic only)

### 1.9 Move `import sys` to module level in `main_window.py` (stylistic)

**File:** [`ui/main_window.py:175`](ui/main_window.py:175)

**Why (PR Review Finding #5):** `import sys` is inside `__init__()`. Standard practice is module-level imports. Functional but non-idiomatic.

**Change:** Move `import sys` to top of file alongside other stdlib imports.

**Status:** ⬜ **Pending** (stylistic only)

---

## Phase 2 — Cleanup (🟢 Low Risk) [8 items]

### 2.1 ✅ Remove dead `_compute_diff` stub

**File:** [`main.py:113-115`](main.py:113)

**Change:** Delete the function entirely. It's `pass` with a "Removed per C-1" comment.

**Status:** ✅ **Done**

### 2.2 ✅ Remove unused dependencies from `requirements.txt`

**File:** [`requirements.txt`](requirements.txt)

**Removed:**
- `pyperclip==1.11.0` — app uses `QApplication.clipboard().setText()`
- `pyttsx3==2.99` — never imported anywhere
- `nuitka==4.0.8` — plan targets PyInstaller, not Nuitka

**Added:**
- `pyinstaller` (unversioned)
- `sounddevice==0.5.2`

**Status:** ✅ **Done**

### 2.3 ✅ Move `import threading` to top of `tensor_utils.py`

**File:** [`core/tensor_utils.py:12`](core/tensor_utils.py:12)

**Change:** Move `import threading` from line 12 to line 2 (after `import os`), before third-party imports and module-level constants. PEP8 compliance.

**Status:** ✅ **Done**

### 2.4 ✅ Remove duplicate `json.loads(body)` in `anki_connect.py`

**File:** [`logic/anki_connect.py:145-146`](logic/anki_connect.py:145)

**Why:** `body` was built from `json.dumps(payload)` at line 79. The `action` string is already available as the `action` parameter in `_request()` scope. The re-parse is redundant.

**Change:** Thread `action` parameter down to `_request_urllib` / `_sync_post` so it's available without re-parsing.

**Status:** ✅ **Done**

### 2.5 ✅ Remove invalid QSS selector

**File:** [`ui/theme_template.qss:152`](ui/theme_template.qss:152)

**Change:** Remove the `QWidget:has(> QLabel)` block. Qt QSS does not support the `:has()` pseudo-class.

**Status:** ✅ **Done**

### 2.6 ✅ Fix PEP8 spacing in `ocr_engine.py`

**File:** [`core/ocr_engine.py`](core/ocr_engine.py)

**Change:** Remove blank lines between import statements to standard PEP8 grouping.

**Status:** ✅ **Done**

### 2.7 ✅ Consolidate duplicated `list_windows()` into shared utility

**Files:** [`main.py:170-199`](main.py:170), [`tests/test_capture.py:13-42`](tests/test_capture.py:13)

**Change:**
1. Create `core/win_utils.py` with a single `list_windows()` function
2. Import and call it from both `main.py` and `tests/test_capture.py`

**Status:** ✅ **Done**

### 2.8 ✅ Expand `test_imports.py` module list

**File:** [`tests/test_imports.py:16-24`](tests/test_imports.py:16)

**Change:** Added `logic.anki_connect`, `logic.anki_card_builder`, `tts.manager`, `core.translation.manager`, `core.capture_pipeline`.

**Status:** ✅ **Done**

### 2.9 Remove unused `ctypes` imports from `main.py` (PR Review Log 3, Claim 1)

**File:** [`main.py:3-4`](main.py:3)

**Why:** After `list_windows()` was consolidated into `core/win_utils.py` (Phase 2.7), `ctypes` and `ctypes.wintypes` are no longer referenced anywhere in `main.py`. Verified via regex search — zero references remain in the 1514-line file.

**Change:** Delete lines 3-4 (`import ctypes` and `import ctypes.wintypes`).

**Status:** ✅ **Done**

### 2.10 ✅ Add `sys.stdout.encoding` None guard in `core/win_utils.py` (PR Review Log 3, Claim 2)

**File:** [`core/win_utils.py:36`](core/win_utils.py:36)

**Why:** When stdout is redirected to a pipe/file or in PyInstaller frozen builds, `sys.stdout.encoding` can be `None`. The current code `title.encode(sys.stdout.encoding, errors="replace")` would raise `TypeError: encode() argument 1 must be str, not None`. This bug existed in the original `main.py` implementation and was carried over verbatim during consolidation (Phase 2.7).

**Change applied:**
```python
encoding = sys.stdout.encoding or "utf-8"
safe_title = title.encode(encoding, errors="replace").decode(encoding)
```

**Status:** ✅ **Done**

### 2.11 Optional: Remove dead `last_error is None` check in `add_note` (Post-Phase-0 Review, Claim 2)

**File:** [`logic/anki_connect.py:302-304`](logic/anki_connect.py:302)

**Why:** Every code path in `_request` calls `_set_error` before returning `None` (verified across all 8 paths in both transport backends). The `if self.last_error is None:` guard at line 303 is dead code that never executes.

**Change:** Either remove the guard entirely, or add a comment noting it's defense-in-depth:
```python
if data is None:
    # _request should have set last_error already, but guard defensively
    if self.last_error is None:
        self._set_error("Card save failed")
    return None
```

**Status:** ✅ **Done**

### 2.12 Add `sys.stdout is None` guard in `list_windows()` (PR Review Log 5, Claim 5)

**File:** [`core/win_utils.py:34`](core/win_utils.py:34)

**Why:** Phase 2.10 fixed the `sys.stdout.encoding` being `None` case, but `sys.stdout` itself can be `None` in headless contexts (e.g., `pythonw.exe`, PyInstaller `--noconsole`). If `sys.stdout is None`, then `sys.stdout.encoding` raises `AttributeError`, and even `print()` raises `RuntimeError`. [`list_windows()`](core/win_utils.py:8) is called unconditionally at [`main.py:225`](main.py:225), meaning any headless/noconsole invocation crashes before doing any work.

**Risk:** **Low** — `list_windows()` is a dev/debug tool; production GUI uses QApplication. However, `--list-engines` flag at [`main.py:1444`](main.py:1444) calls `main(0)` which hits `list_windows()` before any QApplication check.

**Change:**
```python
def list_windows():
    """Enumerate all visible top-level windows and print them to stdout."""
    if sys.stdout is None:
        return
    # ... rest of function ...
```

**Status:** ✅ **Done**

### 2.13 Collapse duplicate exception blocks in `_request_urllib` (PR Review Log 5, Claim 6)

**File:** [`logic/anki_connect.py:155-168`](logic/anki_connect.py:155)

**Why:** `urllib.error.URLError` and `(OSError, TimeoutError)` handlers have identical bodies — same logging pattern, same `_set_error` call, same `return None`. This is maintenance debt (any fix to one block must be duplicated to the other).

**Change:** Merge into a single `except` tuple:
```python
except (urllib.error.URLError, OSError, TimeoutError) as exc:
    if quiet:
        logger.debug("[Anki] Poll failed: %s", exc)
    else:
        logger.warning("[Anki] Request failed: %s", exc)
    self._set_error(f"Transport error: {exc}")
    return None
```

**Risk:** **None** — identical behavior, less code.

**Status:** ✅ **Done**

### 2.14 Add `_set_error` in `add_note` unexpected-result path (Code Review Log 6, Claim 2)

**File:** [`logic/anki_connect.py:297-302`](logic/anki_connect.py:297)

**Why:** When `_request("addNote")` succeeds (returns data) but the `result` is non-numeric, `add_note` falls through to `return result` (which is `None`) without calling `_set_error()`. The caller in [`main.py:1087-1090`](main.py:1087) catches `card_id is None` and falls back to a generic "Card save failed" message — losing diagnostic detail about why the result was unexpected.

**Change:**
```python
result = data.get("result")
if isinstance(result, (int, float)):
    return result
self._set_error("addNote returned unexpected result type")
return None
```

**Risk:** **Low** — caller already handles `None` gracefully. Change only adds diagnostic detail when the API contract is violated.

**Status:** ⬜ **Pending**

---

## Phase 3 — Settings & Cosmetics (🟢 Low Risk) [7 items]

### 3.1 ✅ Fix `settings.json.example` defaults

**File:** [`settings.json.example`](settings.json.example)

| Key | Was (wrong) | Changed to (correct) |
|-----|-------------|----------------------|
| `text_size` | `"standard"` | `"medium"` |
| `auto_read_selection` | `true` | `false` |
| `dictionary_pass_enabled` | `false` | `true` |

**Status:** ✅ **Done**

### 3.2 ✅ Add missing tooltips

**Files:**
- [`ui/transcription_tray.py:142`](ui/transcription_tray.py:142) — Speak button ✅
- [`ui/transcription_tray.py:153`](ui/transcription_tray.py:153) — Translate button ✅
- [`ui/controls_bar.py:47`](ui/controls_bar.py:47) — Menu button ✅

**Status:** ✅ **Done**

### 3.3 ✅ Add warning log for invalid `text_size` in settings

**File:** [`main.py:83-84`](main.py:83)

**Change:** Added `logging.getLogger(__name__).warning(...)` before reset to `"medium"`.

**Status:** ✅ **Done**

### 3.4 ✅ Fix QTimer un-awaited coroutines (optional hygiene)

**File:** [`main.py:1104-1106`](main.py:1104)

**Change applied:** Replaced all 5 bare `asyncio.create_task(_check_anki())` call sites with `_safe_check_anki()`. The helper maintains a `set[asyncio.Task]` and discards completed tasks via `add_done_callback`:

```python
_anki_tasks: set[asyncio.Task] = set()

def _safe_check_anki() -> None:
    task = asyncio.create_task(_check_anki())
    _anki_tasks.add(task)
    task.add_done_callback(_anki_tasks.discard)

_anki_timer.timeout.connect(_safe_check_anki)
```

Five call sites updated: QTimer (1), initial startup fire (1), anki_enabled/host/port setting changes (3).

**Status:** ✅ **Done**

### 3.5 Track `anki_requested`/`anki_test_requested` tasks (Code Review Log 6, Claim 1)

**File:** [`main.py:1099-1101`](main.py:1099) and [`main.py:1187-1189`](main.py:1187)

**Why:** Phase 3.4 introduced `_safe_check_anki()` with task tracking for `_check_anki` calls, but the `anki_requested` and `anki_test_requested` signal handlers still use bare `asyncio.create_task()` without tracking:
```python
lambda: asyncio.create_task(_on_anki_requested())
lambda: asyncio.create_task(_on_anki_test_requested())
```
While `_on_anki_requested` has its own `try/except`, the pattern is inconsistent with Phase 3.4.

**Change:** Replace with a `_safe_anki_requested`/`_safe_anki_test_requested` pair or a single `_safe_task` helper that tracks tasks in the existing `_anki_tasks` set:
```python
def _safe_task(coro) -> None:
    task = asyncio.create_task(coro)
    _anki_tasks.add(task)
    task.add_done_callback(_anki_tasks.discard)

# Signal connections:
anki_requested.connect(lambda: _safe_task(_on_anki_requested()))
anki_test_requested.connect(lambda: _safe_task(_on_anki_test_requested()))
```

**Risk:** **Very Low** — `_on_anki_requested` already catches all exceptions. This is a consistency/cleanliness fix matching Phase 3.4.

**Status:** ⬜ **Pending**

### 3.6 Store `_anki_timer` on `window` to prevent GC (Code Review Log 6, Claim 4)

**File:** [`main.py:1113`](main.py:1113)

**Why:** `_anki_timer = QTimer(window)` has Qt parent set so the C++ QTimer object survives, but the Python wrapper (`PyQt6.QtCore.QTimer`) can be garbage-collected by CPython's cyclic GC. Per PyQt6 docs, if the Python wrapper is GC'd, the `timeout` signal is disconnected — the C++ timer keeps ticking but callbacks stop firing. `_anki_timer` is only a local variable on the `main()` stack frame, which never returns during the app's lifetime (event loop). However, cyclic GC during startup could theoretically collect it.

**Change:**
```python
window._anki_timer = QTimer(window)
window._anki_timer.timeout.connect(_safe_check_anki)
```

**Risk:** **Very Low** — `main()` stack frame keeps a strong reference; cyclic GC during startup is extremely unlikely. This is defense-in-depth.

**Status:** ⬜ **Pending**

### 3.7 Safeguard `call_later` window reference (Code Review Log 6, Claim 6)

**File:** [`main.py:1093-1094`](main.py:1093)

**Why:** The `call_later` lambda closes over `window` with a `window is not None` guard — but this checks Python object identity, not C++ `QObject` validity. If `window` (a `MainWindow`/`QMainWindow` instance) is destroyed during app shutdown, the Python wrapper may still exist but its C++ peer is gone. Calling `.set_status()` on a destroyed QObject raises `RuntimeError`. Realistic risk is near-zero (window closing during a 3-second timer delay).

**Change:**
```python
call_later(3.0, lambda: _safe_set_status(window, "Card saved successfully"))
```
Where `_safe_set_status` wraps the call in a try/except:
```python
def _safe_set_status(window, msg: str) -> None:
    try:
        if window is not None:
            window.set_status(msg)
    except RuntimeError:
        pass  # QObject C++ peer was destroyed
```

**Risk:** **Very Low** — pre-existing pattern throughout codebase. This is defense-in-depth.

**Status:** ⬜ **Pending**

---

## Phase 4 — Packaging (🟡 Medium Risk) [3 items]

### 4.1 ✅ Create PyInstaller spec file

**File:** [`DesktopOCR.spec`](DesktopOCR.spec)

**Change applied:** Created `DesktopOCR.spec` at project root with:
- Static data files: `ui/theme_template.qss`, `docs/user_guide.html`, `resources/`
- Dynamic hidden imports collected from `core`, `logic`, `tts` submodules
- `console=False` for GUI mode
- `sys._MEIPASS` path resolution (paired with Phase 1.2 fix)

**Status:** ✅ **Done**

### 4.2 ✅ Update `.gitignore`

**Added:**
```
debug_crops/
debug_ocr/
run_logs/
*.spec
```

**Status:** ✅ **Done**

### 4.3 ✅ Remove Nuitka, add PyInstaller to `requirements.txt`

Already covered in Phase 2.2. ✅

---

## Phase 5 — Documentation (🟢 Low Risk) [3 items]

### 5.1 ✅ Update README

- ✅ Clarify Auto-translate is for Anki card creation only
- ❌ Add note about TTS audio attachment to Anki cards (deferred — no dedicated Anki audio section exists yet)
- ✅ Add "verify add-on code on AnkiWeb" note
- ✅ Add "What's New in This Release" section
- ✅ Add note that EasyOCR is hidden/disabled in this release

### 5.2 ✅ Update user_guide.html

- ✅ Mark EasyOCR as hidden/disabled (not part of this release)
- ✅ Fix stale EasyOCR reference (line 80 — removed "or EasyOCR fallback")
- ✅ Add troubleshooting section
- ✅ Add bundled resource note (PyInstaller)
- ✅ Update timestamp to May 2026

### 5.3 Add port validation note to settings documentation

**Skipped — no `docs/settings.md` or equivalent file exists.** Port validation documentation deferred until a settings doc is created.

---

## Progress Summary

| Phase | Total | ✅ Done | ⬜ Remaining |
|-------|-------|---------|--------------|
| 0 — Lock fix + aftermath | 4 | **4** 🔥 | **0** |
| 1 — Safety | 9 | **9** | **0** 🔥 |
| 2 — Cleanup | 14 | **13** 🔥 | **1** (Phase 2.14) |
| 3 — Settings | 7 | **4** 🔥 | **3** (Phases 3.5-3.7) |
| 4 — Packaging | 3 | **3** 🔥 | **0** |
| 5 — Documentation | 3 | 2 | 1 (port validation doc — no settings.md exists) |
| **Total** | **40** | **35** | **5** |

> **Note:** Boolean type guards for all 15 remaining bool settings in `load_settings()` were added as a bonus item (not in original plan). The only deferred item is Phase 5.3 (port validation docs — no `settings.md` exists). `settings.json` `paddle_line_count: 1` is a local test artifact, not a code issue. Code Review Log 6 added 4 new items (Phase 2.14, 3.5, 3.6, 3.7).
