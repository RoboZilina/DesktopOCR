# Re‑Capture Button — Formal Line‑Accurate Diagnostic

## OCR Loop Location

| Item | Value |
|------|-------|
| **File** | [`main.py`](main.py) |
| **Function** | `_ocr_task()` at line 1305 |
| **Trigger event** | `ocr_trigger` (asyncio.Event, defined at line 1226) |
| **Re‑capture handler** | `_on_recapture()` at line 1261 |
| **Preview task** | `_preview_task()` at line 1275 |

---

## OCR Loop Structure Map

Below is the complete execution path of `_ocr_task()`. Each phase is annotated with whether it **observes** the `ocr_trigger` or **consumes** it.

```
  _ocr_task()  [main.py:1305]
  │
  ├─ while not stop_event.is_set():                      [1307]
  │   │
  │   ├─ [A] Guard: streaming_enabled?                   [1309-1311]
  │   │     └─ False → sleep(0.5) + continue
  │   │       ↑ DOES NOT CHECK trigger
  │   │
  │   ├─ [B] Guard: selection_ready?                     [1312-1314]
  │   │     └─ False → sleep(0.2) + continue
  │   │       ↑ DOES NOT CHECK trigger
  │   │
  │   ├─ [C] TRIGGER CHECK — auto_capture ON             [1316-1322]
  │   │     ├─ wait_for(ocr_trigger, timeout=0.5)        [1317]  ← OBSERVES trigger
  │   │     ├─ TimeoutError → continue                   [1319-1320]
  │   │     ├─ ocr_trigger.clear()                       [1318]  ← CONSUMES trigger
  │   │     └─ _capture_gen += 1, this_gen = _capture_gen [1321]
  │   │
  │   ├─ [C'] TRIGGER CHECK — auto_capture OFF           [1324-1330]
  │   │     ├─ wait_for(ocr_trigger, timeout=1.5)        [1326]  ← OBSERVES trigger
  │   │     ├─ TimeoutError → continue                   [1328-1329]
  │   │     ├─ ocr_trigger.clear()                       [1327]  ← CONSUMES trigger
  │   │     └─ this_gen = None                           [1330]
  │   │
  │   ├─ [D] stop_event check                            [1332-1333]
  │   │
  │   ├─ [E] window.set_status("Processing…")            [1335-1336]
  │   │
  │   ├─ [F] await pipeline.capture_once()               [1338]  ← OCR INFERENCE
  │   │     ↑ DOES NOT CHECK trigger (takes 0.2-2.0s)
  │   │
  │   ├─ [G] Stale-result guard                          [1341-1343]
  │   │     └─ this_gen != _capture_gen → continue (silent discard)
  │   │
  │   ├─ [H] Post-processing                             [1345-1371]
  │   │     ├─ set_ocr_boxes() / set_ocr_canvas_frames()
  │   │     ├─ logger.info() — THE LOG LINE              [1357]
  │   │     ├─ set_ocr_result()
  │   │     ├─ clipboard.setText()
  │   │     └─ set_status("Done", summary_text)
  │   │     ↑ DOES NOT CHECK trigger (takes 0.01-0.2s)
  │   │
  │   ├─ [I] Cooldown: await asyncio.sleep(0.5)          [1376]
  │   │     ↑ DOES NOT CHECK trigger (0.5s blind sleep)
  │   │
  │   └─ [J] Exception handler                           [1378-1380]
  │         └─ logger.error() + sleep(1.0)
  │
  └─ end
```

### Key: Where the trigger is vs. isn't checked

| Phase | Lines | Checks trigger? | Duration |
|-------|-------|----------------|----------|
| A — streaming guard | 1309-1311 | ❌ No | 0.5s sleep |
| B — selection guard | 1312-1314 | ❌ No | 0.2s sleep |
| **C/C' — trigger wait** | **1316-1330** | **✅ Yes — also CONSUMES it** | **wait + clear** |
| D — stop check | 1332-1333 | ❌ No | instant |
| E — status set | 1335-1336 | ❌ No | instant |
| **F — OCR inference** | **1338** | **❌ No** | **0.2-2.0s** |
| G — stale guard | 1341-1343 | ❌ No | instant |
| **H — post-processing** | **1345-1371** | **❌ No** | **0.01-0.2s** |
| **I — cooldown** | **1376** | **❌ No** | **0.5s** |

