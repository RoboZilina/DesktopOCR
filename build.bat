@echo off
powershell -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)
echo Build finished.
