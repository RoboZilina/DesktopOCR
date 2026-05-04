# DesktopOCR — Windows Build Guide (Nuitka)

> Last updated: 2026-05-04
> Tested with: Nuitka 4.0.8, Python 3.11, PyQt6, Windows 11

---

## Prerequisites

- **Python 3.11** + virtual environment (`.venv`)
- **Visual Studio 2022 Build Tools** with C++ workload **AND Windows SDK** (or full VS 2022)
- **Pillow** (`pip install Pillow`) — for generating `icon.ico`

> **CRITICAL:** The **Windows SDK** component is required. Without it, Nuitka rejects MSVC and falls back to gcc, which is 10-50× slower. In Visual Studio Installer, under the C++ workload, check "Windows 11 SDK" (or "Windows 10 SDK").

---

## How to Build

Double-click `build.bat` in Explorer, or run `.\build.bat` from PowerShell/CMD. The script handles MSVC environment setup automatically via `vswhere` + `vcvars64.bat`.

> **Requires Windows SDK installed** (see Prerequisites). Without it, Nuitka rejects MSVC and falls back to gcc — build time goes from ~15 min to **1-3 hours**.

Output: `build\DesktopOCR.dist\DesktopOCR.exe`

---

## What NOT to Do

| Mistake | Why it fails |
|---|---|
| Missing Windows SDK in VS Build Tools | Nuitka rejects MSVC → gcc fallback (1-3 hours instead of ~15 min) |
| Use `--msvc=latest` | Forces internal MSVC search that fails with Build Tools; overrides vcvars64.bat and causes `CC is not set` |
| Use `--lto=yes` with gcc fallback | Linking 2985 files with gcc LTO takes **5-10 hours** |
| Use `--disable-console` | Deprecated; use `--windows-console-mode=disable` |
| Build without `icon.ico` | `.exe` will have default Windows icon |

---

## Size Optimizations

Unoptimized builds are ~**1.3 GB**. The following exclusions cut it to ~**300-500 MB**:

```
--noinclude-dlls=api-ms-win-*.dll
--noinclude-dlls=winrt-*.dll
--noinclude-dlls=*onnxruntime_providers_dml.dll
--noinclude-dlls=*onnxruntime_providers_cuda.dll
--noinclude-dlls=*onnxruntime_providers_tensorrt.dll
--noinclude-dlls=*onnxruntime_providers_openvino.dll
--noinclude-dlls=*torch_cuda*.dll
--noinclude-dlls=*caffe2*.dll
--noinclude-dlls=*mkl*.dll
--include-qt-plugins=platforms
--include-qt-plugins=imageformats
--include-qt-plugins=styles
```

These strip:
- GPU/CUDA inference backends (keep CPU-only ONNX Runtime)
- Torch CUDA runtime (~200-400 MB)
- Legacy Caffe2 and Intel MKL libs
- Unnecessary Qt plugins (iconengines, tls, etc.)
- Windows API-set DLLs (already on target Windows installs)

---

## Icon Setup

1. Keep `icon-512.png` in project root
2. Generate `icon.ico` (256×256 + smaller sizes) via Pillow:
   ```python
   from PIL import Image
   img = Image.open("icon-512.png")
   img.save("icon.ico", format="ICO", sizes=[(256,256), (128,128), (64,64), (32,32), (16,16)])
   ```
3. Build script uses: `--windows-icon-from-ico=icon.ico`

---

## ArgosTranslate Model (Offline Translation)

- **Git**: Model files (`*.argosmodel`) are **excluded** via `.gitignore` — too large for GitHub's 100 MB limit
- **GitHub Releases**: Bundled in pre-built EXE — releases allow 2 GB per file
- **Developers**: Install manually:
  ```bash
  argospm install translate-ja_en
  ```
- **Bundled path**: `assets/argos/ja_en.argosmodel` — included in build via `--include-data-dir=assets=assets`

---

## `build.bat` Reference

```batch
@echo off
setlocal

echo === Activating virtual environment ===
call .venv\Scripts\activate

echo === Cleaning old build folders ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist main.build rmdir /s /q main.build
if exist __pycache__ rmdir /s /q __pycache__

echo === Locating MSVC via vswhere ===
for /f "tokens=*" %%i in ('"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath') do (
    set VSINSTALL=%%i
)

if "%VSINSTALL%"=="" (
    echo ERROR: MSVC not found.
    exit /b 1
)

echo === Loading MSVC environment ===
call "%VSINSTALL%\VC\Auxiliary\Build\vcvars64.bat"

echo === Starting Nuitka build ===
python -m nuitka main.py ^
    --standalone ^
    --enable-plugin=pyqt6 ^
    --windows-console-mode=disable ^
    --include-data-dir=resources=resources ^
    --include-data-dir=models=models ^
    --include-data-dir=docs=docs ^
    --include-data-dir=ui=ui ^
    --include-data-dir=assets=assets ^
    --include-data-file=settings.json.example=settings.json.example ^
    --noinclude-dlls=api-ms-win-*.dll ^
    --noinclude-dlls=winrt-*.dll ^
    --noinclude-dlls=*onnxruntime_providers_dml.dll ^
    --noinclude-dlls=*onnxruntime_providers_cuda.dll ^
    --noinclude-dlls=*onnxruntime_providers_tensorrt.dll ^
    --noinclude-dlls=*onnxruntime_providers_openvino.dll ^
    --noinclude-dlls=*torch_cuda*.dll ^
    --noinclude-dlls=*caffe2*.dll ^
    --noinclude-dlls=*mkl*.dll ^
    --include-qt-plugins=platforms ^
    --include-qt-plugins=imageformats ^
    --include-qt-plugins=styles ^
    --lto=yes ^
    --output-dir=build ^
    --output-filename=DesktopOCR.exe ^
    --windows-icon-from-ico=icon.ico

echo === Build complete ===
pause
```

---

## Build Time Expectations

| Condition | Compiler | Time |
|---|---|---|
| Windows SDK installed + `vcvars64.bat` | MSVC | ~15 min |
| Windows SDK missing | gcc (fallback) | 1-3 hours |
| Windows SDK missing + `--lto=yes` | gcc with LTO | **5-10 hours** |

> **Do NOT use `--msvc=latest`**. It forces Nuitka's internal registry-based MSVC search which fails with Visual Studio **Build Tools** installations. The script loads MSVC via `vcvars64.bat` instead, and Nuitka auto-detects `cl.exe` from PATH.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `CC is not set` / scons crash | `--msvc=latest` present in script | Remove `--msvc=latest`; keep `vcvars64.bat` |
| `Windows SDK must be installed...` then gcc fallback | Windows SDK component missing from VS Build Tools | Install Windows SDK via Visual Studio Installer |
| `Slow C compilation detected` + stuck at linking | Using gcc with `--lto=yes` | Cancel build, remove `--lto=yes`, rerun |
| 1.3 GB output | No DLL exclusions applied | Use `--noinclude-dlls` flags above |
| Default `.exe` icon | Missing `icon.ico` | Generate from `icon-512.png` and rebuild |
