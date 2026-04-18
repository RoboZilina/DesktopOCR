# Project: desktopOCR
## Version: 1.0 | Status: Active Development

---

## Goal

A high-accuracy, low-latency, fully local Japanese OCR tool for Visual Novels on Windows.
This is a **native Python desktop application** — not a web app, not an Electron wrapper.
It replaces a browser-based predecessor (`personalOCR`) that hit hard platform ceilings:
WASM processing (~30s per frame), WebGPU incompatibility with ONNX MaxPool ceil(),
browser sandbox memory limits, and mandatory paid hosting for large model files.

---

## Folder Structure

```
desktopOCR/
├── instructions.md               ← this file, AI source of truth
├── requirements.txt
├── main.py                       ← entry point, wires everything together
│
├── reference/                    ← READ-ONLY JS source from predecessor webapp
│   ├── paddle_engine.js          ← maps to core/ocr_engine.py
│   ├── paddle_core.js            ← maps to core/tensor_utils.py
│   ├── capture_pipeline.js       ← maps to core/capture_pipeline.py
│   └── engine_manager.js         ← maps to core/engine_manager.py
│
├── core/
│   ├── capture.py                ← WinRT screen capture → numpy BGR frames
│   ├── capture_pipeline.py       ← frame diff, locking, generation stamping, multi-pass
│   ├── ocr_engine.py             ← PaddleOCR ONNX det+rec pipeline, CTC decoder
│   ├── tensor_utils.py           ← numpy tensor prep, buffer pooling, box utils
│   ├── engine_manager.py         ← engine lifecycle, switching, silent preload
│   ├── windows_ocr.py            ← WinRT Windows.Media.Ocr fallback engine
│   └── vision.py                 ← OpenCV preprocessing (optional, toggleable)
│
├── logic/
│   └── validator.py              ← Japanese char-range filter + confidence threshold
│
├── ui/
│   ├── overlay.py                ← PyQt6 transparent always-on-top window
│   └── components.py             ← status pill, history log, engine selector
│
├── models/
│   ├── paddle/
│   │   ├── det.onnx              ← PP-OCRv5 server detection model (~84MB)
│   │   ├── rec.onnx              ← PP-OCRv5 server recognition model (~100MB)
│   │   ├── det_mobile.onnx       ← PP-OCRv5 mobile detection model (lighter)
│   │   ├── rec_mobile.onnx       ← PP-OCRv5 mobile recognition model (lighter)
│   │   └── japan_dict.txt        ← character dictionary (port from reference)
│   └── README.md                 ← instructions for downloading models
│
└── tests/
    ├── test_capture.py           ← manual: list HWNDs, verify capture region visually
    ├── test_ocr_pipeline.py      ← manual: run full pipeline, print text to console
    └── test_preprocessing.py     ← manual: show cv2.imshow at each pipeline stage
```

---

## Tech Stack

| Component        | Technology                                      | Reason |
|------------------|-------------------------------------------------|--------|
| Screen Capture   | `winsdk` 0.10.0 — WinRT Windows.Graphics.Capture | Handles DX12/anti-cheat games; BitBlt fails on modern titles |
| Preprocessing    | OpenCV — CLAHE + bilateral filter (optional)    | Toggleable; PP-OCRv5 may perform better on raw frames |
| Primary OCR      | PP-OCRv5 server — ONNX Runtime + DirectML       | +13pt accuracy over v4; native DirectML fixes the WASM MaxPool ceil() incompatibility |
| Secondary OCR    | PP-OCRv5 mobile — ONNX Runtime + DirectML       | Faster fallback on weaker hardware |
| Fallback OCR     | WinRT Windows.Media.Ocr                         | Zero model weight, already on machine, instant |
| Validation       | Unicode range filter + confidence threshold     | Replaces MeCab/fugashi — same effect, no 500MB dictionary |
| GUI              | PyQt6 + qasync                                  | Transparent resizable overlay, async-compatible |
| Distribution     | Nuitka standalone .exe                          | Build last, after all features work |

**Python version: 3.11**
**Windows only** — WinRT and DirectML are not cross-platform. Do not add compatibility shims.

---

## Engine Hierarchy

The pipeline tries engines in order, falling back on low confidence:

```
Captured frame
      ↓
PP-OCRv5 server (raw frame first, DirectML)
      ↓  confidence < 0.75
PP-OCRv5 mobile (with optional light preprocessing, DirectML)
      ↓  confidence < 0.75 or empty
Windows OCR (WinRT, zero deps, instant)
      ↓  all return empty or fail
Discard frame — do not update UI
```

The preprocessing toggle applies only to the mobile model pass.
PP-OCRv5 server is always fed the raw frame first (per GameTranslate finding:
aggressive preprocessing hurts v5 accuracy on stylized VN fonts).

---

## Reference File Mapping

