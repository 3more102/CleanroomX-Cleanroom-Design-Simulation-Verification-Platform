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

$process = Start-Process -FilePath $exe -ArgumentList "--check" -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Frozen CleanroomX --check failed with exit code $($process.ExitCode)"
}

Write-Host "Standalone CleanroomX executable validated: $exe"
Write-Host "Windows product metadata validated: CleanroomX $projectVersion"
