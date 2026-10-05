from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launchers_use_repository_source_and_open_demo_by_default():
    powershell = (ROOT / "start-cleanroomx.ps1").read_text(encoding="utf-8")
    cmd = (ROOT / "start-cleanroomx.cmd").read_text(encoding="utf-8")

    assert '".venv\\Scripts\\python.exe"' in powershell
    assert '"src"' in powershell
    assert '"--demo"' in powershell
    assert "-m cleanroomx.gui" in powershell

    assert ".venv\\Scripts\\python.exe" in cmd
    assert "PYTHONPATH=%CD%\\src" in cmd
    assert "CLEANROOMX_PY=" in cmd
    assert "-m cleanroomx.gui --demo" in cmd
    assert "-m cleanroomx.gui %*" in cmd
    assert cmd.rstrip().endswith("exit /b %ERRORLEVEL%")


def test_packaging_exposes_separate_console_and_desktop_gui_entry_points():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["scripts"]["cleanroomx-gui"] == "cleanroomx.gui:main"
    assert project["gui-scripts"]["cleanroomx-desktop"] == "cleanroomx.gui:main"
    assert "cleanroomx-desktop" not in project["scripts"]
