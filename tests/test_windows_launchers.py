from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_launchers_use_repository_source_and_open_demo_by_default():
    powershell = (ROOT / "start-cleanroomx.ps1").read_text(encoding="utf-8")
    cmd = (ROOT / "start-cleanroomx.cmd").read_text(encoding="utf-8")

    assert '".venv\\Scripts\\python.exe"' in powershell
    assert '"src"' in powershell
    assert '"--demo"' in powershell
    assert "-m cleanroomx.gui" in powershell
    assert "sys.version_info >= (3, 11)" in powershell
    assert '-c "import tkinter"' in powershell
    assert "CleanroomX requires Python 3.11 or newer" in powershell
    assert "CleanroomX GUI requires Tkinter" in powershell

    assert ".venv\\Scripts\\python.exe" in cmd
    assert "PYTHONPATH=%CD%\\src" in cmd
    assert "CLEANROOMX_PY=" in cmd
    assert "where python >nul 2>nul" in cmd
    assert "sys.version_info.minor in range(11, 100)" in cmd
    assert '-c "import tkinter"' in cmd
    assert "CleanroomX requires Python 3.11 or newer" in cmd
    assert "CleanroomX GUI requires Tkinter" in cmd
    assert "-m cleanroomx.gui --demo" in cmd
    assert "-m cleanroomx.gui %*" in cmd
    assert cmd.rstrip().endswith("exit /b %ERRORLEVEL%")
