# Stage 5 — Header Controls Bar (Engine + Auto-capture)

Add a `ControlsBar` widget docked above the preview with engine selector and auto-capture toggle. Mode selector is a disabled placeholder pending a proper pipeline mode refactor in a future stage.

## Files to create/modify

| File | Action |
|------|--------|
| `ui/controls_bar.py` | **Create** — `ControlsBar` widget |
| `ui/__init__.py` | Append export |
| `main.py` | Wire controls into layout and capture loop |

## `ui/controls_bar.py`

Widget layout (left-to-right, fixed height 48px):
- `QLabel("Engine:")` + `QComboBox` (engine selector)
- `QLabel("Mode:")` + `QComboBox` (placeholder, disabled)
- stretch
- `QPushButton("Auto-capture: ON")` (checkable toggle)

Signals:
- `engine_changed(str)` — emitted on combo change
- `capture_toggled(bool)` — emitted on button toggle

Methods:
- `set_engine(engine_id)` — programmatic combo selection, blocks signals
- `set_capture_state(bool)` — programmatic toggle state

## `main.py` wiring

1. Import `ControlsBar` and instantiate with `engine_manager.get_supported_engines()`
2. `layout.insertWidget(0, controls)` above preview widget
3. Wire `engine_changed` → `asyncio.ensure_future(engine_manager.switch_engine(...))`
4. Add `auto_capture` bool flag in `_capture_loop()` scope; wire toggle to set it
5. When `auto_capture=False`, skip `pipeline.capture_once()` but keep pushing frames to preview
6. Programmatically set initial engine via `controls.set_engine()` so init doesn't fire signal

## Acceptance criteria

- [ ] Engine selector lists all available engines; switching loads new engine and OCR continues
- [ ] Auto-capture toggle pauses/resumes OCR without freezing preview
- [ ] Mode selector visible but disabled (placeholder)
- [ ] Programmatic `set_engine()` on init doesn't fire signal
- [ ] `--hwnd` CLI mode unaffected
