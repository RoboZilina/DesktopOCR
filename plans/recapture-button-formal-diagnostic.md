# Re‑Capture Button — Formal Line‑Accurate Diagnostic (Revised)

> **Scope:** Pre-OCR trigger cycle only.
> **Excludes:** Post-OCR cooldown, crash-handler gaps, translation/result phases.
> **Reviewers consulted:** Reviewer 1 (asyncio.Event persistence), Reviewer 3 (scope narrowing).

---

## 1. All `ocr_trigger` Interaction Sites

### 1.1 Trigger SET sites

| Site | File:Line | Triggered by | Context |
|------|-----------|-------------|---------|
| `_on_recapture()` | [`main.py:1270`](main.py:1270) | User presses re‑capture button | `_capture_gen += 1` at [`main.py:1269`](main.py:1269) runs first |
| `_trigger_after_stabilize()` | [`main.py:1281`](main.py:1281) | Stabilize timer expires (auto mode only) | `await asyncio.sleep(STABILIZE_DELAY)` = 0.5s delay |

### 1.2 Trigger WAIT sites

| Site | File:Line | Mode | Timeout |
|------|-----------|------|---------|
| Auto‑capture trigger wait | [`main.py:1317`](main.py:1317) | `auto_capture=True` | 0.5s |
| Manual trigger wait | [`main.py:1326`](main.py:1326) | `auto_capture=False` | 1.5s |

### 1.3 Trigger CLEAR sites

| Site | File:Line | When |
|------|-----------|------|
| Auto‑capture clear | [`main.py:1318`](main.py:1318) | Immediately after `wait_for` returns (non‑timeout) |
| Manual clear | [`main.py:1327`](main.py:1327) | Immediately after `wait_for` returns (non‑timeout) |

### 1.4 `_capture_gen` mutation sites

| Site | File:Line | Direction | Why |
|------|-----------|-----------|-----|
| `_on_recapture()` | [`main.py:1269`](main.py:1269) | `+= 1` | Invalidate in‑flight OCR result |
| `_ocr_task()` (auto mode) | [`main.py:1321`](main.py:1321) | `+= 1` | Generation for this OCR cycle |
| Stale‑result guard | [`main.py:1342`](main.py:1342) | read | Compares `this_gen` vs current `_capture_gen` |

---

## 2. Critical Re‑evaluation Against Reviewer Feedback

### Reviewer 1's Key Point: `asyncio.Event` is persistent

> *"If a trigger is set during the 'Post-OCR sleep' or the OCR processing itself, `ocr_trigger.wait()` should return immediately on the next iteration because `asyncio.Event` state is persistent—unless something is clearing it unexpectedly."*

**Verdict: CORRECT.** This is the most important nuance.

`asyncio.Event` is a **sticky boolean flag**. Once `.set()` is called, all subsequent `.wait()` calls return `True` immediately — until `.clear()` is called. This means:

- ✅ If the re‑capture trigger is set **while the loop is busy** in `capture_once()` (line 1338) or cooldown (line 1376), the trigger **persists** and will be picked up on the next `wait_for()`.
- ❌ My original diagnosis overstated the "busy loop loses trigger" scenario. The trigger does NOT get lost just because the loop is busy — it waits.
- ⚠️ The **only** point where the trigger can be lost is if `.clear()` is called after `.set()` and before the next `.wait()`.

### Reviewer 3's Scope: Pre-OCR phase only

> *"Map the exact trigger-check and trigger-set points... Exclude post-OCR cooldown, crash-handler gaps."*

**Verdict: Accepted.** The post-OCR phase bugs (trigger stealing, crash handlers) are separate issues. The pre-OCR race is the focus.

---

## 3. The Pre-OCR Race Condition — Precise Analysis

### 3.1 The ONLY pre-OCR race window

The race exists at precisely two lines:

| Mode | Race location | Window |
|------|--------------|--------|
| Auto | [`main.py:1317-1318`](main.py:1317) | Between `wait_for` return and `ocr_trigger.clear()` |
| Manual | [`main.py:1326-1327`](main.py:1326) | Between `wait_for` return and `ocr_trigger.clear()` |

```python
# Lines 1317-1318 (auto) / 1326-1327 (manual)
await asyncio.wait_for(ocr_trigger.wait(), timeout=0.5)  # ← returns
# ⚠️ RACE WINDOW: _on_recapture can fire here
ocr_trigger.clear()  # ← CONSUMES whatever trigger was set
```

**How the race works:**

```
Time │ Async event loop                  │ Qt signal handler
─────┼───────────────────────────────────┼────────────────────
  T  │ wait_for returns (stabilize set)  │
  T  │                                   │ _on_recapture fires
  T  │                                   │   _capture_gen += 1  [1269]
  T  │                                   │   ocr_trigger.set()  [1270]
  T  │ ocr_trigger.clear() ← EATS IT!    │
```

