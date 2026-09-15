@echo off
REM Download (or resume) model packs. Usage: Download-Models.bat [-Pack starter^|ltx^|wan21-14b^|flux-fp8^|all]
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-models.ps1" -InstallDir "%~dp0." %*
pause
