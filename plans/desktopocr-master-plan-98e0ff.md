# DesktopOCR Master Plan

Consolidated roadmap from Stage 1 through Stage 11, incorporating all completed work and planned features including TTS, translation, and quality improvements identified during the web app comparison.

---

## Completed Stages

### Stage 1 — Window Picker Dialog
- `ui/window_picker.py` — `WindowPickerDialog` for interactive HWND selection
- `ui/overlay.py` — `select_window()` crosshair overlay
- **Status:** ✅ Complete

### Stage 2 — Live Preview
- `ui/preview_widget.py` — `PreviewWidget` with `QLabel` + `QPixmap`, deque frame feed, 50ms polling timer
- **Status:** ✅ Complete

### Stage 3 — Snipping Overlay
- `ui/selection_overlay.py` — `SelectionOverlay` with click-drag region selection
- Coordinate transform from widget-space to frame-space
- `PreviewWidget` exposes `frame_size` property + overlay child widget
- **Status:** ✅ Complete

### Stage 4 — qasync Event Loop
- Replace `asyncio.run()` + `QApplication.processEvents()` hack with `qasync.QEventLoop`
- `asyncio.Event` + task cancellation for clean GUI shutdown
- Windows `SIGINT` handler: `signal.signal(signal.SIGINT, _handle_sigint)`
- `RuntimeError` catch for expected `loop.stop()` on shutdown
- **Status:** ✅ Complete

### Stage 5 — Header Controls Bar
- `ui/controls_bar.py` — `ControlsBar` widget (engine selector, mode placeholder, auto-capture toggle)
- `set_engine()` with `blockSignals(True)` for programmatic init
- `engine_changed` → `asyncio.ensure_future(engine_manager.switch_engine())`
- `capture_toggled` → `auto_capture` bool in capture loop scope
- **Status:** ✅ Complete

---

## Current / Next

### Stage 5b — Real-Time Preview + Change-Detection Auto-Capture
**Goal:** Decouple preview cadence from OCR cadence; trigger OCR on frame change, not fixed timer.

**Changes to `main.py`:**
- Split single `_capture_loop()` into two concurrent async tasks:
  - `_preview_task()` — `await capture.get_frame(full=True)` every `PREVIEW_INTERVAL` (0.25s), pushes to `frame_queue`
  - `_ocr_task()` — event-driven via `asyncio.Event`, blocked until preview signals change
- `_compute_diff()` — mean absolute pixel diff with `int16` subtraction (avoids uint8 wraparound)
- `DIFF_THRESHOLD = 8.0` — module-level constant, 0–255 scale
- `PREVIEW_INTERVAL = 0.25` — preview capture interval
- `STABILIZE_DELAY = 0.5` — wait 500ms after last detected change before firing OCR (prevents mid-transition garbage)
- Stabilization: cancel/restart timer on successive changes; only fire after steady state

**Toggle behavior:**
- ON: change-detect OCR ("Auto-capture: change detect")
- OFF: fixed 1.5s interval OCR ("Auto-capture: fixed 1.5s")
- Preview always live regardless of toggle state

**Status:** 🔄 In progress — stabilization delay implemented, generation counter pending

---

## Planned Stages

### Stage 6 — History Panel
**Goal:** Scrollable OCR result log with timestamps, mirroring web app's `historyContent`.

**UI:** Add a panel below or beside the preview showing previous OCR results with:
- Timestamp
- Engine ID
- Confidence
- Text snippet (click to expand full text)

**Implementation:**
- `QListWidget` or `QTextEdit` (read-only, append-only)
- Max entries (e.g., 100), auto-scroll to latest
- Click to copy text to clipboard

**Status:** ⏳ Planned

---

### Stage 6b — Translation Tray
**Goal:** Machine translation or dictionary lookup displayed alongside history.

**Options:**
- DeepL API (best quality, requires key)
- Google Translate API (requires key)
- Sugoi Translator (local, offline, purpose-built for VNs)
- Jisho API lookup (free, word-by-word)

**UI:** Second column next to history panel, or tabbed view. Show original + translated text.

**Status:** ⏳ Planned

---

### Stage 6c — TTS (Text-to-Speech)
**Goal:** Speak OCR result and/or translation output, with multiple backend options.

**Backends (in priority order):**

| Backend | Quality | Internet | Cost | Notes |
|---|---|---|---|---|
| **edge-tts** | Excellent — neural voices | Required | Free | Best Japanese quality, Microsoft Edge voices, async-native. **Primary recommendation.** |
| **voicevox** | Excellent — native Japanese neural | Offline | Free | Local server, purpose-built for Japanese, character voices. Used by VN industry. Most authentic for VN readers. |
| **OpenAI TTS** | Excellent | Required | Paid | `tts-1` / `tts-1-hd`, requires API key |
| **ElevenLabs** | Best overall | Required | Paid | Most natural, multilingual, requires API key |
| **gTTS** | Good | Required | Free | Google TTS, mp3 output, adds playback dependency |
| **pyttsx3** | Poor — SAPI5 | Offline | Free | Fallback when no internet. Robotic Japanese voice. Last resort. |

