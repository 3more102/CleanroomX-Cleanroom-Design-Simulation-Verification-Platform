from __future__ import annotations

import os
import tkinter as tk

import pytest

import cleanroomx.gui_panels as gui_panels
from cleanroomx.gui_panels import ProjectDiagnosticsPanel


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.withdraw()
    try:
        yield window
    finally:
        window.destroy()


def _diagnostic_result():
    return {
        "summary": {
            "status": "failed",
            "error_count": 1,
            "warning_count": 1,
            "info_count": 1,
        },
        "issues": [
            {
                "sequence": 1,
                "severity": "warning",
                "rule": "AIRFLOW.BALANCE",
                "category": "airflow",
                "message": "Balance exceeds tolerance",
                "suggested_action": "Review supply and return flow.",
                "element": {"type": "spatial_element", "id": "room-a", "name": "Room A"},
                "details": {"level": "L1", "actual": 12.0, "required": 10.0},
            },
            {
                "sequence": 2,
                "severity": "error",
                "rule": "PRESSURE.CASCADE",
                "category": "pressure",
                "message": "Pressure cascade failed",
                "suggested_action": "Review adjacent pressure targets.",
                "element": {"type": "analysis", "id": "pressure-1", "name": "Pressure Check"},
                "details": {"actual_pa": 2.0, "required_pa": 5.0},
            },
            {
                "sequence": 3,
                "severity": "info",
                "rule": "MODEL.CURRENCY",
                "category": "freshness",
                "message": "Verification evidence is current",
                "suggested_action": "",
                "element": {"type": "project", "id": "project"},
                "details": {},
            },
        ],
    }


def _panel(root, monkeypatch):
    monkeypatch.setattr(
        gui_panels,
        "analyze_project_diagnostics",
        lambda _project, base_dir=None: _diagnostic_result(),
    )
    navigated = []
    panel = ProjectDiagnosticsPanel(
        root,
        project_getter=lambda: object(),
        base_dir_getter=lambda: None,
        navigate_callback=navigated.append,
    )
    panel.pack(fill="both", expand=True)
    assert panel.refresh() is not None
    root.update()
    return panel, navigated


def test_diagnostics_filters_category_object_and_search(root, monkeypatch):
    panel, _ = _panel(root, monkeypatch)
    assert len(panel.tree.get_children()) == 3

    panel.category_var.set("pressure")
    root.update()
    assert len(panel.tree.get_children()) == 1
    assert panel.tree.item(panel.tree.get_children()[0], "values")[1] == "PRESSURE.CASCADE"

    panel.category_var.set("All")
    panel.element_type_var.set("spatial_element")
    root.update()
    assert len(panel.tree.get_children()) == 1
    assert panel.tree.item(panel.tree.get_children()[0], "values")[3] == "Room A"

    panel.element_type_var.set("All")
    panel.search_var.set("current")
    root.update()
    assert len(panel.tree.get_children()) == 1
    assert "1/3 shown" in panel.summary_var.get()


def test_diagnostics_sort_traversal_and_navigation(root, monkeypatch):
    panel, navigated = _panel(root, monkeypatch)
    panel.sort_by("severity")
    root.update()

    children = panel.tree.get_children()
    assert panel.tree.item(children[0], "values")[0] == "ERROR"

    panel.select_relative(1)
    first = panel.tree.selection()[0]
    panel.select_relative(1)
    second = panel.tree.selection()[0]
    assert first != second

    panel._navigate_selected()
    assert navigated
    assert navigated[-1] == panel.selected_issue()


def test_filtered_projection_preserves_canonical_result(root, monkeypatch):
    panel, _ = _panel(root, monkeypatch)
    panel.severity_var.set("Error")
    root.update()

    projection = panel.filtered_result()
    assert projection is not None
    assert len(projection["issues"]) == 1
    assert projection["issues"][0]["rule"] == "PRESSURE.CASCADE"
    assert projection["view_filter"]["displayed_issue_count"] == 1
    assert projection["view_filter"]["total_issue_count"] == 3
    assert len(panel.last_result["issues"]) == 3
