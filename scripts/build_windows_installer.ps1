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

if ($AppVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(?:[A-Za-z0-9._-]+)?$') {
    throw "Installer version contains unsupported characters: $AppVersion"
}

if (-not $FileVersion) {
    if ($AppVersion -notmatch '^([0-9]+)\.([0-9]+)\.([0-9]+)') {
        throw "Installer version must begin with major.minor.patch: $AppVersion"
    }
    $FileVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"
}
if ($FileVersion -notmatch '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$') {
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

# Inno Setup still encounters legacy path-resolution limits on deeply nested
# native dependency trees. Stage the application under the user's short temp
# path so installer creation does not depend on checkout-directory length.
$stageRoot = Join-Path $env:TEMP "cleanroomx-installer-$PID"
$stageSource = Join-Path $stageRoot "app"
$stageOutput = Join-Path $stageRoot "out"
Remove-Item -Recurse -Force $stageRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stageSource, $stageOutput | Out-Null

try {
    & robocopy.exe (Split-Path -Parent $standaloneExe) $stageSource /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
    $robocopyExit = $LASTEXITCODE
    if ($robocopyExit -gt 7) {
        throw "Installer staging copy failed with robocopy exit code $robocopyExit"
    }

    Push-Location $scriptDir
    try {
        & $iscc "/DMyAppVersion=$AppVersion" "/DMyFileVersion=$FileVersion" "/DMyOutputBaseFilename=$OutputBaseFilename" "/DMySourceDir=$stageSource" "/DMyOutputDir=$stageOutput" $scriptPath
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup compiler failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }

    $stagedInstaller = Join-Path $stageOutput "$OutputBaseFilename.exe"
    if (-not (Test-Path $stagedInstaller -PathType Leaf)) {
        throw "Expected staged installer was not produced: $stagedInstaller"
    }
    $installer = Join-Path $outputDir "$OutputBaseFilename.exe"
    Copy-Item -Force $stagedInstaller $installer
}
finally {
    Remove-Item -Recurse -Force $stageRoot -ErrorAction SilentlyContinue
}

if (-not (Test-Path $installer -PathType Leaf)) {
    throw "Expected installer was not published: $installer"
}

$hash = (Get-FileHash -Algorithm SHA256 $installer).Hash.ToLowerInvariant()
"$hash  $OutputBaseFilename.exe" | Set-Content -Encoding ascii "$installer.sha256"

Write-Host "CleanroomX installer built: $installer"
Write-Host "SHA-256: $hash"
