# DesktopOCR Window + Area Selector (Staged)

This plan implements a web-app-style flow where a selected source window is previewed inside DesktopOCR and an in-app snipping overlay defines the OCR area, while OCR still crops from the original full-quality capture frame.

## Stage 1 — Source Window Selector (HWND)
- Build a PyQt window picker dialog listing visible top-level windows (`title`, `HWND`).
- Add search/filter and refresh actions.
- Return selected HWND to runtime and initialize `ScreenCapture(hwnd)`.
- Fallback behavior: if picker canceled, keep current source or abort startup cleanly.
- Keep existing CLI `--hwnd` support for debugging/backward compatibility.

## Stage 2 — In-App Preview Surface
- Add a preview widget in DesktopOCR that displays the selected window stream.
- Render latest frame on a timer/event loop without blocking OCR pipeline.
- Track preview display size (`canvasW`, `canvasH`) for coordinate normalization.
- Keep preview rendering decoupled from OCR crop quality decisions.

## Stage 3 — In-App Snipping Overlay (Web-Style UX)
- Add transparent overlay layer above preview widget.
- Implement drag lifecycle:
  - mouse press: start selection
  - mouse move: live rectangle update
  - mouse release: finalize
- Draw selection box with fill, border, and corner accents (web parity feel).
- Enforce minimum crop size (8x8 px equivalent in preview space).
- Preserve `lastValidSelectionRect` if user makes an invalid tiny drag.

## Stage 4 — Normalized Selection Model + Mapping
- Store area as normalized rect relative to preview (`x,y,w,h` in 0..1).
- Implement robust denormalization from preview space to source-frame pixels.
- Include aspect-fit/letterbox compensation exactly like web logic.
- Clamp final pixel crop to frame bounds.
- Persist normalized rect per selected source window.

## Stage 5 — OCR Pipeline Integration (Quality-Safe)
- Ensure OCR crop uses original capture frame from `ScreenCapture`, not preview buffer.
- Apply normalized rect mapping each frame to crop native-quality pixels.
- Keep engine preprocessing split unchanged:
  - Paddle: `preprocess_paddle_slice`
  - EasyOCR/Windows OCR: `preprocess_natural_slice`
- Keep validator/output schema unchanged.

## Stage 6 — UX Controls and State
- Add controls:
  - `Select Window`
  - `Re-select Area`
  - `Reset Area`
- Show status hints (`No source selected`, `Selection too small`, `Ready`).
- Disable OCR actions when source/selection is invalid.
- Save and restore last source + area on restart (with validation).

## Stage 7 — Validation and Hardening
- Manual tests:
  - window select/cancel/reselect
  - drag select/resize/new select
  - window move/resize while app running
  - DPI scaling sanity check
- Accuracy check: compare OCR from original-frame crop vs preview-based crop (must match original-frame path).
- Regression checks for `paddle`, `windows_ocr`, `easyocr` smoke paths.

## Deliverables
- New/updated UI components for source picker and overlay selector.
- Normalized selection mapping utilities.
- Capture-to-OCR wiring using original frame crop.
- Manual smoke instructions for selector flow + OCR output verification.
