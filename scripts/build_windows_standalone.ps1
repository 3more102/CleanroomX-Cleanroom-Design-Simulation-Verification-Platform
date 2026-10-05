$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

$buildRoot = Join-Path $repoRoot "build\pyinstaller"
$distRoot = Join-Path $repoRoot "dist\windows-standalone"
$entryPoint = Join-Path $repoRoot "packaging\cleanroomx_desktop_entry.py"

Remove-Item -Recurse -Force $buildRoot -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $distRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name CleanroomX `
    --paths (Join-Path $repoRoot "src") `
    --collect-data cleanroomx `
    --collect-all ifcopenshell `
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

$process = Start-Process -FilePath $exe -ArgumentList "--check" -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Frozen CleanroomX --check failed with exit code $($process.ExitCode)"
}

Write-Host "Standalone CleanroomX executable validated: $exe"
