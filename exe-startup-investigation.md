# EXE Startup Investigation (DesktopOCR)

Date: 2026-04-19
Workspace: `C:\Users\rober\.gemini\antigravity\scratch\DesktopOCR`

## Symptom
Built `.exe` does not appear to start (no visible window / immediate silent exit).

## Findings

### 1) Primary root cause: CLI entrypoint + no console build
- `main.py` is currently terminal-interactive and requires user input:
  - `main.py:41` uses `input("Enter HWND...")`
- Build template disables the console:
  - `instructions.md:346` uses `--windows-console-mode=disable`
- In a no-console executable, `input()` cannot be satisfied (often fails with EOF), causing early exit.

### 2) No GUI startup path in entrypoint
- `main.py` only prints/logs to terminal and runs capture loop output to console.
- There is no PyQt application/window bootstrap in `main.py` yet.
- Result: double-clicking the `.exe` won’t show a desktop window by design in current state.

### 3) Potential secondary packaging blockers
Known in project instructions:
- `onnxruntime-directml` may need manual DLL inclusion.
- PyQt6 needs `--include-qt-plugins=platforms,imageformats`.
- `winsdk` may need `--include-package=winsdk`.

If these are missing, startup can also fail before visible UI.

## Why this explains “does not start”
Current code is effectively a CLI prototype, while the intended `.exe` mode is windowed/no-console. That mismatch alone can produce silent launch failure.

## Recommended next steps
1. Remove `input()` dependency from packaged startup path (use CLI args/config/env for HWND).
2. Keep console enabled for current CLI builds **or** wire real PyQt UI first.
3. Add file logging on startup (e.g., `%LOCALAPPDATA%/DesktopOCR/logs/startup.log`) to capture early exceptions in packaged runs.
4. Verify Nuitka packaging includes required Qt plugins, `winsdk`, and DirectML runtime dependencies.

## Relevant files checked
- `main.py`
- `instructions.md`
- `core/engine_manager.py`
- `core/ocr_engine.py`
- `requirements.txt`
