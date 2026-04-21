# Tomorrow Plan — DesktopOCR EXE Startup

## Priority 0 (Unblock launch)
- [ ] Replace interactive `input()` in `main.py` with non-interactive startup config.
  - [ ] Accept `--hwnd` CLI arg.
  - [ ] Optional fallback: read HWND from env var (e.g. `DESKTOCR_HWND`).
  - [ ] If missing, exit with clear error message (and log), not blocking prompt.
- [ ] Add startup exception logging to file.
  - [ ] Create log path under `%LOCALAPPDATA%/DesktopOCR/logs/`.
  - [ ] Log uncaught exceptions during bootstrap.

## Priority 1 (Make behavior consistent with build mode)
- [ ] Decide one temporary path for next build:
  1. CLI mode: keep console enabled (`--windows-console-mode=force`).
  2. GUI mode: keep console disabled and wire UI bootstrap.
- [ ] If staying CLI temporarily, document exact run command and expected terminal behavior in `README.md`.

## Priority 2 (Packaging hardening)
- [ ] Verify Nuitka includes all runtime pieces:
  - [ ] `--include-qt-plugins=platforms,imageformats`
  - [ ] `--include-package=winsdk`
  - [ ] Ensure `onnxruntime-directml` dependencies are bundled.
  - [ ] Keep models bundled: `--include-data-dir=models=models`
- [ ] Build test executable and run from terminal once to capture startup output.

## Priority 3 (Validation checklist)
- [ ] Launch `.exe` by double-click: app starts (or logs a clear fatal error).
- [ ] Launch `.exe --hwnd <value>`: no prompt required.
- [ ] Confirm model load path resolves in packaged app.
- [ ] Confirm no immediate silent exit.

## Priority 4 (GitHub storage hygiene + clone workflow)
- [ ] Add/verify `.gitignore` for heavy and local-only artifacts.
  - [ ] Exclude `.venv/`, `build/`, `dist/`, caches, logs, temp files.
  - [ ] Exclude binaries (`*.exe`, `*.dll`, `*.pyd`) from source branches.
- [ ] Decide model strategy for repo size control.
  - [ ] Keep large ONNX model files out of normal git history.
  - [ ] Keep `models/README.md` with exact download/place instructions.
  - [ ] Optional: add `scripts/download_models.ps1` for one-step setup.
- [ ] Document clone/setup flow for other developers in `README.md`.
  - [ ] Clone repo.
  - [ ] Create venv + install requirements.
  - [ ] Download/copy models into `models/paddle/`.
  - [ ] Run `tests/test_imports.py` and `tests/test_capture.py`.
- [ ] Check if large files already entered git history.
  - [ ] If yes, plan history cleanup (`git filter-repo`/BFG) before wider collaboration.

## Nice-to-have
- [ ] Add `--list-windows` flag to print HWND list and exit.
- [ ] Add `--config <path>` support for future GUI/automation.
