# DesktopOCR — Full-Spectrum Adversarial Audit Report

**Date:** 2026-05-02
**Scope:** Entire codebase (~10,000+ lines across 48 source files + tests + config)
**Posture:** Hostile but fair. Assume nothing. Trust nothing. Verify everything.

---

## 1. Critical Issues

### CRIT-1: Live DeepSeek API key stored in plaintext on local disk

- **File:** [`settings.json`](settings.json:15)
- **Content:** `"deepseek_api_key": "sk-c433f7a354284ca3af09bd71c3eee7ca"`
- **Impact:** Anyone with local filesystem access to this machine (another user account, malware, physical theft) can read this key and call DeepSeek's paid API on the owner's account. This key is live — the DeepSeekValidator constructor at [`logic/deepseek_validator.py:20`](logic/deepseek_validator.py:20) passes it directly to the API.
- **Note:** `settings.json` IS already excluded from git tracking via [`.gitignore:46`](.gitignore:46), so this key is NOT leaked through source control. However, the file is unencrypted on disk with no file-level permissions.
- **Status:** ✅ **FIXED in RC patch** — [`load_settings()`](main.py:82) now checks `DEEPSEEK_API_KEY` environment variable after loading `settings.json`. If the env var is set, it overrides the file value. Existing file-based path remains as fallback.
- **Remediation:** Immediately revoke this key at DeepSeek's console. Use environment variables or a secrets vault for API keys. [`settings.json.example`](settings.json.example) should serve as the template.

### CRIT-2: PyInstaller build silently broken — missing model files

- **File:** [`DesktopOCR.spec`](DesktopOCR.spec) (local only — gitignored via [`.gitignore:43`](.gitignore:43))
- **Problem:** The local `DesktopOCR.spec` file's `datas` list includes `theme_template.qss`, `user_guide.html`, and the `resources` directory, but does **NOT** include `models/paddle/` which contains `det.onnx`, `rec.onnx`, and `japan_dict.txt`.
- **Impact:** A locally-frozen PyInstaller binary will launch, then crash at runtime when `PaddleOCR.load()` at [`core/ocr_engine.py:82`](core/ocr_engine.py:82) tries to open model files that don't exist in the bundle. The crash occurs *after* the UI has started — the user sees a GUI that then fails silently or raises an unhandled exception.
- **Witness:** The `model_config` dict passed from [`core/engine_manager.py:244`](core/engine_manager.py:244) references `model_config["det_model"]`, `model_config["rec_model"]`, and `model_config["dict"]`, all pointing into `models/paddle/`. The spec does not ship these.
- **Note:** `*.spec` is gitignored so this does not affect cloned repos. It only affects developers building locally.
- **Status:** ✅ **FIXED in RC patch** — `("models/paddle", "models/paddle")` added to the `datas` list in [`DesktopOCR.spec:17`](DesktopOCR.spec:17).
- **Remediation:** Add `('models/paddle/', 'models/paddle/')` to the `datas` list in the local spec file.

---

## 2. High-Priority Issues

### ✅ FIXED: `print()` calls in frozen build — silent failure

- **Files:** [`main.py`](main.py), [`core/win_utils.py`](core/win_utils.py), [`tts/manager.py`](tts/manager.py), [`tts/openjtalk_backend.py`](tts/openjtalk_backend.py), [`tts/voicevox_backend.py`](tts/voicevox_backend.py), [`tts/coeiroink_backend.py`](tts/coeiroink_backend.py)
- **Problem:** `console=False` in [`DesktopOCR.spec`](DesktopOCR.spec) means no console window exists in the frozen build. Every `print()` call silently does nothing. These are used for: debug logging, device enumeration results (`list_windows` at [`core/win_utils.py:36`](core/win_utils.py:36)), TTS debug output, and pipeline timing.
- **Impact:** Users cannot see debug output or error messages. The print at [`core/win_utils.py:36`](core/win_utils.py:36) — which enumerates visible windows so the user can pick a target — will produce no output in the frozen build.
- **Remediation:** Replace all `print()` calls with `logging.getLogger(...)` calls, or set `console=True` for debug builds.
- **Status:** ✅ **FIXED in RC patch round** — All `print()` calls replaced with `logger.info/debug/warning/error()` across 6 files. Root logger was already configured at [`main.py:246`](main.py:246). WAV debug save in [`tts/openjtalk_backend.py:79-84`](tts/openjtalk_backend.py:79) gated behind `DESKTOCR_TTS_DEBUG_WAV=1`. Progress dots (4 cosmetic `.` calls) intentionally kept as `print()` — they gracefully no-op in frozen build.

