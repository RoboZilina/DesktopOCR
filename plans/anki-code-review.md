# Anki Integration — Objective Code Review

**⚠ CRITICAL BUGS FOUND — See "Critical Bugs" section below.**


**Reviewer:** Roo (Architect mode)
**Scope:** All 7 files involved in the Anki card creator feature  
**Date:** 2026-05-01

---

## Architecture Overview

```
User clicks 🃏 button
       │
       ▼
main.py:_on_anki_requested()
       │
       ├── 1. Read ocr_text, selection_text from tray widgets
       ├── 2. Fire async translation tasks concurrently (asyncio.gather)
       ├── 3. Get last_audio_path from TTSManager
       └── 4. Call build_and_send_card()
              │
              ├── a. Capture screenshot (retry ×3)
              ├── b. Build fields dict → Front/Back HTML with placeholder substitution
              ├── c. Build optional audio/picture dicts
              └── d. Call AnkiConnect methods:
                     ├── ensure_deck()
                     ├── ensure_note_type()
                     └── add_note()
       │
       └── 5. Update status bar (success/failure)

Background: QTimer fires _check_anki() every 30s
  → is_available() (quiet=True, DEBUG log level)
  → ensure_note_type() once per session
  → set_anki_available() updates tray button tooltip
```

**Data flow is linear, single-direction, and clean.** Each layer has clear responsibility.

---

## Critical Bugs (from Runtime Log)

Two bugs were confirmed at runtime — both prevent card creation entirely.

### Bug 1: Screenshot capture always fails via BitBlt with `full=True`

**Log evidence:**
```
[Anki] Screenshot capture failed after 3 attempts, continuing without it
```

**Root cause:** [`core/capture.py:639-641`](core/capture.py:639-641) — `_apply_diff_and_crop()` performs an MD5 frame-diff check even when `full=True`. The first call succeeds (hash is `None`, so `new_hash == None` is `False`), but the **second** call sees the same frame content and returns `None` because `new_hash == self._last_full_hash`.

The retry loop in [`anki_card_builder.py:51-62`](logic/anki_card_builder.py:51-62) calls `capture.get_frame(full=True)` up to 3 times with 100ms delay. Since the screen content doesn't change in 200ms, all 3 attempts return `None` due to the MD5 dedup.

**Impact:** Screenshot is **never** captured on the first attempt. The card is created without a screenshot.

**Fix:** The retry loop needs to force-capture by bypassing the MD5 check. Options:
1. Add a `force` parameter to `get_frame()` that skips the hash check
2. Or, in `build_and_send_card()`, call `capture.get_frame(full=True)` once, and if it returns `None`, call it again with a mechanism to bypass the hash

### Bug 2: "cannot create note because it is empty"

**Log evidence:**
```
[Anki] Error in 'addNote': cannot create note because it is empty
```

**Root cause:** When `anki_front` is `"screenshot"` (the default) and the screenshot capture fails (Bug 1), the front HTML template `"{Screenshot}"` gets substituted with an empty string. The Front field becomes `""`. AnkiConnect rejects notes with empty Front/Back fields.

The substitution at [`anki_card_builder.py:141-143`](logic/anki_card_builder.py:141-143):
```python
for placeholder, value in _subs.items():
    front_html = front_html.replace(placeholder, value)
```
When `screenshot_b64` is `None`, `fields["Screenshot"]` is `""` (line 83), so `"{Screenshot}"` → `""`.

**Impact:** Card creation fails with "cannot create note because it is empty".

**Fix:** When screenshot is unavailable and the front template is screenshot-based, fall back to showing `{TargetText}` instead of an empty front. Or, always ensure Front has content regardless of screenshot availability.

---

## File-by-File Review

### [`logic/anki_connect.py`](logic/anki_connect.py)

#### Strengths

