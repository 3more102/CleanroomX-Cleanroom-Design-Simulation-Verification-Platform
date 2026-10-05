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


def test_inno_installer_contract_is_per_user_and_uninstallable() -> None:
    script = (ROOT / "packaging" / "windows" / "CleanroomX.iss").read_text(encoding="utf-8")
    assert "DefaultDirName={localappdata}\\Programs\\CleanroomX" in script
    assert "PrivilegesRequired=lowest" in script
    assert "UninstallDisplayIcon={app}\\{#AppExeName}" in script
    assert 'Source: "..\\..\\dist\\CleanroomX\\*"' in script
    assert "SetupIconFile=..\\..\\build\\windows\\cleanroomx.ico" in script


def test_ci_requires_windows_installer_install_run_uninstall_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-installer-smoke:" in workflow
    assert "Build standalone Windows installer" in workflow
    assert "Install, launch, and uninstall on clean runner path" in workflow
    required = workflow.split("required-ci:", 1)[1]
    assert "- windows-installer-smoke" in required
    assert "WINDOWS_INSTALLER_RESULT:" in required
    assert 'test "${WINDOWS_INSTALLER_RESULT}" = "success"' in required