The `/reference` folder contains battle-tested JavaScript from the predecessor webapp.
These files are **specs, not dependencies** — never import or run them.
Port their logic to Python exactly, preserving algorithms, constants, and patterns.

### `reference/paddle_engine.js` → `core/ocr_engine.py`

Critical constants to preserve exactly:
```python
NORMALIZE_MEAN = [0.5, 0.5, 0.5]
NORMALIZE_STD  = [0.5, 0.5, 0.5]
DET_INPUT_SIZE = (960, 960)
REC_INPUT_SIZE = (48, 320)   # [H, W]
MIN_BOX_AREA   = 40 * 40     # noise-box filter threshold (pixels²)

# Detection box padding (applied in detection-space BEFORE scaling to original coords)
PAD_LEFT   = 20
PAD_RIGHT  = 12
PAD_TOP    = 12
PAD_BOTTOM = 12
```

The CTC greedy decoder (`_ctcGreedyDecode` in JS) must be ported exactly.
Batch recognition (`recognizeLines`) must support both single and batched tensors.
The `busy` flag pattern must be preserved as an `asyncio.Lock()`.

### `reference/paddle_core.js` → `core/tensor_utils.py`

`canvasToFloat32Tensor` ports to a numpy function:
- Resize to target shape with aspect-ratio preservation for rec (height=48, scale width)
- Fill background black before drawing
- Normalize: `(pixel/255 - mean) / std` per channel
- Output shape: `[1, 3, H, W]` CHW format, BGR channel order

Pre-allocated buffer pooling must be preserved:
```python
# Pre-allocate once, reuse every frame — never allocate inside the hot path
det_buffer = np.zeros((1, 3, 960, 960), dtype=np.float32)
rec_buffer = np.zeros((1, 3, 48, 320), dtype=np.float32)
```

### `reference/capture_pipeline.js` → `core/capture_pipeline.py`

**Generation stamping** must be preserved exactly — this prevents UI ghosting from
stale frames when the user moves the selection rect mid-capture:
```python
self.capture_generation = 0  # increment on every new capture cycle

async def capture_frame(self):
    my_gen = self.capture_generation  # snapshot at start
    # ... after every await ...
    if self.capture_generation != my_gen:
        return  # stale, discard
```

**Multi-pass voting** logic (`pickBestMultiPassResult`) must be ported:
1. Majority vote (3+ identical results win immediately)
2. Highest confidence fallback
3. Japanese character density fallback (`scoreJapaneseDensity`)
4. Weighted score fallback: `confidence * 0.7 + density * 0.3`

**Frame diff detection** (not in capture_pipeline.js but must be added):
```python
# Only run OCR pipeline if the frame has actually changed
# Compare frame hashes — skip if identical to last processed frame
import hashlib
frame_hash = hashlib.md5(frame.tobytes()).hexdigest()
if frame_hash == self.last_frame_hash:
    return  # identical frame, skip
self.last_frame_hash = frame_hash
```

### `reference/engine_manager.js` → `core/engine_manager.py`

State machine states to preserve: `not_loaded`, `loading`, `ready`, `error`

**Idempotent loading** — concurrent calls must not create duplicate sessions:
```python
# Use asyncio.Lock() per engine ID — equivalent to JS loadPromise deduplication
self._load_locks: dict[str, asyncio.Lock] = {}
self._load_tasks: dict[str, asyncio.Task] = {}
```

**Silent background preloading** — mobile model preloads silently while server model
is active. Errors must always surface even in silent mode (port the reporter logic).

**Engine eviction** — when switching engines, dispose sessions not in the keep-cached set.
Keep-cached set: `{'server', 'mobile'}`. Always evict `windows_ocr` is stateless (no-op).

---

## Preprocessing Pipeline (OpenCV)

Preprocessing is **optional and toggleable per-capture**. Default: OFF for server model.

When enabled (for mobile model fallback pass):
```python
def preprocess_for_ocr(image: np.ndarray, debug: bool = False) -> np.ndarray:
    # 1. Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 2. CLAHE — handles gradients better than global histogram eq
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 3. Bilateral filter — removes background noise, preserves text edges
    gray = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # 4. Adaptive threshold — handles semi-transparent textboxes
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31, C=10
    )

    # 5. Invert if predominantly white (want dark text on white)
    if np.mean(binary) > 127:
        binary = cv2.bitwise_not(binary)

    # 6. Morphological opening — clean up outline/shadow artifacts
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
```

---

## Validation Layer

No MeCab. No fugashi. No 500MB dictionary.
Validation uses two fast checks only:

```python
JAPANESE_RANGES = [
    (0x3040, 0x309F),  # Hiragana
    (0x30A0, 0x30FF),  # Katakana
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs (kanji)
    (0xFF65, 0xFF9F),  # Halfwidth Katakana
]

def is_valid_japanese(text: str, confidence: float | None = None) -> bool:
    if not text or len(text) < 2:
        return False
    # Confidence gate (from OCR engine)
    if confidence is not None and confidence < 0.75:
        return False
    # Japanese character ratio gate
    jp_chars = sum(
        1 for c in text
        if any(lo <= ord(c) <= hi for lo, hi in JAPANESE_RANGES)
    )
    return (jp_chars / len(text)) >= 0.5
```

