import base64
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-standalone.yml"
BUILD_SCRIPT = ROOT / "scripts" / "build_windows_standalone.ps1"
ENTRY_POINT = ROOT / "packaging" / "cleanroomx_desktop_entry.py"
ICON_PAYLOAD = ROOT / "packaging" / "windows" / "CleanroomX.ico.b64"
VERSION_SCRIPT = ROOT / "scripts" / "write_windows_version_info.py"


def test_windows_standalone_workflow_pins_builder_and_bundles_bim() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'python-version: "3.12"' in workflow
    assert 'pip install -e ".[bim]"' in workflow
    assert 'pyinstaller==6.22.3' in workflow
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in workflow
    assert "CleanroomX-windows-x64.sha256" in workflow


def test_windows_standalone_build_is_windowed_onedir_branded_and_smoke_checked() -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "--windowed" in script
    assert "--onedir" in script
    assert "--collect-data cleanroomx" in script
    assert "--collect-all ifcopenshell" in script
    assert "[Convert]::FromBase64String" in script
    assert "--icon $iconPath" in script
    assert "--version-file $versionFile" in script
    assert "CleanroomX Engineering Workstation" in script
    assert "ProductVersion" in script
    assert "CleanroomX.exe" in script
    assert '-ArgumentList "--check"' in script


def test_windows_icon_payload_decodes_to_a_real_multi_image_ico() -> None:
    payload = base64.b64decode(ICON_PAYLOAD.read_text(encoding="ascii").strip(), validate=True)

    assert payload[:4] == b"\x00\x00\x01\x00"
    assert int.from_bytes(payload[4:6], "little") >= 4
    assert len(payload) > 1024


def test_windows_version_info_is_generated_from_project_version(tmp_path: Path) -> None:
    output = tmp_path / "CleanroomX.version.txt"
    subprocess.run(
        [sys.executable, str(VERSION_SCRIPT), "--output", str(output)],
        cwd=ROOT,
        check=True,
    )

    generated = output.read_text(encoding="utf-8")
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]

    release = version.split(".")
    patch_digits = []
    for char in release[2]:
        if not char.isdigit():
            break
        patch_digits.append(char)
    expected_tuple = (
        int(release[0]),
        int(release[1]),
        int("".join(patch_digits)),
        0,
    )
    tuple_text = ", ".join(str(value) for value in expected_tuple)

    assert f"filevers=({tuple_text})" in generated
    assert f"StringStruct('ProductVersion', '{version}')" in generated
    assert "StringStruct('ProductName', 'CleanroomX')" in generated
    assert (
        "StringStruct('FileDescription', 'CleanroomX Engineering Workstation')"
        in generated
    )


def test_frozen_entry_point_delegates_to_production_gui_main() -> None:
    entry = ENTRY_POINT.read_text(encoding="utf-8")

    assert "from cleanroomx.gui import main" in entry
    assert "raise SystemExit(main())" in entry
