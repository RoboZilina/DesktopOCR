# DesktopOCR v1.0.0-rc5 — Release Notes

## New in This Release

### Recapture Button Force Flag
- **Recapture button now works correctly when auto-capture is enabled** — previously, clicking the recapture button while auto-capture was active would not force a fresh capture because the MD5 frame-diff gate always returned `None` for unchanged frames. The recapture button now sets a `_recapture_requested` flag that bypasses the frame-diff check, guaranteeing a fresh capture even on static/transparent windows
- **Diagnostic logging added** to trace the recapture button flow through `_on_recapture()`, `capture_once()`, and `get_frame()`

### COEIROINK TTS — Anki Audio Fix
- **Fixed missing COEIROINK audio from Anki cards** — the `generate()` method was not implemented (only `speak()` existed), so Anki cards were created without audio when using the COEIROINK backend. Added `generate()` that calls the COEIROINK API, saves WAV bytes to a temp file, and returns the path for the card builder
- **Refactored** `speak()` and `generate()` to share a common `_call_api()` helper, reducing code duplication

### Diagnostic Logging Improvements
- **Per-box recognition logging in `--debug-once` mode** — each detection box is now individually recognized and logged with its score, recognition confidence, text, and crop dimensions. Helps diagnose recognition model issues for specific VNs
- **Detection score logging** in the PaddleOCR pipeline — scores are logged at multiple stages (raw detection output, box filtering, pre-recognition gate, recognition groups) to trace where boxes are dropped
- **BitBlt/WinRT path logging** in `get_frame()` — logs which capture path is used and the returned frame shape
- **Zero client area diagnostics** in `_capture_bitblt()` — when BitBlt returns zero client area, the code now queries `GetWindowPlacement()` and `IsWindowVisible()` to determine if the window is minimized, hidden, or genuinely zero-sized

### Code Quality
- All diagnostic logging is additive — no logic changes to existing code paths
- Recapture force flag logic is consistent across manual and auto-capture modes

## Files Changed

| File | Change |
|------|--------|
| `main.py` | Version bump to `1.0.0-rc5`; added `_recapture_requested` flag and force logic in `_ocr_task()`; added per-box recognition logging to `--debug-once` |
| `core/capture.py` | Added WINDOWPLACEMENT diagnostic logging in `_capture_bitblt()`; added BitBlt/WinRT path logging in `get_frame()` |
| `core/capture_pipeline.py` | Added `force` parameter to `capture_once()` with diagnostic logging |
| `core/engine_manager.py` | Added diagnostic logging at multiple pipeline stages (detection scores, box filtering, pre-recognition gate, recognition groups) |
| `core/ocr_engine.py` | Added detection score diagnostic logging |
| `tts/coeiroink_backend.py` | Added `generate()` method; refactored `speak()` and `generate()` to share `_call_api()` helper |
| `docs/release-notes-v1.0.0-rc5.md` | This file |

## Upgrade Notes

- **No settings migration needed** — all changes are internal logic and diagnostic logging. Existing `settings.json` files are fully compatible
- **Recapture button behavior** now works identically regardless of whether auto-capture is enabled or disabled. Clicking recapture always forces a fresh capture and OCR pass
- **COEIROINK users** will now get audio on Anki cards automatically (no configuration change needed)
