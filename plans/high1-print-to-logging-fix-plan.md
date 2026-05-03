# HIGH-1 Fix Plan: `print()` → `logger.*()` Migration in Frozen Build

## Background

**Issue:** [`DesktopOCR.spec:50`](DesktopOCR.spec:50) sets `console=False`, meaning the frozen (PyInstaller) build has **no console window**. Every `print()` call silently does nothing — output goes to `/dev/null`.

**Root cause:** `print()` was used for debug logging, user-facing output (OCR results, engine status, window enumeration), and TTS diagnostics. When `console=False`, all of it is invisible.

**Key finding:** The logging infrastructure **already exists** at [`main.py:246-247`](main.py:246):
```python
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
```

So the root logger is already configured. The fix is purely mechanical: `print()` → `logger.info/warning/error/debug()`.

---

## Scope: Files to Modify

### 1. [`main.py`](main.py) — Already has `import logging`, `logging.basicConfig`, `logger`

| Line(s) | Current `print()` | New Log Call | Category | Notes |
|---------|-------------------|-------------|----------|-------|
| 217 | `print("Available engines:")` | `logger.info(...)` | Non-GUI `--list-engines` | |
| 218-219 | `print(f"- {engine_id}")` | `logger.info(...)` | Non-GUI `--list-engines` | Loop body |
| 222 | `print("Engine status:")` | `logger.info(...)` | Non-GUI `--list-engine-status` | |
| 235 | `print(f"- {engine_id}: state={state}...")` | `logger.info(...)` | Non-GUI `--list-engine-status` | Loop body |
| 1357 | `print(f"\n[{timestamp}] [{engine_id}] [Conf: {conf:.2f}] {text}")` | `logger.info(...)` | GUI capture loop — OCR result | |
| 1399 | `print(".", end="", flush=True)` | **KEEP as `print()`** | Progress dot | Cosmetic, not data |
| 1443-1446 | `print(f"\n[{timestamp}] ...")` | `logger.info(...)` | Non-GUI `--show-canvas` OCR result | |
| 1448 | `print(".", end="", flush=True)` | **KEEP as `print()`** | Progress dot | Cosmetic, not data |
| 1465-1468 | `print(f"\n[{timestamp}] ...")` | `logger.info(...)` | Non-GUI `--raw-ocr` OCR result | |
| 1471 | `print(".", end="", flush=True)` | **KEEP as `print()`** | Progress dot | Cosmetic, not data |
| 1480 | `print("\nCleaning up resources...")` | `logger.info(...)` | `finally` block | |
| 1491 | `print("Stopped.")` | `logger.info(...)` | `finally` block | |
| 1525 | `print("ERROR: Install PyQt6 or PyQt5")` | **KEEP as `print()`** | Early-exit before `main()` | Logging NOT configured yet at this point |

**Progress dots rationale:** `print(".", end="", flush=True)` at lines 1399, 1448, 1471 show inline progress in terminal mode. Converting to `logger.info(".")` would add `\n`, timestamps, and log level prefix — making them useless as progress indicators. They are cosmetic (not informational), so keeping them as `print()` is acceptable — they gracefully no-op in frozen build.

### 2. [`core/win_utils.py`](core/win_utils.py:1) — Needs `import logging` + `logger`

| Line(s) | Current `print()` | New Log Call | Notes |
|---------|-------------------|-------------|-------|
| 36 | `print("--- Visible Windows ---")` | `logger.info(...)` | |
| 40 | `print(f"HWND: {hwnd:<10} (0x{hwnd:08X}) \| Title: {safe_title}")` | `logger.info(...)` | Loop body |
| 41 | `print("-----------------------")` | `logger.info(...)` | |

**Add at top:** `logger = logging.getLogger(__name__)`

### 3. [`tts/manager.py`](tts/manager.py:1) — Needs `import logging` + `logger`

| Line(s) | Current `print()` | New Log Call | Notes |
|---------|-------------------|-------------|-------|
| 24 | `print(f"[TTSManager] Switching backend: {self.active.name} -> {name}")` | `logger.debug(...)` | Debug/trace |
| 28 | `print(f"[TTSManager] speak() active backend: {self.active.name}")` | `logger.debug(...)` | Debug/trace |
| 73 | `print(f"[TTSManager] set_voice() received: {voice_id}")` | `logger.debug(...)` | Debug/trace |
| 76 | `print(f"[TTSManager] Parsed backend={backend_name}, voice={real_id}")` | `logger.debug(...)` | Debug/trace |
| 79 | `print(f"[TTSManager] Active backend now: {self.active.name}")` | `logger.debug(...)` | Debug/trace |

