# Publish original CleanroomX multiroom CFD screenshots, their README gallery,
# and verification code from the reviewed ChatGPT ZIP archive.
# This helper does NOT replace or resize the original PNGs.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ZipPath,
    [switch]$Push
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$zip = (Resolve-Path -LiteralPath $ZipPath -ErrorAction Stop).Path
if ([IO.Path]::GetExtension($zip).ToLowerInvariant() -ne '.zip') {
    throw "Expected the original CleanroomX gallery ZIP: $zip"
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ("cleanroomx-gallery-" + [guid]::NewGuid().ToString('N'))
New-Item -Path $temp -ItemType Directory -Force | Out-Null
try {
    Expand-Archive -LiteralPath $zip -DestinationPath $temp -Force
    $installer = Join-Path $temp 'Install-CleanroomX-Gallery.ps1'
    if (-not (Test-Path -LiteralPath $installer)) {
        $installer = Join-Path $temp 'CleanroomX_Multiroom_CFD_GitHub_Package\Install-CleanroomX-Gallery.ps1'
    }
    if (-not (Test-Path -LiteralPath $installer)) {
        throw "ZIP does not contain Install-CleanroomX-Gallery.ps1"
    }
    & $installer -RepoPath $repoRoot -ExpectedBranch 'feat/doors-5pa-ceiling-downflow-demo-20261020' -Push:$Push
    if (-not $?) { throw 'CleanroomX gallery installer failed.' }
    $validator = Join-Path $repoRoot 'tools\validate_multiroom_cfd_gallery.py'
    if (Test-Path -LiteralPath $validator) {
        & python $validator
        if ($LASTEXITCODE -ne 0) { throw "Gallery validation failed ($LASTEXITCODE)." }
    }
} finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