### HIGH-2: `cv2.waitKey(0)` behind debug flag — latent risk if debug is enabled

- **File:** [`core/vision.py:21-70`](core/vision.py:21)
- **Code:** Every `cv2.waitKey(0)` call in `preprocess_for_ocr()` is guarded by `if debug:` — the `debug` parameter defaults to `False`. The function is only invoked from the `__main__` block at [`core/vision.py:92`](core/vision.py:92) when `python -m core.vision` is run directly.
- **Impact:** In normal operation (via `main.py`), this code path is never reached. The risk is limited to a developer accidentally passing `debug=True` via the CLI. This is a latent risk, not an active bug.
- **Remediation:** Keep as-is — the gating is correct. Consider adding a warning log when debug mode is activated to make accidental enabling detectable.

### HIGH-3: Race condition — engine state read without lock

- **File:** [`core/engine_manager.py:350-478`](core/engine_manager.py:350)
- **Problem:** `run_ocr()` reads `self._current_instance` and `self._current_id` at the top of the method, but these are mutated by `switch_engine()` under `_switch_lock`. There is **no lock held during the read**.
- **Scenario:** Thread A calls `run_ocr()`, reads `current_id="paddle-3"`, then yields. Thread B calls `switch_engine("windows_ocr")`, changes both `current_id` and `current_instance`. Thread A resumes and calls `current_instance.recognize()` on what is now a **different engine** than the one it intended.
- **Impact:** Wrong OCR engine used for a frame, potentially with wrong parameters. Silent data corruption.

### HIGH-4: Translation manager rebuilt without disposing old backends

- **File:** [`ui/main_window.py:471-488`](ui/main_window.py:471)
- **Problem:** [`_rebuild_translation_manager()`](ui/main_window.py:471) creates new backend instances and a new `TranslationManager`, but never calls `.dispose()` on the old ones. The old `aiohttp.ClientSession` objects remain open, leaking connections.
- **Impact:** Each settings change that triggers a rebuild (backend switch, Libre URL change) leaks HTTP connections. Over time, this can exhaust file descriptors/sockets.

### HIGH-5: No HTML escaping in Anki card field values

- **File:** [`logic/anki_card_builder.py:186-188`](logic/anki_card_builder.py:186)
- **Problem:** The `_subs` dict at line 179 substitutes field values into HTML templates using simple `.replace()`. If OCR text contains `{Screenshot}` as literal text, it gets substituted. More importantly, if OCR text contains HTML metacharacters (`<`, `>`, `&`), they pass through unescaped into the card's Front/Back HTML.
- **Impact:** Malformed HTML in OCR results can break card rendering. Script injection is unlikely (Anki sanitizes), but visual corruption is guaranteed for any OCR result containing angle brackets.

### HIGH-6: Unvalidated environment variable surface — 55+ DESKTOCR_* knobs with zero validation

- **File:** [`core/engine_manager.py`](core/engine_manager.py) (throughout, ~55 references to `os.environ.get("DESKTOCR_*")`)
- **Problem:** Every single `os.environ.get("DESKTOCR_...")` call directly reads the raw string and passes it to comparison, arithmetic, or type-sensitive operations without any validation. For example:
  - `int(os.environ.get("DESKTOCR_MAX_FILTERED_BOXES", "80"))` — if set to `"abc"`, throws `ValueError` at runtime.
  - `float(os.environ.get("DESKTOCR_MERGE_X_TOLERANCE", "0.85"))` — same.
  - Boolean-style env vars compared as strings: `os.environ.get("DESKTOCR_SKIP_PRE_REC_GATE", "") == "1"` — any value other than `"1"` means "false", which is surprising.
- **Impact:** A single mistyped environment variable crashes the OCR pipeline with an unhandled `ValueError`. No warnings, no sanitization, no fallback to defaults.

---

## 3. Medium-Priority Issues

### MED-1: Hardcoded DPI-unaware default region