---

## Screen Capture

**Pin winsdk to version 0.10.0.** The WinRT API surface changed in later versions.

Required capabilities:
- Target a specific HWND (found by the user via `tests/test_capture.py`)
- Capture a sub-region `(x, y, width, height)` defined by the PyQt6 overlay
- Return a `numpy.ndarray` in BGR format (OpenCV compatible)
- Async — must not block the PyQt6 event loop
- `stop()` method that releases all WinRT resources cleanly

Add a BitBlt fallback for older VNs running in windowed GDI mode that do not expose
a WinRT-capturable DXGI surface.

**Frame diff check must be in the capture layer**, not the OCR layer — avoids
feeding identical frames through tensor conversion unnecessarily.

---

## Windows OCR Fallback

At startup, check for Japanese language pack:
```python
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.globalization import Language

def check_japanese_ocr_available() -> bool:
    lang = Language("ja")
    return OcrEngine.is_language_supported(lang)
```

If not available, log a warning and disable the Windows OCR fallback gracefully.
Do not crash — the primary and mobile engines work without it.

---

## GUI (PyQt6 Overlay)

Transparent, frameless, always-on-top window that sits over the VN.

Features to implement (matching predecessor webapp):
- Click-and-drag region selection on a mirrored video preview
- RE-CAPTURE button with 300ms cooldown
- AUTO toggle (polls every 500ms, waits 800ms after stabilization)
- Engine selector dropdown (server / mobile / windows_ocr)
- Preprocessing toggle (on/off)
- Status pill (idle / processing / ready / error)
- History log (last 100 lines, with copy button per line)
- TTS button per line (Windows SAPI via `pyttsx3`)
- Auto-copy to clipboard on new result (`pyperclip`)
- Settings persistence to `%APPDATA%/desktopOCR/settings.json`

**Settings keys** (port from `reference/settings.js` `defaultSettings`):
```python
DEFAULT_SETTINGS = {
    "ocr_engine": "server",          # "server", "mobile", "windows_ocr"
    "preprocessing_enabled": False,  # off by default for server model
    "auto_capture": True,
    "auto_copy": True,
    "upscale_factor": 2.0,
    "history_visible": True,
    "text_size": "standard",         # "small", "standard", "large"
    "tts_enabled": False,
    "confidence_threshold": 0.75,
    "poll_interval_ms": 500,
    "stabilize_wait_ms": 800,
}
```

---

## Distribution (Build Last)

Do not attempt Nuitka bundling until all features work in a normal venv.

Known Nuitka pain points for this stack:
- `onnxruntime-directml` requires manual DLL inclusion
- PyQt6 requires `--include-qt-plugins=platforms,imageformats`
- `winsdk` may need `--include-package=winsdk`

Build command template (fill in after features complete):
```bash
python -m nuitka \
  --standalone \
  --windows-console-mode=disable \
  --include-qt-plugins=platforms,imageformats \
  --include-package=winsdk \
  --include-data-dir=models=models \
  main.py
```

---

## Requirements

```
winsdk==0.10.0
opencv-python
numpy
onnxruntime-directml
PyQt6
qasync
pyperclip
pyttsx3
nuitka
```

---

## Development Rules for the AI

1. **Reference files are specs, not code to run.** When asked to implement a Python
   file, read the corresponding reference JS file and port its logic. Never import JS.

2. **Never allocate buffers inside the hot path.** Pre-allocate numpy arrays once at
   engine initialization. The tensor conversion loop runs every 500ms.

3. **Always release the capture lock in a `finally` block.** Port the `releaseLock()`
   pattern from `reference/capture_pipeline.js` exactly.

4. **Check generation stamp after every `await`.** Any async suspension point is a
   potential stale-frame escape. This is non-negotiable.

5. **Preprocessing is optional.** Never hardcode it in the pipeline. Always check
   `settings.preprocessing_enabled` before applying OpenCV transforms.

6. **PP-OCRv5 server gets the raw frame.** Only the mobile fallback pass gets
   preprocessed input.

7. **Confidence threshold is configurable.** Never hardcode `0.75`. Always read from
   settings.

8. **Test scripts are manual, not unit tests.** `tests/test_capture.py` opens a cv2
   window. `tests/test_ocr_pipeline.py` prints to console. They are not pytest.

9. **Windows only.** Do not add `sys.platform` guards or cross-platform shims.
   This tool is for Windows VN players. Period.

10. **Build order:** capture → tensor_utils → ocr_engine → engine_manager →
    capture_pipeline → validator → overlay UI → main.py wiring → Nuitka last.
