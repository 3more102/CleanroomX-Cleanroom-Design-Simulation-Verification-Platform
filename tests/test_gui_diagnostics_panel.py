from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui_panels import ProjectDiagnosticsPanel
from cleanroomx.gui_theme import theme_palette


@pytest.fixture
def panel():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    widget = ProjectDiagnosticsPanel(
        root,
        project_getter=lambda: object(),
        base_dir_getter=lambda: None,
        navigate_callback=lambda _issue: None,
    )
    widget.pack(fill="both", expand=True)
    root.update()
    try:
        yield widget
        assert callback_errors == []
    finally:
        root.destroy()


def _diagnostics_result():
    return {
        "summary": {
            "status": "fail",
            "error_count": 1,
            "warning_count": 1,
            "info_count": 1,
        },
        "issues": [
            {
                "sequence": 1,
                "severity": "error",
                "rule": "ACH_MIN",
                "category": "airflow",
                "message": "ACH is below the project requirement.",
                "suggested_action": "Review supply airflow.",
                "element": {"type": "room", "id": "room-a", "name": "Room A"},
                "details": {"level": "L1", "actual": 8.0, "required": 12.0},
            },
            {
                "sequence": 2,
                "severity": "warning",
                "rule": "IFC_LINK",
                "category": "bim",
                "message": "IFC source revision changed.",
                "suggested_action": "Review the IFC re-import plan.",
                "element": {"type": "room", "id": "room-b", "name": "Room B"},
                "details": {"level": "L2"},
            },
            {
                "sequence": 3,
                "severity": "info",
                "rule": "EVIDENCE_PRESENT",
                "category": "evidence",
                "message": "Evidence is linked.",
                "suggested_action": "",
                "element": {"type": "analysis", "id": "analysis-a"},
                "details": {},
            },
        ],
    }


def test_diagnostics_panel_filters_by_rule_and_level(panel):
    panel.last_result = _diagnostics_result()
    panel._refresh_filter_values()
    panel._populate()

    assert "ACH_MIN" in panel.rule_combo.cget("values")
    assert "L1" in panel.level_combo.cget("values")
    assert "L2" in panel.level_combo.cget("values")

    panel.rule_var.set("ACH_MIN")
    assert [item["sequence"] for item in panel._filtered_issues()] == [1]

    panel.rule_var.set("All")
    panel.level_var.set("L2")
    assert [item["sequence"] for item in panel._filtered_issues()] == [2]

    panel.clear_filters()
    assert len(panel._filtered_issues()) == 3


def test_diagnostics_panel_uses_semantic_state_colors(panel):
    palette = theme_palette("dark")
    panel.apply_theme(palette)

    assert panel.tree.tag_cget("error", "foreground") == palette["error"]
    assert panel.tree.tag_cget("warning", "foreground") == palette["warning"]
    assert panel.tree.tag_cget("info", "foreground") == palette["info"]
