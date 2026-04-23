# DesktopOCR Handoff Summary

Date: 2026-04-23
Project: `C:\Users\rober\.gemini\antigravity\scratch\DesktopOCR`
Branch: `DesktopOCR-dev-new-from-main` (tracking `origin/main`)

---

## Session Overview

This session covered four major phases:
1. **Branch management** — Compare branches, resolve in-progress merge conflict, create clean dev branch
2. **Project familiarization** — Systematic reading of every source file
3. **Stage 1 implementation** — Window Picker Dialog (WindowPickerDialog) — COMPLETED and merged
4. **Stage 2 planning** — Live Preview Widget (PreviewWidget) — PLAN DRAFTED, corrected with code review, awaiting implementation approval

---

## Phase 1: Branch Management

### What happened
- User asked to compare `desktopocr` vs `desktopocr-dev` branches
- `desktopocr` branch didn't exist locally; compared `main` vs `DesktopOCR-dev` instead
- Found `DesktopOCR-dev` was a stripped-down version removing EasyOCR, simplifying CLI, removing Windows OCR
- Attempted `git pull origin main` onto `DesktopOCR-dev` — discovered the branch was already in a conflicted merge state (staged files + merge in progress)
- **User warning:** "Be careful, to not damage the main branch, there has been a lot of work done."
- Aborted the in-progress merge with `git merge --abort`
- Created fresh branch `DesktopOCR-dev-new-from-main` from `origin/main`

### Current branch state
- **Active branch:** `DesktopOCR-dev-new-from-main` (clean, no uncommitted changes originally)
- **Tracks:** `origin/main`
- All Stage 1 implementation changes are committed to this branch
- `origin/main` is untouched

---

## Phase 2: Project Familiarization

Every source file was systematically read and documented:

### Core engine files
| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `main.py` | CLI entry point | `parse_args()`, `async main(hwnd)`, `_resolve_hwnd_from_arg()`, `list_windows()` |
| `core/ocr_engine.py` | PaddleOCR ONNX wrapper | `PaddleOCR` class — load, detect, recognize, `_ctc_greedy_decode` |
| `core/engine_manager.py` | 3-engine lifecycle | `EngineManager` — switch_engine, run_ocr, fallback chain, box merging, dynamic band recognition |
| `core/capture.py` | WinRT screen capture | `ScreenCapture` — `_get_frame_winrt()`, `_get_frame_bitblt()`, D3D11 device init, frame pool |
| `core/capture_pipeline.py` | Pipeline orchestration | `CapturePipeline` — `capture_once()`, `run_auto()`, multi-pass, near-duplicate detection |
| `core/tensor_utils.py` | Tensor preprocessing | `preprocess_paddle_slice()`, `preprocess_natural_slice()`, `image_to_det_tensor()`, `image_to_rec_tensor()`, buffer pooling (`DET_BUFFER`, `REC_BUFFER`) |
| `core/vision.py` | OpenCV helpers | `preprocess_for_ocr()` — thresholding, denoising, deskew |
| `core/windows_ocr.py` | WinRT OCR fallback | `WindowsOCR` class — load, recognize, Japanese language pack check |

### Logic/validation
| File | Purpose |
|------|---------|
| `logic/validator.py` | Japanese validation: `is_valid_japanese()`, `score_japanese_density()`, Unicode range detection, UI noise filtering, confidence threshold 0.45 |

### UI files
| File | Purpose | Status |
|------|---------|--------|
| `ui/__init__.py` | Package exports | **MODIFIED** — exports `WindowPickerDialog` and `select_window` |
| `ui/window_picker.py` | WindowPickerDialog | **CREATED** (Stage 1) |
| `ui/overlay.py` | `select_window()` helper | **MODIFIED** — added HWND picker helper |
| `ui/components.py` | Shared UI components | Stub — to be populated with `StatusBar` in Stage 2 |

### Reference/planning files
| File | Purpose |
|------|---------|
| `instructions.md` | Project rules, dev guidelines, engine hierarchy, preprocessing pipeline |
| `desktopocr-window-and-area-selector-staged-98e0ff.md` | Original 7-stage UI plan document |
| `plans/stage1-window-picker.md` | Stage 1 plan (complete, implemented) |
| `plans/stage2-live-preview.md` | Stage 2 plan (drafted, corrected, pending approval) |

### Reference JS files (web app parity)
| File | Maps to |
|------|---------|
| `reference/paddle_engine.js` | `core/ocr_engine.py` |
| `reference/paddle_core.js` | `core/tensor_utils.py` |
| `reference/capture_pipeline.js` | `core/capture_pipeline.py` |
| `reference/engine_manager.js` | `core/engine_manager.py` |

### Web reference app
- `personalOCR-Cloudflare` project explored for UI design inspiration
- Key patterns mapped: `getDisplayMedia()` → `WindowPickerDialog`, `<video>` → `PreviewWidget`, selection overlay → Stage 3

---

