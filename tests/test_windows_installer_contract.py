from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import tomllib


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_SCRIPT = ROOT / "scripts" / "build_windows_resources.py"


def _resource_module():
    spec = importlib.util.spec_from_file_location("build_windows_resources", RESOURCE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_release_extra_is_pinned() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["optional-dependencies"]["release"] == [
        "pyinstaller==6.22.3",
        "ifcopenshell==0.9.0",
    ]


def test_windows_resource_builder_emits_multisize_icon_and_version_metadata(tmp_path) -> None:
    module = _resource_module()
    icon, version_file = module.build_resources(tmp_path, version="0.103.0.dev7")

    raw = icon.read_bytes()
    reserved, icon_type, count = struct.unpack("<HHH", raw[:6])
    assert (reserved, icon_type, count) == (0, 1, 6)
    assert len(raw) > 1000

    text = version_file.read_text(encoding="utf-8")
    assert "CleanroomX Engineering Workstation" in text
    assert "FileVersion', '0.103.0.dev7'" in text
    assert "filevers=(0, 103, 0, 7)" in text


def test_inno_installer_contract_is_per_user_upgradeable_and_uninstallable() -> None:
    script = (ROOT / "packaging" / "windows" / "CleanroomX.iss").read_text(
        encoding="utf-8"
    )

    assert "AppId={{8A609071-4521-4B60-B8D2-ACAD5BF53A72}" in script
    assert "DefaultDirName={localappdata}\\Programs\\CleanroomX" in script
    assert "PrivilegesRequired=lowest" in script
    assert "SetupArchitecture=x64" in script
    assert "Source: \"{#SourceDir}\\*\"" in script
    assert "SetupIconFile={#AppIconPath}" in script
    assert "UninstallDisplayIcon={app}\\{#AppExeName}" in script
    assert "VersionInfoVersion={#AppFileVersion}" in script
    assert "VersionInfoProductVersion={#AppFileVersion}" in script


def test_windows_build_script_pins_inno7_and_builds_upgrade_fixture() -> None:
    script = (
        ROOT / "packaging" / "windows" / "build_installer.ps1"
    ).read_text(encoding="utf-8")

    assert "[switch]$BuildUpgradeFixture" in script
    assert "Inno Setup 7.1.0 is required" in script
    assert "CleanroomX-upgrade-baseline-setup" in script
    assert '"--collect-submodules", "cleanroomx"' in script
    assert '"--collect-all", "ifcopenshell"' in script
    assert "import ifcopenshell, importlib.metadata as m" in script


def test_ci_requires_windows_installer_upgrade_lifecycle_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "windows-installer-smoke:" in workflow
    assert "--id JRSoftware.InnoSetup.7 --version 7.1.0" in workflow
    assert "Build standalone Windows installer and upgrade fixture" in workflow
    assert "Install, upgrade, launch, and uninstall on clean runner path" in workflow
    assert "In-place installer upgrade failed" in workflow
    assert "unins000.exe" in workflow
    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        in workflow
    )

    required = workflow.split("required-ci:", 1)[1]
    assert "- windows-installer-smoke" in required
    assert "WINDOWS_INSTALLER_RESULT:" in required
    assert 'test "${WINDOWS_INSTALLER_RESULT}" = "success"' in required
