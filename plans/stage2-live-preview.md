# Stage 2 — In-App Live Preview (Window Feed)

## Objective

Add a live video feed widget that displays the captured window's contents in real-time within the PyQt6 UI. This replaces the current terminal-only output with a visual preview — the same function the web app's `<video>` element serves.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                Main Window (QMainWindow)          │
│  ┌──────────────────────────────────────────────┐ │
│  │   PreviewWidget (QLabel + QPixmap)           │ │
│  │   ┌────────────────────────────────────────┐ │ │
│  │   │  Live window feed (scaled to fit)      │ │ │
│  │   │  Updated at ~20 fps                    │ │ │
│  │   └────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────┐ │
│  │  Status: [Engine] [FPS] [Conf] [Window]      │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘

Frame flow:

  async capture loop (main.py)
       │
       │  await capture.get_frame() → np.ndarray (BGR)
       │
       ▼
  deque (maxlen=1) ← thread-safe, no lock needed
       │                 (same-thread interleaving)
       │
       │  QTimer (50ms interval) polls deque
       ▼
  PreviewWidget._update_frame()
       │
       │  cv2.cvtColor(BGR→RGB) → QImage → QPixmap
       ▼
  self.label.setPixmap(scaled_pixmap)
```

---

## Key Design Decisions

### Frame handoff: `collections.deque(maxlen=1)`

The async capture loop writes frames into a deque. The Qt timer reads from it. Because both run on the same thread (async loop pumps Qt via `QApplication.processEvents()`), there are no thread-safety concerns. `maxlen=1` ensures we always show the latest frame, never accumulating stale frames.

### Rendering: `QLabel` + `QPixmap`

- `QLabel` provides automatic scaling via `setScaledContents(True)` or `setPixmap(scaled)`.
- No OpenGL overhead needed for a VN preview at ~20fps.
- Conversion path: `np.ndarray (BGR)` → `cv2.cvtColor(BGR→RGB)` → `QImage(rgb_data, w, h, QImage.Format.Format_RGB888)` → `QPixmap.fromImage()`.

### Qt event loop integration: `QApplication.processEvents()`

Since `main()` runs via `asyncio.run()`, the Qt event loop is not driving the thread. We call `QApplication.processEvents()` once per capture iteration to process pending Qt events (timer ticks, paint events, input). This is a pragmatic bridge until qasync integration (Stage 4+).

### Timer: `QTimer` at 50ms (20fps)

The timer polls the deque. If no new frame is available (deque empty), the timer callback is a no-op. This decouples capture rate from display rate — capture runs as fast as possible, display runs at a smooth 20fps.

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `ui/preview_widget.py` | **Create** | `PreviewWidget` — QLabel-based live feed |
| `ui/components.py` | Modify | Add status bar rendering |
| `main.py` | Modify | Wire preview widget into capture loop |
| `plans/stage2-live-preview.md` | **Create** | This plan |

---

## Detailed Implementation

### 1. [`ui/preview_widget.py`](ui/preview_widget.py) — New file

```python
"""
QLabel-based live preview widget for the captured window feed.

Receives numpy BGR frames via a deque and renders them as QPixmap.
"""

import cv2
import numpy as np
from collections import deque
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap


class PreviewWidget(QWidget):
    """
    Widget that displays a live feed of the captured window.

    Wire it up:
        1. Create PreviewWidget instance
        2. Pass frame_queue (deque, maxlen=1) to it
        3. Async capture loop puts frames into the deque
        4. PreviewWidget's QTimer polls the deque at 50ms intervals
    """

    def __init__(self, frame_queue: deque, parent=None):
        super().__init__(parent)
        self._frame_queue = frame_queue
        self._last_frame: np.ndarray | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("No feed")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            "background-color: #1e1e1e; color: #888; font-size: 16px;"
        )
        self._label.setMinimumSize(320, 180)
        layout.addWidget(self._label)

        # Timer: poll deque at 50ms (~20 fps)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)
        self._timer.start(50)

    def _poll_frame(self):
        """Pop the latest frame from the deque and update display."""
        if not self._frame_queue:
            return

        frame = self._frame_queue.popleft()  # get latest, discard older
        self._last_frame = frame
        self._render_frame(frame)

    def _render_frame(self, frame: np.ndarray):
        """Convert numpy BGR → QPixmap and display."""
        if frame is None or frame.size == 0:
            return

        h, w = frame.shape[:2]

        # BGR → RGB conversion
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Build QImage from raw data — hold bytes reference for lifetime
        rgb_bytes = rgb.tobytes()
        qimage = QImage(
            rgb_bytes, w, h,
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        )

        pixmap = QPixmap.fromImage(qimage)

        # Scale to fit label while maintaining aspect ratio
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self._label.setPixmap(scaled)

    @property
    def latest_frame(self) -> np.ndarray | None:
        return self._last_frame

    def stop(self):
        """Stop the polling timer."""
        self._timer.stop()
