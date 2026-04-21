# DesktopOCR Handoff Summary

Date: 2026-04-19
Project: `C:\Users\rober\.gemini\antigravity\scratch\DesktopOCR`

## Objective
Investigate why desktop scripts / future `.exe` startup appear to not work or seem stuck.

## Confirmed Findings

### 1) Interactive behavior looked like "stuck" but is expected
- `tests/test_capture.py` intentionally waits for:
  - user HWND input (`input(...)`)
  - manual key press in OpenCV window (`cv2.waitKey(0)`)
- This can look frozen if run non-interactively or without focusing the CV2 window.

### 2) Real bug found in capture fallback path (now fixed)
- In `core/capture.py`, when WinRT init failed, `_use_bitblt=True` was set, but `_get_frame_winrt()` still attempted to use WinRT frame pool.
- This caused:
  - `AttributeError: 'NoneType' object has no attribute 'add_frame_arrived'`
- Fix applied:
  - `_get_frame_winrt()` now immediately routes to BitBlt when `_use_bitblt` is enabled or frame pool is unavailable.

### 3) Real bug found in EnumWindows callback typing (fixed in test script)
- Wrong ctypes callback signature caused HWND formatting/parse errors in `tests/test_capture.py`.
- Fix applied:
  - Proper Win32 types (`BOOL`, `HWND`, `LPARAM`) and safe integer conversion for HWND values.

### 4) Environment mismatch created contradictory guidance
- Project docs/code originally target older winsdk API layout.
- Runtime environment currently installs `winsdk==1.0.0b10` (older pin may not be available from current index).
- Import error observed:
  - `No module named 'winsdk.windows.graphics.directx.direct3d11.interop'`
- This indicates current capture implementation is not fully aligned with installed winsdk API surface.

## Current State Snapshot
- Python environment: `.venv` with Python 3.11 active.
- Key deps available in venv:
  - `cv2` imports OK
  - `onnxruntime` imports OK
  - `winsdk.windows.graphics.capture` imports OK
- `tests/test_capture.py` now produces window listing and clearer diagnostics.
- Capture fallback logic bug in `core/capture.py` has been patched.

## Fixes Completed After Initial Investigation

### 5) WinRT compatibility patch for current installable winsdk
- `core/capture.py` was updated to remove dependency on the missing module:
  - `winsdk.windows.graphics.directx.direct3d11.interop`
- New approach uses direct Win32 bridge call:
  - `CreateDirect3D11DeviceFromDXGIDevice`
  - then wraps with `IDirect3DDevice._from(...)`
- This aligns capture initialization with the currently available package ecosystem.

### 6) Main entrypoint callback typing fixed
- `main.py` `list_windows()` now uses robust Win32 ctypes callback types:
  - `BOOL`, `HWND`, `LPARAM`
- This removes callback/formatting instability for HWND output.

### 7) Dependency alignment completed
- `requirements.txt` updated to:
  - `winsdk==1.0.0b10`
- Rationale: this is the winsdk line available in the active Python 3.11 environment.

## Validation Results (Latest)
- `tests/test_imports.py`: `7/7 modules imported successfully`.
- `tests/test_capture.py` with piped test input (`0x0`):
  - no crash
  - WinRT failure path reported cleanly
  - BitBlt fallback path entered cleanly
  - script completed normally

## Current Remaining Work
- Run `tests/test_capture.py` with a real game/window HWND (not `0x0`) to verify an actual frame is returned and displayed.
- If needed, tune region defaults and continue with packaging/startup hardening for exe mode.

## Full Files Touched by Cascade in This Conversation

### Created
- `exe-startup-investigation.md`
- `tomorrow-plan.md`
- `handoff-summary.md`

### Modified
- `tests/test_capture.py`
- `core/capture.py`
- `main.py`
- `requirements.txt`
- `handoff-summary.md` (this file, updated multiple times)

## Notes for Future Session
- If script appears stuck, first confirm whether it is waiting for input or `cv2.waitKey(0)`.
- For automated checks, pipe HWND input and avoid waiting window paths.
- Do not mix global Python with project venv when installing/running (`.venv\Scripts\python.exe`).


