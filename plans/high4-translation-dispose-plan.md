# HIGH-4: Translation Manager Dispose — Fix Plan

## Current State Analysis

### What the audit says

> `_rebuild_translation_manager()` creates new backend instances and a new `TranslationManager`, but never calls `.dispose()` on the old ones. Old `aiohttp.ClientSession` objects remain open, leaking connections.

### What the code actually does

The audit is **partially inaccurate**. [`_rebuild_translation_manager()`](ui/main_window.py:471) **does** call dispose, but as a fire-and-forget `asyncio.create_task()`:

```python
# Line 473-475 — fire-and-forget dispose
old_manager = getattr(self, '_translation_manager', None)
if old_manager is not None:
    asyncio.create_task(self._dispose_translation_manager(old_manager))
```

The [`_dispose_translation_manager()`](ui/main_window.py:454) method iterates `manager._backends` via `getattr` and calls `await backend.dispose()` on each. All backend `dispose()` methods (DeepLBackend, LibreTranslateBackend, GoogleTranslateBackend) close the underlying `aiohttp.ClientSession`.

### Critical code flow

```
SideMenu signal: translation_backend_changed
  → MainWindow._on_translation_backend_changed (sync, line 490)
    → _rebuild_translation_manager() (sync, line 471)
      1. Snapshot old_manager (line 473)
      2. Create dispose task (line 475) — fire-and-forget, runs in background
      3. Create new backends (lines 478-483)
      4. Assign new TranslationManager (line 484)
```

### Actual risk assessment

| Concern | Verdict | Rationale |
|---------|---------|-----------|
| Connection leak | **Not happening** | `asyncio.create_task` stores the task in the event loop's internal task list. The dispose **will** execute within the next event loop iteration. |
| In-flight translation during dispose | **Not a bug** | New manager is assigned BEFORE dispose runs (step 4 after step 2). In-flight translations use the new manager, not the disposed one. |
| Rapid backend switching | **Not a bug** | Each switch creates a new dispose task for the previous manager. Managers are independent — concurrent dispose tasks don't conflict. |
| Silent error swallowing | **REAL concern** | Both `_dispose_translation_manager` (line 463-464) and `TranslationManager.dispose()` (line 103-104) have `except Exception: pass` — any dispose failure is invisible. |
| Bypassing `TranslationManager.dispose()` | **Minor** | `_dispose_translation_manager` uses `getattr(manager, "_backends", [])` instead of `await manager.dispose()`. Currently identical, but fragile if `TranslationManager.dispose()` gains extra cleanup logic. |

---

## Proposed Fix: Keep fire-and-forget, add logging, use `TranslationManager.dispose()`

### Rationale

The current fire-and-forget pattern is **correct** for RC — it ensures the new manager is available immediately while old backends are cleaned up in the background. The only real issues are:
1. Silent error swallowing
2. Bypassing `TranslationManager.dispose()`

### Changes

#### Change 1: [`ui/main_window.py:454-464`](ui/main_window.py:454) — Use `TranslationManager.dispose()` instead of manual iteration, add logging

**Before:**
```python
async def _dispose_translation_manager(self, manager) -> None:
    """Dispose all backends in a translation manager."""
    if manager is None:
        return
    backends = getattr(manager, "_backends", [])
    for backend in backends:
        if hasattr(backend, "dispose"):
            try:
                await backend.dispose()
            except Exception:  # noqa: BLE001
                pass
```

**After:**
```python
async def _dispose_translation_manager(self, manager) -> None:
    """Dispose all backends in a translation manager."""
    if manager is None:
        return
    try:
        await manager.dispose()
    except Exception as exc:  # noqa: BLE001
        _logger.warning("[MainWindow] Translation manager dispose failed: %s", exc)
```

#### Change 2: [`core/translation/manager.py:97-104`](core/translation/manager.py:97) — Add logging to `TranslationManager.dispose()`

**Before:**
```python
async def dispose(self) -> None:
    """Dispose all backend sessions."""
    for backend in self._backends:
        if hasattr(backend, "dispose"):
            try:
                await backend.dispose()
            except Exception:  # noqa: BLE001
                pass
```

**After:**
```python
async def dispose(self) -> None:
    """Dispose all backend sessions."""
    for backend in self._backends:
        if hasattr(backend, "dispose"):
            try:
                await backend.dispose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Backend dispose failed for %s: %s", type(backend).__name__, exc)
```

---

## Risk Analysis

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Bug risk** | **LOW** | Existing code is functionally correct. Fix only adds logging and uses the proper manager API. |
| **Fix risk** | **VERY LOW** | 2 changes, ~6 lines total. No behavioral change to dispose logic — just replacing manual `getattr` + iteration with `manager.dispose()` which does the same thing. |
| **RC impact** | **None** | Fire-and-forget pattern preserved. New manager still assigned immediately. No timing changes. |

## Files Affected

| File | Lines | Change |
|------|-------|--------|
| [`ui/main_window.py`](ui/main_window.py:454) | 454-464 | Replace manual iteration with `manager.dispose()`, add warning log |
| [`core/translation/manager.py`](core/translation/manager.py:97) | 97-104 | Add warning log to existing dispose (belt-and-suspenders) |

## What this does NOT change

- Fire-and-forget `asyncio.create_task` pattern — preserved (it's correct)
- Signal handler wiring — untouched
- Backend creation logic — untouched
- `_on_libre_url_changed` (dead code) — left as-is, not relevant to HIGH-4

## Verification

```bash
python -m py_compile ui/main_window.py
python -m py_compile core/translation/manager.py
```

## Post-fix Documentation Update

After applying, update:
1. [`SECURITY_AUDIT_REPORT.md`](SECURITY_AUDIT_REPORT.md) — mark HIGH-4 as ✅ FIXED
2. [`plans/rc-risk-analysis.md`](plans/rc-risk-analysis.md) — update HIGH-4 row to ✅ status
