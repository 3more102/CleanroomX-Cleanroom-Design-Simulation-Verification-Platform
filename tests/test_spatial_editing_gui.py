"""Real Tk interactions; run with xvfb-run -a python -m pytest -q this_file."""
from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.project import save_project_document
from cleanroomx.spatial import _Hit


@pytest.fixture
def app():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(root, autosave_interval_seconds=0)
    application.load_project_path(bundled_demo_project_path())
    application.notebook.select(application.spatial_workspace)
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_duplicate_edit_undo_redo_save_reopen_and_analysis(app, tmp_path):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    source_id = room["id"]
    original_count = len(workspace.layout["rooms"])
    inputs_before = [copy.deepcopy(analysis.input) for analysis in app.project.analyses]
    workspace.selected = _Hit("room", source_id)
    workspace._load_property_panel()
    workspace.duplicate_selected()
    app.root.update()
    copied_id = workspace.selected.item_id
    duplicated = copy.deepcopy(workspace.layout)
    assert len(duplicated["rooms"]) == original_count + 1
    assert workspace.canvas_2d.find_withtag(f"room:{copied_id}")
    assert workspace.canvas_3d.find_withtag(f"room:{copied_id}")

    assert app.undo_project_edit()
    assert len(workspace.layout["rooms"]) == original_count
    assert workspace.selected == _Hit("room", source_id)
    assert app.redo_project_edit()
    assert workspace.layout == duplicated
    assert workspace.selected == _Hit("room", copied_id)

    before = copy.deepcopy(workspace.layout)
    copied_room = before["rooms"][-1]
    workspace._property_vars["x_m"].set(str(copied_room["x_m"] + 2))
    workspace._property_vars["y_m"].set(str(copied_room["y_m"] + 1))
    workspace._property_vars["height_m"].set("4.5")
    workspace._property_vars["pressure_pa"].set("15")
    workspace.apply_properties()
    app.root.update()
    edited = copy.deepcopy(workspace.layout)
    assert edited["rooms"][-1]["height_m"] == 4.5
    assert edited["rooms"][-1]["pressure_pa"] == 15
    for old, new in zip(before["devices"], edited["devices"]):
        if old.get("room_id") == copied_id:
            assert new["x_m"] == old["x_m"] + 2
            assert new["y_m"] == old["y_m"] + 1
    assert [analysis.input for analysis in app.project.analyses] == inputs_before
    assert app.undo_project_edit()
    assert workspace.layout == before
    assert app.redo_project_edit()
    assert workspace.layout == edited

    path = tmp_path / "spatial-workflow.cleanroomx.json"
    save_project_document(path, app.project)
    app.load_project_path(path)
    app.root.update()
    assert workspace.layout == edited
    run = app.smoke_run_active()
    assert run.result
    assert app.result_text.get("1.0", "end").strip()
    assert app.report_text.get("1.0", "end").strip()


def test_invalid_inspector_edit_leaves_undo_and_geometry_intact(app, monkeypatch):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.selected = _Hit("room", room["id"])
    workspace._load_property_panel()
    before = copy.deepcopy(workspace.layout)
    can_undo = app._project_history.can_undo
    errors = []
    monkeypatch.setattr("cleanroomx.spatial.messagebox.showerror", lambda *args, **kwargs: errors.append(args))
    workspace._property_vars["name"].set("Should not apply")
    workspace._property_vars["height_m"].set("NaN")
    workspace.apply_properties()
    assert errors and "Height" in errors[0][1]
    assert workspace.layout == before
    assert app.project.metadata["spatial_layout"] == before
    assert app._project_history.can_undo == can_undo
    assert workspace._property_vars["height_m"].get() == "NaN"


@pytest.mark.parametrize("size", ["1050x680", "1440x900"])
def test_editing_toolbar_controls_remain_visible(app, size):
    app.root.geometry(size)
    app.root.update()
    workspace = app.spatial_workspace
    for row in workspace.winfo_children():
        if not isinstance(row, ttk.Frame):
            continue
        for button in row.winfo_children():
            if isinstance(button, (ttk.Button, ttk.Menubutton)):
                assert button.winfo_ismapped(), button.cget("text")
                assert button.winfo_x() + button.winfo_width() <= row.winfo_width(), button.cget("text")



def test_workspace_modes_make_2d_and_3d_first_class_views(app):
    workspace = app.spatial_workspace

    workspace.set_workspace_mode("2d")
    app.root.update()
    panes = tuple(str(item) for item in workspace._view_panes.panes())
    assert str(workspace._two_d_frame) in panes
    assert str(workspace._three_d_frame) not in panes
    assert workspace.canvas_2d.winfo_ismapped()

    workspace.set_workspace_mode("3d")
    app.root.update()
    panes = tuple(str(item) for item in workspace._view_panes.panes())
    assert str(workspace._two_d_frame) not in panes
    assert str(workspace._three_d_frame) in panes
    assert workspace.canvas_3d.winfo_ismapped()

    workspace.set_workspace_mode("split")
    app.root.update()
    panes = tuple(str(item) for item in workspace._view_panes.panes())
    assert str(workspace._two_d_frame) in panes
    assert str(workspace._three_d_frame) in panes


