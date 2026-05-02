# Pre-Release Plan — Independent Evaluation

**Evaluator:** Roo (Architect mode)
**Source files checked:** `main.py`, `logic/anki_connect.py`, `core/tensor_utils.py`, `core/ocr_engine.py`, `core/capture.py`, `ui/transcription_tray.py`, `ui/theme.py`, `ui/theme_template.qss`, `ui/side_menu.py`, `ui/controls_bar.py`, `ui/main_window.py`, `tts/manager.py`, `requirements.txt`, `settings.json.example`, `tests/test_imports.py`, `tests/test_capture.py`
**Status per claim:** Verified against actual source code on disk

---

## 1. Viability Rating

| Category | Verdict |
|----------|---------|
| Safe to execute as-is | ~70% of items |
| Requires correction before execution | 1 item (Critical Lock fix is dangerously wrong) |
| Already handled by existing code | 1 item (sequential translation) |
| Would accept as-is despite concerns | Remainder |

---

## 2. Claim-by-Claim Verification

### Section 1: Code Cleanup

| # | Claim | Source Truth | Verdict |
|---|-------|-------------|---------|
| 1 | `main.py:113` `_compute_diff` is dead `pass` stub | ✅ Confirmed at [`main.py:113-115`](main.py:113) — comment says "Removed per C-1". Nothing references it. | **✅ Valid — safe to remove** |
| 2 | `list_windows()` duplicated in `tests/test_capture.py` | ✅ Confirmed. [`main.py:170-199`](main.py:170) and [`tests/test_capture.py:13-42`](tests/test_capture.py:13) are ~95% identical (print formatting differs slightly). | **✅ Valid — consolidate into `core/win_utils.py`** |
| 3 | `pyperclip` unused in requirements.txt | ✅ Confirmed. `search_files` found zero `import pyperclip` or `from pyperclip` across all `.py` files. App uses `QApplication.clipboard()`. | **✅ Valid — safe to remove** |
| 4 | `pyttsx3` unused in requirements.txt | ✅ Confirmed. Zero imports found. | **✅ Valid — safe to remove** |
| 5 | `import threading` between constants in `tensor_utils.py:12` | ✅ Confirmed. [`core/tensor_utils.py:12`](core/tensor_utils.py:12) is between `DET_LIMIT_SIDE_LEN` (line 11) and `DET_BUFFER` (line 14). However, `_det_buffer_lock = threading.Lock()` on line 16 does need the import, so moving it up is purely cosmetic (PEP8). | **✅ Valid but cosmetic** |
| 6 | `ocr_engine.py` excessive blank lines | ✅ Confirmed. Every import at [`core/ocr_engine.py:1-13`](core/ocr_engine.py:1) has a blank line between them. 14 lines where 3 would suffice per PEP8. | **✅ Valid — PEP8 formatting** |
| 7 | Duplicate `json.loads(body)` in `anki_connect.py:146` | ✅ Confirmed. `body` was already built at [`logic/anki_connect.py:79`](logic/anki_connect.py:79) from `json.dumps(payload)`. The `action` string is accessible from the outer `_request` scope as the `action` parameter. The re-parse at line 146 is redundant. | **✅ Valid — micro-optimization** |
| 8 | `test_imports.py` omits newer modules | ✅ Confirmed. List at [`tests/test_imports.py:16-24`](tests/test_imports.py:16) includes only 7 core/logic modules. Missing: `logic.anki_connect`, `logic.anki_card_builder`, `tts.manager`, `core.translation.*`, `core.capture_pipeline`. | **✅ Valid — add modules** |

### Section 2: Safety and Correctness