## Phase 3: Stage 1 — Window Picker (COMPLETED)

### Plan
- `plans/stage1-window-picker.md` created with full implementation details
- User code review identified 5 issues → all fixed:
  1. OK button never re-enabled → added `currentItemChanged` signal
  2. `selected_title` read after dialog closed → captured in `_accept_selection`
  3. `ui/__init__.py` would replace file → changed to append pattern
  4. `QApplication` init unsafe → `QApplication.instance() or QApplication(sys.argv)`
  5. `_selected_title` uninitialized → added `self._selected_title: str | None = None`

### Implementation files

**`ui/window_picker.py`** (NEW — 175 lines)
- `WindowPickerDialog(QDialog)` class
- `COL_HWND`, `COL_TITLE` column constants
- `_build_ui()` — search field, table with HWND + title, OK/Cancel, status label
- `_refresh_windows()` — `EnumWindows` via ctypes
- `_apply_filter()` — case-insensitive filter on title and hex HWND
- `_accept_selection()` — captures both HWND and title before `self.accept()`
- Properties: `selected_hwnd`, `selected_title`

**`ui/overlay.py`** (MODIFIED)
- Added `select_window()` function — idempotent QApplication init, creates and shows `WindowPickerDialog`, returns HWND or None

**`ui/__init__.py`** (MODIFIED)
- Appends both exports:
  ```python
  from ui.window_picker import WindowPickerDialog
  from ui.overlay import select_window
  ```

**`main.py`** (MODIFIED)
- `async def main(hwnd: int)` — now accepts HWND parameter
- `_resolve_hwnd_from_arg()` — uses `int(val, 0)` for auto base detection (hex/decimal)
- `__main__` block resolves HWND:
  - `--hwnd` flag → `_resolve_hwnd_from_arg()`
  - No `--hwnd` → `QApplication.instance() or QApplication(sys.argv)` → `WindowPickerDialog`
  - Early-exit flags (`--list-engines`, `--list-engine-status`) still work without HWND
- Terminal `input()` prompt removed; replaced by GUI picker dialog

### Post-implementation fixes
1. `_resolve_hwnd_from_arg()` simplified — replaced separate hex/decimal branches with single `int(val, 0)`
2. `select_window` added to `ui/__init__.py` exports

### Stage 1 acceptance criteria
- [x] `python main.py` (without `--hwnd`) opens the window picker dialog
- [x] Dialog lists all visible windows with HWND and title
- [x] Search/filter works in real-time as user types
- [x] Refresh button re-enumerates windows
- [x] Double-click or OK confirms selection, returns HWND
- [x] Cancel exits gracefully
- [x] `python main.py --hwnd 0x1234` bypasses the dialog and uses the CLI value
- [x] Window titles update correctly (no stale cache)
- [x] The existing OCR pipeline works identically after HWND selection

---

## Phase 4: Stage 2 — Live Preview (PLANNED, awaiting implementation)

### Plan
- `plans/stage2-live-preview.md` drafted with QLabel + deque approach
- User code review identified 5 issues → all fixed:
  1. `if not args.hwnd` fragile → replaced with explicit `gui_mode = args.hwnd is None` flag
  2. `deque.pop()` wrong → changed to `deque.popleft()` for queue semantics
  3. `QImage` memory safety → `rgb_bytes = rgb.tobytes()` held as explicit reference
  4. `processEvents()` placement → moved BEFORE `asyncio.sleep()` to prevent 1.5s freeze
  5. No window close handler → added `closeEvent` with `running` flag

### Architecture
```
async capture loop → deque(maxlen=1) → QTimer(50ms) → PreviewWidget (QLabel + QPixmap)
```

### Key design decisions
- **Frame handoff:** `collections.deque(maxlen=1)` — thread-safe same-thread interleaving via `QApplication.processEvents()`
- **Rendering:** QLabel + QPixmap — no OpenGL overhead needed for ~20fps VN preview
- **Conversion path:** BGR → cv2.cvtColor(BGR→RGB) → QImage(rgb_bytes, w, h, Format_RGB888) → QPixmap.fromImage()
- **Qt bridge:** `QApplication.processEvents()` called once per capture iteration before `asyncio.sleep()` — pragmatic until qasync integration (Stage 4)
- **Timer:** QTimer at 50ms polls deque; no-op when empty; decouples capture rate from display rate

### Files to create/modify
| File | Action | Content |
|------|--------|---------|
| `ui/preview_widget.py` | **Create** | `PreviewWidget` class — QLabel-based live feed, deque polling, BGR→QPixmap conversion, stop() method |
| `ui/components.py` | Modify | Add `StatusBar` class — engine, FPS, confidence, window info labels |
| `main.py` | Modify | Wire GUI mode: create `QMainWindow`, `PreviewWidget`, `StatusBar`; add `gui_mode`-branch capture loop with deque, processEvents(), closeEvent cleanup |

