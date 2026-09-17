@echo off
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
#__PS1__ (embedded PowerShell - do not edit here, edit setup-everything.ps1 and run build-setup-bat.py)
#Requires -Version 5.1
<#
.SYNOPSIS
  ONE-CLICK SETUP for the Lenovo Legion AI Studio.
  Installs Git, downloads this repository, installs ComfyUI + models, installs the Legion
  assistant (Ollama brain, voice, PC control), installs Claude Code, verifies everything,
  then opens Claude Code on the laptop so it can fix anything that is still wrong.

.USAGE
  Double-click Legion-Setup.bat (it asks for administrator rights itself), or:
    powershell -ExecutionPolicy Bypass -File setup-everything.ps1 [-ComfyDir C:\ComfyUI] [-Model qwen3:8b] [-SkipModels] [-NoClaudeCode] [-NoLaunch]

  Safe to run again: every step skips what is already done.
#>
[CmdletBinding()]
param(
    [string]$RepoDir = (Join-Path $env:USERPROFILE "zenithwallart-store"),
    [string]$ComfyDir = "C:\ComfyUI",
    [string]$Model = "qwen3:8b",
    [switch]$SkipModels,
    [switch]$NoClaudeCode,
    [switch]$NoLaunch
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoUrl = "https://github.com/moustafashaban1986-boop/zenithwallart-store.git"
$RepoZip = "https://github.com/moustafashaban1986-boop/zenithwallart-store/archive/refs/heads/main.zip"
$Log = Join-Path $env:USERPROFILE "legion-setup.log"
Start-Transcript -Path $Log -Append | Out-Null

function Step([string]$n, [string]$m) { Write-Host "`n##### [$n] $m #####" -ForegroundColor Magenta }
function Ok([string]$m) { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "  !!  $m" -ForegroundColor Yellow }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + (Join-Path $env:USERPROFILE ".local\bin")
}
$failures = @()

Write-Host @"

  Lenovo Legion AI Studio - one-click setup
  Repository : $RepoDir
  ComfyUI    : $ComfyDir
  Brain      : Ollama / $Model
  Log        : $Log
"@ -ForegroundColor Cyan

# ---------------------------------------------------------------------------
Step 1 "Git"
Refresh-Path
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    try {
        & winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
    } catch { Warn "winget failed: $_" }
    Refresh-Path
}
if (Get-Command git -ErrorAction SilentlyContinue) { Ok (& git --version) } else { Warn "Git not available; the repository will be downloaded as a ZIP instead." }

