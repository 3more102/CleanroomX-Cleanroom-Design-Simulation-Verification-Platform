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
$uninstallSubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall"

function Invoke-Installer([string]$Path) {
    $arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$installDir")
    $process = Start-Process -FilePath $Path -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Installer failed ($Path) with exit code $($process.ExitCode)"
    }
}

function Find-CleanroomXUninstallEntry {
    foreach ($hive in @(
        [Microsoft.Win32.RegistryHive]::CurrentUser,
        [Microsoft.Win32.RegistryHive]::LocalMachine
    )) {
        foreach ($view in @(
            [Microsoft.Win32.RegistryView]::Registry64,
            [Microsoft.Win32.RegistryView]::Registry32
        )) {
            $baseKey = $null
            $uninstallKey = $null
            try {
                $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
                $uninstallKey = $baseKey.OpenSubKey($uninstallSubkey)
                if ($null -eq $uninstallKey) {
                    continue
                }
                foreach ($name in $uninstallKey.GetSubKeyNames()) {
                    $entryKey = $null
                    try {
                        $entryKey = $uninstallKey.OpenSubKey($name)
                        if ($null -eq $entryKey -or $entryKey.GetValue("DisplayName") -ne "CleanroomX") {
                            continue
                        }
                        return [pscustomobject]@{
                            DisplayVersion = [string]$entryKey.GetValue("DisplayVersion")
                            UninstallString = [string]$entryKey.GetValue("UninstallString")
                            RegistryHive = $hive.ToString()
                            RegistryView = $view.ToString()
                            RegistryKey = $name
                        }
                    }
                    finally {
                        if ($null -ne $entryKey) { $entryKey.Dispose() }
                    }
                }
            }
            finally {
                if ($null -ne $uninstallKey) { $uninstallKey.Dispose() }
                if ($null -ne $baseKey) { $baseKey.Dispose() }
            }
        }
    }
    return $null
}

function Get-CleanroomXUninstallEntry {
    $entry = Find-CleanroomXUninstallEntry
    if (-not $entry) {
        throw "CleanroomX uninstall registration was not found in either 32-bit or 64-bit registry view"
    }
    return $entry
}

function Invoke-CleanroomXCheck([string]$ExePath, [string]$Label) {
    $process = Start-Process -FilePath $ExePath -ArgumentList "--check" -PassThru
    if (-not $process.WaitForExit(30000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "$Label --check did not exit within 30 seconds"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) {
        throw "$Label --check failed with exit code $($process.ExitCode)"
    }
}

$existing = Find-CleanroomXUninstallEntry
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
Invoke-CleanroomXCheck $exe "Installed baseline"

Invoke-Installer $CurrentInstaller
$currentEntry = Get-CleanroomXUninstallEntry
if ($currentEntry.DisplayVersion -ne $currentVersion) {
    throw "Upgrade did not publish current DisplayVersion: $($currentEntry.DisplayVersion)"
}
Invoke-CleanroomXCheck $exe "Installed upgraded CleanroomX"

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
$remaining = Find-CleanroomXUninstallEntry
if ($remaining) {
    throw "CleanroomX uninstall registration remains after uninstall"
}

Write-Host "Windows installer lifecycle: PASS (install -> launch -> upgrade -> launch -> uninstall)"
