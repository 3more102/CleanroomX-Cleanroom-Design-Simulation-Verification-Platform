from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "packaging" / "windows" / "CleanroomX.iss"
WORKFLOW = ROOT / ".github" / "workflows" / "windows-installer.yml"


def test_windows_installer_has_stable_upgrade_identity_and_uninstaller() -> None:
    script = INSTALLER.read_text(encoding="utf-8")

    assert "AppId={{8A609071-4521-4B60-B8D2-ACAD5BF53A72}" in script
    assert "PrivilegesRequired=lowest" in script
    assert "DefaultDirName={localappdata}\\Programs\\CleanroomX" in script
    assert "SetupArchitecture=x64" in script
    assert "UninstallDisplayIcon={app}\\CleanroomX.exe" in script
    assert 'Filename: "{app}\\CleanroomX.exe"' in script


def test_windows_installer_gate_is_reproducibly_pinned_and_exercises_lifecycle() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '"pyinstaller==6.22.3"' in workflow
    assert '"ifcopenshell==0.9.0"' in workflow
    assert "--version 7.1.0" in workflow
    assert "CleanroomX-Baseline-Setup" in workflow
    assert "In-place upgrade failed" in workflow
    assert "unins000.exe" in workflow
    assert "--demo --smoke" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        in workflow
    )
