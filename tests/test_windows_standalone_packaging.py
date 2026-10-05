from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-standalone.yml"
BUILD_SCRIPT = ROOT / "scripts" / "build_windows_standalone.ps1"
ENTRY_POINT = ROOT / "packaging" / "cleanroomx_desktop_entry.py"
ICON = ROOT / "packaging" / "windows" / "CleanroomX.ico"


def test_windows_standalone_workflow_pins_builder_and_bundles_bim() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'python-version: "3.12"' in workflow
    assert 'pip install -e ".[bim]"' in workflow
    assert 'pyinstaller==6.22.3' in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "CleanroomX-windows-x64.sha256" in workflow


def test_windows_standalone_build_is_windowed_onedir_and_smoke_checked() -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "--windowed" in script
    assert "--onedir" in script
    assert "--icon $iconPath" in script
    assert "--version-file $versionFile" in script
    assert "CleanroomX Engineering Workstation" in script
    assert "ProductVersion" in script
    assert ICON.is_file()
    assert ICON.stat().st_size > 0
    assert "--collect-data cleanroomx" in script
    assert "--collect-all ifcopenshell" in script
    assert "CleanroomX.exe" in script
    assert '-ArgumentList "--check"' in script


def test_frozen_entry_point_delegates_to_production_gui_main() -> None:
    entry = ENTRY_POINT.read_text(encoding="utf-8")

    assert "from cleanroomx.gui import main" in entry
    assert "raise SystemExit(main())" in entry
