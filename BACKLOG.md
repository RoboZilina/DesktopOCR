# DesktopOCR — Known Issues & Backlog

Issues discovered during reviews that are **not currently fixed**. Ordered by severity.
Resolved items are moved to a separate section at the bottom.

---

## High Severity

### COM reference leak in D3D11 device creation
- **File**: [`core/capture.py:88-104`](core/capture.py:88-104)
- **Issue**: `p_device` and `p_context` returned by `D3D11CreateDevice` are never `Release()`'d. Only the temporary `dxgi_device_ptr` is released. Leaks two COM references per capture session.
- **Impact**: Minor — capture session is created once per app lifetime.
- **Reported**: 2026-05-03 review

### `get_or_load_engine()` can infinite-loop
- **File**: [`core/engine_manager.py:313-318`](core/engine_manager.py:313-318)
- **Issue**: If `meta["state"] == "loading"` but `meta["task"]` is `None` (e.g., a task setter crashed between `state=loading` and task assignment), it sleeps 50 ms and recurses indefinitely.
- **Impact**: Stack overflow on extremely rare crash timing.
- **Reported**: 2026-05-03 review

---

## Medium Severity

### TranslationManager lock race condition
- **File**: [`core/translation/manager.py:38-41`](core/translation/manager.py:38-41)
- **Issue**: `if self._lock.locked(): return ""` is a TOCTOU race. Between checking `locked()` and entering `async with self._lock:`, another task can acquire the lock. Two tasks can both pass the check, resulting in duplicate translation work.
- **Impact**: Low — duplicate work, no crash.
- **Reported**: 2026-05-03 review

