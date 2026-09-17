@echo off
REM ============================================================================
REM  Claude Code desktop shortcuts (no administrator needed)
REM  Double-click this file. It installs Claude Code if missing and puts two
REM  shortcuts on the desktop:
REM    Claude - Full Control     PowerShell + Claude Code, no permission prompts
REM    Claude - Remote (phone)   same session on your phone (Claude app > Code)
REM                              and at https://claude.ai/code on any computer
REM  Uses claude-shortcuts.ps1 next to this file, or downloads it from GitHub.
REM  Safe to run again.
REM ============================================================================
set "PS1=%~dp0claude-shortcuts.ps1"
if not exist "%PS1%" (
  set "PS1=%TEMP%\claude-shortcuts.ps1"
  echo Downloading claude-shortcuts.ps1 ...
  curl.exe -fsSL -o "%TEMP%\claude-shortcuts.ps1" "https://raw.githubusercontent.com/moustafashaban1986-boop/zenithwallart-store/main/claude-shortcuts.ps1"
)
if not exist "%PS1%" curl.exe -fsSL -o "%PS1%" "https://raw.githubusercontent.com/moustafashaban1986-boop/zenithwallart-store/claude/lenovo-legion-ai-video-setup-xnilya/claude-shortcuts.ps1"
if not exist "%PS1%" (
  echo ERROR: could not download claude-shortcuts.ps1. Check the internet connection.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
echo.
pause
exit /b
