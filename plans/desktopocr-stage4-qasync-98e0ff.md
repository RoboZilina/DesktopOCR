# Stage 4 — Replace `processEvents()` hack with proper qasync event loop

Replace the `asyncio.run()` + `QApplication.processEvents()` polling pattern in `main.py` with a native `qasync.QEventLoop` that drives Qt and asyncio concurrently on the same thread.

## Problem

The GUI capture loop calls `QApplication.processEvents()` once per 1.5 s iteration. Resize, drag, and close events can be delayed by up to that interval.

## Solution

Use `qasync` (already installed: `qasync==0.28.0`) to replace the asyncio loop with one backed by Qt's event loop.

## Changes in `main.py`

**1. Entry point (`__main__` block)**
Replace `asyncio.run(main(...))` with:
```python
import qasync, signal
loop = qasync.QEventLoop(app)
asyncio.set_event_loop(loop)

def _handle_sigint(*_):
    loop.call_soon_threadsafe(loop.stop)
signal.signal(signal.SIGINT, _handle_sigint)

with loop:
    loop.run_until_complete(main(...))
```

**2. GUI capture loop**  
- Remove `_gui_running = True` flag and `while _gui_running`  
- Remove `QApplication.processEvents()` call (lines 317–319)  
- Remove the Stage 4 TODO comment (line 276)  
- Replace with an `asyncio.Event` + task pattern:
```python
stop_event = asyncio.Event()
window.closeEvent = lambda e: (stop_event.set(), e.accept())

async def _capture_loop():
    while not stop_event.is_set():
        frame = await capture.get_frame(full=True)
        ...  # existing frame/OCR logic
        await asyncio.sleep(1.5)

capture_task = asyncio.ensure_future(_capture_loop())
await stop_event.wait()
capture_task.cancel()
try:
    await capture_task
except asyncio.CancelledError:
    pass
finally:
    preview.stop()
    window.close()
```

**3. CLI mode**  
Unchanged — `qasync` loop transparently replaces `asyncio.run()` for all code paths.

**4. Cleanup**  
`preview.stop()` and `window.close()` move to a `finally` block after task cancellation.

## Acceptance Criteria

- [ ] UI responds instantly to resize, drag, close at all times
- [ ] Closing window stops capture cleanly — no hung process
- [ ] `Ctrl+C` still terminates
- [ ] CLI mode (`--hwnd`) still works end-to-end
- [ ] No `processEvents()` calls remain in `main.py`
- [ ] Stage 4 TODO comment removed
