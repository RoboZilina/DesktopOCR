Write-Host "Cleaning old build folders..."

if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

Write-Host "Starting Nuitka build..."

python -m nuitka main.py `
  --standalone `
  --enable-plugin=pyqt6 `
  --enable-plugin=tk-inter `
  --include-data-dir=resources=resources `
  --include-data-dir=models=models `
  --include-data-dir=docs=docs `
  --include-data-dir=ui=ui `
  --include-data-dir=tts=tts `
  --include-data-file=settings.json.example=settings.json.example `
  --output-dir=build `
  --output-filename=DesktopOCR.exe

Write-Host ""
Write-Host "======================================="
Write-Host " Build complete!"
Write-Host " Your app is here: build/main.dist/"
Write-Host "======================================="
