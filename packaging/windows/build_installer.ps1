param(
    [switch]$SkipDependencyInstall,
    [switch]$BuildUpgradeFixture
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Find-InnoSetupCompiler {
    $candidates = @(
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

function Invoke-CleanroomXInnoBuild {
    param(
        [Parameter(Mandatory = $true)][string]$Compiler,
        [Parameter(Mandatory = $true)][string]$InstallerVersion,
        [Parameter(Mandatory = $true)][string]$FileVersion,
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string]$OutputDir,
        [Parameter(Mandatory = $true)][string]$IconPath,
        [Parameter(Mandatory = $true)][string]$OutputBaseFilename
    )

    $arguments = @(
        "/DAppVersion=$InstallerVersion",
        "/DAppFileVersion=$FileVersion",
        "/DSourceDir=$SourceDir",
        "/DOutputDir=$OutputDir",
        "/DAppIconPath=$IconPath",
        "/DOutputBaseFilename=$OutputBaseFilename",
        "$Root\packaging\windows\CleanroomX.iss"
    )
    & $Compiler @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE"
    }
}

Push-Location $Root
try {
    if (-not $SkipDependencyInstall) {
        python -m pip install --upgrade pip
        python -m pip install ".[release]"
        if ($LASTEXITCODE -ne 0) {
            throw "Release dependency installation failed with exit code $LASTEXITCODE"
        }
    }

    python -c "import ifcopenshell, importlib.metadata as m; print(m.version('ifcopenshell'))"
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned IfcOpenShell runtime is unavailable"
    }

    $version = (python -c "import cleanroomx; print(cleanroomx.__version__)").Trim()
    if (-not $version) {
        throw "Unable to determine CleanroomX version"
    }
    $fileVersion = (python -c "import re, cleanroomx; n=[int(x) for x in re.findall(r'\d+', cleanroomx.__version__)[:4]]; n += [0] * (4-len(n)); print('.'.join(str(x) for x in n))").Trim()

    python scripts/build_windows_resources.py --output-dir build/windows --version $version
    if ($LASTEXITCODE -ne 0) {
        throw "Windows resource generation failed with exit code $LASTEXITCODE"
    }

    $iscc = Find-InnoSetupCompiler
    if (-not $iscc) {
        throw "Inno Setup 7.1.0 compiler (ISCC.exe) was not found"
    }
    $innoVersion = (Get-Item $iscc).VersionInfo.ProductVersion
    if (-not $innoVersion.StartsWith("7.1.0")) {
        throw "Inno Setup 7.1.0 is required; found $innoVersion at $iscc"
    }

    Remove-Item -Recurse -Force "build\pyinstaller" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "dist\CleanroomX" -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "dist\installer" -ErrorAction SilentlyContinue

    $pyinstallerArgs = @(
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--noupx",
        "--name", "CleanroomX",
        "--paths", "$Root\src",
        "--icon", "$Root\build\windows\cleanroomx.ico",
        "--version-file", "$Root\build\windows\file_version_info.txt",
        "--collect-submodules", "cleanroomx",
        "--collect-data", "cleanroomx",
        "--collect-all", "ifcopenshell",
        "--distpath", "$Root\dist",
        "--workpath", "$Root\build\pyinstaller",
        "$Root\packaging\windows\cleanroomx_desktop.py"
    )
    python -m PyInstaller @pyinstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    $desktopExe = "$Root\dist\CleanroomX\CleanroomX.exe"
    if (-not (Test-Path $desktopExe)) {
        throw "PyInstaller did not produce $desktopExe"
    }

    $check = Start-Process -FilePath $desktopExe -ArgumentList @("--check") -Wait -PassThru
    if ($check.ExitCode -ne 0) {
        throw "Standalone CleanroomX --check failed with exit code $($check.ExitCode)"
    }
    $smoke = Start-Process -FilePath $desktopExe -ArgumentList @("--demo", "--smoke") -Wait -PassThru
    if ($smoke.ExitCode -ne 0) {
        throw "Standalone CleanroomX GUI smoke failed with exit code $($smoke.ExitCode)"
    }

    $sourceDir = "$Root\dist\CleanroomX"
    $outputDir = "$Root\dist\installer"
    $iconPath = "$Root\build\windows\cleanroomx.ico"
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

    if ($BuildUpgradeFixture) {
        $fixtureParams = @{
            Compiler = $iscc
            InstallerVersion = "0.102.1"
            FileVersion = "0.102.1.0"
            SourceDir = $sourceDir
            OutputDir = $outputDir
            IconPath = $iconPath
            OutputBaseFilename = "CleanroomX-upgrade-baseline-setup"
        }
        Invoke-CleanroomXInnoBuild @fixtureParams
    }

    $outputBase = "CleanroomX-$version-windows-x64-setup"
    $currentParams = @{
        Compiler = $iscc
        InstallerVersion = $version
        FileVersion = $fileVersion
        SourceDir = $sourceDir
        OutputDir = $outputDir
        IconPath = $iconPath
        OutputBaseFilename = $outputBase
    }
    Invoke-CleanroomXInnoBuild @currentParams

    $installer = Join-Path $outputDir "$outputBase.exe"
    if (-not (Test-Path $installer)) {
        throw "Inno Setup did not produce the expected CleanroomX installer: $installer"
    }
    Write-Host "CleanroomX installer: $installer"
}
finally {
    Pop-Location
}