| Aspect | Assessment |
|--------|------------|
| Error isolation | All public methods catch exceptions and never raise — safe for UI handlers |
| Transport fallback | aiohttp preferred, urllib.request as fallback if aiohttp not installed |
| Error state | `last_error` with `asyncio.Lock` for thread-safe read/write |
| Quiet mode | `quiet=True` suppresses WARNING → DEBUG for background polls |
| Fresh sessions | `_reset_session()` creates a new aiohttp session per request, avoiding AnkiConnect's keep-alive issues |

#### Issues Found

**Medium — `_consecutive_failures` is dead code**
- [`anki_connect.py:34`](logic/anki_connect.py:34): `self._consecutive_failures: int = 0` is declared
- [`anki_connect.py:187`](logic/anki_connect.py:187): `self._consecutive_failures += 1` is written
- **Never read anywhere.** Was likely intended for exponential backoff or UI feedback but never wired.
- **Impact:** Zero (dead state). Clean it up or wire it to something useful (e.g., show "N consecutive failures" in tooltip).

**Low — `_reset_session()` docstring is stale**
- [`anki_connect.py:65-66`](logic/anki_connect.py:65-66): Docstring says "avoids racing with the `async with` context manager by not awaiting the close"
- Line 71: `await self._session.close()` **does** await.
- **Impact:** Misleading documentation. The comment is no longer accurate after the fix.

**Low — `_get_session()` type annotation is imprecise**
- [`anki_connect.py:49`](logic/anki_connect.py:49): Return type annotated as `aiohttp.ClientSession`
- Line 54: Returns `None` when aiohttp is unavailable (with `# type: ignore[return-value]`)
- Never actually called without aiohttp (caller `_request_aiohttp()` is only invoked when `_HAS_AIOHTTP` is True), so this is cosmetic.

**Low — `add_note()` error-guard is fragile**
- [`anki_connect.py:297-299`](logic/anki_connect.py:297-299):
  ```python
  if data is None:
      if self.last_error is None:
          await self._set_error("Card save failed")
      return None
  ```
  The guard `if self.last_error is None` only sets a fallback error if no error was set by earlier operations. Since `_request()` never calls `_set_error()`, this guard is relying on **previous calls in the chain** (ensure_deck, ensure_note_type) having cleared the error. In the current call chain in `build_and_send_card()`, those calls do clear errors on success, so this works. But it's brittle — if anyone calls `anki.add_note()` directly without first calling ensure_deck/ensure_note_type, `self.last_error` could contain stale error state from a previous background poll.
- **Recommendation:** Remove the guard; always set the error:
  ```python
  if data is None:
      await self._set_error("Card save failed")
      return None
  ```

---

### [`logic/anki_card_builder.py`](logic/anki_card_builder.py)

#### Strengths

| Aspect | Assessment |
|--------|------------|
| Screenshot retry | 3 attempts with 100ms delay — robust against WinRT frame pool race |
| HTML substitution | `.replace()` loop correctly interpolates placeholders BEFORE storing in Front/Back fields |
| Defensive defaults | Fallthrough cases in front/back template selection handle unknown modes gracefully |
| Audio/picture attachment | Properly structured dicts for AnkiConnect's media API |
| Top-level try/except | Catches any unexpected exception and returns False |

#### Issues Found

**High — Documentation mismatch: field names vs user guide**
- [`anki_card_builder.py:78-81`](logic/anki_card_builder.py:78-81):
  - `TargetText` = `(selection_text or "").strip()` — **this is the selected/highlighted text**
  - `ContextText` = `(ocr_text or "").strip()` — **this is the full OCR text**
- [`docs/user_guide.html:259-260`](docs/user_guide.html:259-260):
  - Says: `TargetText` — "raw OCR text" ❌
  - Says: `ContextText` — "selected/highlighted text" ❌
- **These are swapped in the documentation.** The code is correct, the docs are wrong.