**What gets consumed:** The re‑capture trigger that was just `.set()` by the Qt handler is **immediately** `.clear()`'d by the async loop. The re‑capture event is gone.

### 3.2 Why this race is real (not just theoretical)

`_on_recapture` is a **PyQt6 signal handler** connected at [`main.py:1271`](main.py:1271):

```python
window.recapture_requested.connect(_on_recapture)
```

PyQt6 signals run on the **Qt event loop**, which is interleaved with the **asyncio event loop** via `QEventLoop` integration. The Qt event loop can process signals at any `await` point in the async code — including **between** `wait_for()` returning and the next bytecode instruction (`.clear()`).

Under CPython's GIL, the interleaving is at bytecode granularity, but there is **no mutual exclusion** between the two operations on `asyncio.Event`'s internal `_value` flag.

### 3.3 What happens AFTER the race (the "no log" mechanism)

The race doesn't directly cause "no log." The chain of events is:

**Step A:** Re‑capture trigger consumed by `clear()`.

**Step B:** The loop proceeds with the current iteration's OCR (triggered by stabilize timer or previous event):

```
_capture_gen += 1          [1321]  ← bump A
this_gen = _capture_gen            ← matches current gen
capture_once() runs        [1338]
```

If `_on_recapture` fired **after** line 1321 (bump A) but **before** capture_once, then:

```
_capture_gen += 1          [1321]  ← _capture_gen = N+1
this_gen = N+1
_on_recapture fires         [1269] ← _capture_gen = N+2, ocr_trigger.set()
capture_once() returns     [1338]
this_gen (N+1) != _capture_gen (N+2)  →  continue  [1342] ← SILENT DISCARD
```

**The stale guard discards the result — no log produced.**

**Step C:** The loop returns to `wait_for` at line 1317/1326.

Now the question: **is the trigger still set?**

| If `_on_recapture` fired... | Trigger state at next `wait_for` | Result |
|---|---|---|
| **Before** `clear()` (race window) | CLEARED by step 2 | ❌ No trigger → timeout → continue |
| **After** `clear()` but before capture_once | ✅ STILL SET → `wait_for` returns | OCR runs → LOGGED ✓ |
| During capture_once | ✅ STILL SET → `wait_for` returns | OCR runs → LOGGED ✓ |

**The "no log" scenario requires BOTH:**
1. The trigger consumed by `clear()` (narrow race window)
2. The stale guard discards the current OCR (double-bump of `_capture_gen`)

---

## 4. Double‑Bump Problem — The Hidden Amplifier

The `_capture_gen` counter is incremented at **two independent sites**:

| Site | Line | When |
|------|------|------|
| `_on_recapture()` | [`1269`](main.py:1269) | On every re‑capture button press |
| `_ocr_task()` auto mode | [`1321`](main.py:1321) | On every OCR cycle (after trigger consumed) |

**This means:** A single re‑capture button press during an OCR cycle bumps `_capture_gen` **twice** — once by the button handler, once by the loop body.

**The stale guard** at [`main.py:1342`](main.py:1342) is:

```python
if this_gen is not None and this_gen != _capture_gen:
    continue
```

**In auto mode** (`this_gen` = `_capture_gen` at line 1321): If `_on_recapture` fires after line 1321, `_capture_gen` is bumped again, making `this_gen != _capture_gen` → **result discarded** → no log.

**In manual mode** (`this_gen = None`): The stale guard is **always skipped** → results are never discarded → a log is ALWAYS produced for the current OCR cycle (if `res is not None`).

---

## 5. Complete Trigger Timeline: Pre-OCR Only

```mermaid
sequenceDiagram
    participant Qt as Qt Signal (_on_recapture)
    participant Preview as Preview (_trigger_after_stabilize)
    participant Trigger as ocr_trigger (asyncio.Event)
    participant Loop as _ocr_task (pre-OCR only)

    Note over Loop: Guard checks [1309-1314]
    
    alt Normal auto cycle
        Preview->>Trigger: set() [1281] after 0.5s stabilize
        Loop->>Trigger: wait_for returns [1317]
        Note over Qt,Loop: ⚠️ RACE WINDOW (microseconds)
        Qt->>Trigger: set() [1270]
        Loop->>Trigger: clear() [1318] ← CONSUMES Qt's set
        Loop->>Loop: _capture_gen += 1 [1321]
        Note over Loop: Proceeds with stabilize-triggered OCR
    else Race hits + stale discard
        Preview->>Trigger: set() [1281]
        Loop->>Trigger: wait_for returns [1317]
        Loop->>Trigger: clear() [1318]
        Loop->>Loop: _capture_gen += 1 [1321]
        Qt->>Loop: _capture_gen += 1 [1269]
        Qt->>Trigger: set() [1270] ← PERSISTS
        Loop->>Loop: OCR runs → stale guard fires [1342]
        Loop->>Loop: continue ← NO LOG
        Loop->>Trigger: wait_for [1317] → returns (Qt set persists!)
        Loop->>Trigger: clear() [1318]
        Loop->>Loop: OCR runs → LOGGED ✓
    else Manual mode + race
        Qt->>Trigger: set() [1270]
        Loop->>Trigger: wait_for returns [1326]
        Loop->>Trigger: clear() [1327] ← CONSUMES
        Loop->>Loop: this_gen = None [1330]
        Loop->>Loop: OCR runs → LOGGED ✓ (stale guard skipped)
        Loop->>Trigger: wait_for [1326] → NO trigger → 1.5s timeout
    end
```

