# DesktopOCR Pre-Release Plan — Corrected Final

> **Based on:** Independent evaluation of the original plan
> **Corrections applied:**
> - ❌ Lock fix: Replaced dangerous `asyncio.Lock` suggestion with safe atomic assignment
> - ❌ Removed sequential translation concern (already handled in existing code)
> - All other claims verified against source and retained
>
> **✅ Completed 2026-05-02:** Zero-risk cleanup (Phases 2-4 partially) + Phase 5 documentation (2/3 items) — see checkmarks below

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

## Phase 0 — Must Correct (🚨) [1 item]

### 0.1 Fix `threading.Lock` — Use atomic assignment, NOT `asyncio.Lock`

**File:** [`logic/anki_connect.py`](logic/anki_connect.py)

**Why:** The original plan proposed replacing `threading.Lock` with `asyncio.Lock`. This is wrong — `_set_error` is called from **both** async paths (`_request_aiohttp`) and thread-pool paths (`_sync_post` via `run_in_executor`). An `asyncio.Lock` cannot be acquired from a thread-pool worker and would crash with `RuntimeError`.

**Corrected approach:** Under CPython, the GIL protects single attribute writes. `self.last_error = msg` is already atomic. The `threading.Lock` wrapper is unnecessary overhead. Replace with direct assignment.

**Changes:**
```python
# Remove threading.Lock entirely
# self._last_error_lock = threading.Lock()  # DELETE
```

```python
# _set_error — simple atomic assignment (GIL-protected)
def _set_error(self, msg: str) -> None:
    self.last_error = msg

# _clear_error — simple atomic assignment
def _clear_error(self) -> None:
    self.last_error = None
```

Also remove `import threading` if it's no longer needed elsewhere in the file (check — it may be needed for `_sync_post` thread-pool execution).

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

### 2.4 Remove duplicate `json.loads(body)` in `anki_connect.py`

**File:** [`logic/anki_connect.py:145-146`](logic/anki_connect.py:145)

**Why:** `body` was built from `json.dumps(payload)` at line 79. The `action` string is already available as the `action` parameter in `_request()` scope. The re-parse is redundant.

**Change:** Thread `action` parameter down to `_request_urllib` / `_sync_post` so it's available without re-parsing.

### 2.5 ✅ Remove invalid QSS selector

**File:** [`ui/theme_template.qss:152`](ui/theme_template.qss:152)

**Change:** Remove the `QWidget:has(> QLabel)` block. Qt QSS does not support the `:has()` pseudo-class.

**Status:** ✅ **Done**

### 2.6 ✅ Fix PEP8 spacing in `ocr_engine.py`

**File:** [`core/ocr_engine.py`](core/ocr_engine.py)

**Change:** Remove blank lines between import statements to standard PEP8 grouping.

**Status:** ✅ **Done**

### 2.7 Consolidate duplicated `list_windows()` into shared utility

**Files:** [`main.py:170-199`](main.py:170), [`tests/test_capture.py:13-42`](tests/test_capture.py:13)

**Change:**
1. Create `core/win_utils.py` with a single `list_windows()` function
2. Import and call it from both `main.py` and `tests/test_capture.py`

### 2.8 ✅ Expand `test_imports.py` module list

**File:** [`tests/test_imports.py:16-24`](tests/test_imports.py:16)

**Change:** Added `logic.anki_connect`, `logic.anki_card_builder`, `tts.manager`, `core.translation.manager`, `core.capture_pipeline`.

**Status:** ✅ **Done**

---

## Phase 3 — Settings & Cosmetics (🟢 Low Risk) [4 items]

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

### 3.4 Fix QTimer un-awaited coroutines (optional hygiene)

**File:** [`main.py:1104-1106`](main.py:1104)

**Change:** Maintain a `set` of pending tasks and clean them on completion:
```python
_anki_tasks: set[asyncio.Task] = set()

def _safe_check_anki():
    task = asyncio.create_task(_check_anki())
    _anki_tasks.add(task)
    task.add_done_callback(_anki_tasks.discard)

_anki_timer.timeout.connect(_safe_check_anki)
```

(Low priority — `_check_anki` already catches exceptions internally.)

---

## Phase 4 — Packaging (🟡 Medium Risk) [3 items]

### 4.1 Create PyInstaller spec file

Create `DesktopOCR.spec` at project root that:
- Collects `ui/theme_template.qss`, `docs/user_guide.html`, `resources/` as `--add-data`
- Documents that `models/paddle/` ONNX files must be supplied separately
- Uses `--windowed` for GUI mode
- Sets `sys._MEIPASS` path for user_guide.html (paired with Phase 1.2 fix)

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
| 0 — Lock fix | 1 | 0 | 1 |
| 1 — Safety | 9 | 5 | 4 (1.5 bool fix, 1.6 defense, 1.7 optional, 1.8 cosmetic, 1.9 stylistic) |
| 2 — Cleanup | 8 | 6 | 2 (json.loads duplicate, consolidate list_windows) |
| 3 — Settings | 4 | 3 | 1 (QTimer hygiene, optional) |
| 4 — Packaging | 3 | 2 | 1 (PyInstaller spec) |
| 5 — Documentation | 3 | 2 | 1 (port validation doc — no settings.md exists) |
| **Total** | **28** | **18** | **10** |
