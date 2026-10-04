"""Real Tk interactions; run with xvfb-run -a python -m pytest -q this_file."""
from __future__ import annotations

import copy
import os
import tkinter as tk
from types import SimpleNamespace
from tkinter import ttk

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


def test_measurement_and_visibility_tools_are_display_only(app):
    workspace = app.spatial_workspace
    workspace.set_workspace_mode("split")
    room = workspace.layout["rooms"][0]
    other_rooms = workspace.layout["rooms"][1:]
    before = copy.deepcopy(workspace.layout)

    assert workspace.select_item("room", room["id"])
    workspace.isolate_selected()
    app.root.update()

    assert workspace.canvas_2d.find_withtag(f"room:{room['id']}")
    assert workspace.canvas_3d.find_withtag(f"room:{room['id']}")
    for other in other_rooms:
        assert not workspace.canvas_2d.find_withtag(f"room:{other['id']}")
        assert not workspace.canvas_3d.find_withtag(f"room:{other['id']}")

    workspace.show_all_objects()
    app.root.update()
    for other in other_rooms:
        assert workspace.canvas_2d.find_withtag(f"room:{other['id']}")
        assert workspace.canvas_3d.find_withtag(f"room:{other['id']}")

    start = workspace._world_to_canvas(0.0, 0.0)
    end = workspace._world_to_canvas(3.0, 4.0)
    workspace._measure_mode.set(True)
    workspace._toggle_measure_mode()
    workspace._on_measure_click(SimpleNamespace(x=start[0], y=start[1]))
    workspace._on_measure_click(SimpleNamespace(x=end[0], y=end[1]))
    app.root.update()

    assert workspace._measure_var.get() == "Distance: 5.000 m"
    assert workspace.canvas_2d.find_withtag("measurement")
    assert workspace.layout == before

    workspace._measure_mode.set(False)
    workspace._toggle_measure_mode()
    app.root.update()
    assert not workspace.canvas_2d.find_withtag("measurement")


def test_fit_selected_centers_the_selected_room_without_changing_geometry(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    assert workspace.select_item("room", room["id"])
    geometry_before = copy.deepcopy(workspace.layout["rooms"])

    workspace.layout["view"]["zoom_2d"] = 0.2
    workspace.layout["view"]["pan_x"] = 800.0
    workspace.layout["view"]["pan_y"] = -600.0
    workspace.fit_selected()
    app.root.update()

    center_x = room["x_m"] + room["length_m"] / 2.0
    center_y = room["y_m"] + room["width_m"] / 2.0
    screen_center = workspace._world_to_canvas(center_x, center_y)
    assert screen_center[0] == pytest.approx(workspace.canvas_2d.winfo_width() / 2.0)
    assert screen_center[1] == pytest.approx(workspace.canvas_2d.winfo_height() / 2.0)
    assert workspace.layout["rooms"] == geometry_before