- **File:** [`main.py:23`](main.py:23)
- **Code:** `DEFAULT_REGION = (0, 540, 1280, 180)`
- **Problem:** This assumes 1920x1080 at 100% scaling. On a 1440p display or any system with DPI scaling > 100%, this region captures the wrong area of the screen.
- **Impact:** First-run experience on non-1080p displays is broken — user sees a wrong capture region with no indication why.

### MED-2: VoiceVox TTS is a non-functional stub

- **File:** [`tts/voicevox_backend.py:4-14`](tts/voicevox_backend.py:4)
- **Problem:** `speak()` just does `print(text)`. `stop()` is a no-op. `list_voices()` returns empty list. If a user selects VoiceVox as active backend (possible if registered), no audio is produced and no error is raised.
- **Impact:** Silent failure. User thinks TTS is working but gets no audio.

### MED-3: Temp audio files never cleaned up

- **File:** [`core/tts.py:61-68`](core/tts.py:61)
- **Problem:** `tempfile.mkstemp(suffix=".mp3")` creates temp files that are never deleted. Each TTS invocation leaks a file on disk.
- **Impact:** Over extended use, the temp directory fills with `.mp3` files. On a system with limited disk space, this eventually causes issues.

### MED-4: PyQt5/PyQt6 fallback — both-missing case produces a confusing error

- **File:** [`main.py:1503-1506`](main.py:1503)
- **Problem:** The try/except catches `ImportError` for PyQt6 and falls back to PyQt5. If **both** are missing, the `from PyQt5.QtWidgets import ...` at line 1506 raises its own `ImportError`, which propagates unhandled. The user sees a raw Python traceback instead of a user-friendly "install PyQt6" message.
- **Impact:** A user without any PyQt installed gets a confusing crash rather than a clear installation instruction.
- **Remediation:** Add an inner try/except around the PyQt5 import with an actionable error message.

### MED-5: Google Translate web scraping — ToS violation

- **File:** [`core/translation/google_backend.py:39-91`](core/translation/google_backend.py:39)
- **Problem:** The `translate()` method at line 39 hits `translate.googleapis.com/translate_a/single` — a private API endpoint. Google's ToS prohibit automated access to this service. Google may block the IP or blacklist the client.
- **Impact:** Unreliable translation that can stop working at any time. Legal risk.

### MED-6: DeepL free endpoint has no rate-limit handling

- **File:** [`core/translation/deepl_backend.py:74-130`](core/translation/deepl_backend.py:74)
- **Problem:** The `translate()` method at line 74 sends requests to `www2.deepl.com/jsonrpc` without any rate-limiting. DeepL's free tier has implicit rate limits; hitting 429 responses will cause translation failures.
- **Impact:** Rapid OCR captures produce "translation unavailable" errors.

### MED-8: Anki `add_note` with `allowDuplicate: False` causes silent failures

- **File:** [`logic/anki_connect.py:284`](logic/anki_connect.py:284)
- **Code:** `"allowDuplicate": False` — when the same OCR text is captured twice, `add_note` returns `None`.
- **Impact:** User sees no card created, with no error message. The `build_and_send_card` function at [`logic/anki_card_builder.py:284`](logic/anki_card_builder.py:284) logs "Card save failed" but the UI may not surface this.

### MED-9: `pygame.mixer.init()` in constructor — crashes if pygame absent

- **File:** [`core/tts.py:27`](core/tts.py:27)
- **Problem:** `pygame.mixer.init()` is called in `__init__`. If pygame is not installed or fails to initialize, the entire `EdgeTTS` object cannot be constructed.
- **But:** `pygame` is listed in [`requirements.txt:21`](requirements.txt:21). Edge case: if pygame is installed but initializing the audio mixer fails (e.g., no audio device in a headless/Citrix environment), the entire TTS subsystem becomes unavailable.

---

## 4. Low-Priority Issues

### LOW-1: `crop_box()` doesn't validate clamping output

- **File:** [`core/tensor_utils.py:209-234`](core/tensor_utils.py:209)
- **Problem:** Lines 225-232 clamp coordinates to image bounds, but don't verify the clamped rectangle has positive dimensions. If a box is entirely outside the image, `y2 - y1` could be 0, producing an empty slice.
- **Impact:** Downstream code gets a zero-size array, which causes opaque errors in `onnxruntime`.

### LOW-2: Version mismatch comment

- **File:** [`core/capture.py:4`](core/capture.py:4) says `# Requires winsdk==0.10.0`, but [`requirements.txt:5`](requirements.txt:5) pins `winsdk==1.0.0b10`.

