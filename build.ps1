$ErrorActionPreference = "Stop"

Write-Host "=== Activating virtual environment ==="
& .\.venv\Scripts\Activate.ps1

Write-Host "=== Cleaning old build folders ==="
Remove-Item -Recurse -Force build, dist, main.build, __pycache__ -ErrorAction SilentlyContinue

Write-Host "=== Locating MSVC via vswhere ==="
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    Write-Host "ERROR: vswhere.exe not found. Install Visual Studio Build Tools."
    exit 1
}

$installationPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installationPath) {
    Write-Host "ERROR: MSVC not found. Install Visual Studio or Build Tools with C++ workload."
    exit 1
}

Write-Host "=== Loading MSVC environment ==="
$vcvarsPath = Join-Path $installationPath "VC\Auxiliary\Build\vcvars64.bat"
& cmd /c "`"$vcvarsPath`" && set" | ForEach-Object {
    if ($_ -match "^(.*?)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}
Write-Host "MSVC environment loaded from $installationPath"

Write-Host "=== Starting Nuitka build ==="
python -m nuitka main.py `
    --standalone `
    --enable-plugin=pyqt6 `
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

Write-Host "=== Build complete ==="