### `_rebuild_translation_manager()` fire-and-forget dispose race
- **File**: [`ui/main_window.py:469-486`](ui/main_window.py:469-486)
- **Issue**: Creates a task `asyncio.create_task(self._dispose_translation_manager(old_manager))` but never awaits it. If `_rebuild_translation_manager()` is called twice in quick succession, old backends from the first rebuild are still being disposed while the second rebuild creates new ones. Sessions can be closed while in-flight requests reference them.
- **Impact**: Low — errors are caught by backend try/except blocks.
- **Reported**: 2026-05-03 reviewer evaluation (item #2 from first batch)

### Cursor restoration swaps selection direction
- **File**: [`ui/transcription_tray.py:460-462`](ui/transcription_tray.py:460-462)
- **Issue**: When restoring the text cursor after highlighting, `cursor.setPosition(saved_anchor)` then `cursor.setPosition(saved_pos, KeepAnchor)` always uses `saved_anchor` as the anchor point. If the user selected right-to-left (anchor > position), the restored selection has its anchor and position swapped, moving the caret to the opposite end.
- **Impact**: Low — visual only, selection content unchanged.
- **Reported**: 2026-05-03 review

---

## Low Severity

### `_get_session()` race in MyMemoryBackend / GoogleTranslateBackend
- **File**: [`core/translation/mymemory_backend.py:34-38`](core/translation/mymemory_backend.py:34-38) and [`core/translation/google_backend.py`](core/translation/google_backend.py)
- **Issue**: `_get_session()` is not async and not lock-protected. If two coroutines race when `_session is None`, both pass the `None` check and create separate sessions. One session leaks (never closed) because only the last-assigned one is tracked.
- **Impact**: Low — caught by exception handlers in all callers, no crash. One aiohttp session leaks per race event (~a few KB + connection pool).
- **Reported**: 2026-05-04 review (safe-port-to-main audit)
- **Note**: Both backends share this pattern; fixing one should fix both for consistency.

### Redundant digit check in `_normalize_rank`
- **File**: [`ui/transcription_tray.py:471-478`](ui/transcription_tray.py:471-478)
- **Issue**: `if stripped.isdigit(): return int(stripped)` already returns for pure digit strings. The immediately following `try: return int(stripped)` can never succeed (digits already handled) and will never raise for non-digits (isdigit was already false). Dead code.
- **Impact**: None — dead code, no behavioral impact.
- **Reported**: 2026-05-03 review

### Speak/Translate buttons don't strip selection whitespace
- **File**: [`ui/transcription_tray.py:147-161`](ui/transcription_tray.py:147-161)
- **Issue**: `self._sel_text.toPlainText() or self._ocr_text.toPlainText()` — if the selection is whitespace-only (`"   "`), it's truthy, so it's used instead of falling back to the full OCR text. Should use `.strip()`.
- **Impact**: Low — edge case where whitespace-only selection is spoken/translated instead of full OCR text.
- **Reported**: 2026-05-03 review

### `openai_validator.cost_estimate_chars` accessed without None-guard
- **File**: [`main.py:1372`](main.py:1372)
- **Issue**: `window.side_menu.update_openai_usage(openai_validator.cost_estimate_chars)` is called without checking if `openai_validator` is `None`. If OpenAI is not configured, this would crash the OCR loop.
- **Note**: The property exists on the class (set in `__init__`), but the variable itself could be `None`.
- **Impact**: Depends on whether `openai_validator` can be `None` at this point.
- **Reported**: 2026-05-03 review

---

## Infrastructure

### `build.ps1` hard-codes `.venv` path
- **File**: [`build.ps1`](build.ps1)
- **Issue**: The build script assumes the virtual environment is always named `.venv` and located in the project root. This breaks in CI/CD or on machines with a different venv setup.
- **Reported**: 2026-05-03 reviewer evaluation

---

## Reliability / Fragility

### Google Translate free endpoint is undocumented/unofficial
- **File**: [`core/translation/google_backend.py`](core/translation/google_backend.py)
- **Issue**: Uses `translate.googleapis.com/translate_a/single` — an undocumented internal API. Could break at any time if Google changes the endpoint format or adds stricter rate-limiting. No SLA.
- **Impact**: Auto-mode falls back to MyMemory if Google breaks (ArgosTranslate was not ported to `main`).
- **Noted**: Design known since initial translation implementation.

### TranslationManager silently drops concurrent requests
- **File**: [`core/translation/manager.py:38-41`](core/translation/manager.py:38-41)
- **Issue**: The non-blocking lock check (`if self._lock.locked(): return ""`) intentionally skips translation if one is already in flight. This means rapid OCR cycles can silently drop translation updates. The user sees stale text without any notification.
- **Impact**: OCR updates quickly but translation may lag behind silently.
- **Noted**: Design known since initial implementation.

### `settings.json` load doesn't validate field types
- **File**: [`main.py:73-143`](main.py:73-143)
- **Issue**: `load_settings()` wraps the entire parse in try/except but doesn't validate individual field types. A corrupted settings.json (e.g., string where int expected) loads defaults silently with no warning to the user.
- **Impact**: User settings lost without notification on corruption.
- **Noted**: Ongoing.

### `settings.json.example` may be out of sync
- **File**: `settings.json.example`
- **Issue**: The example file may not reflect all current settings keys or default values, making it unreliable as a reference.
- **Noted**: Ongoing — not verified against actual `settings.json` schema.

---

## Development & Infrastructure

### Limited automated test coverage for cloud translation backends
- **Issue**: `mymemory_backend.py` and `google_backend.py` have no unit tests. `tests/test_translation.py` exercises the full pipeline but only with live API calls (no mocking).
- **Risk**: Regressions in cloud API backends (session handling, response parsing) go undetected without internet.

### No crash reporting in release builds
- **Issue**: The Nuitka build produces a console-less GUI EXE (`--windows-console-mode=disable`). Any unhandled exception is silently swallowed — the app window disappears with no diagnostic trace.
- **Risk**: Post-release bugs are invisible to the developer.

---

## Stub / Not Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| VoiceVox TTS | Stub | `__init__` only, no implementation |
| OpenJTalk TTS | Partial | Requires MeCab on PATH — doesn't work on most Windows setups |
| LibreTranslateBackend | Dead | File kept on disk but module is not imported anywhere; not ported to `main` |
| DeepLBackend | Dead | File kept on disk but not imported anywhere; replaced by MyMemory on `main` |
| ONNX INT8 quantization | Pending | Models are graph-optimized but still FP32 |
| Anki "auto-translate" | Pending | UI control exists but not wired to translation pipeline |
| ONNX Runtime CUDA/TensorRT | Pending | Currently uses DirectML only |

---

## Low Severity

### `hasattr` check for TTS `generate()` is always `True`
- **File**: [`main.py:1060`](main.py:1060)
- **Issue**: `hasattr(tts_backend, "generate")` is always `True` because the base class [`TTSBackend`](tts/base.py:9) defines a default `generate()` that returns `None`. The `if path:` guard catches the `None` return correctly, but the `hasattr` check provides no useful signal — it can't distinguish between a proper override (EdgeTTS) and the base default (VoiceVox, OpenJTalk).
- **Impact**: None — the `if path:` guard works correctly. Cosmetic code clarity issue.
- **Reported**: 2026-05-10 Anki pipeline review

### TTS temp files never cleaned up after card creation
- **File**: [`core/tts.py:69`](core/tts.py:69), [`tts/coeiroink_backend.py:67`](tts/coeiroink_backend.py:67)
- **Issue**: Temp files created by `tempfile.mkstemp()` are never deleted. The comment in `core/tts.py:64-67` explains they can't be deleted immediately (multiple `generate()` calls before the card builder reads them). After the card builder reads them at [`logic/anki_card_builder.py:200`](logic/anki_card_builder.py:200), they could be cleaned up but aren't.
- **Impact**: Minor disk leak — files accumulate in `%TEMP%` over long sessions. Windows temp cleanup or reboot handles this.
- **Reported**: 2026-05-10 Anki pipeline review

---

## Resolved

| Issue | Resolved | Notes |
|-------|----------|-------|
| `docs/BUILD.md` embedded `build.bat` stale (missing `--include-data-file=icon.ico=icon.ico`, had `--lto=yes`) | 2026-05-04 | Synced with actual `build.bat` during safe-port-to-main |
| `icon.ico` missing in project root (no app icon) | 2026-05-04 | Generated from `icon-512.png` via Pillow during safe-port-to-main |
| `MyMemoryBackend._session` eager init — crashes after `dispose()` | 2026-05-04 | Changed to lazy `None` init + `None`-safe check in `_get_session()` |
| `main_window.py` missing `QIcon` import + `setWindowIcon()` — no taskbar icon in Nuitka builds | 2026-05-04 | Added `QIcon` import, `setWindowIcon()` block after `setWindowTitle()` |
| `main_window.py` `label_map` had `"deepl"` instead of `"mymemory"` — incorrect display label | 2026-05-04 | Corrected to `"mymemory": "MyMemory"` |
| `build.ps1` lacks MSVC detection and icon support (superseded by `build.bat`) | 2026-05-04 | Deprecated `build.ps1` with header pointing to `build.bat` |
| COEIROINK TTS `generate()` missing — Anki cards created without audio | 2026-05-10 | Added `generate()` method that saves WAV to temp file and returns path. Also refactored `speak()` to share `_call_api()` helper. |
| Recapture button does not force fresh capture when auto-capture is enabled | 2026-05-10 | Added `_recapture_requested` flag consumed before trigger wait; passes `force=True` to `capture_once()` → `get_frame()` to bypass MD5 frame-diff gate |