**Implementation approach:**
- Primary: `edge-tts` — best free quality, async-native, zero setup
- Offline fallback: `voicevox` — if local server running; auto-detect on port 50021
- Optional paid: OpenAI / ElevenLabs behind API key field in settings
- Last resort: `pyttsx3` — always available, acceptable for non-Japanese

**UI:**
- TTS backend selector (`QComboBox`)
- Voice selector (populated dynamically per backend)
- Speak button + auto-speak toggle (speak every new OCR result automatically)
- Placed in ControlsBar or Settings panel

**Status:** ⏳ Planned

---

### Stage 7 — Mode Selector (Proper Pipeline Mode API)
**Goal:** Runtime mode switching with proper API in `CapturePipeline`.

**Current state:** Mode is set via env vars at startup (`DESKTOCR_RAW_OCR_MODE`, etc.) — not runtime-switchable.

**Target:**
- `CapturePipeline.set_mode(mode_id: str)`
- `CapturePipeline.available_modes()` → list of mode IDs
- Modes: `baseline-reset`, `raw`, `light-preprocess`, etc.
- ControlsBar mode combo becomes enabled and functional

**Blocked by:** Pipeline refactor to move flags from env vars to instance state.

**Status:** ⏳ Planned (deferred from Stage 5)

---

### Stage 8 — Settings Persistence
**Goal:** JSON config file saving user preferences across restarts.

**Saved settings:**
- Last selected region (`x, y, w, h`)
- Last selected engine
- `DIFF_THRESHOLD`
- `PREVIEW_INTERVAL`
- TTS backend + voice
- Auto-capture toggle state
- Window position/size

**File:** `config.json` in app directory (e.g., `%APPDATA%/DesktopOCR/config.json` or local)

**Status:** ⏳ Planned

---

### Stage 9 — Pipeline Quality Improvements
**Goal:** Strengthen OCR output quality beyond current basic validator.

**Items:**
1. **Generation counter / stale trigger prevention** — increment `_capture_gen` on each trigger, check after `capture_once()` returns; discard results from superseded captures. Prevents race conditions when rapid changes occur.
2. **Text density scoring** — `scoreJapaneseDensity()` equivalent: calculate ratio of Japanese characters vs. total. Discard output below threshold (indicates wrong region, blank frame, UI noise).
3. **Validator improvements** — more robust `_apply_validator_assist()`: repeated character detection, length heuristics, confidence gating.

**Status:** ⏳ Planned

---

### Stage 10 — Translation Dictionary
**Goal:** Word-by-word lookup from OCR output.

**Components:**
- Word segmentation: `fugashi` (MeCab wrapper) or `SudachiPy` for Japanese
- Dictionary source: JMdict (local SQLite) or Jisho API (online)
- UI panel showing words + definitions inline

**Complexity:** High — word segmentation is non-trivial dependency. Self-contained feature.

**Status:** ⏳ Planned

---

### Stage 11 — Polish
**Goal:** Quality-of-life improvements and performance hardening.

**Items:**
- Keyboard shortcuts (Ctrl+C copy last result, Ctrl+Space toggle capture, etc.)
- Re-select / Reset region button
- Engine memory eviction — unload heavy engines (e.g., MangaOCR ~1.2GB) when switching away
- Performance instrumentation — optional timing logs for preprocess / inference / postprocess
- Promise deduplication on engine switch — queue or deduplicate rapid engine selector clicks
- Per-engine preprocessing registry — move preprocess/postprocess into engine adapters rather than pipeline-level flags

**Status:** ⏳ Planned

---

## Deferred / Not Planned

| Feature | Reason |
|---|---|
| Multi-pass Tesseract with voting | DesktopOCR uses PaddleOCR which already outperforms Tesseract on Japanese. Marginal gain for significant complexity. |
| Browser SpeechSynthesis equivalent | Replaced by Stage 6c TTS with superior options (edge-tts, voicevox). |

---

## File Index

| File | Purpose |
|---|---|
| `main.py` | Entry point, argument parsing, GUI/CLI mode, qasync loop, capture tasks |
| `ui/preview_widget.py` | Live preview QLabel with deque polling |
| `ui/selection_overlay.py` | Click-drag region selection overlay |
| `ui/controls_bar.py` | Engine selector, mode placeholder, auto-capture toggle |
| `ui/window_picker.py` | HWND list dialog |
| `ui/overlay.py` | Crosshair window selection |
| `core/capture.py` | `ScreenCapture` — WinRT + BitBlt fallback |
| `core/capture_pipeline.py` | `CapturePipeline` — OCR orchestration |
| `core/engine_manager.py` | `EngineManager` — engine registry, switch, normalize |
| `core/ocr_engine.py` | `PaddleOCR` — detect + recognize |
| `core/windows_ocr.py` | `WindowsOCR` — guarded Windows OCR path (stub) |
| `ui/components.py` | `StatusBar` — engine, FPS, confidence, title |