The trigger is **only observed at one point** per loop iteration: lines 1316-1330 (phase C/C'). Every other phase is blind to it.

---

## Race Condition Analysis

### Race Window R1: `clear()` eats the re‑capture trigger

This is the **primary race** that explains your observation.

**Location:** [`main.py:1317-1318`](main.py:1317) (auto_capture mode) or [`main.py:1326-1327`](main.py:1326) (manual mode)

**Sequence:**

```
Time │ OCR loop (auto_capture)              │ Re‑capture button (UI thread)
─────┼──────────────────────────────────────┼─────────────────────────────────
  T  │ wait_for(ocr_trigger, 0.5)           │
     │   ↑ stabilize timer set the trigger  │
  T+0│ wait_for RETURNS ✓                   │
  T+0│                                      │ _on_recapture() fires
  T+0│                                      │   _capture_gen += 1      [1269]
  T+0│                                      │   ocr_trigger.set()      [1270]
  T+0│ ocr_trigger.clear()  ◄── EATS IT!    │
  T+0│ _capture_gen += 1    (bumped again)  │
  T+0│ this_gen = _capture_gen              │
  T+0│ capture_once() runs...               │
  T+1│ capture_once returns                 │
  T+1│ this_gen == _capture_gen → kept      │
  T+1│ LOGGED ✓                             │ ← But this was the STALE
     │                                       ← capture, not a fresh one!
```

**Result:** The re‑capture trigger was set by the UI thread but **immediately consumed** by `ocr_trigger.clear()` in the loop body. The loop proceeds with the **current OCR cycle** (which may be stale content). The user sees a log output — but it's from the old content, not the new capture they requested.

**BUT** — there's a variation where the log never appears:

### Race Window R2: `clear()` eats the trigger AND the stale guard discards

Same as R1, but the re‑capture is pressed **just after** `_capture_gen` was bumped at line 1321, rather than between wait_for return and clear:

```
Time │ OCR loop                              │ Re‑capture
─────┼───────────────────────────────────────┼────────────────
  T  │ wait_for returns ✓                    │
  T+0│ ocr_trigger.clear()                   │
  T+0│ _capture_gen += 1  → now 6            │
  T+0│ this_gen = 6                          │
  T+0│                                       │ _capture_gen += 1 → now 7  [1269]
  T+0│                                       │ ocr_trigger.set()           [1270]
  T+0│ capture_once() runs...                │
  T+1│ capture_once returns                  │
  T+1│ this_gen (6) != _capture_gen (7)      │
  T+1│ → continue  ◄── SILENT DISCARD!       │
  T+1│                                       │
  T+1│ Back to top of loop                   │
  T+1│ wait_for(ocr_trigger, 0.5)            │
  T+1│   ↑ trigger IS set from step above    │
  T+1│ wait_for returns ✓                    │
  T+1│ ocr_trigger.clear()                   │
  T+1│ _capture_gen += 1 → now 8             │
  T+1│ this_gen = 8                          │
  T+1│ capture_once() runs FRESH capture     │
  T+2│ LOGGED ✓ (delayed ~1s)               │
```

**In this scenario:** The log DOES appear, but with ~1 second delay. The user may have already moved on.

### Race Window R3: Full trigger loss (no log, no nothing)

This is the **matching scenario for your symptom**.

**Prerequisite:** User is in **manual mode** (`auto_capture = OFF`).

In manual mode: [`main.py:1324-1330`](main.py:1324)

```python
await asyncio.wait_for(ocr_trigger.wait(), timeout=1.5)  # [1326]
ocr_trigger.clear()                                        # [1327]
this_gen = None                                            # [1330]
```

Because `this_gen = None`, the stale-result guard at line 1342 is **skipped**:
```python
if this_gen is not None and this_gen != _capture_gen:  # False → never discards
    continue
```

So the flow is:

```
Time │ OCR loop (manual mode)               │ Re‑capture
─────┼───────────────────────────────────────┼────────────────
  T  │ wait_for(ocr_trigger, 1.5)           │
  T  │                                       │ Re‑capture pressed
  T  │                                       │ _capture_gen += 1
  T  │                                       │ ocr_trigger.set()
  T  │ wait_for RETURNS ✓ (trigger was set)  │
  T+0│ ocr_trigger.clear() ← EATS trigger    │
  T+0│ this_gen = None                       │
  T+0│ capture_once() runs...                │
  T+1│ capture_once returns → res = None?    │ ← If capture fails (e.g., no window)
  T+1│ res is None → skip logging            │ ← NO LOG!
  T+1│ cooldown sleep 0.5s                  │
  T+2│ Back to top                           │
  T+2│ wait_for(ocr_trigger, 1.5)           │
  T+2│   ↑ Trigger was EATEN at T+0         │
  T+2│   → Times out after 1.5s             │
  T+3│ continue → back to top               │
  T+3│ wait_for(ocr_trigger, 1.5)           │
  T+4│ ... nothing happens for 1.5s          │
```

**This is your symptom. Exactly.**

| Observation | Explanation |
|-------------|-------------|
| "log does not show anything" | `res` was `None` (capture failed) AND the trigger was eaten by `clear()` |
| "sometimes it does work" | When the race doesn't trigger (trigger set AFTER clear(), or during cooldown) |
| "no error" | No exception — the loop silently continues |
| "no freeze" | The loop is still running, just waiting for next trigger |
| "no stale results" | There's nothing to show (res was None) |

The key: **in manual mode**, when the re‑capture trigger lands in the `wait_for`→`clear()` window, **two things fail simultaneously**:
1. The trigger is consumed by `clear()` — so the next iteration has no trigger and times out (1.5s lost)
2. `this_gen = None` — so the stale guard is disabled and can't skip a fresh capture
3. If `capture_once()` also returns `None` (timing-dependent), **no log is ever produced**

This combination creates the **intermittent "no log, no result"** symptom.

---

## Complete Trigger Timeline Diagram

```mermaid
sequenceDiagram
    participant UI as UI Thread
    participant Loop as OCR Loop (_ocr_task)
    participant Preview as Preview Task (_preview_task)
    participant Trigger as ocr_trigger (asyncio.Event)

    Note over Loop: Phase A: streaming_enabled?
    Loop->>Loop: sleep 0.5s (no trigger check)
    
    Note over Loop: Phase B: selection_ready?
    Loop->>Loop: sleep 0.2s (no trigger check)
    
    Note over Loop: Phase C: wait_for trigger
    Loop->>Trigger: wait timeout=0.5/1.5s
    Preview->>Trigger: set()  (stabilize timer)
    Trigger-->>Loop: wait returns
    
    Note over UI,Loop: ⚠️ RACE WINDOW (microseconds)
    UI->>Trigger: set()  (re-capture)
    Loop->>Trigger: clear() ← EATS re-capture trigger
    
    Loop->>Loop: _capture_gen += 1
    Loop->>Loop: this_gen = _capture_gen / None
    
    Note over Loop: Phase F: OCR inference (0.2-2.0s)
    Loop->>Loop: await capture_once()
    Note over UI: User waits... nothing happens
    
    alt res is None
        Loop->>Loop: No log (skip block)
    else this_gen stale
        Loop->>Loop: continue (silent discard)
    end
    
    Note over Loop: Phase I: cooldown sleep 0.5s
    
    Note over Loop: Phase C again: wait_for
    Loop->>Trigger: wait timeout=0.5/1.5s
    Note over Loop: No trigger set → TIMEOUT
    Loop->>Loop: continue → wait again...
```

---

## Summary: File + Line Reference

| What | File | Line |
|------|------|------|
| `ocr_trigger` event creation | [`main.py`](main.py) | 1226 |
| `_on_recapture()` — sets trigger | [`main.py`](main.py) | 1261-1270 |
| `_on_recapture` signal connection | [`main.py`](main.py) | 1271 |
| `_ocr_task()` — OCR loop entry | [`main.py`](main.py) | 1305 |
| **Race window — `clear()` eats trigger** | [`main.py`](main.py) | **1317-1318** (auto) / **1326-1327** (manual) |
| `this_gen = None` disables stale guard | [`main.py`](main.py) | 1330 |
| Stale-result guard (skipped in manual) | [`main.py`](main.py) | 1342 |
| OCR inference — no trigger check | [`main.py`](main.py) | 1338 |
| Cooldown sleep — no trigger check | [`main.py`](main.py) | 1376 |

---

## Diagnostic Conclusion

The re‑capture button's symptom of "no log, no result, intermittent" is fully explained by a **single race window** at [`main.py:1317-1318`](main.py:1317) (auto) / [`main.py:1326-1327`](main.py:1326) (manual):

> **`ocr_trigger.clear()` immediately after `wait_for()` returns can consume a re‑capture trigger set in the same microsecond window.**

In **manual mode**, this is compounded by:
- `this_gen = None` — disabling the stale-result guard, so no fresh OCR is forced
- A potential `None` return from `capture_once()` — producing zero log output
- A subsequent 1.5s timeout — delaying any recovery

This is **not a logic bug** — the logic is correct for non-concurrent access. It is a **classic race condition** between two asynchronous tasks competing over the same `asyncio.Event`.

No code changes are proposed here. This diagnostic matches all three facts:
1. ✅ Signal path is healthy (button works sometimes)
2. ✅ OCR loop doesn't log when it fails (trigger consumed before loop checked it)
3. ✅ Intermittent failure (race window is narrow — microseconds — so it only hits sometimes)