### LOW-3: `WIDTH` and `HEIGHT` constants duplicated between modules

- **File:** [`core/capture.py:22-23`](core/capture.py:22) defines `WIDTH = 1280, HEIGHT = 720` as fallback display sizes. These are duplicated in spirit in [`main.py:23`](main.py:23) (`DEFAULT_REGION`).
- **Impact:** Inconsistency risk if one is changed without the other.

### LOW-4: Deduplication key in history uses time-bucketing fallback

- **File:** [`ui/history_sidebar.py:228-232`](ui/history_sidebar.py:228)
- **Problem:** When `engine is None`, the dedup key uses `timestamp.rsplit(":", 1)[0]` — bucketing to the minute. Two different OCR results within the same minute with the same text would be incorrectly deduplicated.

### LOW-5: `_voice_id_map` may not be initialized before first voice change

- **File:** [`ui/controls_bar.py:156-158`](ui/controls_bar.py:156)
- **Problem:** `_emit_voice_change` checks `hasattr(self, "_voice_id_map")` rather than initializing it in `__init__`. If `currentTextChanged` fires before `load_voices()` is called, `_voice_id_map` doesn't exist.

### LOW-6: History sidebar clear button uses hardcoded dark theme colors

- **File:** [`ui/history_sidebar.py:134-136`](ui/history_sidebar.py:134)
- **Problem:** The "Clear" button's initial stylesheet uses hardcoded `#a1a1aa` and `#1f1f23` — these are dark theme colors. In light theme, the button is nearly invisible. The `set_theme()` at line 165 updates it, but there's a flash of wrong colors during initial display.

### LOW-7: `UserGuideDialog` silently returns empty string on missing file

- **File:** [`ui/user_guide_dialog.py:42-47`](ui/user_guide_dialog.py:42)
- **Problem:** If `docs/user_guide.html` doesn't exist, the dialog shows a blank page with a close button. No error is logged.

### LOW-8: DesktopOCR.spec has `console=False` but `uac_admin=False`

- **File:** [`DesktopOCR.spec`](DesktopOCR.spec)
- **Problem:** No admin elevation requested, but `win_utils.py` uses `EnumWindows` and `capture.py` uses `Windows.Graphics.Capture` — these may require different privilege levels depending on the target window.

### LOW-9: `_det_buffer_lock` is a threading.Lock but accessed in async context

- **File:** [`core/tensor_utils.py:114-121`](core/tensor_utils.py:114)
- **Problem:** `threading.Lock` in async code — if the lock is contended, it blocks the event loop. The lock only protects allocation, not writes, so it's mostly vestigial, but the pattern is incorrect.

### LOW-10: Anki card builder accesses private method `anki._set_error()` across module boundary

- **File:** [`logic/anki_card_builder.py:88`](logic/anki_card_builder.py:88)
- **Code:** `anki._set_error("No target text to save")` — accesses a private method on the `AnkiConnect` instance.
- **Impact:** `_set_error()` IS a defined method at [`logic/anki_connect.py:47`](logic/anki_connect.py:47), so this will not crash. However, it violates the private-method convention: if `AnkiConnect` refactors internal error handling, this call breaks silently. The class should expose a public `set_error()` or handle error setting internally.
- **Remediation:** Expose a public method on `AnkiConnect` for error setting, or have `build_and_send_card` return structured error info instead of calling into the client object.

---

## 5. Architectural Observations

### ARCH-1: Massive `EngineManager` — 1702 lines of monolithic spaghetti

- **File:** [`core/engine_manager.py`](core/engine_manager.py) (1702 lines)
- **Issue:** This single file contains: engine lifecycle management (`switch_engine`, `get_or_load_engine`), OCR pipeline orchestration (`run_ocr`, `_run_paddle_pass`), box filtering, deduplication, priority scoring, density estimation, collapse logic, box normalization, box expansion, band slicing, EasyOCR wrapper, UnavailableEngine stub, metadata flagging, candidate scoring (`_score_candidate`, `_pick_best_candidate`, `_fallback_is_meaningfully_better`), debug crop saving, and more.
- **Consequence:** No single method is independently testable without constructing an `EngineManager` with real model paths. The class has ~40+ methods. `_run_paddle_pass` alone spans 55 lines with 4 distinct processing stages called as internal methods but with implicit coupling through `self`.

