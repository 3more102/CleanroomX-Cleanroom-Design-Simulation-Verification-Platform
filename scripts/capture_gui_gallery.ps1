# Capture a genuine high-resolution CleanroomX GUI gallery on Windows.
# Run this script by full path from any working directory; the script finds its repo.
[CmdletBinding()]
param(
    [ValidatePattern('^\d{4}x\d{3,4}$')]
    [string]$Size = '1920x1080',
    [ValidateSet('light', 'dark', 'both')]
    [string]$Theme = 'both',
    [switch]$NoOpen
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }
$themes = if ($Theme -eq 'both') { @('light', 'dark') } else { @($Theme) }
Push-Location -LiteralPath $root
try {
    & $python 'tools/capture_gui_screenshots.py' '--output' 'docs/screenshots' '--size' $Size '--themes' @themes
    if ($LASTEXITCODE -ne 0) {
        throw "Screenshot capture failed (exit $LASTEXITCODE). Check Python dependencies and desktop resolution."
    }
    & $python 'tools/verify_gui_screenshots.py' '--input' 'docs/screenshots'
    if ($LASTEXITCODE -ne 0) {
        throw "Screenshot verification failed (exit $LASTEXITCODE). Do not publish these captures."
    }
    $gallery = Join-Path $root 'docs\screenshots\gallery.html'
    Write-Host "Verified GUI gallery: $gallery"
    if (-not $NoOpen) {
        Start-Process -FilePath $gallery
    }
}
finally {
    Pop-Location
}