| # | Priority | Claim | Source Truth | Verdict |
|---|----------|-------|-------------|---------|
| 1 | **Critical** | `threading.Lock` blocks event loop; switch to `asyncio.Lock` | ❌ **PARTIALLY TRUE diagnosis, WRONG solution.** The diagnosis that `_set_error` is called from async paths is correct (e.g., [`anki_connect.py:100`](logic/anki_connect.py:100)). However, `_set_error` is ALSO called from `_sync_post` at lines 153, 170-173 which runs via `run_in_executor` (thread pool). An `asyncio.Lock` would **CRASH** with `RuntimeError: cannot await from a non-async context` when the thread-pool worker calls `_set_error`. The `threading.Lock` is actually **required** here. The plan's suggested fix would **break Anki functionality**. | **🚨 DANGEROUS — Do not apply as written** |
| 2 | **High** | QTimer lambda creates un-awaited coroutines | ✅ Valid concern. [`main.py:1104-1106`](main.py:1104): `lambda: asyncio.create_task(_check_anki())` has no task reference. If `_check_anki` raises, "Task exception was never retrieved" warning appears. However, `_check_anki` only calls `anki.is_available()` and `anki.ensure_note_type()`, both of which catch exceptions internally, so in practice this is unlikely to trigger. | **✅ Valid — low probability but good hygiene** |
| 3 | **High** | Sequential translations may return empty due to manager lock | ❌ **FALSE — already handled.** The plan says "If the first translation is still in-flight, the second will return empty." But looking at [`main.py:1029-1034`](main.py:1029): the code is **already sequential** (`await` before second call). The comment at lines 1022-1025 explicitly acknowledges the lock issue and the sequential pattern is the mitigation. The plan author missed this. | **❌ Already handled — no fix needed** |
| 4 | **High** | `QWidget:has(> QLabel)` is invalid QSS | ✅ Confirmed at [`ui/theme_template.qss:152`](ui/theme_template.qss:152). Qt QSS does not support the `:has()` pseudo-class (CSS Selectors Level 4). It's silently ignored. | **✅ Valid — safe to remove** |
| 5 | **Medium** | No port range validation in `side_menu.py:1162-1170` | ✅ Confirmed. [`ui/side_menu.py:1162-1170`](ui/side_menu.py:1162): `int(raw)` catches non-numeric input but does not validate 1-65535. Port 0 or 99999 would be emitted. | **✅ Valid — easy fix with `QIntValidator`** |
| 6 | **Medium** | No port range clamping in `main.py:83` | ✅ Confirmed. [`main.py:88-89`](main.py:88) checks `isinstance(anki_port, int)` but doesn't clamp. | **✅ Valid — add range check** |
| 7 | **Medium** | `settings.json.example` defaults mismatch code defaults | ✅ Confirmed three mismatches: `"text_size": "standard"` vs `"medium"`, `"auto_read_selection": true` vs `false`, `"dictionary_pass_enabled": false` vs `true`. | **✅ Valid — align examples** |
| 8 | **Medium** | `sounddevice` not in requirements.txt but imported | ✅ Confirmed. [`tts/manager.py:36`](tts/manager.py:36): `import sounddevice as sd`, but no `sounddevice` entry in [`requirements.txt`](requirements.txt). Will crash with `ModuleNotFoundError` when TTS audio is played. | **✅ Valid — must add** |
| 9 | **Low** | `anki_card_builder.py:61-64` buffer concern | Plan says "no action needed." Confirmed — `buf.tobytes()` is safe for non-contiguous arrays. | **✅ Accept no-action** |
| 10 | **Low** | Translate button tooltip missing | ✅ Confirmed. The fix at [`ui/transcription_tray.py:157-159`](ui/transcription_tray.py:157) is already applied (uses OCR fallback). No tooltip exists. | **✅ Valid — polish item** |
| 11 | **Low** | `capture.py:596-598` ctypes fallback fragility | Plan says "acceptable." Confirmed — this is a deep fallback path unlikely to be hit with current winsdk. | **✅ Accept no-action** |

### Section 3: Configuration

| # | Claim | Verdict |
|---|-------|---------|
| 1 | `text_size: "standard"` invalid | ✅ Confirmed — change to `"medium"` |
| 2 | `auto_read_selection: true` ≠ default `False` | ✅ Confirmed — change to `false` |
| 3 | `dictionary_pass_enabled: false` ≠ default `True` | ✅ Confirmed — change to `true` |
| 4 | `text_size` guard doesn't log | ✅ Confirmed at [`main.py:83`](main.py:83) — no logging. Low-severity. |
| 5 | `anki_port` not range-checked | ✅ Confirmed — see Section 2 item 6 |
| 6 | Port edit no range enforcement | ✅ Confirmed — see Section 2 item 5 |
| 7 | `paddle_line_count` int cast without try/except | ✅ Confirmed at [`main.py:320`](main.py:320) — `int(settings_state.get("paddle_line_count", 3) or 3)` would crash on `"three"`. **However**, `load_settings()` at line 80 only copies keys present in `DEFAULT_SETTINGS`, so user can't inject arbitrary keys. But a corrupted `settings.json` could still crash. | **✅ Valid — wrap in try/except** |

### Section 4: Packaging

| # | Claim | Verdict |
|---|-------|---------|
| 1 | `nuitka` listed, needs `pyinstaller` | ✅ Valid |
| 2 | No `.spec` or build script | ✅ Valid — needs creation |
| 3 | `theme.py:69` QSS path is PyInstaller-safe | ✅ Confirmed — `Path(__file__).parent` handles `sys._MEIPASS` correctly. But should note this works because the QSS is a data file included via `--add-data`. |
| 4 | `main_window.py:175` relative path broken in PyInstaller | ✅ Confirmed — `pathlib.Path("docs/user_guide.html")` is relative to CWD, not `__file__`. Will **fail** in `--onefile` builds unless CWD happens to be the extraction dir. | **⚠️ Must fix — use `__file__` or `sys._MEIPASS`** |
| 5 | `.gitignore` gaps | ✅ Valid — `debug_crops/`, `debug_ocr/`, `run_logs/` not ignored |

