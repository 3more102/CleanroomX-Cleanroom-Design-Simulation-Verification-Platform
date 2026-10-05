$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

$buildRoot = Join-Path $repoRoot "build\pyinstaller"
$distRoot = Join-Path $repoRoot "dist\windows-standalone"
$entryPoint = Join-Path $repoRoot "packaging\cleanroomx_desktop_entry.py"
$iconPath = Join-Path $repoRoot "packaging\windows\CleanroomX.ico"
$versionFile = Join-Path $buildRoot "CleanroomX.version.txt"

if (-not (Test-Path $iconPath -PathType Leaf)) {
    throw "CleanroomX application icon is missing: $iconPath"
}

Remove-Item -Recurse -Force $buildRoot -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $distRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null

$pyproject = Get-Content -Raw (Join-Path $repoRoot "pyproject.toml")
if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"\s*$') {
    throw "Unable to read project version from pyproject.toml"
}
$packageVersion = $Matches[1]
if ($packageVersion -notmatch '^(\d+)\.(\d+)\.(\d+)') {
    throw "CleanroomX package version is not semantic-version compatible: $packageVersion"
}
$major = [int]$Matches[1]
$minor = [int]$Matches[2]
$patch = [int]$Matches[3]
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($major, $minor, $patch, 0),
    prodvers=($major, $minor, $patch, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'CleanroomX contributors'),
          StringStruct('FileDescription', 'CleanroomX Engineering Workstation'),
          StringStruct('FileVersion', '$packageVersion'),
          StringStruct('InternalName', 'CleanroomX'),
          StringStruct('OriginalFilename', 'CleanroomX.exe'),
          StringStruct('ProductName', 'CleanroomX'),
          StringStruct('ProductVersion', '$packageVersion')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -Path $versionFile -Value $versionInfo -Encoding ascii

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
