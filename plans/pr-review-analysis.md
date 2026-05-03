# DesktopOCR — PR Review Analysis

**Date:** 2026-05-03  
**Scope:** Cross-reference each PR review finding against actual source code to verify accuracy, assess severity, and evaluate fix risk at RC.

---

## 1. HIGH Priority — Verified Findings

### H-1: `DEFAULT_REGION` reassigned without `global` — **HIGH, must fix**

| Aspect | Detail |
|--------|--------|
| **File** | [`main.py:315-328`](main.py:315) |
| **PR Claim** | Assignment creates a local variable; module-level is never updated |
| **Code Evidence** | Line 321: `DEFAULT_REGION = tuple(int(v * scale) for v in DEFAULT_REGION)` inside `main()` with no `global` declaration |
| **My Assessment** | **The PR is correct AND there is a second, worse bug:** When `scale == 1.0` (exactly 96 DPI — the most common 1080p display), the `if` at line 320 is False, so `DEFAULT_REGION` is **never assigned** as a local. Line 327 `selected_region = DEFAULT_REGION` then raises **`UnboundLocalError`**, crashing the app. The DPI-scaling fix actually **introduces a crash on the most common display configuration** (1080p @ 100%). |
| **Bug Risk** | **HIGH** — crashes on every 1080p/100%-scale display at startup |
| **Fix Risk** | **LOW** — two options: (a) add `global DEFAULT_REGION` before line 316, or (b) better: avoid mutating the module constant and use a local `scaled_region` variable. Either is 1-2 lines. |
| **Verdict** | ⚠️ **Fix NOW before RC** |

---

### H-2: TTS dual `last_audio_path` / `_last_audio_path` — **LOW, intentional redundancy**

| Aspect | Detail |
|--------|--------|
| **File** | [`core/tts.py:24-25,74-75`](core/tts.py:24) |
| **PR Claim** | Redundant attributes; risk of state drift |
| **Code Evidence** | `self.last_audio_path` (public, line 24) is read by [`tts/edge_tts_backend.py:22`](tts/edge_tts_backend.py:22) and [`tts/manager.py:30`](tts/manager.py:30). `self._last_audio_path` (private, line 25) is used internally for temp file cleanup (line 64). Both are always set to the same value at line 74-75. |
| **My Assessment** | **Intentional, not a bug.** The public attribute is an external API for the TTS backend wrappers (`tts/manager.py`, `tts/edge_tts_backend.py`). The private one is for internal cleanup. They always hold the same value. Removing one would break the external API. The redundancy is a safety measure — if someone in the future modifies one without the other, they'd diverge, but that's a future maintenance concern, not an RC bug. |
| **Bug Risk** | **NONE** at RC |
| **Fix Risk** | **LOW** but unnecessary — would change public API surface |
| **Verdict** | ✅ **DOCUMENT** — known intentional design. No RC action needed. |

---

### H-3: DeepL retry doesn't retry network errors — **MEDIUM, real gap**

| Aspect | Detail |
|--------|--------|
| **File** | [`core/translation/deepl_backend.py:76-141`](core/translation/deepl_backend.py:76) |
| **PR Claim** | `aiohttp.ClientError` immediately returns `""` without retrying |
| **Code Evidence** | The `except aiohttp.ClientError` at line 136 is **inside** the `for attempt in range(max_retries)` loop (same indent as `try:`). When a `ClientError` fires, the except handler runs `return ""` which **exits the loop**, preventing any retry. Only HTTP 429 is retried (lines 84-89). |
| **My Assessment** | **PR is correct.** Transient network errors (DNS failure, connection reset, timeout) abort immediately with no retry. For a free web endpoint (www2.deepl.com), network blips are arguably more common than rate limits. The fix is to `continue` (not `return`) on `ClientError` within the retry loop, just like the 429 handler does. |
| **Bug Risk** | **LOW-MEDIUM** — intermittent translation failures on flaky networks |
| **Fix Risk** | **LOW** — move `return ""` inside a check for `attempt == max_retries - 1`, similar to the 429 handler pattern. 3 lines change. |
| **Verdict** | ⚠️ **Fix NOW** — low risk, improves reliability |

---

### H-4: `_on_engine_changed` creates task without error tracking — **LOW, pre-existing**

| Aspect | Detail |
|--------|--------|
| **File** | [`main.py:418-419`](main.py:418) |
| **PR Claim** | `asyncio.create_task` without storing reference; unhandled exceptions are silently logged |
| **Code Evidence** | `lambda eid: asyncio.create_task(_on_engine_changed(eid))` — fires and forgets. If `switch_engine()` raises, the task exception is logged via the event loop's `call_exception_handler` but not surfaced to the user. |
| **My Assessment** | **PR is correct but low impact.** This is a pre-existing pattern (not introduced by RC patches). The risk of `switch_engine()` raising is very low — it's wrapped in its own try/except internally. The consequence of an unhandled exception is a silent engine-change failure (engine doesn't switch), which the user notices immediately and can retry. |
| **Bug Risk** | **LOW** — very unlikely to trigger |
| **Fix Risk** | **LOW** — add task exception callback or use a task-set pattern |
| **Verdict** | **DEFER** — pre-existing issue, low impact, not introduced by RC patches |

---

## 2. MEDIUM Priority — Verified Findings

### M-1: Pygame mixer busy-wait — **LOW, overstated by PR**