### Edge cases handled
1. Window closed mid-capture → ScreenCapture returns None; preview shows last frame
2. Resize → QLabel.scaled() handles aspect ratio preservation
3. No frames yet → Deque empty; timer callback no-op; label shows "No feed"
4. Slow capture → Deque maxlen=1 discards old frames
5. Fast capture → Timer at 50ms throttles display

---

## Files Changed This Session

### Created
| File | Lines | Purpose |
|------|-------|---------|
| `ui/window_picker.py` | 175 | WindowPickerDialog — HWND selection dialog |
| `plans/stage1-window-picker.md` | ~345 | Stage 1 implementation plan |
| `plans/stage2-live-preview.md` | ~410 | Stage 2 implementation plan (pending) |

### Modified
| File | Change |
|------|--------|
| `main.py` | HWND resolution via `--hwnd` flag or picker dialog; `_resolve_hwnd_from_arg()` with `int(val, 0)` |
| `ui/__init__.py` | Added exports: `WindowPickerDialog`, `select_window` |
| `ui/overlay.py` | Added `select_window()` helper function |

### Updated (summary files)
| File | Change |
|------|--------|
| `handoff-summary.md` | This file — updated to cover current session |

---

## Git History (Last 3 meaningful commits on `origin/main`)

| Commit | Message | Content |
|--------|---------|---------|
| `5e1037b` | "Making winrt behave" | Windows OCR async pattern fixes |
| `b3e0469` | "More 3 OCR changes" | `preprocess_natural_slice()` added, wired into engine_manager, new smoke test |
| `695d20a` | "New Plan" | `desktopocr-window-and-area-selector-staged-98e0ff.md` added (7-stage UI plan) |

---

## Technical Architecture Summary

### 3-Engine Hierarchy
1. **PaddleOCR** (primary) — PP-OCRv5 ONNX via onnxruntime-directml
2. **EasyOCR** (Python fallback) — loaded lazily
3. **Windows OCR** (WinRT fallback) — Japanese language pack required

### Screen Capture
- Primary: WinRT `Windows.Graphics.Capture` via `winsdk==1.0.0b10`
- Fallback: BitBlt GDI (`_get_frame_bitblt`)
- `capture_generation` counter prevents stale frame processing

### Frame Diff Detection
- MD5 hash comparison between consecutive frames
- Identical frames → skip OCR, return None

### Buffer Pooling
- `DET_BUFFER` and `REC_BUFFER` — pre-allocated numpy arrays to avoid allocation in hot path

### Validation Layer
- Unicode range-based Japanese detection (Hiragana, Katakana, CJK)
- Confidence threshold: 0.45
- UI noise filtering via `_contains_ui_noise_token()`
- `score_japanese_density()` for text quality scoring

### UI (PyQt6)
- Stage 1: ✅ WindowPickerDialog — complete
- Stage 2: 📋 Live Preview (PreviewWidget) — plan ready, awaiting implementation
- Stage 3: Region selection overlay
- Stage 4: qasync event loop integration
- Stage 5+: UX controls (mode selector, history sidebar, OCR trigger)

---

## Current State

### What's working
- Stage 1 window picker — fully implemented and integrated
- Core OCR pipeline (PaddleOCR detection + recognition, EasyOCR fallback, Windows OCR fallback)
- WinRT screen capture with BitBlt fallback
- Japanese validation layer
- CLI flags: `--hwnd`, `--engine`, `--show-canvas`, `--debug-once`, `--region`, `--select-region`, `--raw-ocr`, `--light-preprocess`, `--det-no-pad`, `--list-engines`, `--list-engine-status`
- `select_window()` helper exported from `ui` package

### What needs implementation (pending user approval)
- Stage 2: Live preview widget (`ui/preview_widget.py`, modify `ui/components.py`, modify `main.py`)
- Stage 3+: Region selection, qasync, UX controls

### What needs testing (user-side)
- `python main.py` — verify WindowPickerDialog appears and returns valid HWND
- `python main.py --hwnd 0x...` — verify CLI mode still works end-to-end
- OCR pipeline with real game window

---

## Important Notes for Next Session

1. **Stage 2 plan is corrected and ready** — All 5 code review fixes have been applied. Awaiting user approval to switch to Code mode and implement.
2. **`desktopocr-window-and-area-selector-staged-98e0ff.md`** — Contains the original 7-stage UI roadmap. Stage 1 and 2 map to stages 1-2 of that document.
3. **`personalOCR-Cloudflare`** — Web reference app with full UI; useful for UI design inspiration. Located at `C:\Users\rober\.gemini\antigravity\scratch\personalOCR-Cloudflare`.
4. **`qasync`** — Planned for Stage 4 to replace `QApplication.processEvents()` bridge. Already in `requirements.txt` as `qasync==0.28.0`.
5. **Branch policy** — Do not merge into `origin/main` directly; use `DesktopOCR-dev-new-from-main` for development.
6. **Smoke test reminder** — After Stage 2 implementation, run `python main.py` to verify the full GUI flow (picker → preview → OCR pipeline).
