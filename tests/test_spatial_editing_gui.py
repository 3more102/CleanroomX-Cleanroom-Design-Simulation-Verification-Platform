"""Real Tk interactions; run with xvfb-run -a python -m pytest -q this_file."""
from __future__ import annotations

import copy
import os
import tkinter as tk
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



def test_selected_room_shows_engineering_dimensions(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    app.root.update()

    dimension_items = workspace.canvas_2d.find_withtag("room_dimension")
    assert dimension_items
    texts = [
        workspace.canvas_2d.itemcget(item_id, "text")
        for item_id in dimension_items
        if workspace.canvas_2d.type(item_id) == "text"
    ]
    assert f"{room['length_m']:g} m" in texts
    assert f"{room['width_m']:g} m" in texts


def test_snap_indicator_tracks_configured_grid_without_mutating_geometry(app):
    workspace = app.spatial_workspace
    before = copy.deepcopy(workspace.layout)
    workspace._snap_to_grid.set(True)
    x, y = workspace._world_to_canvas(1.26, 2.24)

    workspace._draw_snap_indicator_2d(x, y)
    app.root.update()

    assert workspace.canvas_2d.find_withtag("snap_indicator")
    grid = workspace.layout["grid_m"]
    sx, sy = workspace._snap_indicator_world
    assert sx == pytest.approx(round(1.26 / grid) * grid)
    assert sy == pytest.approx(round(2.24 / grid) * grid)
    assert workspace.layout == before


def test_room_context_menu_exposes_real_editing_actions(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    hit = _Hit("room", room["id"])
    workspace.select_item("room", room["id"])

    menu = workspace._build_context_menu_2d(hit)
    try:
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) != "separator"
        ]
    finally:
        menu.destroy()

    assert "Properties" in labels
    assert "Fit selected" in labels
    assert "Isolate" in labels
    assert "Hide" in labels
    assert "Show all" in labels
    assert "Duplicate" in labels
    assert "Delete" in labels
    assert "Add Door" in labels
    assert "Add Opening" in labels
    assert "Add Device" in labels
    assert "Link Analysis…" in labels