### Section 5: Documentation

| # | Claim | Verdict |
|---|-------|---------|
| 1 | Speak btn no tooltip | ✅ Confirmed at [`ui/transcription_tray.py:142`](ui/transcription_tray.py:142) |
| 2 | Translate btn no tooltip | ✅ Confirmed at [`ui/transcription_tray.py:153`](ui/transcription_tray.py:153) |
| 3 | Menu btn no tooltip | ✅ Confirmed at [`ui/controls_bar.py:47`](ui/controls_bar.py:47) |
| 4-6 | README/User Guide updates | ✅ All valid suggestions |

---

## 3. Summary of Issues with the Plan Itself

| Issue | Severity |
|-------|----------|
| **❌ Section 2 Critical — Lock fix is dangerously wrong.** Switching `threading.Lock` to `asyncio.Lock` would crash the app because `_set_error` is called from `_sync_post` (thread-pool executor). `asyncio.Lock` cannot be acquired from a non-async context. The `threading.Lock` is actually **required** for the thread-pool path. | **🚨 HIGH — would break Anki** |
| **❌ Section 2 High — Sequential translation concern is already handled.** Code at main.py:1029-1034 is already sequential. Comment at 1022-1025 explains the lock-aware design. | **⚠️ LOW — wasted effort** |
| **ℹ️ `python -m` vs `python` for Windows** — The plan uses Unix paths (`c:\Users\...`) inconsistently and some commands assume bash. Minor. | **ℹ️ Informational** |

---

## 4. Risk Analysis by Execution Order

Here is the recommended execution order WITH risk annotations:

### Phase 1: Safety First (items that prevent crashes)

| Step | Item | Risk if done wrong | Actual risk |
|------|------|-------------------|-------------|
| 1 | **Add `sounddevice` to `requirements.txt`** | None (adding a dep) | 🟢 None |
| 2 | **Fix `main_window.py:175` user_guide_path** | Wrong path = guide won't open in PyInstaller | 🟢 Low — fallible but not crash |
| 3 | **Add `paddle_line_count` try/except** | None (narrow scope) | 🟢 None |
| 4 | **Add port range validation** | None (narrow scope) | 🟢 None |

### Phase 2: DO NOT DO THIS (unless corrected)

| Step | Plan's suggestion | What to do instead |
|------|------------------|-------------------|
| Lock fix | Switch to `asyncio.Lock` | **Use atomic attribute assignment.** The GIL protects single string writes to `self.last_error`. Replace `_set_error`/`_clear_error` with direct attribute access. `threading.Lock` is only needed if the thread-pool and async paths truly contend — but a single string write is atomic under CPython. |

### Phase 3: Cleanup (low risk, mechanical)

| Step | Item | Risk |
|------|------|------|
| 5 | Remove `_compute_diff`, `pyperclip`, `pyttsx3` | 🟢 None (dead code) |
| 6 | Move `import threading` to top of tensor_utils.py | 🟢 None |
| 7 | Remove duplicate `json.loads(body)` in anki_connect.py:146 | 🟢 None |
| 8 | Remove invalid QSS selector | 🟢 None (already ignored) |
| 9 | Fix ocr_engine.py PEP8 spacing | 🟢 None |
| 10 | Consolidate `list_windows()` into `core/win_utils.py` | 🟢 Low — import path must match |

### Phase 4: Settings/Cosmetic

| Step | Item | Risk |
|------|------|------|
| 11 | Fix settings.json.example defaults | 🟢 None |
| 12 | Add missing tooltips | 🟢 None |
| 13 | Expand test_imports.py module list | 🟢 None |

### Phase 5: Packaging

| Step | Item | Risk |
|------|------|------|
| 14 | Create PyInstaller spec | 🟡 Medium — must verify paths work in frozen build |
| 15 | Update .gitignore | 🟢 None |

---

## 5. Conclusion

**The plan is ~80% valid and well-researched, but contains one dangerously wrong fix and one already-addressed concern.**

The critical issue is the **Lock fix** (Section 2, Critical Item 1). The plan correctly identifies that `threading.Lock` can block the event loop, but its proposed solution (`asyncio.Lock`) would break the app because `_set_error` is also called from thread-pool workers. The correct fix is to use **atomic attribute assignment** (the GIL protects single string writes to `self.last_error`) since there's no compound operation that needs atomicity.

The sequential translation concern (Section 2, High Item 3) is already handled by existing code — the plan author simply missed the `await` between the two translate calls.

Everything else is safe to execute as written.