**Medium — Screenshot data sent twice**
- [`anki_card_builder.py:82-84`](anki_card_builder.py:82-84): `Screenshot` field contains `<img src="{screenshot_filename}">` — references the media file
- [`anki_card_builder.py:174-180`](anki_card_builder.py:174-180): `picture_dict` sends the same base64 data as a media attachment
- **Result:** AnkiConnect receives the screenshot data twice in the same `addNote` call. AnkiConnect should deduplicate by filename, but payload size is ~2× what's needed. For a 1080p screenshot (~2-4 MB as PNG), this means ~4-8 MB per card request.
- **Recommendation:** Consider whether both are needed. The `<img>` tag in the `Screenshot` field requires the media file to exist in Anki's collection.media. The `picture` dict uploads it there. So both are necessary for the screenshot to display. This is correct, not wasteful — the `<img>` is the display mechanism, `picture` is the upload mechanism. **No change needed**, but worth documenting in a comment.

**Low — `audio_path` file read blocks the event loop**
- [`anki_card_builder.py:154`](anki_card_builder.py:154): `with open(audio_path, "rb") as f` runs synchronously inside an async function.
- For typical TTS clips (< 1 MB, < 30 seconds) this is negligible (~1-5 ms read time). For edge cases (large WAV files), it could stall the UI.
- **Recommendation:** Wrap in `asyncio.to_thread()` or `loop.run_in_executor()`.

**Low — No OCR text truncation**
- [`anki_card_builder.py:80`](anki_card_builder.py:80): `ContextText` stores the **entire** OCR output.
- If OCR captures a full screen of dense text (e.g., a browser page), this could be thousands of characters. Anki notes have no hard field size limit, but very large notes slow down the Anki UI.
- **Recommendation:** Add optional truncation (e.g., first 1000 chars) with a `...` suffix.

---

### [`main.py`](main.py) — Anki Integration Section (lines 957–1104)

#### Strengths

| Aspect | Assessment |
|--------|------------|
| Note type caching | `_anki_note_type_ensured` flag prevents redundant API calls |
| Async translation | `asyncio.gather()` for concurrent OCR + selection translation |
| Fallback chain | Async translation result → cached display translation → None |
| QTimer polling | 30s interval with immediate first-run on startup |
| Test Connection | Dedicated handler with status bar feedback + auto-clear after 3s |

#### Issues Found

**Medium — No guard against concurrent `_on_anki_requested()` calls**
- [`main.py:1027-1029`](main.py:1027-1029): Each click schedules a new `asyncio.ensure_future(_on_anki_requested())`.
- If the user clicks 🃏 rapidly twice while the first card is still being created, two tasks will run in parallel. `allowDuplicate: False` in `add_note` prevents true duplicates, but both tasks will attempt screenshot capture, both will call ensure_deck/ensure_note_type (harmless), and both will attempt to add notes. One will succeed, the other will see "duplicate" error.
- **Recommendation:** Add a `_anki_busy` flag:
  ```python
  _anki_busy = False
  async def _on_anki_requested():
      nonlocal _anki_busy
      if _anki_busy:
          return
      _anki_busy = True
      try:
          ...
      finally:
          _anki_busy = False
  ```

**Low — `anki_enabled` setting is implicitly enforced via visibility only**
- The "Enable Anki" toggle controls button visibility. But there's no explicit check in `_on_anki_requested()` that `anki_enabled` is True. If someone programmatically emits `anki_requested` while the button is hidden, the card creation proceeds.
- **Impact:** Near-zero in practice (no other code path emits this signal). But defense-in-depth would add a check.

