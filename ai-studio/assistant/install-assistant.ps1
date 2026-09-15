#Requires -Version 5.1
<#
.SYNOPSIS
  Install Legion - the local voice assistant - on top of the AI Studio ComfyUI install.
  Installs Ollama (offline brain) + a default model, the Python packages (into ComfyUI's
  embedded Python so no second PyTorch download is needed), and registers Legion with Claude.

.USAGE
  Right-click INSTALL-ASSISTANT.bat -> Run as administrator, or:
    powershell -ExecutionPolicy Bypass -File install-assistant.ps1 [-ComfyDir C:\ComfyUI] [-Model qwen3:8b] [-SkipVoice] [-SkipOllama]
#>
[CmdletBinding()]
param(
    [string]$ComfyDir = "C:\ComfyUI",
    [string]$Model = "qwen3:8b",
    [switch]$SkipVoice,
    [switch]$SkipOllama,
    [switch]$SkipClaude
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = Join-Path $ComfyDir "legion"
$Py = Join-Path $ComfyDir "python_embeded\python.exe"

function Step([string]$n, [string]$m) { Write-Host "`n=== [$n] $m ===" -ForegroundColor Cyan }
function Ok([string]$m) { Write-Host "  OK  $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "  !!  $m" -ForegroundColor Yellow }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
function Pip([string[]]$PipArgs) { & $Py -s -m pip @PipArgs; if ($LASTEXITCODE -ne 0) { throw "pip $($PipArgs -join ' ') failed" } }

Step 0 "Pre-flight"
if (-not (Test-Path $Py)) {
    throw "ComfyUI portable Python not found at $Py. Run ai-studio\INSTALL.bat first (Legion reuses its Python + PyTorch)."
}
Ok "Using $Py"

Step 1 "Ollama (offline brain)"
if ($SkipOllama) { Warn "skipped" } else {
    Refresh-Path
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host "  installing Ollama with winget ..."
        & winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements --silent
        Refresh-Path
    }
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        Ok (& ollama --version)
        Start-Process -WindowStyle Hidden ollama -ArgumentList "serve" -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 4
        Write-Host "  pulling $Model (a few GB, once) ..."
        & ollama pull $Model
        if ($LASTEXITCODE -eq 0) { Ok "$Model ready" } else { Warn "pull failed - run 'ollama pull $Model' later" }
    } else {
        Warn "Ollama not installed. Get it from https://ollama.com/download and run: ollama pull $Model"
    }
}

Step 2 "Copy Legion + Python packages"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Recurse -Force (Join-Path $Here "legion") $Dest
Copy-Item -Force (Join-Path $Here "requirements*.txt") $Dest
Copy-Item -Force (Join-Path $Here "*.bat") $Dest
Copy-Item -Force (Join-Path $Here "run_legion.py") $Dest
Copy-Item -Force (Join-Path $Here "README.md") $Dest
Get-ChildItem -Path $Dest -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Pip @("install", "-r", (Join-Path $Dest "requirements.txt"))
Ok "core packages installed"
if ($SkipVoice) { Warn "voice packages skipped (-SkipVoice)" } else {
    try {
        Pip @("install", "-r", (Join-Path $Dest "requirements-voice.txt"))
        Ok "voice packages installed (faster-whisper, kokoro, sounddevice)"
    } catch {
        Warn "voice packages failed: $_  -> Windows built-in voices will be used; re-run later with: python_embeded\python.exe -s -m pip install -r legion\requirements-voice.txt"
    }
}
& $Py -s (Join-Path $Dest "run_legion.py") doctor
if ($LASTEXITCODE -ne 0) { throw "Legion doctor failed (see above)" }

Step 3 "Launchers"
$launch = @"
@echo off
cd /d "%~dp0.."
.\python_embeded\python.exe -s "%~dp0run_legion.py" %*
"@
Set-Content -Path (Join-Path $Dest "legion.cmd") -Value $launch -Encoding ASCII
Ok "legion.cmd (run:  legion\legion.cmd doctor | serve | voice | chat)"

Step 4 "Connect to Claude (MCP)"
if ($SkipClaude) { Warn "skipped" } else {
    $runner = Join-Path $Dest "run_legion.py"
    $server = [ordered]@{
        command = $Py
        args    = @("-s", $runner, "mcp")
        env     = [ordered]@{ COMFY_BRIDGE_DIR = (Join-Path $ComfyDir "claude-comfy"); LEGION_MCP_ALLOW_DANGEROUS = "0" }
    }
    $cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    New-Item -ItemType Directory -Force -Path (Split-Path $cfgPath) | Out-Null
    $cfg = if (Test-Path $cfgPath) { (Get-Content $cfgPath -Raw) | ConvertFrom-Json } else { [pscustomobject]@{} }
    if (-not ($cfg.PSObject.Properties.Name -contains "mcpServers") -or $null -eq $cfg.mcpServers) {
        $cfg | Add-Member -Force -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    $cfg.mcpServers | Add-Member -Force -NotePropertyName legion -NotePropertyValue ([pscustomobject]$server)
    $cfg | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $cfgPath
    Ok "Claude Desktop: 'legion' server added to $cfgPath (restart Claude Desktop)"
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        & claude mcp remove legion -s user 2>$null | Out-Null
        & claude mcp add --scope user --env "COMFY_BRIDGE_DIR=$(Join-Path $ComfyDir 'claude-comfy')" legion -- $Py -s $runner mcp
        Ok "Claude Code: 'legion' registered"
    }
}

Write-Host @"

=========================================================================
  Legion is installed in $Dest
  Start the web UI:    $Dest\Start-Assistant.bat        (http://127.0.0.1:7860)
  Hands-free voice:    $Dest\Start-Assistant-Voice.bat
  Check everything:    $Dest\legion.cmd doctor
  Default brain: Ollama / $Model (offline). Add API keys in the web UI for Claude, Kimi, Groq, Gemini, DeepSeek, OpenRouter.
  Claude Desktop now has a 'legion' tool server for controlling this PC (safe mode on by default).
=========================================================================
"@ -ForegroundColor Green