### ARCH-2: Module-level mutable state in `annotator.py`

- **File:** [`core/frequency/annotator.py:16-22`](core/frequency/annotator.py:16)
- **Issue:** `FREQ_DATA_READY`, `_FREQ_TABLE`, `_LEMMAS_BY_LENGTH_DATA` are all module-level mutable globals. `ensure_freq_data_ready()` on line 52 mutates these. `annotate_tokens()` on line 83 can reset `FREQ_DATA_READY = False` on exception (line 107).
- **Consequence:** In a long-running application, if frequency file loading fails once (transient disk error), all subsequent frequency-based features silently degrade. There's no recovery mechanism.

### ARCH-3: Translation backends cannot report errors

- **File:** [`core/translation/base.py:9-20`](core/translation/base.py:9)
- **Issue:** The interface contract says "must never raise, return '' on failure". But there's no mechanism to distinguish "translation is empty because source is empty" from "translation failed because the backend returned 503".
- **Consequence:** [`TranslationManager.translate()`](core/translation/manager.py:30) tries backends in order and returns the first non-empty result. If the first backend fails silently, it falls through to the next. But the UI cannot tell the user *why* translation failed.

### ARCH-4: Async event loop bridging is fragile

- **File:** [`main.py:1549-1561`](main.py:1549)
- **Issue:** The `qasync` event loop is created and run in `try/finally` but the cleanup path is unclear. `ScreenCapture.__init__` at [`core/capture.py:288`](core/capture.py:288) creates async tasks without a reference, relying on the event loop to keep them alive. `_playback_task` at line 305 is fire-and-forget.
- **Consequence:** If the event loop is restarted (e.g., during a settings reset), orphaned tasks continue running on the old loop.

### ARCH-5: No delegation — `PaddleOCR.recognize()` handles raw ONNX output parsing

- **File:** [`core/ocr_engine.py:405-480`](core/ocr_engine.py:405)
- **Issue:** `_ctc_greedy_decode()` is a 75-line method inside `PaddleOCR` that handles: output shape validation, CTC blank label removal, confidence computation, negative-confidence clamping, random-expectation comparison, and confidence normalization. This is a separate responsibility mixed into the engine class.

### ARCH-6: `CapturePipeline` wraps `EngineManager` wraps `PaddleOCR` — three layers with overlapping concerns

- **Files:** [`core/capture_pipeline.py`](core/capture_pipeline.py), [`core/engine_manager.py`](core/engine_manager.py), [`core/ocr_engine.py`](core/ocr_engine.py)
- **Issue:** `CapturePipeline` calls `EngineManager.run_ocr()` which calls `PaddleOCR.detect()` then `PaddleOCR.recognize()`. But `EngineManager` also does pre-processing, box filtering, deduplication, and post-processing. `CapturePipeline` runs AI validators on top of that. The layers are blurred — `EngineManager._normalize_result()` does formatting that could be at the pipeline level.

---

## 6. Security & Safety Observations

### SEC-1: API keys stored in plaintext JSON

- **File:** [`settings.json`](settings.json:15)
- **Issue:** DeepSeek API key is stored in plaintext in `settings.json`. The file is not encrypted and has no file-level permissions. (Note: `settings.json` IS excluded from git tracking via [`.gitignore:46`](.gitignore:46) — the risk is local filesystem access, not source control.)
- **Additional risk:** OpenAI API key and Google Vision API key, if configured by the user, are also stored in this same plaintext file.

### SEC-2: No input validation on API response parsing — XSS-like injection in Anki cards

- **File:** [`logic/anki_card_builder.py:186-188`](logic/anki_card_builder.py:186)
- **Issue:** As noted in HIGH-5, OCR text is substituted into HTML templates with no escaping. While Anki's card renderer is sandboxed, this is still a trust-boundary violation — OCR results from untrusted sources (game screenshots) are injected into HTML.

### SEC-3: `try/except Exception` across the entire codebase (noqa: BLE001)