**Add at top:** `import logging; logger = logging.getLogger(__name__)`

### 4. [`tts/openjtalk_backend.py`](tts/openjtalk_backend.py:1) — Needs `import logging` + `logger`

| Line(s) | Current `print()` | New Log Call | Notes |
|---------|-------------------|-------------|-------|
| 14 | `print("[TTS] OpenJTalkBackend initialized")` | `logger.info(...)` | One-time init |
| 25 | `print(f"[TTS] Cleaned text: '{cleaned[:50]}'")` | `logger.debug(...)` | Debug/trace |
| 32 | `print(f"[TTS] OpenJTalk voice set to: {voice_id}")` | `logger.debug(...)` | Debug/trace |
| 36 | `print(f"[TTS] OpenJTalk rate set to: {self._rate}")` | `logger.debug(...)` | Debug/trace |
| 40 | `print(f"[TTS] OpenJTalk volume set to: {self._volume}")` | `logger.debug(...)` | Debug/trace |
| 44 | `print("[TTS] OpenJTalk: no text to speak")` | `logger.info(...)` | Notice |
| 47 | `print(f"[TTS] OpenJTalk raw input: {text[:60]}...")` | `logger.debug(...)` | Debug/trace |
| 54 | `print(f"[TTS] g2p phonemes: {phonemes[:80]}...")` | `logger.debug(...)` | Debug/trace |
| 56 | `print(f"[TTS] g2p failed: {e}")` | `logger.warning(...)` | Warning |
| 62 | `print(f"[TTS] pyopenjtalk.tts() failed: {e}")` | `logger.error(...)` | Error |
| 82 | `print("[TTS] Saved last_tts.wav for inspection")` | `logger.info(...)` | Notice |
| 84 | `print(f"[TTS] WAV save failed (scipy not installed?): {e}")` | `logger.warning(...)` | Warning |
| 90 | `print(f"[TTS] sd.play() failed: {e}")` | `logger.error(...)` | Error |

**Add at top:** `import logging; logger = logging.getLogger(__name__)`

### 5. [`tts/voicevox_backend.py`](tts/voicevox_backend.py:1) — Needs `import logging` + `logger`

| Line(s) | Current `print()` | New Log Call | Notes |
|---------|-------------------|-------------|-------|
| 8 | `print("[TTS] VoiceVox speak:", text)` | `logger.debug(...)` | Debug/trace — VoiceVox is a stub |

**Add at top:** `import logging; logger = logging.getLogger(__name__)`

### 6. [`tts/coeiroink_backend.py`](tts/coeiroink_backend.py:1) — Needs `import logging` + `logger`

| Line(s) | Current `print()` | New Log Call | Notes |
|---------|-------------------|-------------|-------|
| 52 | `print(f"[COEIROINK] Voice style set to: {voice_id}")` | `logger.debug(...)` | Debug/trace |
| 77 | `print("[COEIROINK] Internal Server Error (invalid speaker/style?)")` | `logger.warning(...)` | Warning |
| 87 | `print("[COEIROINK] Engine not running")` | `logger.warning(...)` | Warning |
| 90 | `print(f"[COEIROINK] Error: {e}")` | `logger.error(...)` | Error |

**Add at top:** `import logging; logger = logging.getLogger(__name__)`

---

## Files NOT Modified (out of scope)

These files have `print()` calls but are **not shipped in the frozen build** (test scripts, dev tools):

| File | Print count | Reason |
|------|-------------|--------|
| `tests/test_capture.py` | 10+ | Test only, not in frozen build |
| `tests/test_engine_smoke.py` | 4 | Test only, not in frozen build |
| `tests/test_translation.py` | 20+ | Test only, not in frozen build |
| `tests/test_imports.py` | multiple | Test only, not in frozen build |
| `tools/clean_jp_freq.py` | multiple | Standalone tool, not in frozen build |
| `scripts/analyze_density_boost.py` | multiple | Standalone script, not in frozen build |
| `benchmark_models.py` | multiple | Standalone benchmark, not in frozen build |
| `validate_models.py` | multiple | Standalone validation, not in frozen build |

---

## Risk Assessment

