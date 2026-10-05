from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_native_bundle_is_windowed_and_includes_bim_runtime():
    spec = (ROOT / "packaging" / "windows" / "CleanroomX.spec").read_text(
        encoding="utf-8"
    )

    assert 'name="CleanroomX"' in spec
    assert "console=False" in spec
    assert 'collect_all("ifcopenshell")' in spec
    assert 'collect_submodules("cleanroomx")' in spec
    assert '"cleanroomx/demo"' in spec
    assert '"cleanroomx.ico"' in spec


def test_windows_installer_is_per_user_and_uninstallable():
    installer = (ROOT / "packaging" / "windows" / "CleanroomX.iss").read_text(
        encoding="utf-8"
    )

    assert "PrivilegesRequired=lowest" in installer
    assert "DefaultDirName={localappdata}\\Programs\\CleanroomX" in installer
    assert "UninstallDisplayIcon={app}\\{#MyAppExeName}" in installer
    assert "recursesubdirs createallsubdirs" in installer
    assert "VersionInfoVersion={#MyVersionInfo}" in installer
    assert "SetupIconFile=cleanroomx.ico" in installer


def test_windows_icon_generator_is_deterministic_build_input():
    generator = (ROOT / "packaging" / "windows" / "build_icon.py").read_text(
        encoding="utf-8"
    )

    assert 'format="ICO"' in generator
    assert "(256, 256)" in generator
    assert 'label = "CX"' in generator
