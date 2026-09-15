@echo off
REM ONE-CLICK SETUP: Git + ComfyUI + AI models + Legion assistant + Claude Code, then opens Claude Code to verify.
REM Download this file (and optionally setup-everything.ps1 next to it) and double-click it.
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
set "PS1=%~dp0setup-everything.ps1"
if not exist "%PS1%" (
  set "PS1=%TEMP%\setup-everything.ps1"
  echo Downloading the setup script...
  curl.exe -fsSL -o "%TEMP%\setup-everything.ps1" https://raw.githubusercontent.com/moustafashaban1986-boop/zenithwallart-store/main/setup-everything.ps1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
echo.
pause