| Axis | Rating | Rationale |
|------|--------|-----------|
| Bug Risk | **MEDIUM** | All `print()` output invisible in frozen build. Users cannot see OCR results, error messages, window enumeration, or TTS diagnostics. |
| Fix Risk | **LOW** | Each replacement is one-line mechanical. The logging infrastructure already exists (`logging.basicConfig` at [`main.py:246`](main.py:246)). No behavior change — just `print()` → `logger.*()`. No code logic changes. |
| Regression Risk | **LOW** | If logging is somehow misconfigured, users see nothing — same as status quo. Worst case: fix has no effect (still invisible). Can't break functionality. |

**Verdict: Fix NOW** (not CAREFULLY — lower risk than previously assessed because `logging.basicConfig` already exists)

---

## Execution Order

| Step | File | Operation | Lines Changed |
|------|------|-----------|--------------|
| 1 | `core/win_utils.py` | Add `import logging; logger = logging.getLogger(__name__)` at top | +2 lines |
| 2 | `core/win_utils.py` | Replace 3 `print()` calls with `logger.info()` | 3 lines |
| 3 | `tts/manager.py` | Add `import logging; logger = logging.getLogger(__name__)` at top | +2 lines |
| 4 | `tts/manager.py` | Replace 5 `print()` calls with `logger.debug()` | 5 lines |
| 5 | `tts/openjtalk_backend.py` | Add `import logging; logger = logging.getLogger(__name__)` at top | +2 lines |
| 6 | `tts/openjtalk_backend.py` | Replace 13 `print()` calls with appropriate `logger.*()` calls | 13 lines |
| 7 | `tts/voicevox_backend.py` | Add `import logging; logger = logging.getLogger(__name__)` at top | +2 lines |
| 8 | `tts/voicevox_backend.py` | Replace 1 `print()` call with `logger.debug()` | 1 line |
| 9 | `tts/coeiroink_backend.py` | Add `import logging; logger = logging.getLogger(__name__)` at top | +2 lines |
| 10 | `tts/coeiroink_backend.py` | Replace 4 `print()` calls with appropriate `logger.*()` calls | 4 lines |
| 11 | `main.py` | Replace 8 `print()` calls with `logger.info()` (excluding 4 progress dots + 1 early-exit error) | 8 lines |
| 12 | Verification | Run Python syntax check on all 6 modified files | — |
| 13 | Acceptance test | Run `python main.py --list-engines` and verify output appears via logging | — |

**Total: ~45 line changes across 6 files**

---

## Log Level Mapping Convention

| Old `print()` context | New log level | Rationale |
|-----------------------|---------------|-----------|
| OCR result, engine status, cleanup messages | `logger.info()` | User-facing operational output |
| TTS init, "no text to speak", WAV saved | `logger.info()` | Notice-level events |
| TTS debug trace, phonemes, voice set, cleaned text | `logger.debug()` | Internal diagnostics, verbose |
| Recoverable errors (g2p failed, WAV save failed, COEIROINK offline) | `logger.warning()` | Non-fatal issues user should know about |
| Fatal errors (sd.play failed, tts() failed) | `logger.error()` | Operation failures that may affect UX |
| Progress dots (`.`, end="", flush=True) | **Keep as `print()`** | Cosmetic, not informational. Gracefully no-ops in frozen build |
| Early-exit error before `main()` | **Keep as `print()`** | Logging not configured yet |

---

## Potential Pitfalls

1. **`logging.basicConfig` is a no-op if called after any logging has occurred.** It already runs at [`main.py:246`](main.py:246), before any `logger.*()` calls. Safe.

2. **`tts/` modules use `print("[TTS] ...")` prefix.** With `logger`, the format string handles this: `%(name)s` will show `tts.openjtalk_backend` — more informative than `[TTS]`.

3. **Line 1525 `print("ERROR: Install PyQt6 or PyQt5")`** — This runs in the `__main__` block before `main()` is called, and before `logging.basicConfig()` is set up. If we want this to use logging, we'd need to move `basicConfig()` earlier (e.g., module level or first thing in `__main__`). **Recommendation:** Keep as `print()` — in frozen build, PyQt6/PyQt5 is bundled, so this path is never reached. In dev mode, `print()` works fine.

4. **`list_windows()` is called at [`main.py:261`](main.py:261), BEFORE `logging.basicConfig` at line 246?** Wait — line 261 is AFTER line 246. So `logging.basicConfig` is already set when `list_windows()` executes. Good.

5. **The `print(".", end="", flush=True)` progress dots** in the non-GUI paths (lines 1399, 1448, 1471) are inside loops — each prints a single `.` to indicate progress. Converting these to `logger.info(".")` would flood logs with useless dot entries. **Keep as `print()`** — they gracefully no-op in frozen build.
