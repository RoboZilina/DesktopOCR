$ErrorActionPreference = "Stop"

Write-Host "Cleaning build directory..."
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue

Write-Host "Running Nuitka build..."
.\.venv\Scripts\python.exe -m nuitka main.py `
    --standalone `
    --enable-plugin=pyqt6 `
    --module-parameter=torch-disable-jit=yes `
    --msvc=latest `
    --include-data-dir=resources=resources `
    --include-data-dir=models=models `
    --include-data-dir=docs=docs `
    --include-data-dir=ui=ui `
    --include-data-file=settings.json.example=settings.json.example `
    --include-data-dir=assets=assets `
    --output-dir=build `
    --output-filename=DesktopOCR.exe `
    --windows-console-mode=disable

Write-Host "Build complete."
