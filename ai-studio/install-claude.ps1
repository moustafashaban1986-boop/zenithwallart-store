#Requires -Version 5.1
<#
.SYNOPSIS
  Register the ComfyUI MCP server with Claude Desktop and Claude Code so Claude can
  generate images and videos on this laptop.

.USAGE
  powershell -ExecutionPolicy Bypass -File install-claude.ps1 [-InstallDir C:\ComfyUI]
#>
[CmdletBinding()]
param([string]$InstallDir = "C:\ComfyUI")
$ErrorActionPreference = "Stop"

$Py = Join-Path $InstallDir "python_embeded\python.exe"
$Server = Join-Path $InstallDir "claude-comfy\server.py"
if (-not (Test-Path $Py)) { throw "ComfyUI portable python not found at $Py. Run install.ps1 first." }
if (-not (Test-Path $Server)) { throw "Bridge not found at $Server. Run install.ps1 first." }

$entry = [ordered]@{
    command = $Py
    args    = @($Server)
    env     = [ordered]@{ COMFY_DIR = $InstallDir; COMFY_URL = "http://127.0.0.1:8188" }
}

# --- Claude Desktop ---------------------------------------------------------
$cfgDir = Join-Path $env:APPDATA "Claude"
$cfgPath = Join-Path $cfgDir "claude_desktop_config.json"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
if (Test-Path $cfgPath) {
    Copy-Item -Force $cfgPath "$cfgPath.bak"
    $raw = Get-Content $cfgPath -Raw
    $cfg = if ($raw.Trim()) { $raw | ConvertFrom-Json } else { [pscustomobject]@{} }
} else {
    $cfg = [pscustomobject]@{}
}
if (-not ($cfg.PSObject.Properties.Name -contains "mcpServers") -or $null -eq $cfg.mcpServers) {
    $cfg | Add-Member -Force -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
}
$cfg.mcpServers | Add-Member -Force -NotePropertyName comfyui -NotePropertyValue ([pscustomobject]$entry)
$cfg | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $cfgPath
Write-Host "  OK  Claude Desktop: added 'comfyui' server to $cfgPath" -ForegroundColor Green
Write-Host "      (fully quit Claude Desktop from the tray icon and start it again to load it)"

# --- Claude Code (CLI) ------------------------------------------------------
$snippet = [ordered]@{ mcpServers = [ordered]@{ comfyui = $entry } } | ConvertTo-Json -Depth 10
$snippetPath = Join-Path $InstallDir "claude-comfy\mcp.json"
$snippet | Set-Content -Encoding UTF8 $snippetPath
if (Get-Command claude -ErrorAction SilentlyContinue) {
    & claude mcp remove comfyui -s user 2>$null | Out-Null
    & claude mcp add --scope user --env "COMFY_DIR=$InstallDir" comfyui -- $Py $Server
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  OK  Claude Code: registered 'comfyui' (user scope). Run 'claude mcp list' to verify." -ForegroundColor Green
    } else {
        Write-Host "  !!  'claude mcp add' failed. Add it manually with the JSON in $snippetPath" -ForegroundColor Yellow
    }
} else {
    Write-Host "  --  Claude Code CLI not found (optional). To add later:" -ForegroundColor DarkGray
    Write-Host "      claude mcp add --scope user comfyui -- `"$Py`" `"$Server`"" -ForegroundColor DarkGray
}
Write-Host "  MCP config snippet saved to $snippetPath (also usable as a project .mcp.json)"
