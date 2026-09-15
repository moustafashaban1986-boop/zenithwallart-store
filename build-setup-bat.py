"""Build Legion-Setup.bat: a self-contained one-click installer.

The batch header self-elevates, extracts the PowerShell script embedded after the
#__PS1__ marker into %TEMP%, and runs it. Re-run this after editing setup-everything.ps1.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ps1 = (ROOT / "setup-everything.ps1").read_text(encoding="utf-8")
assert ps1.isascii(), "setup-everything.ps1 must stay ASCII so the .bat is safe"
header = r"""@echo off
REM ============================================================================
REM  Lenovo Legion AI Studio - ONE-CLICK SETUP (self-contained)
REM  Double-click this file. It asks for administrator rights, then installs:
REM  Git, this repository, ComfyUI + AI models, the Legion voice assistant
REM  (Ollama brain, speech, PC control), Claude Code - and finally opens
REM  Claude Code on this laptop to verify and fix anything that failed.
REM  Log: %USERPROFILE%\legion-setup.log      Safe to run again.
REM ============================================================================
if "%~1"=="elevated" goto :admin
fltmc >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
  exit /b
)
:admin
set "PS1=%TEMP%\setup-everything.ps1"
powershell -NoProfile -Command "$c = Get-Content -Raw -LiteralPath '%~f0'; $m = '#__PS' + '1__'; $i = $c.IndexOf($m); Set-Content -LiteralPath '%PS1%' -Value $c.Substring($i) -Encoding UTF8"
if not exist "%PS1%" (
  echo ERROR: could not extract the setup script.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
echo.
echo Log file: %USERPROFILE%\legion-setup.log
pause
exit /b
"""
body = "#__PS1__ (embedded PowerShell - do not edit here, edit setup-everything.ps1 and run build-setup-bat.py)\r\n" + ps1
out = (header + body).replace("\r\n", "\n").replace("\n", "\r\n")
(ROOT / "Legion-Setup.bat").write_bytes(out.encode("ascii"))
print("wrote Legion-Setup.bat", len(out), "bytes")