| Aspect | Detail |
|--------|--------|
| **File** | [`core/tts.py:84-85`](core/tts.py:84) |
| **PR Claim** | "Blocks the async event loop for the entire audio duration" |
| **Code Evidence** | `while pygame.mixer.music.get_busy(): await asyncio.sleep(0.1)` — polls every 100ms. |
| **My Assessment** | **PR is partially inaccurate.** `await asyncio.sleep(0.1)` **yields** to the event loop — it does NOT block it. Other coroutines can run during the 0.1s intervals. However, the `self._lock` (acquired at line 54) prevents concurrent TTS operations on the same instance. For a 2-second clip, that's ~20 iterations of poll-and-sleep — trivially low overhead. The 0.1s sleep granularity means a ~100ms delay between audio finishing and the coroutine unblocking, which is imperceptible. |
| **Bug Risk** | **NONE** — works correctly, just not maximally elegant |
| **Fix Risk** | **LOW** — could change to 0.01s for slightly faster unblock, but no practical benefit |
| **Verdict** | ✅ **DOCUMENT** — not a bug. Could optimize to 0.01s post-RC but no value at RC. |

---

### M-2: PyQt6 error message — **LOW, cosmetic**

| Aspect | Detail |
|--------|--------|
| **File** | [`main.py:1524`](main.py:1524) |
| **PR Claim** | Error says "Install PyQt6" but code falls back to PyQt5 |
| **Code Evidence** | `print("ERROR: Install PyQt6: pip install PyQt6")` — only mentions PyQt6. The fallback tries PyQt5 first at line 1521-1522. |
| **My Assessment** | **PR is correct.** The error message is incomplete — should say "Install PyQt6 or PyQt5" since both are tried. Trivial fix. |
| **Bug Risk** | **NONE** — only triggers if both PyQt5 AND PyQt6 are missing (extremely unlikely) |
| **Fix Risk** | **NONE** — 1 line string change |
| **Verdict** | **Fix NOW** — 1 line, zero risk, trivially correct |

---

## 3. LOW Priority — Correct Findings

| Finding | File | Verdict |
|---------|------|---------|
| L-1: capture.py:4 comment correct | [`core/capture.py:4`](core/capture.py:4) | ✅ Correct, already applied |
| L-2: crop_box None return — callers OK | [`core/tensor_utils.py:228-229`](core/tensor_utils.py:228) | ✅ Verified: both callers in [`engine_manager.py:1271`](core/engine_manager.py:1271) (`if crop is None or crop.size == 0`) and [`engine_manager.py:1467`](core/engine_manager.py:1467) (`if crop is not None and crop.size > 0`) handle None correctly. This is a strictly additive safety check — cropping code that previously received `(4,4)` or larger would now also correctly receive `(4,4)` or larger from valid boxes. For invalid boxes (negative dims), they now get `None` which both callers already handle. |
| L-3: anki_card_builder.html.escape correct | [`logic/anki_card_builder.py:187-189`](logic/anki_card_builder.py:187) | ✅ Correct, already applied |
| L-4: controls_bar._voice_id_map init correct | [`ui/controls_bar.py:38`](ui/controls_bar.py:38) | ✅ Correct, already applied |

---

## 4. Summary: What Actually Needs Action

### 🔴 Fix NOW (RC-blocking — 2 items)

| # | Issue | Fix | File | Lines | Risk |
|---|-------|-----|------|-------|------|
| 1 | **H-1: `DEFAULT_REGION` scope bug** — crashes on 1080p @ 100% DPI | Add `global DEFAULT_REGION` before line 316 OR use local `scaled_region` variable instead of mutating the module constant | [`main.py:321`](main.py:321) | +1 | **None** — pure scoping fix |
| 2 | **M-2: PyQt6 error message** | Change `"Install PyQt6"` → `"Install PyQt6 or PyQt5"` | [`main.py:1524`](main.py:1524) | +1 | **None** — string literal |

### 🟡 Fix NOW (low risk, real gap — 1 item)

| # | Issue | Fix | File | Lines | Risk |
|---|-------|-----|------|-------|------|
| 3 | **H-3: DeepL network error retry** | Move `return ""` for `ClientError` behind a last-attempt check, `continue` otherwise | [`core/translation/deepl_backend.py:136-138`](core/translation/deepl_backend.py:136) | ~4 | **Low** — only changes retry behavior for transient errors |

### ⏸️ DEFER / DOCUMENT (5 items — no RC action)

| # | Issue | Rationale |
|---|-------|-----------|
| 4 | H-2: TTS dual `last_audio_path` | Intentional design — public API + private cleanup. No bug. |
| 5 | H-4: `_on_engine_changed` create_task | Pre-existing. Low impact. Defer to post-RC. |
| 6 | M-1: pygame mixer busy-wait | `await asyncio.sleep()` does yield to event loop. Claim is overstated. Not a bug. |
| 7 | L-2: crop_box None callers | Already verified — both callers handle None correctly. No action needed. |
| 8 | L-1, L-3, L-4 | Already applied and verified in previous RC patches. |

---

## 5. RC Action Plan

### Execution Order

```
 1. 🔴 H-1: Add `global DEFAULT_REGION` to main()         [main.py:316]   1 line
 2. 🟡 H-3: Retry on ClientError in DeepL backend          [deepl_backend.py:136]  ~4 lines
 3. 🟢 M-2: Fix PyQt6→PyQt5 error message                  [main.py:1524]   1 line
```

**Total:** ~6 lines across 2 files. All three are independently verifiable. Zero changes touch the core OCR pipeline.

### Potential Concern

Item 1 (H-1) is a bug in the MED-1 RC patch applied in the previous round. The DPI-scaling code at [`main.py:315-324`](main.py:315) was supposed to improve first-run UX on non-1080p displays, but the missing `global` declaration means it crashes on the **most common** display configuration (1080p @ 100% DPI). This must be fixed before any RC build is distributed.
