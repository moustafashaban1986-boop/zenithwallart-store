#Requires -Version 5.1
<#
.SYNOPSIS
  One-click installer: ComfyUI portable + Manager + GGUF + VideoHelperSuite + AI models
  + the Claude MCP bridge, tuned for a Lenovo Legion 7 16ITHg6 (RTX 3080 Laptop 16 GB).

.USAGE
  Right-click INSTALL.bat -> "Run as administrator"  (admin is only needed if winget has to
  install Git / 7-Zip; otherwise a normal prompt works too), or:

    powershell -ExecutionPolicy Bypass -File install.ps1 [-InstallDir C:\ComfyUI] [-Pack starter|ltx|wan21-14b|flux-fp8|all|none] [-SkipClaude]

  Safe to re-run: every step is skipped when it is already done.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\ComfyUI",
    [ValidateSet("starter", "ltx", "wan21-14b", "flux-fp8", "all", "none")]
    [string]$Pack = "starter",
    [switch]$SkipClaude
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$PortableUrl = "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
$Downloads = Join-Path $InstallDir "_downloads"
$Py = Join-Path $InstallDir "python_embeded\python.exe"
$CustomNodes = Join-Path $InstallDir "ComfyUI\custom_nodes"

function Step([string]$n, [string]$msg) { Write-Host "`n=== [$n] $msg ===" -ForegroundColor Cyan }
function Ok([string]$msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Warn([string]$msg) { Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}
function Download-File([string]$Url, [string]$Dest) {
    # curl.exe ships with Windows 10 1803+; resumes partial downloads.
    $part = "$Dest.part"
    & curl.exe -L --fail --retry 5 --retry-delay 5 -C - -o $part $Url
    if ($LASTEXITCODE -eq 33 -or $LASTEXITCODE -eq 22) {
        # server refused the resume range (file probably complete) -> restart once without resume
        Remove-Item -Force $part -ErrorAction SilentlyContinue
        & curl.exe -L --fail --retry 5 --retry-delay 5 -o $part $Url
    }
    if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit $LASTEXITCODE): $Url" }
    Move-Item -Force $part $Dest
}
function Pip([string[]]$PipArgs) {
    & $Py -s -m pip @PipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip $($PipArgs -join ' ') failed" }
}
function Git-CloneOrUpdate([string]$Repo, [string]$Dest) {
    if (Test-Path (Join-Path $Dest ".git")) {
        Write-Host "  updating $(Split-Path -Leaf $Dest)"
        & git -C $Dest pull --ff-only 2>$null | Out-Null
    } else {
        & git clone --depth 1 $Repo $Dest
        if ($LASTEXITCODE -ne 0) { throw "git clone $Repo failed" }
    }
    $req = Join-Path $Dest "requirements.txt"
    if (Test-Path $req) { Pip @("install", "-r", $req) }
}

Write-Host @"

  Claude x ComfyUI AI Studio installer
  Target:  $InstallDir
  Models:  $Pack pack
"@ -ForegroundColor Magenta

# ---------------------------------------------------------------------------
Step 0 "Pre-flight checks"
if ($env:OS -ne "Windows_NT") {
    throw "This installer is for Windows. On Linux/macOS install ComfyUI manually and run claude-comfy/server.py with any Python 3.10+."
}
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { throw "curl.exe not found. Update Windows 10/11." }
try {
    $gpu = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null)
    if ($gpu) { Ok "GPU: $gpu" } else { Warn "nvidia-smi not found. Install the latest NVIDIA driver from nvidia.com before running ComfyUI." }
} catch { Warn "nvidia-smi not found. Install the latest NVIDIA driver from nvidia.com before running ComfyUI." }

$drive = (Split-Path -Qualifier $InstallDir)
$freeGB = [math]::Round((Get-PSDrive $drive.TrimEnd(':')).Free / 1GB, 1)
$manifest = Get-Content (Join-Path $Here "models.json") -Raw | ConvertFrom-Json
$needGB = 12
if ($Pack -ne "none") {
    $names = if ($Pack -eq "all") { $manifest.files.PSObject.Properties.Name } else { $manifest.packs.$Pack.files }
    foreach ($n in $names) { $needGB += $manifest.files.$n.gb }
}
Write-Host "  Free space on $drive : $freeGB GB  (needed ~ $([math]::Round($needGB)) GB)"
if ($freeGB -lt $needGB) { Warn "Low disk space. The install may fail; free up space or choose -Pack none and download models later." }
New-Item -ItemType Directory -Force -Path $InstallDir, $Downloads | Out-Null

