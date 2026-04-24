# Stage 3 — In-App Snipping Overlay (Web-Style UX)

Implement a transparent overlay on top of the preview widget for click-and-drag region selection, with normalized coordinates mapped back to the original capture frame.

## Architecture

Overlay is a child `QWidget` of `PreviewWidget`, always active, positioned above the `QLabel`. Mouse press → drag → release defines the selection rectangle. Coordinates are stored normalized `[0,1]` relative to the original frame.

## Coordinate Transform (Core Problem)

Preview uses `KeepAspectRatio`, so the displayed image is centered and may be letterboxed. Mapping:

```python
scale = min(labelW / imgW, labelH / imgH)
dispW, dispH = imgW * scale, imgH * scale
offsetX, offsetY = (labelW - dispW) / 2, (labelH - dispH) / 2

# Overlay mouse → original frame pixels
ix = (mx - offsetX) / scale
iy = (my - offsetY) / scale
nx, ny = ix / imgW, iy / imgH   # normalized [0,1]
```

Reverse for drawing stored selection on overlay.

## Capture Change — Full-Frame Preview

Currently `get_frame()` crops to `_region`, so the preview only shows the OCR strip. Fix:
- Add `get_frame(full: bool = False)` to `ScreenCapture`.
- `full=True` skips the crop, returns the entire window frame.
- GUI loop calls `get_frame(full=True)` for preview.
- OCR pipeline keeps calling `get_frame()` (cropped, unchanged).
- On selection finalize, `capture.set_region()` is updated; next OCR loop picks up the new region.

## Implementation Steps

1. **Full-frame preview** — modify `ScreenCapture._apply_diff_and_crop()` with `full` parameter, wire GUI loop in `main.py`.
2. **SelectionOverlay widget** — new `ui/selection_overlay.py`:
   - `mousePressEvent` / `mouseMoveEvent` / `mouseReleaseEvent`
   - `paintEvent`: fill + border + corner accents (web parity)
   - Min size enforcement (8x8 px original-frame equivalent)
   - Preserve `last_valid_rect` on tiny drags
   - Emit `region_changed(x, y, w, h)` signal (normalized)
3. **PreviewWidget integration** — add overlay child, expose `frame_size` property.
4. **main.py wiring** — connect overlay signal to `capture.set_region()`.
5. **Visual parity** — semi-transparent fill, white border, crosshair cursor.

## Deferred to Stage 6
- Buttons (Re-select, Reset). Persistence across restarts.

## Verification
- [ ] Drag draws live rectangle
- [ ] Release updates capture region
- [ ] OCR runs on newly selected region
- [ ] Tiny drags are rejected, previous selection preserved
- [ ] Coordinate math verified with known window dimensions
