# DesktopOCR Pre-Release Plan — Corrected Final

> **Based on:** Independent evaluation of the original plan
> **Corrections applied:**
> - ❌ Lock fix: Replaced dangerous `asyncio.Lock` suggestion with safe atomic assignment
> - ❌ Removed sequential translation concern (already handled in existing code)
> - All other claims verified against source and retained
>
> **✅ Completed 2026-05-02:** Zero-risk cleanup (Phases 2-4 partially) — see checkmarks below

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

### 1.2 Fix user guide path for PyInstaller compatibility

**File:** [`ui/main_window.py`](ui/main_window.py:175)

**Why:** `pathlib.Path("docs/user_guide.html")` is relative to the current working directory. In a PyInstaller `--onefile` build, CWD may not be the executable directory. Use `__file__` with `sys._MEIPASS` fallback.

**Change:**
```python
# Before (line 175):
self._user_guide_path = pathlib.Path("docs/user_guide.html")

# After:
import sys
_base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).parent.parent))
self._user_guide_path = _base / "docs" / "user_guide.html"
```

### 1.3 Add `paddle_line_count` try/except guard

**File:** [`main.py:320`](main.py:320)

**Why:** `int(settings_state.get("paddle_line_count", 3) or 3)` will raise `ValueError` if the saved value is a non-integer string (e.g., corrupted `settings.json`).

**Change:**
```python
# Before:
saved_line_count = max(1, min(5, int(settings_state.get("paddle_line_count", 3) or 3)))

# After:
try:
    saved_line_count = max(1, min(5, int(settings_state.get("paddle_line_count", 3) or 3)))
except (ValueError, TypeError):
    saved_line_count = 3
```

### 1.4 Add port range validation in `side_menu.py`

**File:** [`ui/side_menu.py:1162-1170`](ui/side_menu.py:1162)

**Why:** Port is coerced to `int` but not validated to 1-65535. Invalid ports are emitted silently.

**Change:**
```python
# Before:
port = int(raw)

# After:
port = int(raw)
if port < 1 or port > 65535:
    port = 8765
    self._anki_port_edit.setText(str(port))
```

Or simpler: add a `QIntValidator(1, 65535)` to `_anki_port_edit` in the constructor so invalid input is rejected at edit-time.

### 1.5 Add port range clamping in `load_settings()`

**File:** [`main.py:88-89`](main.py:88)

**Why:** Type guard exists for `anki_port` but no range clamp. Corrupted settings can set port 0 or 99999.

**Change:**
```python
# After the isinstance check (line 88-89):
if not isinstance(settings.get("anki_port"), int):
    settings["anki_port"] = 8765
# Add:
if not 1 <= settings.get("anki_port", 8765) <= 65535:
    settings["anki_port"] = 8765
```

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

### 5.1 Update README

- Clarify Auto-translate is for Anki card creation only
- Add note about TTS audio attachment to Anki cards
- Add "verify add-on code on AnkiWeb" note

### 5.2 Update user_guide.html

- Mark EasyOCR as optional (`pip install` if needed)
- Fix any stale references

### 5.3 Add port validation note to settings documentation

---

## Progress Summary

| Phase | Total | ✅ Done | ⬜ Remaining |
|-------|-------|---------|--------------|
| 0 — Lock fix | 1 | 0 | 1 (blocked — needs Code mode) |
| 1 — Safety | 5 | 1 | 4 |
| 2 — Cleanup | 8 | 6 | 2 (json.loads duplicate, consolidate list_windows) |
| 3 — Settings | 4 | 3 | 1 (QTimer hygiene, optional) |
| 4 — Packaging | 3 | 2 | 1 (PyInstaller spec) |
| 5 — Documentation | 3 | 0 | 3 |
| **Total** | **24** | **12** | **12** |