def test_project_navigator_and_workspace_selection_stay_synchronized(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    navigator_id = f"room:{room['id']}"

    assert app.analysis_tree.exists("nav-building")
    assert app.analysis_tree.exists("nav-analyses")
    assert app.analysis_tree.exists(navigator_id)

    app.analysis_tree.selection_set(navigator_id)
    app.analysis_tree.event_generate("<<TreeviewSelect>>")
    app.root.update()
    assert workspace.selected == _Hit("room", room["id"])
    assert app.notebook.select() == str(workspace)

    other = workspace.layout["rooms"][1]
    workspace.select_item("room", other["id"], notify=True)
    app.root.update()
    assert app.analysis_tree.selection() == (f"room:{other['id']}",)


def test_contextual_inspector_hides_irrelevant_fields(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    assert workspace._property_rows["pressure_pa"].winfo_manager() == "pack"
    assert workspace._property_rows["analysis_room_name"].winfo_manager() == "pack"
    assert workspace._property_rows["room_id"].winfo_manager() == ""

    device = workspace.layout["devices"][0]
    workspace.select_item("device", device["id"])
    app.root.update()

    assert workspace._property_rows["room_id"].winfo_manager() == "pack"
    assert workspace._property_rows["pressure_pa"].winfo_manager() == ""
    assert workspace._property_rows["classification"].winfo_manager() == ""

def test_fit_selected_and_3d_view_presets_are_deterministic(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    assert workspace.select_item("room", room["id"])

    workspace.set_3d_view_preset("top")
    app.root.update()
    assert workspace.layout["view"]["azimuth_deg"] == pytest.approx(0.0)
    assert workspace.layout["view"]["elevation_deg"] == pytest.approx(75.0)
    assert workspace.layout["view"]["zoom_3d"] > 0

    workspace.set_3d_view_preset("front")
    assert workspace.layout["view"]["azimuth_deg"] == pytest.approx(0.0)
    assert workspace.layout["view"]["elevation_deg"] == pytest.approx(5.0)

    workspace.set_3d_view_preset("right")
    assert workspace.layout["view"]["azimuth_deg"] == pytest.approx(90.0)
    assert workspace.layout["view"]["elevation_deg"] == pytest.approx(5.0)

    workspace.set_3d_view_preset("iso")
    assert workspace.layout["view"]["azimuth_deg"] == pytest.approx(35.0)
    assert workspace.layout["view"]["elevation_deg"] == pytest.approx(28.0)
    assert workspace.fit_selected()
    assert 0.2 <= workspace.layout["view"]["zoom_2d"] <= 8.0
    assert 0.2 <= workspace.layout["view"]["zoom_3d"] <= 8.0


def test_room_layer_visibility_is_persisted_and_applied(app):
    workspace = app.spatial_workspace
    assert workspace.canvas_2d.find_withtag("room")
    assert workspace.canvas_3d.find_withtag("room3d")

    workspace._show_rooms.set(False)
    workspace._set_view_flag("show_rooms", False)
    app.root.update()
    assert workspace.layout["view"]["show_rooms"] is False
    assert not workspace.canvas_2d.find_withtag("room")
    assert not workspace.canvas_3d.find_withtag("room3d")

    workspace._show_rooms.set(True)
    workspace._set_view_flag("show_rooms", True)
    app.root.update()
    assert workspace.canvas_2d.find_withtag("room")
    assert workspace.canvas_3d.find_withtag("room3d")


def test_2d_distance_and_area_measurement_do_not_change_geometry(app):
    workspace = app.spatial_workspace
    before = copy.deepcopy(workspace.layout)

    p0 = workspace._world_to_canvas(0.0, 0.0)
    p1 = workspace._world_to_canvas(3.0, 4.0)

    workspace.start_measurement("distance")
    workspace._capture_measure_point(SimpleNamespace(x=p0[0], y=p0[1]))
    workspace._capture_measure_point(SimpleNamespace(x=p1[0], y=p1[1]))
    app.root.update()
    assert workspace._measure_var.get() == "Distance: 5.000 m"
    assert workspace.canvas_2d.find_withtag("measurement")
    assert workspace.layout == before

    p2 = workspace._world_to_canvas(2.0, 3.0)
    workspace.start_measurement("area")
    workspace._capture_measure_point(SimpleNamespace(x=p0[0], y=p0[1]))
    workspace._capture_measure_point(SimpleNamespace(x=p2[0], y=p2[1]))
    app.root.update()
    assert workspace._measure_var.get() == "Area: 6.000 m²"
    assert workspace.layout == before

    workspace.clear_measurement()
    app.root.update()
    assert workspace._measure_mode.get() == "none"
    assert not workspace.canvas_2d.find_withtag("measurement")

def test_engineering_output_is_docked_below_primary_workspace(app):
    app.root.update()
    panes = tuple(str(item) for item in app.workspace_panes.panes())
    assert len(panes) == 2

    primary_tabs = [app.notebook.tab(tab_id, "text") for tab_id in app.notebook.tabs()]
    output_tabs = [
        app.output_notebook.tab(tab_id, "text")
        for tab_id in app.output_notebook.tabs()
    ]
    assert "Design" in primary_tabs
    assert "Input" in primary_tabs
    assert "Plot" in primary_tabs
    assert "Results" not in primary_tabs
    assert output_tabs == ["Results", "Diagnostics", "Report"]

    assert app.result_text.master.master == app.output_notebook
    assert app.diagnostics_text.master.master == app.output_notebook
    assert app.report_text.master.master == app.output_notebook