# ---------------------------------------------------------------------------
Step 2 "Repository (the installers and Legion code)"
if (Test-Path (Join-Path $Here "ai-studio\install.ps1")) {
    $RepoDir = $Here
    Ok "running from inside the repository: $RepoDir"
    if ((Test-Path (Join-Path $RepoDir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        & git -C $RepoDir pull --ff-only 2>$null | Out-Null
    }
} elseif ((Test-Path (Join-Path $RepoDir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    & git -C $RepoDir pull --ff-only
    Ok "updated $RepoDir"
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
    if (Test-Path $RepoDir) {
        $bak = "$RepoDir.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Move-Item $RepoDir $bak
        Warn "existing folder without git history moved to $bak"
    }
    & git clone $RepoUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
    Ok "cloned to $RepoDir"
} else {
    $zip = Join-Path $env:TEMP "zenithwallart-store-main.zip"
    & curl.exe -fsSL -o $zip $RepoZip
    if ($LASTEXITCODE -ne 0) { throw "download of $RepoZip failed" }
    $tmp = Join-Path $env:TEMP "zenithwallart-extract"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive -Path $zip -DestinationPath $tmp
    if (Test-Path $RepoDir) { Remove-Item -Recurse -Force $RepoDir }
    Move-Item (Join-Path $tmp "zenithwallart-store-main") $RepoDir
    Ok "downloaded to $RepoDir"
}
$AiStudio = Join-Path $RepoDir "ai-studio"
if (-not (Test-Path (Join-Path $AiStudio "install.ps1"))) { throw "ai-studio\install.ps1 not found under $RepoDir" }

# ---------------------------------------------------------------------------
Step 3 "ComfyUI + custom nodes + AI models + Claude connection"
try {
    $pack = if ($SkipModels) { "none" } else { "starter" }
    & (Join-Path $AiStudio "install.ps1") -InstallDir $ComfyDir -Pack $pack
    Ok "ComfyUI ready"
} catch {
    $failures += "ComfyUI install: $_"
    Warn "ComfyUI step failed: $_"
}

# ---------------------------------------------------------------------------
Step 4 "Legion assistant (Ollama brain, voice, PC control)"
try {
    & (Join-Path $AiStudio "assistant\install-assistant.ps1") -ComfyDir $ComfyDir -Model $Model
    Ok "Legion ready"
} catch {
    $failures += "Legion install: $_"
    Warn "Legion step failed: $_"
}

# ---------------------------------------------------------------------------
Step 5 "Claude Code (so Claude can work directly on this laptop)"
if ($NoClaudeCode) { Warn "skipped (-NoClaudeCode)" } else {
    Refresh-Path
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        try {
            Invoke-Expression (Invoke-RestMethod -Uri "https://claude.ai/install.ps1")
        } catch {
            Warn "native installer failed ($_) - trying winget"
            try { & winget install Anthropic.ClaudeCode --accept-package-agreements --accept-source-agreements --silent } catch { Warn "winget failed: $_" }
        }
        Refresh-Path
    }
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Ok ("Claude Code " + (& claude --version 2>$null))
    } else {
        $failures += "Claude Code not installed (run:  irm https://claude.ai/install.ps1 | iex )"
        Warn "Claude Code is not on PATH yet. Open a NEW PowerShell window and run: claude --version"
    }
}

# ---------------------------------------------------------------------------
Step 6 "Verification"
$py = Join-Path $ComfyDir "python_embeded\python.exe"
$runner = Join-Path $ComfyDir "legion\run_legion.py"
if ((Test-Path $py) -and (Test-Path $runner)) {
    & $py -s $runner doctor
    & $py -s (Join-Path $ComfyDir "claude-comfy\cli.py") models
} else {
    Warn "Legion or the ComfyUI bridge is missing; see the errors above."
}

Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "=== Everything installed. ===" -ForegroundColor Green
} else {
    Write-Host "=== Finished with problems: ===" -ForegroundColor Yellow
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host "  Full log: $Log" -ForegroundColor Yellow
}
Write-Host @"

  Start ComfyUI (images/videos):  $ComfyDir\Start-ComfyUI.bat
  Start Legion (voice assistant): $ComfyDir\legion\Start-Assistant.bat   -> http://127.0.0.1:7860
  Restart Claude Desktop fully (tray icon > Quit) to load the 'comfyui' and 'legion' tools.
"@ -ForegroundColor Cyan

# ---------------------------------------------------------------------------
Step 7 "Hand over to Claude Code on this laptop"
Stop-Transcript | Out-Null
if ($NoLaunch) { Warn "not launching Claude Code (-NoLaunch)"; return }
Refresh-Path
if (Get-Command claude -ErrorAction SilentlyContinue) {
    $task = "You are on the user's Lenovo Legion laptop. The one-click setup just ran; its log is at $Log and the repository is at $RepoDir. " +
            "ComfyUI is installed at $ComfyDir. Read the log, fix any failed step, then: 1) run $ComfyDir\Check-Setup.bat and make sure every model file shows [x] (run $ComfyDir\Download-Models.bat if not); " +
            "2) start $ComfyDir\legion\Start-Assistant.bat and confirm http://127.0.0.1:7860 answers; 3) run 'claude mcp list' and confirm comfyui and legion are registered; " +
            "4) generate one test image through the Legion web API or CLI to prove the GPU pipeline works. Report what you verified."
    $taskFile = Join-Path $env:USERPROFILE "legion-claude-task.txt"
    Set-Content -Path $taskFile -Value $task -Encoding UTF8
    Write-Host "  Opening Claude Code in $RepoDir (log in with your claude.ai account when the browser opens) ..."
    Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
        "Set-Location '$RepoDir'; claude (Get-Content -Raw '$taskFile')")
    Ok "Claude Code launched in a new window"
} else {
    Warn "Claude Code not found. Open a new PowerShell window, run: cd `"$RepoDir`" ; claude"
}
