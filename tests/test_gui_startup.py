"""Startup failures must remain diagnosable; smoke callbacks must fail the check."""
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import pytest

import cleanroomx.gui as gui
from cleanroomx.runtime_diagnostics import GUI_LOG_FILENAME


@pytest.fixture
def startup(monkeypatch, tmp_path):
    monkeypatch.setenv("CLEANROOMX_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(gui, "validate_application_registry", lambda: {
        "plugin_issue_count": 0, "plugin_issues": [],
    })
    return tmp_path


def test_display_failure_has_traceback_log_and_actionable_stderr(startup, monkeypatch, capsys):
    def fail():
        raise tk.TclError("no display name and no $DISPLAY environment variable")
    monkeypatch.setattr(gui.tk, "Tk", fail)
    assert gui.main(["--smoke"]) == 2
    captured = capsys.readouterr()
    assert "PASS" not in captured.out
    assert "cleanroomx-gui --check" in captured.err
    assert "display" in captured.err
    log = (startup / GUI_LOG_FILENAME).read_text()
    assert "Traceback (most recent call last)" in log
    assert "TclError" in log and "no display name" in log
    assert "interpreter=" in log and "cwd=" in log


def test_application_initialization_failure_destroys_partial_window(startup, monkeypatch, capsys):
    root = SimpleNamespace(destroyed=False)
    root.destroy = lambda: setattr(root, "destroyed", True)
    monkeypatch.setattr(gui.tk, "Tk", lambda: root)
    def fail(*args, **kwargs):
        raise AttributeError("confirmed initialization failure")
    monkeypatch.setattr(gui, "CleanroomXApp", fail)
    assert gui.main(["--smoke"]) == 2
    assert root.destroyed
    assert "AttributeError" in capsys.readouterr().err
    assert "confirmed initialization failure" in (startup / GUI_LOG_FILENAME).read_text()


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_autosave_interval_rejected_before_tk(monkeypatch, value):
    monkeypatch.setattr(gui.tk, "Tk", lambda: pytest.fail("Tk must not start"))
    with pytest.raises(SystemExit) as exc:
        gui.main([f"--autosave-interval-seconds={value}", "--check"])
    assert exc.value.code == 2


def test_log_creation_failure_preserves_startup_traceback(startup, monkeypatch, capsys):
    blocked = startup / "not-a-directory"
    blocked.write_text("preserve existing file")
    monkeypatch.setenv("CLEANROOMX_LOG_DIR", str(blocked))
    def fail():
        raise tk.TclError("display unavailable")
    monkeypatch.setattr(gui.tk, "Tk", fail)
    assert gui.main(["--smoke"]) == 2
    error = capsys.readouterr().err
    assert "display unavailable" in error
    assert "log unavailable" in error.lower()
    assert blocked.read_text() == "preserve existing file"


def test_missing_optional_demo_opens_empty_workspace(startup, monkeypatch):
    events = []
    class Root:
        def mainloop(self): events.append("workspace")
        def destroy(self): events.append("destroy")
    class App:
        def __init__(self, root, **kwargs): self.root = root
        def offer_startup_recovery(self): return False
    def missing():
        raise FileNotFoundError("bundled demo missing")
    monkeypatch.setattr(gui.tk, "Tk", Root)
    monkeypatch.setattr(gui, "CleanroomXApp", App)
    monkeypatch.setattr(gui, "bundled_demo_project_path", missing)
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: events.append(a))
    assert gui.main(["--demo"]) == 0
    assert "workspace" in events
    assert any(isinstance(e, tuple) and "demo" in e[1] for e in events)


def test_real_tk_smoke_fails_on_idle_callback_error(startup, monkeypatch, capsys):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("An actual display is required for the Tk callback regression")
    monkeypatch.setattr(gui.tk, "Tk", lambda: root)
    class App:
        def __init__(self, root, **kwargs):
            self.project = SimpleNamespace(analyses=[])
            def fail():
                raise RuntimeError("idle callback regression sentinel")
            root.after_idle(fail)
    monkeypatch.setattr(gui, "CleanroomXApp", App)
    assert gui.main(["--smoke"]) == 2
    captured = capsys.readouterr()
    assert "PASS" not in captured.out
    assert "idle callback regression sentinel" in captured.err
    assert "idle callback regression sentinel" in (startup / GUI_LOG_FILENAME).read_text()