```

### 2. [`ui/components.py`](ui/components.py) — Modify

Add a status bar / info panel that displays at the bottom of the main window. For Stage 2 this is minimal (just engine and window info), but it sets the structure for future stages.

```python
"""
Shared UI components for the DesktopOCR overlay window.
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt


class StatusBar(QWidget):
    """Bottom status bar showing engine, FPS, window info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self._engine_label = QLabel("Engine: —")
        self._fps_label = QLabel("FPS: —")
        self._conf_label = QLabel("Conf: —")
        self._window_label = QLabel("Window: —")

        for lbl in (self._engine_label, self._fps_label,
                     self._conf_label, self._window_label):
            lbl.setStyleSheet("color: #ccc; font-size: 12px;")
            layout.addWidget(lbl)

        layout.addStretch()

    def set_engine(self, name: str):
        self._engine_label.setText(f"Engine: {name}")

    def set_fps(self, fps: float):
        self._fps_label.setText(f"FPS: {fps:.1f}")

    def set_confidence(self, conf: float):
        self._conf_label.setText(f"Conf: {conf:.2f}")

    def set_window_title(self, title: str):
        self._window_label.setText(f"Window: {title}")
```

### 3. [`main.py`](main.py) — Wiring changes

**Goal:** Modify the capture loop to both display the preview AND process OCR.

Key changes:
1. Import `PreviewWidget` and `StatusBar`
2. Create `QApplication`, `PreviewWidget`, `StatusBar` before the capture loop
3. Create a `deque(maxlen=1)` shared between preview and capture
4. Inside the capture loop: put frame into deque, call `QApplication.processEvents()`
5. Show the main window containing preview + status bar

```python
# === In main.py, imports section ===

import sys
from collections import deque
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from ui.preview_widget import PreviewWidget
from ui.components import StatusBar


# === In __main__ block, after HWND resolution ===

# Set mode flag: GUI mode when picker dialog was used (--hwnd not passed)
gui_mode = args.hwnd is None

# Create QApplication (idempotent)
app = QApplication.instance() or QApplication(sys.argv)

if gui_mode:
    # Create main window with preview + status bar
    window = QMainWindow()
    window.setWindowTitle(f"DesktopOCR — {hex(hwnd)}")
    window.setMinimumSize(640, 480)

    central = QWidget()
    window.setCentralWidget(central)
    layout = QVBoxLayout(central)

    frame_queue: deque = deque(maxlen=1)
    preview = PreviewWidget(frame_queue)
    layout.addWidget(preview)

    status_bar = StatusBar()
    layout.addWidget(status_bar)

    window.show()
else:
    frame_queue = None
    preview = None
    status_bar = None


# === In async def main(hwnd: int), capture loop (arm `--show-canvas` path or default) ===

# The capture loop currently has two paths:
#   --show-canvas: OpenCV window with detection boxes
#   default: terminal output via pipeline.capture_once()
#
# For Stage 2, we add a third path (GUI mode) activated when no --hwnd was passed
# (i.e., the picker dialog was used). In GUI mode:
#
#   1. Capture frame
#   2. Put frame into deque for preview widget
#   3. Run OCR on frame
#   4. Update status bar with results
#   5. Call QApplication.processEvents() to update UI
#
# The existing --show-canvas and default paths remain unchanged for CLI mode.

# Pseudocode for the GUI-mode capture loop:

