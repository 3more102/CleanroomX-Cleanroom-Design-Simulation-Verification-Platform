from __future__ import annotations

import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from cleanroomx.gui_dashboard import EngineeringDashboard


@pytest.fixture
def dashboard():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    widget = EngineeringDashboard(
        root,
        open_design=lambda: None,
        open_simulation=lambda: None,
        open_verification=lambda: None,
        open_evidence=lambda: None,
        open_reporting=lambda: None,
    )
    widget.pack(fill="both", expand=True)
    root.update()
    try:
        yield widget
    finally:
        root.destroy()


def test_dashboard_uses_only_supplied_engineering_snapshot(dashboard):
    run = SimpleNamespace(title="Pressure Cascade", status="pass")
    dashboard.set_snapshot(
        {
            "project_name": "Fab A",
            "project_location": "/projects/fab-a.cleanroomx.json",
            "diagnostics": {
                "status": "warning",
                "error_count": 0,
                "warning_count": 2,
                "info_count": 3,
            },
            "verification": {
                "configured_analysis_count": 4,
                "current_count": 2,
                "stale_count": 1,
                "not_verified_count": 1,
            },
            "retained_verification_records": 7,
            "proofgraph_count": 3,
            "room_count": 12,
            "device_count": 41,
            "analysis_count": 4,
            "current_run": run,
        }
    )

    assert dashboard.value("project").startswith("Fab A")
    assert dashboard.value("issues") == "WARNING · 0 error(s) · 2 warning(s) · 3 info"
    assert dashboard.value("verification") == "2/4 current · 1 stale · 1 not verified"
    assert dashboard.value("evidence") == "7 retained verification run(s) · 3 ProofGraph(s)"
    assert dashboard.value("model") == "12 room(s) · 41 device(s) · 4 analysis definition(s)"
    assert dashboard.value("analysis") == "Pressure Cascade · pass"


def test_dashboard_explicitly_represents_unavailable_states(dashboard):
    dashboard.set_snapshot(
        {
            "project_name": "Empty",
            "project_location": "Unsaved project",
            "diagnostics": None,
            "verification": None,
        }
    )

    assert dashboard.value("issues") == "Diagnostics: unavailable"
    assert dashboard.value("verification") == "Verification currency: unavailable"
    assert dashboard.value("analysis") == "No current analysis result"