def test_hover_state_has_distinct_2d_feedback(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    room_item = workspace.canvas_2d.find_withtag(f"room:{room['id']}")[0]
    workspace.canvas_2d.addtag_withtag("current", room_item)
    x, y = workspace._world_to_canvas(
        room["x_m"] + room["length_m"] / 2,
        room["y_m"] + room["width_m"] / 2,
    )
    event = type("Event", (), {"x": int(x), "y": int(y)})()

    workspace._on_motion(event)

    assert workspace._hovered == _Hit("room", room["id"])


def test_viewport_visibility_controls_keep_room_context(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    other = workspace.layout["rooms"][1]
    room_devices = [
        device
        for device in workspace.layout["devices"]
        if device.get("room_id") == room["id"]
    ]
    workspace.select_item("room", room["id"])

    workspace.isolate_selected()
    app.root.update()
    assert workspace.canvas_2d.find_withtag(f"room:{room['id']}")
    assert not workspace.canvas_2d.find_withtag(f"room:{other['id']}")
    for device in room_devices:
        assert workspace.canvas_2d.find_withtag(f"device:{device['id']}")

    workspace.hide_selected()
    app.root.update()
    assert not workspace.canvas_2d.find_withtag(f"room:{room['id']}")
    for device in room_devices:
        assert not workspace.canvas_2d.find_withtag(f"device:{device['id']}")

    workspace.show_all()
    app.root.update()
    assert workspace.canvas_2d.find_withtag(f"room:{room['id']}")
    assert workspace.canvas_2d.find_withtag(f"room:{other['id']}")


@pytest.mark.parametrize(
    ("preset", "azimuth", "elevation"),
    [
        ("top", 0.0, 90.0),
        ("front", 0.0, 0.0),
        ("back", 180.0, 0.0),
        ("left", 270.0, 0.0),
        ("right", 90.0, 0.0),
        ("iso", 35.0, 28.0),
    ],
)
def test_3d_camera_presets_are_deterministic(app, preset, azimuth, elevation):
    workspace = app.spatial_workspace
    workspace.set_3d_view_preset(preset)
    assert workspace.layout["view"]["azimuth_deg"] == azimuth
    assert workspace.layout["view"]["elevation_deg"] == elevation


def test_distance_and_area_measurements_are_view_only(app):
    workspace = app.spatial_workspace
    metadata_before = copy.deepcopy(app.project.metadata)

    workspace.set_measurement_tool("distance")
    start = workspace._world_to_canvas(0.0, 0.0)
    end = workspace._world_to_canvas(3.0, 4.0)
    workspace._handle_measure_click(*start)
    workspace._handle_measure_click(*end)
    app.root.update()
    assert workspace._measurement_result_var.get() == "Distance 5.000 m"
    assert workspace.canvas_2d.find_withtag("measurement")

    workspace.set_measurement_tool("area")
    start = workspace._world_to_canvas(1.0, 1.0)
    end = workspace._world_to_canvas(3.0, 4.0)
    workspace._handle_measure_click(*start)
    workspace._handle_measure_click(*end)
    app.root.update()
    assert workspace._measurement_result_var.get() == "Area 6.000 m²"
    assert workspace.canvas_2d.find_withtag("measurement")

    workspace.clear_measurement()
    assert workspace._tool_mode.get() == "select"
    assert app.project.metadata == metadata_before


def test_fit_selected_centers_selected_room_without_geometry_changes(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    geometry_before = copy.deepcopy(workspace.layout["rooms"])
    workspace.select_item("room", room["id"])
    workspace.fit_selected()
    app.root.update()

    center_x = room["x_m"] + room["length_m"] / 2.0
    center_y = room["y_m"] + room["width_m"] / 2.0
    screen_x, screen_y = workspace._world_to_canvas(center_x, center_y)
    assert screen_x == pytest.approx(workspace.canvas_2d.winfo_width() / 2.0, abs=2.0)
    assert screen_y == pytest.approx(workspace.canvas_2d.winfo_height() / 2.0, abs=2.0)
    assert workspace.layout["rooms"] == geometry_before



def test_3d_fit_changes_only_3d_camera(app):
    workspace = app.spatial_workspace
    workspace.set_workspace_mode("3d")
    workspace.layout["view"].update(
        {
            "zoom_2d": 2.5,
            "pan_x": 42.0,
            "pan_y": -19.0,
            "zoom_3d": 0.2,
            "pan_3d_x": 500.0,
            "pan_3d_y": -400.0,
        }
    )
    before_2d = (
        workspace.layout["view"]["zoom_2d"],
        workspace.layout["view"]["pan_x"],
        workspace.layout["view"]["pan_y"],
    )

    workspace.fit_3d()

    assert workspace.layout["view"]["zoom_3d"] > 0.2
    assert (
        workspace.layout["view"]["zoom_2d"],
        workspace.layout["view"]["pan_x"],
        workspace.layout["view"]["pan_y"],
    ) == before_2d


def test_3d_xray_and_hover_are_view_only(app):
    workspace = app.spatial_workspace
    workspace.set_workspace_mode("3d")
    room = workspace.layout["rooms"][0]
    metadata_before = copy.deepcopy(app.project.metadata)

    workspace._xray_3d.set(True)
    workspace._draw_3d()
    app.root.update()

    room_items = workspace.canvas_3d.find_withtag(f"room:{room['id']}")
    polygons = [
        item_id
        for item_id in room_items
        if workspace.canvas_3d.type(item_id) == "polygon"
    ]
    assert polygons
    assert any(
        workspace.canvas_3d.itemcget(item_id, "stipple") == "gray50"
        for item_id in polygons
    )

    workspace.canvas_3d.addtag_withtag("current", polygons[0])
    workspace._on_3d_motion(type("Event", (), {"x": 0, "y": 0})())
    assert workspace._hovered_3d == _Hit("room", room["id"])

    workspace._on_3d_leave()
    assert workspace._hovered_3d is None
    assert app.project.metadata == metadata_before


def test_invalid_3d_preset_is_rejected(app):
    with pytest.raises(ValueError, match="3D preset"):
        app.spatial_workspace.set_3d_view_preset("perspective")


def test_3d_projection_and_section_plane_are_display_only(app):
    workspace = app.spatial_workspace
    workspace.set_workspace_mode("3d")
    room = workspace.layout["rooms"][0]
    geometry_before = {
        "rooms": copy.deepcopy(workspace.layout["rooms"]),
        "devices": copy.deepcopy(workspace.layout["devices"]),
    }

    workspace.set_3d_projection("Perspective")
    app.root.update()
    assert workspace.layout["view"]["projection_mode"] == "perspective"
    assert workspace._projection_mode.get() == "Perspective"
    assert workspace.canvas_3d.find_withtag(f"room:{room['id']}")

    z0 = room.get(
        "floor_elevation_m",
        workspace.layout["floor"]["elevation_m"],
    )
    section_z = z0 + room["height_m"] / 2.0
    workspace._section_height_var.set(f"{section_z:.2f}")
    workspace._apply_section_height()
    workspace._section_enabled.set(True)
    workspace._toggle_section_plane()
    app.root.update()

    assert workspace.layout["view"]["section_enabled"] is True
    assert workspace.layout["view"]["section_height_m"] == pytest.approx(section_z)
    assert workspace.canvas_3d.find_withtag("section_plane")
    visible_points = workspace._visible_3d_points()
    assert visible_points
    assert max(point[2] for point in visible_points) <= section_z + 1e-9
    assert workspace.layout["rooms"] == geometry_before["rooms"]
    assert workspace.layout["devices"] == geometry_before["devices"]


def test_invalid_3d_projection_is_rejected(app):
    with pytest.raises(ValueError, match="projection"):
        app.spatial_workspace.set_3d_projection("fisheye")