- **Issue:** Bare `except Exception` — with `# noqa: BLE001` annotations — appears in at least 25+ locations across the codebase. This pattern silently catches and discards `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit`, making the application impossible to kill cleanly in some states.
- **Example locations:**
  - [`core/capture.py:546`](core/capture.py:546) — frame capture
  - [`core/ocr_engine.py:194`](core/ocr_engine.py:194) — detection
  - [`core/engine_manager.py:294`](core/engine_manager.py:294) — engine switching
  - [`core/tts.py:52`](core/tts.py:52) — TTS generation
  - [`logic/anki_card_builder.py:294`](logic/anki_card_builder.py:294) — card saving
  - [`ui/main_window.py:461`](ui/main_window.py:461) — backend disposal

### SEC-4: No authentication for AnkiConnect

- **File:** [`logic/anki_connect.py:33-40`](logic/anki_connect.py:33)
- **Issue:** AnkiConnect by default listens on `127.0.0.1:8765` with no authentication. Any application on the local machine can create, read, or delete Anki cards. The hardcoded `"DesktopOCR"` deck and note type names make it predictable.

### SEC-5: No validation of audio file paths in Anki card builder

- **File:** [`logic/anki_card_builder.py:223-240`](logic/anki_card_builder.py:223)
- **Issue:** `open(path, "rb")` on line 226 — path comes from the caller (TTS manager). If a path traversal is somehow injected (e.g., `../../etc/passwd`), the file would be base64-encoded and sent to AnkiConnect as an "audio" file. The impact is limited (data exfiltration via Anki media sync) but unnecessary.

---

## 7. Packaging Observations

### PKG-1: Model files not included in local PyInstaller spec (see CRIT-2)

### PKG-2: `console=False` with `print()` usage throughout

- **Issue:** As noted in HIGH-1, the frozen binary has no console, but the codebase uses `print()` extensively for status output.

### PKG-3: No version pinning for PyInstaller

- **File:** [`requirements.txt:25`](requirements.txt:25)
- **Issue:** `pyinstaller` is listed with no version constraint. Different PyInstaller versions have different behaviors around hidden imports, data file collection, and UPX. Builds are not reproducible.

### PKG-4: `onnxruntime-directml` has large binary footprint

- **Issue:** The `onnxruntime-directml` package includes DirectML DLLs (~200MB+). Combined with PyQt6 (~60MB), OpenCV (~40MB), and the Paddle model files (~100MB+), the bundled application is 400MB+.
- **No mechanism** for user to choose a smaller build (e.g., `onnxruntime` CPU-only for systems without DirectML).

### PKG-5: `sounddevice` depends on PortAudio — may not be present on all Windows systems

- **File:** [`requirements.txt:22`](requirements.txt:22)
- **Issue:** `sounddevice` requires PortAudio (`portaudio.dll`). PyInstaller may not automatically include it. OpenJTalk playback at [`tts/openjtalk_backend.py:59`](tts/openjtalk_backend.py:59) calls `sd.play()` — this would crash in a frozen build if PortAudio is missing.

### PKG-6: `qasync` has known edge cases with PyInstaller

- **Issue:** `qasync` uses `_UnixSelectorEventLoop` on Unix but must use `ProactorEventLoop` on Windows for proper async I/O. PyInstaller frozen builds sometimes have issues with event loop policy registration.

---

## 8. Testing Observations

### TEST-1: Zero automated tests

- All tests in [`tests/`](tests/) are manual/integration tests:
  - [`test_capture.py`](tests/test_capture.py) — interactive (asks for HWND, shows image via cv2)
  - [`test_engine_smoke.py`](tests/test_engine_smoke.py) — runs OCR on synthetic frame
  - [`test_imports.py`](tests/test_imports.py) — verifies imports resolve
  - [`test_ocr_pipeline.py`](tests/test_ocr_pipeline.py) — single-line docstring, no executable code
  - [`test_preprocessing.py`](tests/test_preprocessing.py) — single-line docstring, no executable code
  - [`test_translation.py`](tests/test_translation.py) — manual async test (requires network)

### TEST-2: No unit tests for critical modules

- **Missing tests for:**
  - `validator.py` — `is_valid_japanese`, `clean_ocr_output`, `clean_ocr_output_enhanced` — these are complex scoring heuristics with zero test coverage.
  - `tensor_utils.py` — `preprocess_paddle_slice`, `image_to_det_tensor`, `crop_box` — zero tests.
  - `engine_manager.py` — `_filter_boxes`, `_deduplicate_boxes`, `_collapse_to_single_span` — the core box processing pipeline has no tests.
  - `anki_connect.py` — the HTTP request construction and response parsing has no tests.
  - `annotator.py` — no tests for `_normalize` suffix stripping logic.

