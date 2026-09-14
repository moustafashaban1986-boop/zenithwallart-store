@echo off
REM One-click installer for the Claude x ComfyUI AI Studio (see README.md)
REM Usage: INSTALL.bat            -> C:\ComfyUI with the "starter" model pack
REM        INSTALL.bat -Pack all  -> every model pack
REM        INSTALL.bat -InstallDir D:\ComfyUI -Pack none
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
