param(
    [switch]$SkipDependencyInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $Root
try {
    if (-not $SkipDependencyInstall) {
        python -m pip install --upgrade pip
        python -m pip install ".[release]"
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

    $isccCandidates = @(
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    $iscc = $isccCandidates | Select-Object -First 1
    if (-not $iscc) {
        throw "Inno Setup 6 compiler (ISCC.exe) was not found"
    }

    & $iscc "/DAppVersion=$version" "/DAppFileVersion=$fileVersion" "$Root\packaging\windows\CleanroomX.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup compilation failed with exit code $LASTEXITCODE"
    }

    $installer = Get-ChildItem "$Root\dist\installer\CleanroomX-*-windows-x64-setup.exe" |
        Sort-Object FullName |
        Select-Object -First 1
    if (-not $installer) {
        throw "Inno Setup did not produce the expected CleanroomX installer"
    }
    Write-Host "CleanroomX installer: $($installer.FullName)"
}
finally {
    Pop-Location
}
