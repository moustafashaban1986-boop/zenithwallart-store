#Requires -Version 5.1
<#
.SYNOPSIS
  Puts two Claude Code shortcuts on the desktop so Claude can control this PC from
  PowerShell - and the same session can be driven from your phone or another computer.

  Desktop shortcuts created:
    Claude - Full Control     PowerShell + Claude Code with every permission prompt skipped.
                              Claude can run any command, edit any file and open any app on this PC.
    Claude - Remote (phone)   Claude Code with Remote Control: the session shows up in the Claude
                              app on your phone (Code tab) and at https://claude.ai/code on any
                              computer. Risky actions ask for a tap of approval on your phone.

.USAGE
  Double-click Claude-Shortcuts.bat, or:
    powershell -ExecutionPolicy Bypass -File claude-shortcuts.ps1 [-WorkDir C:\path] [-SessionName "Legion Laptop"] [-NoLaunch]

  Remote Control needs a claude.ai Pro/Max/Team login (an API key does not work).
  Safe to run again: it overwrites the shortcuts.
#>
[CmdletBinding()]
param(
    [string]$WorkDir = "",
    [string]$SessionName = "Legion Laptop",
    [switch]$NoLaunch
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Step([string]$n, [string]$m) { Write-Host "`n##### [$n] $m #####" -ForegroundColor Magenta }
function Ok([string]$m) { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "  !!  $m" -ForegroundColor Yellow }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";" + (Join-Path $env:USERPROFILE ".local\bin")
}

# ---------------------------------------------------------------------------
Step 1 "Claude Code"
Refresh-Path
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "  installing Claude Code (native installer) ..."
    try {
        Invoke-Expression (Invoke-RestMethod -Uri "https://claude.ai/install.ps1")
    } catch {
        Warn "native installer failed: $_  -> trying winget"
        try { & winget install Anthropic.ClaudeCode --accept-package-agreements --accept-source-agreements --silent } catch { Warn "winget failed: $_" }
    }
    Refresh-Path
}
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Ok ("Claude Code " + (& claude --version 2>$null))
} else {
    Warn "Claude Code is not on PATH yet. The shortcuts are still created; open a NEW PowerShell window and run:  irm https://claude.ai/install.ps1 | iex"
}

# ---------------------------------------------------------------------------
Step 2 "Folders"
if (-not $WorkDir) {
    foreach ($c in @((Join-Path $env:USERPROFILE "zenithwallart-store"), "C:\ComfyUI")) {
        if (Test-Path $c) { $WorkDir = $c; break }
    }
    if (-not $WorkDir) { $WorkDir = Join-Path $env:USERPROFILE "Claude-PC" }
}
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$Bin = Join-Path $env:USERPROFILE "Claude-PC"
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Ok "Claude starts in: $WorkDir   (Remote Control needs a project folder, not the home folder)"
Ok "launchers in:     $Bin"

# ---------------------------------------------------------------------------
Step 3 "Launcher scripts"
$common = @"
`$env:Path += ';' + (Join-Path `$env:USERPROFILE '.local\bin')
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host 'Claude Code is not installed. Run Claude-Shortcuts.bat again, or:  irm https://claude.ai/install.ps1 | iex' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
Set-Location -LiteralPath '$WorkDir'
"@

$full = $common + @"
`$Host.UI.RawUI.WindowTitle = 'Claude Code - full control of this PC'
Write-Host 'Claude Code with ALL permission prompts skipped: it can run any command, edit any file, open any app.' -ForegroundColor Yellow
Write-Host 'Type /remote-control inside the session to also see it on your phone.' -ForegroundColor DarkGray
& claude --dangerously-skip-permissions
"@
Set-Content -Path (Join-Path $Bin "Claude-Full-Control.ps1") -Value $full -Encoding UTF8

$remote = $common + @"
`$Host.UI.RawUI.WindowTitle = 'Claude Code - remote control ($SessionName)'
Write-Host 'Claude Code + Remote Control (auto mode: risky actions ask for approval, and the prompt also appears on your phone).' -ForegroundColor Yellow
Write-Host 'Phone:  Claude app > Code tab > "$SessionName"   (type /remote-control here to show a QR code)' -ForegroundColor Cyan
Write-Host 'PC:     https://claude.ai/code  > "$SessionName"' -ForegroundColor Cyan
Write-Host 'First time: log in with your claude.ai account and answer y to "Enable Remote Control?".' -ForegroundColor DarkGray
& claude --remote-control '$SessionName' --permission-mode auto
"@
Set-Content -Path (Join-Path $Bin "Claude-Remote.ps1") -Value $remote -Encoding UTF8
Ok "Claude-Full-Control.ps1, Claude-Remote.ps1"

# ---------------------------------------------------------------------------
Step 4 "Desktop shortcuts"
$ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
function Make-Shortcut([string]$Path, [string]$Script, [string]$Description) {
    $lnk = $shell.CreateShortcut($Path)
    $lnk.TargetPath = $ps
    $lnk.Arguments = "-NoExit -ExecutionPolicy Bypass -File `"$Script`""
    $lnk.WorkingDirectory = $WorkDir
    $lnk.Description = $Description
    $lnk.IconLocation = "$ps,0"
    $lnk.Save()
}
Make-Shortcut (Join-Path $desktop "Claude - Full Control.lnk") (Join-Path $Bin "Claude-Full-Control.ps1") "Claude Code in PowerShell with all permissions (controls this PC)"
Make-Shortcut (Join-Path $desktop "Claude - Remote (phone).lnk") (Join-Path $Bin "Claude-Remote.ps1") "Claude Code with Remote Control: use it from the Claude app or claude.ai/code"
Ok "2 shortcuts on $desktop"

# ---------------------------------------------------------------------------
Write-Host @"

=========================================================================
  Desktop:  Claude - Full Control      -> Claude in PowerShell, no permission prompts
            Claude - Remote (phone)    -> same session on your phone / another PC

  On your PHONE:  install the Claude app (iOS/Android), sign in with the SAME claude.ai
                  account, tap  Code  in the navigation, open "$SessionName".
  On another PC:  https://claude.ai/code  -> "$SessionName"
  QR code:        type /remote-control inside the session.
  Keep the laptop on and awake (or plugged in) while you use it from the phone.

  One-time setup, in the window that opens now:
    1. log in to claude.ai when the browser opens (Pro/Max; API keys do not work)
    2. answer  y  to "Enable Remote Control?"
    3. trust the folder $WorkDir
=========================================================================
"@ -ForegroundColor Green

if (-not $NoLaunch) {
    Start-Process $ps -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Bin "Claude-Remote.ps1")) -WorkingDirectory $WorkDir
    Ok "launched 'Claude - Remote (phone)' so you can do the one-time login now"
}
