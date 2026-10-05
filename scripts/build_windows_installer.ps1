param(
    [switch]$SkipStandaloneBuild,
    [string]$AppVersion = "",
    [string]$FileVersion = "",
    [string]$OutputBaseFilename = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

if (-not $SkipStandaloneBuild) {
    & (Join-Path $repoRoot "scripts\build_windows_standalone.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Standalone build failed with exit code $LASTEXITCODE"
    }
}

$standaloneExe = Join-Path $repoRoot "dist\windows-standalone\CleanroomX\CleanroomX.exe"
if (-not (Test-Path $standaloneExe -PathType Leaf)) {
    throw "Standalone build is required before installer packaging: $standaloneExe"
}

if (-not $AppVersion) {
    $pyproject = Get-Content -Raw (Join-Path $repoRoot "pyproject.toml")
    if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"\s*$') {
        throw "Unable to read project version from pyproject.toml"
    }
    $AppVersion = $Matches[1]
}

if ($AppVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9._-]+)?
    $safeVersion = $AppVersion -replace '[^A-Za-z0-9._-]', '-'
    $OutputBaseFilename = "CleanroomX-Setup-$safeVersion-x64"
}
if ($OutputBaseFilename -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Installer output filename contains unsupported characters: $OutputBaseFilename"
}

$isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$iscc = if ($isccCommand) {
    $isccCommand.Source
} else {
    Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc -PathType Leaf)) {
    throw "Inno Setup compiler not found. Expected ISCC.exe on PATH or under Program Files (x86)."
}

$outputDir = Join-Path $repoRoot "dist\windows-installer"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$scriptPath = Join-Path $repoRoot "packaging\windows\CleanroomX.iss"
$scriptDir = Split-Path -Parent $scriptPath

Push-Location $scriptDir
try {
    & $iscc "/DMyAppVersion=$AppVersion" "/DMyFileVersion=$FileVersion" "/DMyOutputBaseFilename=$OutputBaseFilename" $scriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compiler failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$installer = Join-Path $outputDir "$OutputBaseFilename.exe"
if (-not (Test-Path $installer -PathType Leaf)) {
    throw "Expected installer was not produced: $installer"
}

$hash = (Get-FileHash -Algorithm SHA256 $installer).Hash.ToLowerInvariant()
"$hash  $OutputBaseFilename.exe" | Set-Content -Encoding ascii "$installer.sha256"

Write-Host "CleanroomX installer built: $installer"
Write-Host "SHA-256: $hash"
) {
    throw "Installer version contains unsupported characters: $AppVersion"
}

if (-not $FileVersion) {
    if ($AppVersion -notmatch '^([0-9]+)\.([0-9]+)\.([0-9]+)') {
        throw "Installer version must begin with major.minor.patch: $AppVersion"
    }
    $FileVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"
}
if ($FileVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+
    $safeVersion = $AppVersion -replace '[^A-Za-z0-9._-]', '-'
    $OutputBaseFilename = "CleanroomX-Setup-$safeVersion-x64"
}
if ($OutputBaseFilename -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Installer output filename contains unsupported characters: $OutputBaseFilename"
}

$isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$iscc = if ($isccCommand) {
    $isccCommand.Source
} else {
    Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc -PathType Leaf)) {
    throw "Inno Setup compiler not found. Expected ISCC.exe on PATH or under Program Files (x86)."
}

$outputDir = Join-Path $repoRoot "dist\windows-installer"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$scriptPath = Join-Path $repoRoot "packaging\windows\CleanroomX.iss"
$scriptDir = Split-Path -Parent $scriptPath

Push-Location $scriptDir
try {
    & $iscc "/DMyAppVersion=$AppVersion" "/DMyOutputBaseFilename=$OutputBaseFilename" $scriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compiler failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$installer = Join-Path $outputDir "$OutputBaseFilename.exe"
if (-not (Test-Path $installer -PathType Leaf)) {
    throw "Expected installer was not produced: $installer"
}

$hash = (Get-FileHash -Algorithm SHA256 $installer).Hash.ToLowerInvariant()
"$hash  $OutputBaseFilename.exe" | Set-Content -Encoding ascii "$installer.sha256"

Write-Host "CleanroomX installer built: $installer"
Write-Host "SHA-256: $hash"
) {
    throw "Installer file version must be four dot-separated integers: $FileVersion"
}

if (-not $OutputBaseFilename) {
    $safeVersion = $AppVersion -replace '[^A-Za-z0-9._-]', '-'
    $OutputBaseFilename = "CleanroomX-Setup-$safeVersion-x64"
}
if ($OutputBaseFilename -notmatch '^[A-Za-z0-9._-]+$') {
    throw "Installer output filename contains unsupported characters: $OutputBaseFilename"
}

$isccCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$iscc = if ($isccCommand) {
    $isccCommand.Source
} else {
    Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $iscc -PathType Leaf)) {
    throw "Inno Setup compiler not found. Expected ISCC.exe on PATH or under Program Files (x86)."
}

$outputDir = Join-Path $repoRoot "dist\windows-installer"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$scriptPath = Join-Path $repoRoot "packaging\windows\CleanroomX.iss"
$scriptDir = Split-Path -Parent $scriptPath

Push-Location $scriptDir
try {
    & $iscc "/DMyAppVersion=$AppVersion" "/DMyOutputBaseFilename=$OutputBaseFilename" $scriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compiler failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$installer = Join-Path $outputDir "$OutputBaseFilename.exe"
if (-not (Test-Path $installer -PathType Leaf)) {
    throw "Expected installer was not produced: $installer"
}

$hash = (Get-FileHash -Algorithm SHA256 $installer).Hash.ToLowerInvariant()
"$hash  $OutputBaseFilename.exe" | Set-Content -Encoding ascii "$installer.sha256"

Write-Host "CleanroomX installer built: $installer"
Write-Host "SHA-256: $hash"
