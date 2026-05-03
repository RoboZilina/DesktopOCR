# Status Bar Improvements

## Current Implementation

The status bar is defined in [`ui/components.py`](ui/components.py:14) as a `StatusBar(QStatusBar)` with a single `QLabel` showing two lines of text:

- **Line 1** — status text: `"Ready"`, `"Processing…"`, `"Done"`, `"Error"`, `"Loading engine…"`
- **Line 2** — config summary built by [`_build_status_summary()`](main.py:1231): `Window: ... | Engine: ... | Translator: ... | Validator: ... | TTS: ...`

Font is 12px (`text_dim` color ≈ `#a1a1aa` on dark theme) — set in [`set_theme()`](ui/components.py:39-41).

## Identified Issues

### 1. Font too small / hard to read
12px with dim color is difficult to read at a glance. Status text should be prominent since it's the primary feedback channel for user actions (re-capture, OCR completion, errors).

### 2. No visual distinction between states
`"Processing…"`, `"Done"`, `"Ready"`, `"Error"` all render identically. The user has to read the text to know what's happening — there's no color cue.

### 3. No auto-timeout on transient status
After OCR completes, the status stays `"Done" + summary` indefinitely. Only the Anki test result at [`main.py:1218`](main.py:1218) has a 3-second clear via `_safe_clear_status()`. The "Done" summary is configuration info, not a real-time action log.

### 4. Status flash invisible on fast operations
When `capture_once()` returns None in ~10ms (unchanged frame), the transition `"Processing…" → "Done"` happens so fast the user sees nothing. This is the root cause of "re-capture does nothing" perception — the status bar gives no feedback at all.

### 5. Summary line is configuration, not status
The second line shows Window/Engine/Translator/Validator/TTS — this is useful info but rarely changes. It competes with the actual status text for visual attention.

## Proposed Improvements

### A. Larger, semi-bold font with state-aware coloring
Modify [`StatusBar.set_status()`](ui/components.py:43-47) to apply color based on the status text prefix:

| Status | Color | Example |
|--------|-------|---------|
| `"Ready"` | `text_dim` (current) | Idle state |
| `"Processing…"` | `warn` (`#f59e0b` amber) | Visual feedback that work is happening |
| `"Done"` | `accent` (`#10b981` green) | Success confirmation |
| `"Error"` | `panic` (`#ef4444` red) | Error stands out |
| `"Loading…"` | `text_secondary` | Background activity |

Font size: increase from 12px → 14px with `font-weight: 600`.

```python
def set_status(self, status_text: str, summary_text: str):
    color = self._color_for_status(status_text)
    self._status_label.setStyleSheet(
        f"color: {color}; font-size: 14px; font-weight: 600;"
    )
    if summary_text:
        self._status_label.setText(f"{status_text}\n{summary_text}")
    else:
        self._status_label.setText(status_text)
```

### B. Auto-timeout "Done" → "Ready" after 2 seconds
Add a `QTimer.singleShot` in `set_status()` that resets to `"Ready"` after a delay, but only for `"Done"` and `"Error"` states. This mirrors the existing Anki pattern at [`main.py:1218`](main.py:1218).

```python
def set_status(self, status_text: str, summary_text: str):
    # ... apply styling and text ...
    if status_text in ("Done", "Error"):
        QTimer.singleShot(2500, lambda: self._revert_to_ready())
```

Add a `_revert_to_ready()` method that sets status back to `"Ready"` without the summary.

### C. Minimum display duration for "Processing…"
In the OCR loop at [`main.py:1343-1344`](main.py:1343-1344), the `"Processing…"` status is set just before `capture_once()`. If capture completes in <300ms, the status flash is invisible. Add a minimum display duration:

```python
if window is not None:
    window.set_status("Processing…", "")
ocr_started = time.perf_counter()
res = await pipeline.capture_once(...)
elapsed_ms = (time.perf_counter() - ocr_started) * 1000.0

# Ensure processing status is visible for at least 300ms
min_visible = 0.3 - (elapsed_ms / 1000.0)
if min_visible > 0:
    await asyncio.sleep(min_visible)
```

### D. Optional: split status text into two styled lines
Instead of a single label with `\n`, use two separate `QLabel`s:
- **Line 1** (large, bold, state-colored): `"Done"`, `"Processing…"`, etc.
- **Line 2** (small, dim): config summary `"Window: ... | Engine: ..."`

This makes the status text visually independent from the persistent config info.

## Changes Required

| File | Change | Risk |
|------|--------|------|
| [`ui/components.py`](ui/components.py:43-47) | Add state-aware coloring in `set_status()` | Low — pure UI change |
| [`ui/components.py`](ui/components.py:14) | Add `QTimer.singleShot` auto-timeout | Low — Qt timer, no thread issues |
| [`main.py:1343-1344`](main.py:1343-1344) | Add minimum display duration for "Processing…" | Low — tiny delay, no functional impact |
| [`ui/components.py`](ui/components.py) | Optionally: two-label layout | Low — layout restructure, same API |

## Non-Invasive Principle

All changes are:
- **UI-only** — no logic changes to OCR pipeline, signals, or async flow
- **Backward-compatible** — existing `set_status(text, summary)` API unchanged
- **No new dependencies** — `QTimer` is already available in PyQt6
- **No config/settings changes** — users see the improvement immediately
