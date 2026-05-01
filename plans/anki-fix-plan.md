# Anki Fix Plan — Mandatory Screenshot + Empty-Card Protection

**Based on:** Runtime log analysis + code review  
**Target files:** `core/capture.py`, `logic/anki_card_builder.py`, `main.py`, `ui/transcription_tray.py`

---

## Problem Summary

Two bugs prevent card creation:

1. **Screenshot retry loop always fails** — `get_frame(full=True)` returns `None` on retries because the MD5 frame-diff check sees the same frame content.
2. **Empty Front field** — When screenshot fails and front template is `"{Screenshot}"`, the Front field becomes `""`, causing AnkiConnect to reject with "cannot create note because it is empty".

---

## Step 1: Fix Screenshot Capture — Add `force` parameter to `get_frame()`

**File:** [`core/capture.py`](core/capture.py)

**What:** Add a `force: bool = False` parameter to `get_frame()` and `_apply_diff_and_crop()` that skips the MD5 hash check.

**Why:** The retry loop in `build_and_send_card()` needs to force-capture regardless of whether the frame content matches the previous capture. The MD5 dedup is useful for the main OCR loop (avoid processing identical frames), but for the Anki screenshot we always want a fresh capture.

**Changes:**

In [`core/capture.py:345`](core/capture.py:345) — `get_frame()` signature:
```python
async def get_frame(self, full: bool = False, force: bool = False) -> Optional[np.ndarray]:
```

Pass `force` through to `_apply_diff_and_crop()`:
```python
return await self._get_frame_bitblt(full=full, force=force)
```

In [`core/capture.py:605`](core/capture.py:605) — `_get_frame_bitblt()`:
```python
async def _get_frame_bitblt(self, full: bool = False, force: bool = False) -> Optional[np.ndarray]:
    loop = asyncio.get_running_loop()
    raw_frame = await loop.run_in_executor(None, _capture_bitblt, self._hwnd)
    if raw_frame is None:
        return None
    return self._apply_diff_and_crop(raw_frame, full=full, force=force)
```

In [`core/capture.py:617`](core/capture.py:617) — `_apply_diff_and_crop()`:
```python
def _apply_diff_and_crop(self, frame: np.ndarray, full: bool = False, force: bool = False) -> Optional[np.ndarray]:
```

Add early return before the hash check:
```python
if force:
    return target  # skip MD5 dedup
```

---

## Step 2: Fix Empty Front Field — Fallback when screenshot missing

**File:** [`logic/anki_card_builder.py`](logic/anki_card_builder.py)

**What:** After the screenshot retry loop, if `screenshot_b64` is still `None`, modify the front template to fall back to `{TargetText}` instead of producing an empty field.

**Changes:**

After line 64 (the `else:` clause of the retry loop), add front template fallback logic:

```python
else:
    logger.warning("[Anki] Screenshot capture failed after 3 attempts, continuing without it")
    # Fall back front template to show text instead of empty screenshot
    if front_mode in ("screenshot", "screenshot_selection"):
        front_html = "<div class='target'>{TargetText}</div>"
        logger.info("[Anki] Front template fell back to text-only (screenshot unavailable)")
```

This goes **before** the placeholder substitution loop (line 141), so the fallback HTML gets properly substituted.

---

## Step 3: Add Empty-Text Guard

**File:** [`logic/anki_card_builder.py`](logic/anki_card_builder.py)

**What:** After building the fields dict (line 85), check that at least one text field has content. If both `TargetText` and `ContextText` are empty, return `False` with a clear log message.

**Changes:**

After line 85:
```python
# Guard: at least one text field must have content
if not fields.get("TargetText", "").strip() and not fields.get("ContextText", "").strip():
    logger.warning("[Anki] No text content — card not created")
    return False
```

---

## Step 4: Add Concurrency Guard

**File:** [`main.py`](main.py)

**What:** Prevent rapid double-clicks on the 🃏 button from creating concurrent card creation tasks.

**Changes:**

Near line 977, add a `_anki_busy` flag:
```python
_anki_busy = False

async def _on_anki_requested() -> None:
    nonlocal _anki_busy
    if _anki_busy:
        logger.debug("[Anki] Already busy, ignoring duplicate request")
        return
    _anki_busy = True
    try:
        # ... existing body ...
    finally:
        _anki_busy = False
```

---

## Step 5: Simplify aiohttp Session Management (Optional but Recommended)

**File:** [`logic/anki_connect.py`](logic/anki_connect.py)

**What:** Since we already create a fresh session per request via `_reset_session()`, simplify by using `async with aiohttp.ClientSession()` directly in `_request_aiohttp()` instead of maintaining `self._session`.

**Changes:**

Replace `_get_session()`, `close()`, and `_reset_session()` with inline session creation:

```python
async def _request_aiohttp(self, body: str, timeout: float, *,
                           quiet: bool = False) -> dict[str, Any] | None:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                self._base_url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                # ... rest unchanged ...
```

Remove `_get_session()`, `close()`, `_reset_session()` methods and `self._session` attribute.

---

## Step 6: Update Documentation

**Files:** [`docs/user_guide.html`](docs/user_guide.html), [`README.md`](README.md)

**Changes:**
- Fix TargetText/ContextText descriptions (swapped)
- Fix "comma-separated" → "space-separated" for tags
- Fix "button stays disabled" → "button shows message when unavailable"
- Add note: screenshot is required for card creation

---

## Implementation Order

| Step | File | Change | Priority |
|------|------|--------|----------|
| 1 | `core/capture.py` | Add `force` parameter to `get_frame()` | **Critical** |
| 2 | `logic/anki_card_builder.py` | Use `force=True` in retry loop | **Critical** |
| 3 | `logic/anki_card_builder.py` | Fall back front template when screenshot missing | **Critical** |
| 4 | `logic/anki_card_builder.py` | Add empty-text guard | **High** |
| 5 | `main.py` | Add concurrency guard | **Medium** |
| 6 | `logic/anki_connect.py` | Simplify session management | **Low** |
| 7 | `docs/user_guide.html` | Fix documentation errors | **Medium** |
| 8 | `README.md` | Fix documentation errors | **Medium** |

---

## Verification Checklist

After implementation:

- [ ] `capture.get_frame(full=True, force=True)` returns a frame even if content hasn't changed
- [ ] Screenshot retry loop succeeds on first attempt with `force=True`
- [ ] When screenshot fails AND front template is screenshot-based, card still creates with text-only front
- [ ] When both TargetText and ContextText are empty, card creation is blocked with log message
- [ ] Rapid double-click on 🃏 only creates one card
- [ ] `anki_connect.py` no longer maintains persistent session state
- [ ] User guide correctly describes TargetText/ContextText
