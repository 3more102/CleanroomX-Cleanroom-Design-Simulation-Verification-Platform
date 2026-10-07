$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

$buildRoot = Join-Path $repoRoot "build\pyinstaller"
$distRoot = Join-Path $repoRoot "dist\windows-standalone"
$entryPoint = Join-Path $repoRoot "packaging\cleanroomx_desktop_entry.py"
$iconPath = Join-Path $repoRoot "packaging\windows\CleanroomX.ico"
$versionFile = Join-Path $buildRoot "CleanroomX.version.txt"
$hookDir = Join-Path $repoRoot "packaging\\pyinstaller_hooks"
$ifcHook = Join-Path $hookDir "hook-ifcopenshell.py"

if (-not (Test-Path $iconPath -PathType Leaf)) {
    throw "Windows application icon is missing: $iconPath"
}
if (-not (Test-Path $ifcHook -PathType Leaf)) {
    throw "IfcOpenShell PyInstaller hook is missing: $ifcHook"
}

Remove-Item -Recurse -Force $buildRoot -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $distRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null

python (Join-Path $repoRoot "scripts\write_windows_version_info.py") --output $versionFile
if ($LASTEXITCODE -ne 0) {
    throw "Windows version metadata generation failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path $versionFile -PathType Leaf)) {
    throw "Expected Windows version metadata was not produced: $versionFile"
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name CleanroomX `
    --icon $iconPath `
    --version-file $versionFile `
    --paths (Join-Path $repoRoot "src") `
    --collect-data cleanroomx `
    --collect-submodules cleanroomx `
    --additional-hooks-dir $hookDir `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $buildRoot `
    $entryPoint

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$exe = Join-Path $distRoot "CleanroomX\CleanroomX.exe"
if (-not (Test-Path $exe -PathType Leaf)) {
    throw "Expected standalone executable was not produced: $exe"
}

$projectVersion = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or -not $projectVersion) {
    throw "Unable to resolve project version for executable metadata validation"
}
$projectVersion = $projectVersion.Trim()
$versionInfo = (Get-Item $exe).VersionInfo
if ($versionInfo.ProductName -ne "CleanroomX") {
    throw "Frozen executable ProductName mismatch: $($versionInfo.ProductName)"
}
if ($versionInfo.ProductVersion -ne $projectVersion) {
    throw "Frozen executable ProductVersion mismatch: $($versionInfo.ProductVersion)"
}
if ($versionInfo.FileDescription -ne "CleanroomX Engineering Workstation") {
    throw "Frozen executable FileDescription mismatch: $($versionInfo.FileDescription)"
}

$checkErrorLog = Join-Path $buildRoot "frozen-check-error.log"
Remove-Item -Force $checkErrorLog -ErrorAction SilentlyContinue
$previousCheckErrorFile = $env:CLEANROOMX_CHECK_ERROR_FILE
$env:CLEANROOMX_CHECK_ERROR_FILE = $checkErrorLog
try {
    $process = Start-Process -FilePath $exe -ArgumentList "--check" -PassThru
    if (-not $process.WaitForExit(30000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "Frozen CleanroomX --check did not exit within 30 seconds"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) {
        if (Test-Path $checkErrorLog -PathType Leaf) {
            Write-Host "Frozen CleanroomX --check traceback:"
            Get-Content $checkErrorLog | Write-Host
        }
        throw "Frozen CleanroomX --check failed with exit code $($process.ExitCode)"
    }
}
finally {
    if ($null -eq $previousCheckErrorFile) {
        Remove-Item Env:CLEANROOMX_CHECK_ERROR_FILE -ErrorAction SilentlyContinue
    } else {
        $env:CLEANROOMX_CHECK_ERROR_FILE = $previousCheckErrorFile
    }
}

Write-Host "Standalone CleanroomX executable validated: $exe"
Write-Host "Windows product metadata validated: CleanroomX $projectVersion"
