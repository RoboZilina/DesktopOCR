@echo off
setlocal

cd /d "%~dp0"

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

echo === Activating virtual environment ===
call .venv\Scripts\activate

echo === Cleaning old build folders ===
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist main.build rmdir /s /q main.build
if exist __pycache__ rmdir /s /q __pycache__

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
    --include-data-file=icon.ico=icon.ico ^
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
    --output-dir=build ^
    --output-filename=DesktopOCR.exe ^
    --windows-icon-from-ico=icon.ico

echo === Build complete ===
pause
