# Anki Code Review 2 — Fix Plan

## Finding #6 — Stale/Wrong OCR Translation

**Problem**: `get_ocr_translation()` returns `_trans_text` contents, which is the selection translation from the UI, not the OCR translation. When non-empty, the Anki flow skips fetching a fresh OCR translation, causing `ContextTranslation` to get the wrong text.

**Fix** (in [`main.py`](../main.py:993)): Ignore cached UI translation entirely during Anki creation.

Replace:
```python
cached_translation = window.get_ocr_translation()
```
With:
```python
cached_translation = None
```

This ensures the OCR text is always translated fresh for the Anki card.

---

## Finding #7 — Transport Exceptions Don't Set `last_error`

**Problem**: When aiohttp or urllib throws a transport exception (timeout, connection refused, DNS failure), the handler logs the error but does not set `self.last_error`. The user sees generic "Card save failed".

**Fix** (in [`logic/anki_connect.py`](../logic/anki_connect.py)):

**aiohttp path** (exception handler around lines 109-114): Add `await self._set_error(...)`.

**urllib path** (exception handlers around lines 149-163): Add self.last_error assignment (direct, in thread-pool executor).

Both should set `f"Transport error: {exc}"`.