**Low — `_on_anki_host_changed` accesses `settings_state` directly**
- [`main.py:1050`](main.py:1050): `anki._base_url = f"http://{host}:{settings_state.get('anki_port', 8765)}"` reads from shared state.
- If host and port fields are both edited before either `editingFinished` fires (impossible via Qt's single-threaded UI), there's no race. But the pattern of reading from `settings_state` inside a signal handler for a _different_ setting is slightly fragile.

---

### [`ui/side_menu.py`](ui/side_menu.py) — Anki Section (lines 369–471, 1092–1159)

#### Strengths

| Aspect | Assessment |
|--------|------------|
| Collapsible section | Default collapsed — doesn't overwhelm users |
| Help text | Comprehensive inline HTML with prerequisites, instructions, and settings description |
| Test Connection button | Immediate feedback without needing to save a card |
| Signal separation | 9 distinct signals for 9 controls — clean, no multiplexing |

#### Issues Found

**Low — `_on_anki_port_finished()` silently resets invalid input**
- [`side_menu.py:1154-1159`](side_menu.py:1154-1159): If port input is non-numeric, it resets to 8765 without any feedback to the user.
- The user types "abc" → port silently reverts to 8765 → user may not notice or understand.
- **Recommendation:** Show a brief tooltip or status message: "Invalid port, using 8765".

---

### [`ui/transcription_tray.py`](ui/transcription_tray.py) — Anki Section (lines 106–113, 347–381)

#### Strengths

| Aspect | Assessment |
|--------|------------|
| Always-clickable | Button never disabled — shows QMessageBox when Anki unavailable |
| Error feedback | QMessageBox displays `last_error` content |
| Primary button styling | Uses shared `_apply_primary_button_styles()` — consistent with Recapture button |
| Accessor methods | `get_ocr_text()`, `get_selection_text()`, `get_ocr_translation()`, `get_selection_translation()` |

#### Issues Found

**Medium — `get_selection_translation()` returns the same widget as `get_ocr_translation()`**
- [`transcription_tray.py:357`](ui/transcription_tray.py:357): `return self._trans_text.toPlainText()`
- There is no separate "selection translation" display widget. Both the OCR translation and selection translation accessor return the same value.
- This means the `TargetTranslation` and `ContextTranslation` fields in the Anki card will **always be identical** when both are populated.
- **Impact:** Functional but limits card value. If user selects a subset of text, they get the translation of the full text, not the selected passage.
- **Not a bug** — this is a known design limitation from earlier discussions.

---

### Documentation

#### [`docs/user_guide.html`](docs/user_guide.html) — Anki Section (lines 190–270)

| Line | Issue | Severity |
|------|-------|----------|
| 259 | "TargetText — raw OCR text" is **wrong**. TargetText = selected text, ContextText = full OCR text (swapped). | **High** |
| 234 | "Comma-separated tags" but code splits on **whitespace** ([`anki_card_builder.py:186`](logic/anki_card_builder.py:186): `tags_str.split()`). | **Medium** |
| 268 | "button stays disabled until AnkiConnect is reachable" — button is now **always clickable** (shows QMessageBox when unavailable). | **Medium** |

#### [`README.md`](README.md) — Anki Section (lines 37–56)

| Line | Issue | Severity |
|------|-------|----------|
| 56 | "button stays disabled" — same outdated description as user_guide.html. | **Medium** |

---

## Cross-Cutting Concerns

### Error Message Flow

The path from failure to user visibility:

```
AnkiConnect._request() returns None
    → anki.last_error may or may not be updated (see bug #1)
    → build_and_send_card() returns False
    → main.py checks anki.last_error
    → window.set_status("Error", f"Anki: {reason}")
    → Auto-cleared after 3 seconds
```

**Problem:** The 3-second auto-clear is very fast. If the user looks away for a moment, they miss the error. Compare to the QMessageBox shown by `_on_anki_clicked()` when Anki is unavailable — that's modal and must be dismissed.

**Suggestion:** For card creation failures, consider keeping the error visible until the next successful operation, or showing a longer duration (e.g., 10 seconds).

### Thread Safety

- `anki.last_error` is wrapped in `asyncio.Lock` — correct for async access.
- The 30s QTimer fires in Qt's main thread and calls `asyncio.ensure_future()` — correct for qasync integration.
- `_on_anki_requested()` reads UI widgets from the main thread (Qt) and schedules async work — correct.
- **No thread safety issues found.**

### Dependency Management

- `aiohttp` is a **soft dependency** — gracefully falls back to `urllib.request`.
- `cv2` and `numpy` are hard dependencies of card builder — already required by the main app.
- `base64`, `json`, `os`, `time` — standard library.
- **No new hard dependencies introduced.**

---

## Summary

### Items Requiring Action

| # | Priority | File | Line(s) | Issue |
|---|----------|------|---------|-------|
| 1 | **CRITICAL** | [`core/capture.py`](core/capture.py) | 639–641 | MD5 frame-diff blocks `full=True` on repeated calls — screenshot never captured via retry loop |
| 2 | **CRITICAL** | [`logic/anki_card_builder.py`](logic/anki_card_builder.py) | 91–98 | Front template `{Screenshot}` becomes empty string when screenshot fails → "cannot create note because it is empty" |
| 3 | **High** | [`docs/user_guide.html`](docs/user_guide.html) | 259–262 | TargetText/ContextText descriptions are swapped |
| 4 | **Medium** | [`docs/user_guide.html`](docs/user_guide.html) | 234 | Says "comma-separated" but code splits on whitespace |
| 5 | **Medium** | [`docs/user_guide.html`](docs/user_guide.html) | 268 | Says "button stays disabled" — now always clickable |
| 6 | **Medium** | [`README.md`](README.md) | 56 | Same outdated "disabled" description |
| 7 | **Medium** | [`logic/anki_connect.py`](logic/anki_connect.py) | 34, 187 | `_consecutive_failures` is dead code (written, never read) |
| 8 | **Medium** | [`main.py`](main.py) | 1027–1029 | No guard against concurrent card creation clicks |
| 9 | **Low** | [`logic/anki_connect.py`](logic/anki_connect.py) | 297–299 | `add_note()` error-guard is fragile (remove the `if self.last_error is None` guard) |
| 10 | **Low** | [`logic/anki_connect.py`](logic/anki_connect.py) | 65–66 | Stale docstring in `_reset_session()` about "not awaiting" |
| 11 | **Low** | [`logic/anki_card_builder.py`](logic/anki_card_builder.py) | 154 | Audio file read blocks the event loop |
| 12 | **Low** | [`logic/anki_card_builder.py`](logic/anki_card_builder.py) | 80 | No truncation for very long OCR text |
| 13 | **Low** | [`ui/side_menu.py`](ui/side_menu.py) | 1154–1159 | Invalid port silently resets to 8765 |
| 14 | **Low** | [`ui/transcription_tray.py`](ui/transcription_tray.py) | 357 | Selection translation always equals OCR translation (known limitation) |

### Items Verified as Correct

| Aspect | Status |
|--------|--------|
| Transport layer handles "Server disconnected" | ✅ Fixed — fresh session per request |
| Screenshot capture has retry logic | ✅ 3 attempts with 100ms delay |
| HTML placeholder substitution | ✅ `.replace()` loop, correct |
| Note type creation with 7 fields | ✅ Correct field list, CSS, template |
| Deck auto-creation | ✅ `ensure_deck()` called before `addNote()` |
| Note type auto-creation in card builder | ✅ `ensure_note_type()` called after `ensure_deck()` |
| Audio attachment | ✅ Base64-encoded, configurable target side |
| Tags parsing | ✅ Space-split from string |
| UI settings persistence | ✅ `_do_save()` called in all 9 handlers |
| Background polling | ✅ 30s QTimer, quiet mode, immediate first run |
| Test Connection | ✅ Dedicated button + signal + handler |
| Always-clickable button | ✅ QMessageBox fallback when unavailable |
| Error state propagation | ✅ `last_error` → tooltip → status bar |