---

## 6. Corrected Diagnostic Conclusion

| Claim | Original Diagnosis | Corrected Diagnosis |
|-------|-------------------|-------------------|
| Race condition exists? | Yes, at clear() | Yes, at clear() |
| Loop "busy" loses trigger? | Yes | **NO.** `asyncio.Event` is persistent. Busy phases only **delay** trigger pickup, they don't lose it. |
| Trigger loss mechanism | Loop doesn't check when busy | `.clear()` consumes trigger set in the narrow window between `wait_for` return and `clear()` |
| "No log" cause | Trigger lost + loop never reaches check | Trigger consumed by `clear()` **AND** stale guard discards result (auto mode) **OR** `capture_once()` returns `None` (manual mode) |
| Race window width | Not analyzed | **Microseconds** — between `wait_for()` returning (line 1317/1326) and `clear()` (line 1318/1327) |
| Recovery (auto mode) | Not analyzed | Fast: ~0.5-1.0s via next stabilize timer |
| Recovery (manual mode) | Not analyzed | Slow: 1.5s timeout + user must press re-capture again |

### What actually causes "sometimes works, sometimes doesn't"

**In auto mode:** The race window is narrow (~µs), so it misses most of the time. When it hits, the stale guard discards one OCR cycle and the next one runs normally. The user sees a ~0.5-1.0s delay. If they don't wait, they perceive "no log."

**In manual mode:** The race window is the same width, but the consequences are worse. If the trigger is consumed AND `capture_once()` returns `None` (no content to OCR), the loop returns to `wait_for` with no trigger and blocks for 1.5s. The user sees nothing.

### What does NOT cause the issue

- ❌ The loop being "busy" in `capture_once()` or cooldown — `asyncio.Event` persistence means the trigger waits
- ❌ The post-OCR trigger-stealing bug (already fixed, now uses `asyncio.sleep`)
- ❌ The crash-handler gap (separate issue)
- ❌ Broken signal wiring (Fact 1 already ruled this out)

---

## 7. Line-Accurate Reference Table

| What | File | Line | Relevance |
|------|------|------|-----------|
| `ocr_trigger` creation | [`main.py`](main.py) | 1226 | The shared event object |
| `_on_recapture()` — `set()` | [`main.py`](main.py) | 1270 | **Trigger source** for re-capture |
| `_on_recapture()` — `_capture_gen += 1` | [`main.py`](main.py) | 1269 | **Double-bump contributor** |
| Signal connection | [`main.py`](main.py) | 1271 | Confirms UI→Python path healthy |
| `_trigger_after_stabilize()` — `set()` | [`main.py`](main.py) | 1281 | **Trigger source** for auto-capture |
| Auto trigger `wait_for` | [`main.py`](main.py) | 1317 | **Pre-OCR trigger check** (auto mode) |
| Auto `clear()` | [`main.py`](main.py) | 1318 | **Race window end** — consumes trigger |
| `_capture_gen += 1` (loop) | [`main.py`](main.py) | 1321 | **Double-bump contributor** |
| `this_gen = _capture_gen` | [`main.py`](main.py) | 1322 | Result generation snapshot |
| Manual trigger `wait_for` | [`main.py`](main.py) | 1326 | **Pre-OCR trigger check** (manual mode) |
| Manual `clear()` | [`main.py`](main.py) | 1327 | **Race window end** — consumes trigger (manual) |
| `this_gen = None` | [`main.py`](main.py) | 1330 | Disables stale guard in manual mode |
| Stale guard | [`main.py`](main.py) | 1342 | Silent discard when triggered |

---

## 8. Remaining Questions (Still Diagnosis)

1. **Does `capture_once()` ever return `None` under normal conditions?** If yes, this completes the "no log" puzzle for manual mode.
2. **What is the typical duration of `capture_once()`?** If it's consistently fast (<0.2s), the stale-discard delay is minor. If it's slow (>1s), the delayed-log scenario is more impactful.
3. **Is `auto_capture` typically ON or OFF when the user experiences the failure?** The diagnosis differs significantly between modes.

These are factual data points, not code changes — still in diagnostic scope.
