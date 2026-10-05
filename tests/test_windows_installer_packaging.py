from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inno_installer_is_per_user_registered_branded_and_self_contained():
    text = (ROOT / "packaging" / "windows" / "CleanroomX.iss").read_text(
        encoding="utf-8"
    )

    assert "AppId={{8F32C7AA-9A76-4C56-82EE-CE29DA3587E1}" in text
    assert "PrivilegesRequired=lowest" in text
    assert "DefaultDirName={localappdata}\\Programs\\CleanroomX" in text
    assert "SetupIconFile=CleanroomX.ico" in text
    assert "UninstallDisplayIcon={app}\\CleanroomX.exe" in text
    assert "VersionInfoCompany=CleanroomX contributors" in text
    assert "VersionInfoDescription=CleanroomX Engineering Workstation Installer" in text
    assert "VersionInfoProductName=CleanroomX" in text
    assert "VersionInfoVersion={#MyFileVersion}" in text
    assert "VersionInfoProductVersion={#MyFileVersion}" in text
    assert "VersionInfoTextVersion={#MyAppVersion}" in text
    assert "VersionInfoProductTextVersion={#MyAppVersion}" in text
    assert 'Source: "..\\..\\dist\\windows-standalone\\CleanroomX\\*"' in text
    assert 'Filename: "{app}\\CleanroomX.exe"' in text


def test_installer_build_is_versioned_and_hashes_release_artifact():
    text = (ROOT / "scripts" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Get-Content -Raw (Join-Path $repoRoot "pyproject.toml")' in text
    assert "Inno Setup compiler not found" in text
    assert "Get-FileHash -Algorithm SHA256" in text
    assert '"/DMyFileVersion=$FileVersion"' in text
    assert "Installer file version must be four dot-separated integers" in text
    assert "CleanroomX-Setup-$safeVersion-x64" in text


def test_installer_build_has_one_compilation_path_and_closed_version_guards():
    text = (ROOT / "scripts" / "build_windows_installer.ps1").read_text(
        encoding="utf-8"
    )

    assert text.count('$isccCommand = Get-Command "ISCC.exe"') == 1
    assert text.count('& $iscc "/DMyAppVersion=$AppVersion"') == 1
    assert (
        "if ($AppVersion -notmatch "
        "'^[0-9]+\\.[0-9]+\\.[0-9]+(?:[A-Za-z0-9._-]+)?$') {"
        in text
    )
    assert (
        "if ($FileVersion -notmatch "
        "'^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$') {"
        in text
    )


def test_installer_lifecycle_gate_covers_install_upgrade_launch_and_uninstall():
    text = (ROOT / "scripts" / "test_windows_installer_lifecycle.ps1").read_text(
        encoding="utf-8"
    )
    workflow = (
        ROOT / ".github" / "workflows" / "windows-installer.yml"
    ).read_text(encoding="utf-8")

    assert 'Start-Process -FilePath $exe -ArgumentList "--check"' in text
    assert '$baselineVersion = "0.102.999"' in text
    assert "DisplayVersion" in text
    assert "unins000.exe" in text
    assert "install -> launch -> upgrade -> launch -> uninstall" in text

    assert "runs-on: windows-2025" in workflow
    assert 'pip install -e ".[release]"' in workflow
    assert 'pip install -e ".[bim]"' not in workflow
    assert "build_windows_standalone.ps1" in workflow
    assert "build_windows_installer.ps1" in workflow
    assert "test_windows_installer_lifecycle.ps1" in workflow
    assert "CleanroomX-windows-installer-x64" in workflow