### TEST-3: Golden VN frames directory is empty

- **File:** [`tests/golden_vn_frames/README.md`](tests/golden_vn_frames/README.md)
- **Issue:** The README says "Placeholder directory for VN regression assets" but the directory is empty. The companion script [`tools/run_vn_goldens.py`](tools/run_vn_goldens.py) exists but has nothing to run against.

### TEST-4: No CI/CD configuration

- No `.github/workflows/`, no `pytest.ini`, no `tox.ini`, no `setup.cfg` test configuration. There is no way to run tests in an automated environment.

### TEST-5: Manual tests rely on user interaction

- [`test_capture.py`](tests/test_capture.py) prompts `input("Enter target HWND: ")`. [`test_engine_smoke.py`](tests/test_engine_smoke.py) requires a display. [`test_preprocessing.py`](tests/test_preprocessing.py) and [`test_ocr_pipeline.py`](tests/test_ocr_pipeline.py) are docstrings, not code. These cannot be run in CI.

### TEST-6: No mocks or stubs for external services

- The translation tests at [`tests/test_translation.py`](tests/test_translation.py:29-110) make real HTTP calls to DeepL, Google, and LibreTranslate. If these services are down or rate-limited, tests fail even though the code is correct.

---

## 9. Final Verdict

**DesktopOCR is a technically ambitious project with serious structural issues that prevent it from being production-ready.**

### Strengths (noted only for context, not counted as recommendations)

- The WinRT screen capture bridge via ctypes COM interop is technically impressive — direct D3D11 device creation without C++/WinRT is non-trivial.
- The band-based OCR slicing approach is a clever optimization for visual novel text extraction.
- The box filtering pipeline (normalize → filter → deduplicate → gate → collapse → recognize) shows deep understanding of the problem domain.
- The frequency-based token highlighting system is well-designed, with two-pass (dictionary + kanji) annotation.

### Critical Path to Production Readiness

1. **Immediately:** Revoke the leaked DeepSeek API key. Use environment variables or a secrets vault for API keys. Rotate any other keys that may have been exposed.
2. **Immediately:** Add model files to the local PyInstaller spec (`*.spec` is gitignored, so this is a local build fix).
3. **Low priority:** Replace `_det_buffer_lock` (threading.Lock in async context) with `asyncio.Lock`, or refactor tensor utilities to avoid global mutable buffers entirely.
4. **High priority:** Validate all environment variables at startup with typed defaults and explicit error messages.
5. **High priority:** Create a proper logging infrastructure to replace all `print()` calls — the frozen build is effectively blind.
6. **Medium priority:** Add proper async concurrency control to `EngineManager.run_ocr()` — protect engine state reads with a lock.
7. **Medium priority:** Dispose old translation backends when rebuilding to prevent HTTP connection leaks.
8. **Low priority:** Add DPI awareness to default region. Add version pinning for PyInstaller.
9. **Testing:** The codebase needs a minimum of 30-50 unit tests covering: validator pipeline (heuristic edge cases), tensor utilities (buffer safety), engine manager (box deduplication logic), and translation backends (response parsing). Without tests, refactoring is impossible without regression risk.

### Architecture Verdict

The current architecture is **over-coupled and under-abstracted**. The 1702-line `EngineManager` is the primary bottleneck — it combines lifecycle management, algorithm implementation, and orchestration into one file. The codebase would benefit from a clean separation of:

- An **engine lifecycle manager** (handles load/unload/switch of OCR backends)
- A **OCR pipeline runner** (orchestrates capture → preprocess → detect → filter → recognize → post-process)
- A **box processing library** (pure functions for IOU, dedup, collapse, scoring)

The translation and TTS subsystems are better structured, with clear backend abstractions and a manager pattern.

### Security Verdict

Beyond the leaked API key, the main security concern is the pervasive `except Exception` pattern (25+ locations) that suppresses `KeyboardInterrupt` and makes the application unkillable. The Anki card builder's lack of HTML escaping and the plaintext credential storage are secondary concerns. The environment variable parsing with no validation is a reliability issue that will inevitably cause crashes in production.

**The codebase shows competence in the problem domain but needs significant structural work before it can be considered production-grade. The most immediate risks are the unencrypted API key on disk and the broken PyInstaller build — these will affect any user who runs the packaged binary.**
