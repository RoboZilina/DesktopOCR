# Branch Changes Audit — `local-translator-dead-branch` vs `main`

> Last updated: 2026-05-04
> Branch: `local-translator-dead-branch`
> Scope: Identify non-Argos changes safe to port to `main` (GA / v1.0.0)

---

## TL;DR — What to Port

| File | Action | Risk |
|---|---|---|
| `build.bat` (new) | **PORT** as new canonical build script | Low — pure infrastructure |
| `docs/BUILD.md` (new) | **PORT** alongside `build.bat` | Low — documentation only |
| `icon.ico`, `icon-192.png`, `icon-512.png` (new) | **PORT** as app assets | Low — static assets |
| `ui/main_window.py` | **PARTIAL PORT** — two small edits (see §6) | Zero — isolated, no Argos deps |
| `core/translation/mymemory_backend.py` | **PORT** — defensive session fix | Zero — crash-prevention bugfix |
| `build.ps1` | **DO NOT PORT** — has `--msvc=latest` bug | Superseded by `build.bat` |
| `.gitignore` | **DO NOT PORT** — Argos model exclusion | Argos-specific |
| `README.md` | **DO NOT PORT** — "Bundled Models" section | Argos-specific |
| `BACKLOG.md` | **DO NOT PORT** — Argos-tangled backlog entries | Argos-tangled |
| `docs/comparison-*.md` | **DO NOT PORT** — Argos mention in table | Argos-specific |
| `docs/release-notes-v1.0.0-rc3.md` | **DO NOT PORT** — offline translation bullet | Argos-specific |
| `docs/user_guide.html` | **DO NOT PORT** — Argos troubleshooting note | Argos-specific |
| `requirements.txt` | **DO NOT PORT** — `argostranslate==1.9.6` | Argos-specific |
| `ui/side_menu.py` | **DO NOT PORT** — only change is Argos comment | Argos-specific |

---

## 1. Build System — `build.bat` (NEW FILE)

**Status: PORT**

Completely new file. Final Nuitka build script tested and confirmed working:
- `vswhere` + `vcvars64.bat` MSVC detection (avoids `--msvc=latest` Scons crash)
- Virtual environment activation after MSVC env is loaded
- Clean old build folders (`build/`, `dist/`, `main.build/`, `__pycache__/`)
- Data directories: `resources=resources`, `models=models`, `docs=docs`, `ui=ui`, `assets=assets`
- Data files: `settings.json.example`, `icon.ico` (for runtime taskbar icon)
- DLL exclusions to reduce size (`api-ms-win-*.dll`, `winrt-*.dll`, ONNX GPU providers, `torch_cuda*.dll`, `caffe2*.dll`, `mkl*.dll`)
- Qt plugins limited to: `platforms`, `imageformats`, `styles`
- `--windows-console-mode=disable`, `--windows-icon-from-ico=icon.ico`
- Output: `build/DesktopOCR.dist/DesktopOCR.exe`

**Note:** `build.ps1` on this branch still has `--msvc=latest` and is superseded by `build.bat`. Do not port `build.ps1` changes — either keep the old main version or deprecate `build.ps1` entirely.

---

## 2. Build Documentation — `docs/BUILD.md` (NEW FILE)

**Status: PORT**

New documentation covering:
- Prerequisites (Python 3.11, VS Build Tools + Windows SDK, Pillow)
- How to build (double-click `build.bat`)
- What NOT to do (`--msvc=latest`, missing Windows SDK, `--lto=yes` with gcc)
- Size optimization flags (~1.3 GB → ~300-500 MB)
- ArgosTranslate model handling (section exists but is Argos-specific — can be left in or stripped)
- Build time expectations (MSVC ~15 min, gcc fallback 1-3 hours, gcc+LTO 5-10 hours)
- Troubleshooting table

**Caveat:** The ArgosTranslate model handling section references `assets/argos/ja_en.argosmodel`. Since main won't have Argos, this section can either:
- Be left as-is (harmless, just unused)
- Be stripped with a `TODO: remove if Argos not merged` note

---

## 3. Icon Assets — `icon.ico`, `icon-192.png`, `icon-512.png` (NEW FILES)

**Status: PORT**

Static assets generated from `icon-512.png` via Pillow (`icon.ico` is a multi-resolution ICO). Used by:
- `build.bat`: `--windows-icon-from-ico=icon.ico` (executable file icon)
- `ui/main_window.py`: runtime `setWindowIcon()` for taskbar icon display

---

## 4. MyMemory Backend Defensive Fix — `core/translation/mymemory_backend.py`

**Status: PORT**

Zero-risk crash-prevention fix:

```diff
-        self._session = aiohttp.ClientSession(timeout=_TIMEOUT)
+        self._session: aiohttp.ClientSession | None = None

     def _get_session(self) -> aiohttp.ClientSession:
-        """Return the session, re-creating it if closed (e.g. after dispose)."""
-        if self._session.closed:
+        """Return the session, re-creating it if closed or disposed."""
+        if self._session is None or self._session.closed:
             self._session = aiohttp.ClientSession(timeout=_TIMEOUT)
         return self._session
```

**Why port:** If the backend is disposed (session set to `None`) and then reused, the old code would crash on `self._session.closed` (AttributeError on `None`). This fix makes the backend safe for reuse.

---

## 5. Main Window — `ui/main_window.py`

**Status: PARTIAL PORT — two isolated edits only**

The diff is mixed. Most changes are Argos wiring (import, translation manager rebuild, error message). Two changes are **pure release polish / bugfix** and can be cherry-picked independently:

