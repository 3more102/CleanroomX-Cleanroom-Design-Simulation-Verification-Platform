param(
    [string]$CurrentInstaller = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

$pyproject = Get-Content -Raw (Join-Path $repoRoot "pyproject.toml")
if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"\s*$') {
    throw "Unable to read project version from pyproject.toml"
}
$currentVersion = $Matches[1]

$baselineVersion = "0.102.999"
$baselineName = "CleanroomX-Setup-lifecycle-baseline-x64"
& (Join-Path $repoRoot "scripts\build_windows_installer.ps1") -SkipStandaloneBuild -AppVersion $baselineVersion -OutputBaseFilename $baselineName
if ($LASTEXITCODE -ne 0) {
    throw "Baseline installer build failed with exit code $LASTEXITCODE"
}
$baselineInstaller = Join-Path $repoRoot "dist\windows-installer\$baselineName.exe"

if (-not $CurrentInstaller) {
    $safeVersion = $currentVersion -replace '[^A-Za-z0-9._-]', '-'
    $CurrentInstaller = Join-Path $repoRoot "dist\windows-installer\CleanroomX-Setup-$safeVersion-x64.exe"
}
$CurrentInstaller = [System.IO.Path]::GetFullPath($CurrentInstaller)
if (-not (Test-Path $CurrentInstaller -PathType Leaf)) {
    throw "Current installer not found: $CurrentInstaller"
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\CleanroomX"
$uninstallRoot = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall"

function Invoke-Installer([string]$Path) {
    $arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$installDir")
    $process = Start-Process -FilePath $Path -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Installer failed ($Path) with exit code $($process.ExitCode)"
    }
}

function Get-CleanroomXUninstallEntry {
    $entry = Get-ChildItem $uninstallRoot -ErrorAction SilentlyContinue |
        Get-ItemProperty |
        Where-Object { $_.DisplayName -eq "CleanroomX" } |
        Select-Object -First 1
    if (-not $entry) {
        throw "CleanroomX uninstall registration was not found"
    }
    return $entry
}

$existing = Get-ChildItem $uninstallRoot -ErrorAction SilentlyContinue |
    Get-ItemProperty |
    Where-Object { $_.DisplayName -eq "CleanroomX" } |
    Select-Object -First 1
if ($existing -and (Test-Path (Join-Path $installDir "unins000.exe"))) {
    $cleanup = Start-Process -FilePath (Join-Path $installDir "unins000.exe") -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
    if ($cleanup.ExitCode -ne 0) {
        throw "Pre-test uninstall cleanup failed with exit code $($cleanup.ExitCode)"
    }
}

Invoke-Installer $baselineInstaller
$baselineEntry = Get-CleanroomXUninstallEntry
if ($baselineEntry.DisplayVersion -ne $baselineVersion) {
    throw "Baseline DisplayVersion mismatch: $($baselineEntry.DisplayVersion)"
}
$exe = Join-Path $installDir "CleanroomX.exe"
if (-not (Test-Path $exe -PathType Leaf)) {
    throw "Installed baseline executable missing: $exe"
}
$baselineCheck = Start-Process -FilePath $exe -ArgumentList "--check" -Wait -PassThru
if ($baselineCheck.ExitCode -ne 0) {
    throw "Installed baseline --check failed with exit code $($baselineCheck.ExitCode)"
}

$baselineSmoke = Start-Process -FilePath $exe -ArgumentList @("--demo", "--smoke") -Wait -PassThru
if ($baselineSmoke.ExitCode -ne 0) {
    throw "Installed baseline GUI smoke failed with exit code $($baselineSmoke.ExitCode)"
}

Invoke-Installer $CurrentInstaller
$currentEntry = Get-CleanroomXUninstallEntry
if ($currentEntry.DisplayVersion -ne $currentVersion) {
    throw "Upgrade did not publish current DisplayVersion: $($currentEntry.DisplayVersion)"
}
$currentCheck = Start-Process -FilePath $exe -ArgumentList "--check" -Wait -PassThru
if ($currentCheck.ExitCode -ne 0) {
    throw "Installed upgraded CleanroomX --check failed with exit code $($currentCheck.ExitCode)"
}

$currentSmoke = Start-Process -FilePath $exe -ArgumentList @("--demo", "--smoke") -Wait -PassThru
if ($currentSmoke.ExitCode -ne 0) {
    throw "Installed upgraded GUI smoke failed with exit code $($currentSmoke.ExitCode)"
}

$uninstaller = Join-Path $installDir "unins000.exe"
if (-not (Test-Path $uninstaller -PathType Leaf)) {
    throw "Registered uninstaller was not created: $uninstaller"
}
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
if ($uninstall.ExitCode -ne 0) {
    throw "CleanroomX uninstall failed with exit code $($uninstall.ExitCode)"
}

Start-Sleep -Milliseconds 500
if (Test-Path $exe -PathType Leaf) {
    throw "CleanroomX executable remains after uninstall: $exe"
}
$remaining = Get-ChildItem $uninstallRoot -ErrorAction SilentlyContinue |
    Get-ItemProperty |
    Where-Object { $_.DisplayName -eq "CleanroomX" } |
    Select-Object -First 1
if ($remaining) {
    throw "CleanroomX uninstall registration remains after uninstall"
}

Write-Host "Windows installer lifecycle: PASS (install -> check -> GUI smoke -> upgrade -> check -> GUI smoke -> uninstall)"
