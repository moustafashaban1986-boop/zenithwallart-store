#Requires -Version 5.1
<#
.SYNOPSIS
  Download AI model files into ComfyUI\models\<folder>\ with resume support.

.USAGE
  powershell -ExecutionPolicy Bypass -File download-models.ps1 [-InstallDir C:\ComfyUI] [-Pack starter|ltx|wan21-14b|flux-fp8|all] [-Files name1,name2]

  Packs are defined in models.json (kept next to this script or in claude-comfy\).
  Files that already exist with a plausible size are skipped, so re-running is cheap.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "C:\ComfyUI",
    [ValidateSet("starter", "ltx", "wan21-14b", "flux-fp8", "all")]
    [string]$Pack = "starter",
    [string[]]$Files
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

$manifestPath = @((Join-Path $Here "models.json"), (Join-Path $Here "claude-comfy\models.json"),
                  (Join-Path $InstallDir "claude-comfy\models.json")) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $manifestPath) { throw "models.json not found next to this script." }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$modelsRoot = Join-Path $InstallDir "ComfyUI\models"
if (-not (Test-Path $modelsRoot)) { throw "ComfyUI models folder not found at $modelsRoot. Run install.ps1 first." }

if ($Files) {
    $names = $Files
} elseif ($Pack -eq "all") {
    $names = $manifest.files.PSObject.Properties.Name
} else {
    $names = $manifest.packs.$Pack.files
}
$names = $names | Select-Object -Unique

$totalGB = 0
foreach ($n in $names) { $totalGB += $manifest.files.$n.gb }
Write-Host "`nDownloading pack '$Pack' -> $modelsRoot  (~$([math]::Round($totalGB, 1)) GB, resumable)" -ForegroundColor Cyan

$failed = @()
foreach ($name in $names) {
    $info = $manifest.files.$name
    if (-not $info) { Write-Host "  ?? unknown file $name (not in models.json)" -ForegroundColor Yellow; continue }
    $dir = Join-Path $modelsRoot $info.folder
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $dest = Join-Path $dir $name
    $minBytes = [int64]($info.gb * 0.8 * 1GB)
    if ((Test-Path $dest) -and ((Get-Item $dest).Length -ge $minBytes)) {
        Write-Host "  skip  $name (already there, $([math]::Round((Get-Item $dest).Length / 1GB, 2)) GB)" -ForegroundColor DarkGray
        continue
    }
    Write-Host "`n  get   $name  (~$($info.gb) GB)  -> $($info.folder)\" -ForegroundColor White
    Write-Host "        $($info.note)"
    $part = "$dest.part"
    & curl.exe -L --fail --retry 8 --retry-delay 10 -C - -o $part $info.url
    if ($LASTEXITCODE -eq 33 -or $LASTEXITCODE -eq 22) {
        Remove-Item -Force $part -ErrorAction SilentlyContinue
        & curl.exe -L --fail --retry 8 --retry-delay 10 -o $part $info.url
    }
    if ($LASTEXITCODE -eq 0 -and (Test-Path $part) -and ((Get-Item $part).Length -ge $minBytes)) {
        Move-Item -Force $part $dest
        Write-Host "  done  $name" -ForegroundColor Green
    } else {
        $failed += $name
        Write-Host "  FAIL  $name (curl exit $LASTEXITCODE). Partial file kept for resume." -ForegroundColor Red
        Write-Host "        Check the file list at: $($info.url -replace '/resolve/main/.*$', '/tree/main')" -ForegroundColor Yellow
    }
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "All model files for pack '$Pack' are in place. Restart ComfyUI so it re-scans the folders." -ForegroundColor Green
} else {
    Write-Host "Some downloads failed: $($failed -join ', ')" -ForegroundColor Red
    Write-Host "Re-run this script to resume. If a file name has changed upstream, open the '/tree/main' link above," -ForegroundColor Yellow
    Write-Host "download the matching file manually and put it in ComfyUI\models\<folder>\ (see models.json)." -ForegroundColor Yellow
    exit 1
}