### 5a. Taskbar Icon Fix (lines 49-51) — PORT

```python
icon_path = pathlib.Path(sys.argv[0]).with_name("icon.ico")
if icon_path.exists():
    self.setWindowIcon(QIcon(str(icon_path)))
```

Requires:
- `QIcon` import in `PyQt6.QtGui` (line 11)
- `icon.ico` in distribution folder (handled by `--include-data-file=icon.ico=icon.ico` in `build.bat`)

**Why port:** Without this, the app shows a generic Windows icon in the taskbar even though the `.exe` file has a custom icon. This is pure UI polish with zero Argos dependency.

### 5b. Translation Backend Label Fix (line 346) — PORT

```diff
         label_map = {
             "auto": "Auto",
-            "deepl": "DeepL",
+            "mymemory": "MyMemory",
             "google": "Google",
         }
```

**Why port:** The old code references `"deepl"` which was removed long ago. The UI label map is stale — this corrects it to `"mymemory"` which is the actual secondary cloud backend.

### 5c. Everything else — DO NOT PORT

- `from core.translation.argos_backend import ArgosTranslatorBackend` — Argos import
- Translation manager rebuild adding `ArgosTranslatorBackend()` — Argos wiring
- Error message changing from "LibreTranslate" to "bundled translation model" — Argos-tangled
- `_rebuild_translation_manager()` adding Argos to auto mode — Argos wiring
- Removal of `_libre_url` and `_on_libre_url_changed` — side effect of Argos replacing LibreTranslate

---

## 6. Side Menu — `ui/side_menu.py`

**Status: DO NOT PORT**

Only meaningful change is a comment/docstring update:

```diff
-        # LibreTranslate is hidden for now, so URL field stays hidden
+        # ArgosTranslate is the offline fallback — no URL config needed
```

And a signal docstring correction. Both are Argos-specific. No functional code changes.

---

## 7. Requirements — `requirements.txt`

**Status: DO NOT PORT**

```
+# Offline translation (JA→EN fallback when no internet)
+argostranslate==1.9.6
```

Pure Argos dependency. Skip entirely.

---

## 8. Git Ignore — `.gitignore`

**Status: DO NOT PORT**

```
+# Bundled models (GitHub 100 MB limit)
+assets/argos/*.argosmodel
```

Argos model exclusion. If main keeps an empty `assets/argos/` directory for future use, this is harmless but unnecessary.

---

## 9. Documentation Updates (README, release notes, comparison, user guide)

**Status: DO NOT PORT**

All four files contain Argos-specific text additions:
- `README.md`: "Bundled Models" section explaining Argos model installation
- `docs/comparison-*.md`: ArgosTranslate listed in translation comparison table
- `docs/release-notes-v1.0.0-rc3.md`: "Offline Translation: ArgosTranslate serves as offline fallback"
- `docs/user_guide.html`: Troubleshooting note about `argospm install translate-ja_en`

**Note:** `BACKLOG.md` also grew significantly on this branch but the additions are Argos-tangled infrastructure notes. It is not worth cherry-picking from — update backlog on main independently.

---

## 10. Build Script — `build.ps1` (MODIFIED)

**Status: DO NOT PORT**

The branch version of `build.ps1` is **worse** than main:
- Still contains `--msvc=latest` (causes Scons `CC is not set` crash)
- Missing DLL exclusion flags (larger build)
- Missing Qt plugin limits
- Missing `icon.ico` inclusion
- Missing `vcvars64.bat` / `vswhere` automation

**Recommendation:** Deprecate `build.ps1` on main in favor of `build.bat`. If a PowerShell build script is still desired, rewrite it from scratch to match `build.bat`'s proven configuration.

---

## Port Checklist

To port these changes to `main` cleanly:

1. [ ] Copy `build.bat` → root (new file)
2. [ ] Copy `docs/BUILD.md` → `docs/` (new file)
3. [ ] Copy `icon.ico`, `icon-192.png`, `icon-512.png` → root (new files)
4. [ ] Cherry-pick `core/translation/mymemory_backend.py` session None-check (2-line change)
5. [ ] Cherry-pick `ui/main_window.py`:
   - [ ] `QIcon` import addition
   - [ ] `setWindowIcon()` block (lines 49-51)
   - [ ] `label_map` `"deepl"` → `"mymemory"` (line 346)
6. [ ] Update `build.bat` `--include-data-file=icon.ico=icon.ico` (already included in current version)
7. [ ] Test: double-click `build.bat`, verify MSVC, verify icon in taskbar
8. [ ] **Do NOT cherry-pick** any Argos wiring, imports, or documentation mentions

---

## Risks if ported incorrectly

| Mistake | Consequence |
|---|---|
| Port Argos imports in `main_window.py` | Import error on `main` (module not present) |
| Port `requirements.txt` argostranslate | Unnecessary dependency, import errors if not wired |
| Port `.gitignore` argos exclusion | Harmless but confusing (ignores non-existent dir) |
| Port `build.ps1` changes | Reintroduces `--msvc=latest` crash |
| Miss `setWindowIcon()` | Taskbar shows generic Windows icon |
| Miss `mymemory_backend.py` fix | Crash if translation backend disposed and reused |

---

## Verification Command

After porting, verify no Argos residue:

```bash
grep -r "argos\|ArgosTranslate\|argostranslate" --include="*.py" --include="*.md" --include="*.txt" --include="*.bat" . \
  | grep -v "BRANCH-CHANGES.md" | grep -v "BUILD.md"
```

Expected: zero matches (except possibly in `BUILD.md` which is harmless documentation).
