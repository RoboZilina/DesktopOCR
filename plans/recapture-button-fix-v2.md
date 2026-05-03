# Re‑Capture Button — Corrected Diagnosis & Minimal Fix

## Revised Diagnosis (After Full Re‑Evaluation)

### What I Got Wrong in v1

1. **❌ "clear() eats the re‑capture trigger"** — False for the `qasync.QEventLoop` integration used at [`main.py:1566`](main.py:1566). In `qasync`, Qt signal handlers (like `_on_recapture`) fire **only at `await` points**, not between synchronous lines. Therefore `ocr_trigger.clear()` at [`main.py:1318`](main.py:1318) / [`main.py:1327`](main.py:1327) CANNOT race with `ocr_trigger.set()` from `_on_recapture`. The re‑capture trigger is **never silently consumed**.

2. **❌ "Busy loop loses trigger"** — Overstated. `asyncio.Event` is **persistent** (Reviewer 1 was correct). Being busy in `capture_once()` or cooldown only **delays** trigger pickup; the trigger persists until the next `wait_for()`.

### What IS Actually Happening

The true mechanism has two independent layers:

#### Layer 1: Main thread `_capture_gen` double‑bump

| Site | Line | Bump | Conflict |
|------|------|------|----------|
| `_on_recapture()` | [`1269`](main.py:1269) | `_capture_gen += 1` | Bump A |
| `_ocr_task()` loop body | [`1321`](main.py:1321) | `_capture_gen += 1` | Bump B |

When re‑capture is pressed **during** `capture_once()` (line 1338):

```
_capture_gen = N
Bump B at 1321: _capture_gen = N+1, this_gen = N+1
...
capture_once() starts  [1338] — AWAIT POINT
  → Qt processes re‑capture signal
  → _on_recapture at 1269: Bump A → _capture_gen = N+2
  → ocr_trigger.set() ← PERSISTS
capture_once() returns
stale guard [1342]: this_gen (N+1) != _capture_gen (N+2) → DISCARD, no log
```

The **stale guard silently discards** the result — no log produced. The loop `continue`s back to `wait_for`, finds the trigger still set (persistent), and runs fresh OCR. A log appears ~1 OCR cycle later.

#### Layer 2: Pipeline `capture_generation` — the missing link

The `CapturePipeline` at [`core/capture_pipeline.py`](core/capture_pipeline.py) has its **own independent** generation counter:

```python
# capture_pipeline.py:67-92
async def capture_once(self, ...):
    async with self._lock:
        self.capture_generation += 1          # [73]
        my_gen = self.capture_generation       # [74]
        frame = await self.capture.get_frame() # [77] — AWAIT
        if self.capture_generation != my_gen:  # [81] ← STALE CHECK
            return None                        # [82] ← SILENT FAILURE
        ...
        res = await self.engine_manager.run_ocr(...)  # [89] — AWAIT
        if self.capture_generation != my_gen:  # [91] ← STALE CHECK
            return None                        # [92] ← SILENT FAILURE
```

`capture_once()` returns `None` if `capture_generation` changes mid-flight (stale check).

**`invalidate_generation()`** at [`core/capture_pipeline.py:63`](core/capture_pipeline.py:63) bumps this counter — but it's only called from [`_on_region_changed`](main.py:577), **NOT** from `_on_recapture`.

### Three Pathways to "No Log"

| # | Pathway | How it produces "no log" |
|---|---------|--------------------------|
| 1 | Re‑capture during `capture_once()` → stale guard discards → next `capture_once()` returns None (no text / frame unavailable) | Zero log entries for either OCR cycle |
| 2 | Re‑capture during `capture_once()` → stale guard discards → next `capture_once()` succeeds → log appears delayed (~1-2s) | User doesn't wait long enough |
| 3 | Re‑capture during streaming guard (disabled) → trigger persists → eventual OCR produces log | Same delay issue |

**Pathway #1 is the most likely match for "log does not show anything."**

---

## Proposed Fix — Minimal (1‑line change)

**Add `pipeline.invalidate_generation()` to `_on_recapture()`.**

### What it does

When the re‑capture button is pressed during an in‑flight `capture_once()`:

1. `_on_recapture` bumps `capture_generation` (pipeline's counter)
2. The in‑flight `capture_once()` hits its stale check [`capture_pipeline.py:81`](core/capture_pipeline.py:81) or [`capture_pipeline.py:91`](core/capture_pipeline.py:91) at the next `await`
3. `capture_once()` returns `None` immediately → short-circuits
4. The stale guard at [`main.py:1342`](main.py:1342) discards (already works)
5. `ocr_trigger` is still set (persistent!) → `wait_for` returns immediately
6. **Fresh `capture_once()` starts sooner** — reduced delay

### Before vs After timing

| Phase | Current (ms) | With fix (ms) |
|-------|-------------|---------------|
| In‑flight `capture_once()` runs to completion | 500-2000 | **~0** (short-circuits at next await) |
| Stale guard discards | instant | instant |
| `wait_for` returns (trigger was set) | instant | instant |
| Fresh `capture_once()` runs | 500-2000 | 500-2000 |
| **Total delay to fresh OCR result** | **1000-4000** | **500-2000** |

### Why this is safe

- `invalidate_generation()` is already used the same way in [`_on_region_changed`](main.py:577) — this extends the same pattern to the re‑capture handler.
- `invalidate_generation()` is synchronous (no `await`) — can be called from a Qt signal handler.
- `pipeline` is in scope as a closure variable — no `nonlocal` needed.
- It doesn't acquire the `asyncio.Lock` — safe to call from synchronous context.
- Short‑circuits existing `capture_once()` via stale check — this is the **designed use** of the generation counter.

### The change

**File:** [`main.py`](main.py), function `_on_recapture()`, line 1269

Current (lines 1269-1270):
```python
_capture_gen += 1
ocr_trigger.set()
```

After:
```python
_capture_gen += 1
pipeline.invalidate_generation()  # short-circuit in-flight capture_once
ocr_trigger.set()
```

### What this does NOT fix

- **Pathway #2** (user doesn't wait long enough) — this is a UX perception issue, not a code bug
- **`capture_once()` returning None for other reasons** (no text, no frame) — those are separate concerns
- **Manual mode** — the trigger is correctly picked up; the fix still helps by short‑circuiting any in‑flight OCR

### Files modified

| File | Lines | Change |
|------|-------|--------|
| [`main.py`](main.py) | 1269 | Add `pipeline.invalidate_generation()` between `_capture_gen += 1` and `ocr_trigger.set()` |

**Total: 1 line added, 0 lines removed.**

---

## Summary of Findings

| Finding | Status |
|---------|--------|
| `ocr_trigger` signal path is healthy | ✅ Confirmed (Fact 1) |
| `asyncio.Event` is persistent — trigger is NOT lost while loop is busy | ✅ Confirmed (Reviewer 1 correct) |
| `qasync` prevents signal interleaving between synchronous lines | ✅ Confirmed — no clear() race |
| Pipeline has its own generation counter with stale checks | ✅ Discovered — critical layer |
| `invalidate_generation()` is missing from `_on_recapture()` | ✅ Root cause of unnecessary delay |
| `_capture_gen` double‑bump causes stale guard discard | ✅ Confirmed — amplifies delay |
| Adding `pipeline.invalidate_generation()` is a safe, minimal fix | ✅ Proposed |
