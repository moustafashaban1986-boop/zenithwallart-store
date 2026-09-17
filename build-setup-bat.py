"""Build the self-contained one-click .bat files from their PowerShell scripts.

  Legion-Setup.bat      <- setup-everything.ps1   (self-elevates to administrator)
  Claude-Shortcuts.bat  <- claude-shortcuts.ps1   (no administrator needed; the checked-in
                           Claude-Shortcuts.bat is a small downloader instead - run this
                           with --embed-shortcuts to replace it with the embedded version)

Each .bat header extracts the PowerShell script embedded after the #__PS1__ marker
into %TEMP% and runs it. Re-run this script after editing either .ps1.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ELEVATE = r"""if "%~1"=="elevated" goto :admin
fltmc >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
  exit /b
)
:admin
"""

RUN = r"""set "PS1=%TEMP%\{ps1}"
powershell -NoProfile -Command "$c = Get-Content -Raw -LiteralPath '%~f0'; $m = '#__PS' + '1__'; $i = $c.IndexOf($m); Set-Content -LiteralPath '%PS1%' -Value $c.Substring($i) -Encoding UTF8"
if not exist "%PS1%" (
  echo ERROR: could not extract the script.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
echo.
{tail}pause
exit /b
"""

BUILDS = [
    {
        "ps1": "setup-everything.ps1",
        "bat": "Legion-Setup.bat",
        "elevate": True,
        "tail": "echo Log file: %USERPROFILE%\\legion-setup.log\n",
        "banner": r"""REM ============================================================================
REM  Lenovo Legion AI Studio - ONE-CLICK SETUP (self-contained)
REM  Double-click this file. It asks for administrator rights, then installs:
REM  Git, this repository, ComfyUI + AI models, the Legion voice assistant
REM  (Ollama brain, speech, PC control), Claude Code - and finally opens
REM  Claude Code on this laptop to verify and fix anything that failed.
REM  Log: %USERPROFILE%\legion-setup.log      Safe to run again.
REM ============================================================================
""",
    },
    {
        "ps1": "claude-shortcuts.ps1",
        "bat": "Claude-Shortcuts.bat",
        "elevate": False,
        "tail": "",
        "banner": r"""REM ============================================================================
REM  Claude Code desktop shortcuts (self-contained, no administrator needed)
REM  Double-click this file. It installs Claude Code if missing and puts two
REM  shortcuts on the desktop:
REM    Claude - Full Control     PowerShell + Claude Code, no permission prompts
REM    Claude - Remote (phone)   same session on your phone (Claude app > Code)
REM                              and at https://claude.ai/code on any computer
REM  Safe to run again.
REM ============================================================================
""",
    },
]


def build(spec: dict) -> None:
    ps1 = (ROOT / spec["ps1"]).read_text(encoding="utf-8")
    assert ps1.isascii(), f"{spec['ps1']} must stay ASCII so the .bat is safe"
    assert ps1.count("#__PS1__") == 0, f"{spec['ps1']} must not contain the marker"
    header = "@echo off\n" + spec["banner"]
    if spec["elevate"]:
        header += ELEVATE
    header += RUN.format(ps1=spec["ps1"], tail=spec["tail"])
    body = f"#__PS1__ (embedded PowerShell - do not edit here, edit {spec['ps1']} and run build-setup-bat.py)\r\n" + ps1
    out = (header + body).replace("\r\n", "\n").replace("\n", "\r\n")
    assert out.count("#__PS1__") == 1
    (ROOT / spec["bat"]).write_bytes(out.encode("ascii"))
    print("wrote", spec["bat"], len(out), "bytes")


if __name__ == "__main__":
    for spec in BUILDS:
        if spec["bat"] == "Claude-Shortcuts.bat" and "--embed-shortcuts" not in sys.argv:
            continue
        build(spec)
