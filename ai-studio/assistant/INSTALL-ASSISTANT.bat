@echo off
REM Installs Legion (local voice assistant). Run AFTER ai-studio\INSTALL.bat.
REM Options: -ComfyDir C:\ComfyUI  -Model qwen3:8b  -SkipVoice  -SkipOllama
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-assistant.ps1" %*
echo.
pause