if gui_mode:
    logger.info("Starting GUI capture loop...")

    def _on_close():
        """Handle window close — stop the async loop cleanly."""
        nonlocal running
        running = False

    window.closeEvent = lambda e: (_on_close(), e.accept())

    running = True
    while running:
        frame = await capture.get_frame()
        if frame is not None:
            frame_queue.append(frame.copy())  # preview gets this frame

            # Run OCR
            res = await pipeline.capture_once()
            if res is not None:
                text = res.get("text", "")
                conf = res.get("confidence", 0.0)
                meta = res.get("meta", {}) or {}
                engine_id = meta.get("engine", engine_manager.current_id)
                status_bar.set_engine(engine_id)
                status_bar.set_confidence(float(conf))
                if text:
                    status_bar.set_window_title(text[:60])
                # Print to terminal too (backwards compatible logging)
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] [{engine_id}] [Conf: {conf:.2f}] {text}")

        # Pump Qt events — critical: keeps preview widget responsive
        # Place BEFORE sleep to prevent UI from freezing for 1.5s
        QApplication.processEvents()

        await asyncio.sleep(1.5)

    # Cleanup on window close
    preview.stop()
    window.close()
    logger.info("GUI window closed. Stopping capture.")
else:
    # Existing --hwnd path unchanged (CLI mode, no GUI)
    ...
```

**Important nuances:**

- **`processEvents()` is placed BEFORE `asyncio.sleep()`** — if placed only after the sleep, the UI would be unresponsive for up to 1.5 seconds. Putting it before the sleep ensures Qt events are processed immediately after each iteration, keeping the window responsive.
- **Window close handling** — The `closeEvent` override sets a `running` flag to `False`, which exits the capture loop cleanly. Without this, closing the window would leave the async loop running and the app hanging.
- **Ctrl+C** — KeyboardInterrupt still works because `asyncio.run()` catches it.

---

## Integration with Existing Code

### Web app → DesktopOCR mapping

| Web app | DesktopOCR |
|---------|------------|
| `<video>` element | `PreviewWidget` (QLabel + QPixmap) |
| `vnVideo.srcObject = videoStream` | `frame_queue.append(frame)` |
| `setInterval(checkAutoCapture, 500)` | `QTimer(50ms)` poll + `capture loop(1.5s)` |
| `#selection-overlay` canvas | Stage 3 (region selection overlay) |
| `#latest-text` | Status bar label |

### Edge cases handled

1. **Window closed mid-capture** → `ScreenCapture.get_frame()` returns `None`; preview shows last frame; OCR continues gracefully
2. **Resize** → `QLabel.scaled()` handles aspect ratio preservation
3. **No frames yet** → Deque empty; timer callback is no-op; label shows "No feed"
4. **Slow capture** → Deque `maxlen=1` discards old frames; display always shows latest
5. **Fast capture** → Timer at 50ms throttles display; deque.popleft() always gets newest

---

## Dependencies

All already installed:
- `PyQt6==6.11.0` (QLabel, QTimer, QImage, QPixmap)
- `opencv-python` (cv2.cvtColor, numpy)
- `collections.deque` (stdlib)

---

## Acceptance Criteria

1. [ ] `python main.py` (without `--hwnd`) shows picker → select window → live preview appears
2. [ ] Preview updates in real-time as the window contents change
3. [ ] Preview scales to fit the widget while maintaining aspect ratio
4. [ ] Status bar shows engine name and OCR confidence
5. [ ] `python main.py --hwnd 0x...` still runs in CLI mode without GUI
6. [ ] `python main.py --show-canvas` still works in CLI mode
7. [ ] Window resize works correctly (preview re-scales)
8. [ ] Closing the preview window exits the capture loop cleanly
9. [ ] Ctrl+C still terminates the application

---

## Implementation Order

1. Create `ui/preview_widget.py` with `PreviewWidget` class
2. Add `StatusBar` to `ui/components.py`
3. Wire GUI mode into `main.py` (`__main__` block + capture loop branch)
4. Run smoke test: verify preview appears and updates
5. Run regression test: `--hwnd` CLI mode still works

---

## Future Hook Points (Post-Stage 2)

- **Stage 3** (Region Selection): Canvas overlay on top of PreviewWidget for mouse-drag region selection
- **Stage 4** (qasync): Replace `QApplication.processEvents()` with proper `qasync` event loop integration
- **Stage 5** (UX Controls): Add OCR trigger button, mode selector, history sidebar
