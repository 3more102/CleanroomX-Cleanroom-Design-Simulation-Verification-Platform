from __future__ import annotations

import os
import tkinter as tk

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.gui import CleanroomXApp


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    try:
        yield application
    finally:
        root.destroy()


def _report(*, ready: bool = True) -> dict:
    return {
        "schema": "cleanroomx.system-health",
        "schema_version": 1,
        "application": {"name": "CleanroomX", "version": "test"},
        "runtime": {"platform": "test", "machine": "test", "python": "test"},
        "status": "ready" if ready else "not_ready",
        "required_ready": ready,
        "require_bim": False,
        "deep": False,
        "summary": {
            "pass": 1 if ready else 0,
            "warn": 0,
            "fail": 0 if ready else 1,
            "check_count": 1,
        },
        "checks": [
            {
                "id": "python-runtime",
                "label": "Python runtime",
                "required": True,
                "status": "pass" if ready else "fail",
                "summary": "Synthetic runtime readiness result.",
                "details": {},
                "remediation": None if ready else "Repair the synthetic desktop runtime.",
            }
        ],
    }


def test_gui_system_health_surfaces_ready_report(app, monkeypatch) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gui_module,
        "build_system_health_report",
        lambda: _report(ready=True),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showinfo",
        lambda title, message, **_kwargs: shown.append((title, message)),
    )

    app.show_system_health()

    assert shown
    assert shown[0][0] == "CleanroomX System Health"
    assert "Required readiness: PASS" in shown[0][1]
    assert "[PASS] Python runtime (required)" in shown[0][1]
    assert app.status_var.get() == "System health: ready"


def test_gui_system_health_surfaces_required_failure_as_warning(app, monkeypatch) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gui_module,
        "build_system_health_report",
        lambda: _report(ready=False),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, **_kwargs: shown.append((title, message)),
    )

    app.show_system_health()

    assert shown
    assert "Required readiness: FAIL" in shown[0][1]
    assert "[FAIL] Python runtime (required)" in shown[0][1]
    assert "Action: Repair the synthetic desktop runtime." in shown[0][1]
    assert app.status_var.get() == "System health: required check failed"


def test_gui_system_health_contains_probe_failure(app, monkeypatch) -> None:
    shown: list[tuple[str, str]] = []

    def fail_report() -> dict:
        raise RuntimeError("synthetic health probe failure")

    monkeypatch.setattr(gui_module, "build_system_health_report", fail_report)
    monkeypatch.setattr(
        gui_module.messagebox,
        "showerror",
        lambda title, message, **_kwargs: shown.append((title, message)),
    )

    app.show_system_health()

    assert shown
    assert "RuntimeError: synthetic health probe failure" in shown[0][1]
    assert app.status_var.get() == "System health check failed"