# ---------------------------------------------------------------------------
Step 1 "ComfyUI portable (Windows, NVIDIA build)"
if (Test-Path (Join-Path $InstallDir "ComfyUI\main.py")) {
    Ok "ComfyUI already present at $InstallDir"
} else {
    $archive = Join-Path $Downloads "ComfyUI_windows_portable_nvidia.7z"
    if (-not (Test-Path $archive)) {
        Write-Host "  downloading ~3 GB from GitHub (resumable) ..."
        Download-File $PortableUrl $archive
    } else { Ok "archive already downloaded" }

    $tmp = Join-Path $Downloads "extract"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null

    $sevenZip = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $sevenZip -and (Get-Command 7z.exe -ErrorAction SilentlyContinue)) { $sevenZip = "7z.exe" }
    $extracted = $false
    if ($sevenZip) {
        Write-Host "  extracting with 7-Zip ..."
        & $sevenZip x -y "-o$tmp" $archive | Out-Null
        $extracted = ($LASTEXITCODE -eq 0)
    }
    if (-not $extracted -and (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
        Write-Host "  extracting with Windows tar (libarchive) ... this takes a few minutes"
        & tar.exe -xf $archive -C $tmp 2>$null
        $extracted = (Test-Path (Join-Path $tmp "ComfyUI_windows_portable\ComfyUI\main.py"))
    }
    if (-not $extracted) {
        Write-Host "  installing 7-Zip with winget ..."
        & winget install --id 7zip.7zip -e --accept-package-agreements --accept-source-agreements --silent
        $sevenZip = "$env:ProgramFiles\7-Zip\7z.exe"
        & $sevenZip x -y "-o$tmp" $archive | Out-Null
        $extracted = ($LASTEXITCODE -eq 0)
    }
    if (-not $extracted) { throw "Could not extract $archive. Install 7-Zip (https://www.7-zip.org) and re-run." }

    $inner = Join-Path $tmp "ComfyUI_windows_portable"
    Get-ChildItem $inner | ForEach-Object {
        $target = Join-Path $InstallDir $_.Name
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        Move-Item -Force $_.FullName $InstallDir
    }
    Remove-Item -Recurse -Force $tmp
    Ok "ComfyUI extracted to $InstallDir"
}
if (-not (Test-Path $Py)) { throw "python_embeded\python.exe not found in $InstallDir - extraction incomplete." }

# ---------------------------------------------------------------------------
Step 2 "Git (needed to install custom nodes and for the Manager)"
Refresh-Path
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "  installing Git with winget ..."
    & winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements --silent
    Refresh-Path
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is still not on PATH. Install it from https://git-scm.com/download/win, open a NEW window and re-run INSTALL.bat."
}
Ok (& git --version)

# ---------------------------------------------------------------------------
Step 3 "ComfyUI Manager"
$managerReq = Join-Path $InstallDir "ComfyUI\manager_requirements.txt"
if (Test-Path $managerReq) {
    # Current ComfyUI ships the Manager as a pip package enabled with --enable-manager
    Pip @("install", "-r", $managerReq)
    Ok "Manager installed as a package (Start-ComfyUI.bat passes --enable-manager)"
} else {
    Git-CloneOrUpdate "https://github.com/ltdrdata/ComfyUI-Manager.git" (Join-Path $CustomNodes "comfyui-manager")
    Ok "Manager installed into custom_nodes"
}

# ---------------------------------------------------------------------------
Step 4 "Custom nodes: ComfyUI-GGUF + VideoHelperSuite"
New-Item -ItemType Directory -Force -Path $CustomNodes | Out-Null
Git-CloneOrUpdate "https://github.com/city96/ComfyUI-GGUF.git" (Join-Path $CustomNodes "ComfyUI-GGUF")
Git-CloneOrUpdate "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git" (Join-Path $CustomNodes "ComfyUI-VideoHelperSuite")
Ok "GGUF loader + Video Combine nodes ready"

# ---------------------------------------------------------------------------
Step 5 "Claude bridge (MCP server) + launchers"
$bridge = Join-Path $InstallDir "claude-comfy"
New-Item -ItemType Directory -Force -Path $bridge | Out-Null
Copy-Item -Force (Join-Path $Here "claude-comfy\*.py") $bridge
Copy-Item -Force (Join-Path $Here "claude-comfy\requirements.txt") $bridge
Copy-Item -Force (Join-Path $Here "models.json") $bridge
Copy-Item -Recurse -Force (Join-Path $Here "workflows") (Join-Path $bridge "workflows")
Copy-Item -Force (Join-Path $Here "Start-ComfyUI.bat") $InstallDir
Copy-Item -Force (Join-Path $Here "Check-Setup.bat") $InstallDir
Copy-Item -Force (Join-Path $Here "download-models.ps1") $InstallDir
Copy-Item -Force (Join-Path $Here "Download-Models.bat") $InstallDir
Copy-Item -Force (Join-Path $Here "install-claude.ps1") $InstallDir
Pip @("install", "-r", (Join-Path $bridge "requirements.txt"))
& $Py -s -c "import sys; sys.path.insert(0, r'$bridge'); import server; print('  bridge imports OK')"
if ($LASTEXITCODE -ne 0) { throw "The Claude bridge failed to import. See the error above." }
Ok "Bridge installed at $bridge"

# ---------------------------------------------------------------------------
Step 6 "AI models"
if ($Pack -eq "none") {
    Warn "Skipping model download (-Pack none). Run download-models.ps1 later."
} else {
    & (Join-Path $Here "download-models.ps1") -InstallDir $InstallDir -Pack $Pack
}

# ---------------------------------------------------------------------------
Step 7 "Connect to Claude"
if ($SkipClaude) {
    Warn "Skipped (-SkipClaude). Run install-claude.ps1 later."
} else {
    & (Join-Path $Here "install-claude.ps1") -InstallDir $InstallDir
}

# ---------------------------------------------------------------------------
Write-Host @"

=========================================================================
  DONE.  Next steps:
  1. Double-click  $InstallDir\Start-ComfyUI.bat
     -> a console opens, then your browser shows ComfyUI at http://127.0.0.1:8188
        (the "Manager" button should be in the top bar).
  2. Double-click  $InstallDir\Check-Setup.bat  to confirm GPU + models are detected.
  3. Restart Claude Desktop (fully quit from the tray icon), then ask Claude:
        "Check comfy status"  ->  "Generate an image of ..."  ->  "Make a 2 second video of ..."
  Outputs land in $InstallDir\ComfyUI\output\claude\
=========================================================================
"@ -ForegroundColor Green
