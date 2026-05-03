# Post-HIGH-1 Review Analysis

## Finding 1: `global DEFAULT_REGION` compounding state mutation

**Severity assessment:** MEDIUM (reviewer) → **LOW** (my assessment)

**Current code** ([`main.py:315-325`](main.py:315)):
```python
global DEFAULT_REGION
try:
    ...
    if abs(scale - 1.0) > 0.01:
        DEFAULT_REGION = tuple(int(v * scale) for v in DEFAULT_REGION)
```

### Bug risk analysis

The concern is valid: if `main()` is called twice, DPI scaling compounds. However:

| Call path | `main()` called? | Reaches DPI code? | Compounding? |
|-----------|-----------------|-------------------|--------------|
| `--list-engines` ([line 1512](main.py:1512)) | `asyncio.run(main(0))` | **No** — returns at line 220 | ❌ No |
| GUI mode ([line 1571](main.py:1571)) | `loop.run_until_complete(main(...))` | Yes — once | ❌ No |
| Unit test calling `main()` twice | Yes | Yes | ⚠️ Yes |

**In production: ZERO risk.** `main()` is called exactly once in the frozen build. The `--list-engines` shortcut returns before the DPI block.

**In testing: LOW risk.** If a test calls `main()` twice at non-100% DPI, the second call's region is double-scaled. This would only affect tests that specifically test DPI scaling behavior.

### Fix risk analysis

**VERY LOW.** The fix replaces 2 lines:

```diff
-    global DEFAULT_REGION
-    try:
-        ...
-        if abs(scale - 1.0) > 0.01:
-            DEFAULT_REGION = tuple(int(v * scale) for v in DEFAULT_REGION)
+    try:
+        ...
+        if abs(scale - 1.0) > 0.01:
+            selected_region = tuple(int(v * scale) for v in DEFAULT_REGION)
```

This removes the `global` declaration and assigns to the local `selected_region` variable instead of mutating the module-level constant. The fallback at line 327-329 (`if selected_region is None: selected_region = DEFAULT_REGION`) still works correctly — when scale==1.0, `selected_region` stays `None` and falls back to the original `DEFAULT_REGION` unchanged.

**Verdict: FIX NOW** (fix risk < bug risk)

---

## Finding 2: `global` declaration placement before `try` block

**Severity:** LOW (cosmetic)

Becomes moot if Finding 1 is fixed (the `global` declaration is removed entirely).

---

## Finding 3: Session reuse across `ClientError` retries

**Severity:** LOW (reviewer) → **LOW** (my assessment — same)

**Current code** ([`deepl_backend.py:136-142`](core/translation/deepl_backend.py:136)):
```python
except aiohttp.ClientError as exc:
    logger.warning("[DeepL] Network error: %s", exc)
    if attempt < max_retries - 1:
        backoff = 2 ** attempt
        ...
        continue
    return ""
```

### Analysis

The concern: `self._get_session()` returns the existing session after a `ClientError`, so persistent connection-level problems (stale keep-alive, broken HTTP/2 stream) could fail across all 3 retries.

**Counterpoints:**
1. aiohttp's `ClientSession` manages connection pooling internally and can recover from transient errors on new requests
2. The exponential backoff (1s, 2s, 4s) already handles most transient network issues
3. If the connection is truly broken, all 3 retries fail and return `""` — the caller handles this gracefully
4. Creating a new session on retry adds code complexity with marginal benefit for RC

**Verdict: DEFER** — not worth the complexity for RC. If this becomes a recurring issue in production, revisit.

---

## Pre-existing issues (noted, not introduced by changes)

| Issue | File | Assessment |
|-------|------|------------|
| Non-429 HTTP errors not retried (502/503/504) | [`deepl_backend.py:92-96`](core/translation/deepl_backend.py:92) | Pre-existing. DEFER. |
| Generic `except Exception` aborts without retry | [`deepl_backend.py:144-146`](core/translation/deepl_backend.py:144) | Pre-existing. DEFER. |
| System-wide DPI, not per-monitor | [`main.py:319`](main.py:319) | Pre-existing design limitation. `GetDpiForSystem()` is acceptable for VN use case (single monitor). DEFER. |
| M-2 PyQt error message | [`main.py:1525`](main.py:1525) | Clean change. No issues. |

---

## Summary: Action Items

| # | Action | Risk | Priority | Status |
|---|--------|------|----------|--------|
| 1 | Fix `global DEFAULT_REGION` → local `selected_region` in [`main.py:316-322`](main.py:316) | Fix: VERY LOW / Bug: LOW | **Fix NOW** | ⏳ Pending |
| 2 | `global` placement (cosmetic) | — | **Moot** (removed by #1) | ✅ Resolved |
| 3 | DeepL session reuse on `ClientError` | Fix: LOW / Bug: LOW | **DEFER** | ❌ Not acting |
