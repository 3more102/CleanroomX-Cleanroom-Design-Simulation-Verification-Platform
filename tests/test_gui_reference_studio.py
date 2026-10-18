"""Reference Studio contract tests for the actual Tk CleanroomX application.

Run with: xvfb-run -a python -m pytest -q tests/test_gui_reference_studio.py
"""
from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.spatial import _Hit, design_studio_snapshot


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "studio-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    application.notebook.select(application.spatial_workspace)
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        application._autosave_manager.shutdown(wait=False)
        root.destroy()


def test_reference_demo_dashboard_uses_actual_spatial_data(app):
    workspace = app.spatial_workspace
    snapshot = design_studio_snapshot(workspace.layout, "process")
    assert snapshot["room_count"] == 3
    assert snapshot["total_floor_area_m2"] == pytest.approx(62)
    assert snapshot["total_volume_m3"] == pytest.approx(186)
    assert snapshot["placed_devices"] == 10
    assert snapshot["selected_room_device_count"] == 5
    assert snapshot["other_devices"] == 5
    assert workspace._studio_card_vars["rooms"].get() == "3"
    assert workspace._studio_card_vars["area"].get() == "62.0 m²"
    assert workspace._studio_card_vars["volume"].get() == "186.0 m³"
    assert workspace._studio_card_vars["devices"].get() == "10"
    assert workspace.room_navigator.find_withtag("room:process")
    assert workspace.room_navigator.find_withtag("room:preparation")
    assert workspace.room_navigator.find_withtag("room:ante")


def test_navigator_room_click_synchronizes_selection_and_inspector(app):
    workspace = app.spatial_workspace
    room_items = workspace.room_navigator.find_withtag("room:preparation")
    assert room_items
    bbox = workspace.room_navigator.bbox(room_items[0])
    assert bbox
    event = type("Event", (), {
        "x": (bbox[0] + bbox[2]) // 2,
        "y": (bbox[1] + bbox[3]) // 2,
    })()
    workspace._on_room_navigator_click(event)
    app.root.update()
    assert workspace.selected == _Hit("room", "preparation")
    assert "Preparation" in workspace._selected_room_summary_var.get()
    assert "20 m²" in workspace._selected_room_summary_var.get()
    assert "configured" in workspace._selected_room_summary_var.get()
    assert workspace.canvas_2d.find_withtag("room:preparation")
    assert workspace.canvas_3d.find_withtag("room:preparation")
    assert app.analysis_tree.selection() == ("room:preparation",)


def test_studio_dashboard_refreshes_on_edit_delete_and_undo(app):
    workspace = app.spatial_workspace
    workspace.add_room()
    app.root.update()
    assert workspace._studio_card_vars["rooms"].get() == "4"
    assert workspace._studio_card_vars["area"].get() == "78.0 m²"
    assert workspace._studio_card_vars["volume"].get() == "234.0 m³"
    assert len(workspace.room_navigator.find_withtag("navigator_room")) >= 4
    workspace.add_device("ffu")
    app.root.update()
    assert workspace._studio_card_vars["devices"].get() == "11"
    workspace.delete_selected()  # selected new FFU
    app.root.update()
    assert workspace._studio_card_vars["devices"].get() == "10"
    assert app.undo_project_edit()
    app.root.update()
    assert workspace._studio_card_vars["devices"].get() == "11"


def test_studio_view_and_focus_are_real_camera_and_selection_commands(app):
    workspace = app.spatial_workspace
    workspace.set_inspector_visible(False)
    workspace.set_workspace_mode("split")
    workspace.studio_view()
    app.root.update()
    assert workspace.inspector_visible()
    assert workspace._workspace_mode.get() == "3d"
    assert workspace.canvas_3d.winfo_ismapped()
    assert workspace.room_navigator.winfo_ismapped()
    assert workspace.select_item("device", "ffu-process")
    workspace.focus_selected_room()
    app.root.update()
    assert workspace.selected == _Hit("room", "process")
    workspace.isolate_selected()
    assert workspace._isolated_item == _Hit("room", "process")
    workspace.show_all()
    assert workspace._isolated_item is None


def test_snapshot_never_mislabels_configured_pressure_as_solver_output(app):
    snapshot = design_studio_snapshot(app.spatial_workspace.layout, "process")
    assert snapshot["selected_room"]["pressure_pa"] == 30.0
    assert "solver" not in app.spatial_workspace._selected_room_summary_var.get().lower()
    app.spatial_workspace.select_item("room", "process")
    assert "Design pressure" in app.spatial_workspace._selected_room_summary_var.get()
    assert "(configured)" in app.spatial_workspace._selected_room_summary_var.get()
