"""Real Tk interactions; run with xvfb-run -a python -m pytest -q this_file."""
from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk

import pytest

import cleanroomx.spatial as spatial_module
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_state import load_gui_layout_state
from cleanroomx.project import save_project_document
from cleanroomx.spatial import _Hit


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
        ui_state_path=tmp_path / "gui-layout.json",
    )
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

def test_shell_panels_collapse_and_restore_without_mutating_project(app):
    project_before = copy.deepcopy(app.project.to_dict())

    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)

    app.toggle_navigator_panel()
    app.root.update()
    assert app.navigator_panel_visible_var.get() is False
    assert not app._paned_contains(app.main_panes, app.navigator_panel)

    app.toggle_navigator_panel()
    app.root.update()
    assert app.navigator_panel_visible_var.get() is True
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert tuple(str(item) for item in app.main_panes.panes())[0] == str(
        app.navigator_panel
    )

    app.toggle_output_panel()
    app.root.update()
    assert app.output_panel_visible_var.get() is False
    assert not app._paned_contains(app.workspace_panes, app.output_panel)

    app.toggle_output_panel()
    app.root.update()
    assert app.output_panel_visible_var.get() is True
    assert app._paned_contains(app.workspace_panes, app.output_panel)

    assert app.project.to_dict() == project_before


def test_reset_panel_layout_restores_shell_panels(app):
    app.toggle_navigator_panel()
    app.toggle_output_panel()
    app.root.update()
    assert not app._paned_contains(app.main_panes, app.navigator_panel)
    assert not app._paned_contains(app.workspace_panes, app.output_panel)

    app.reset_panel_layout()
    app.root.update_idletasks()
    app.root.update()

    assert app.navigator_panel_visible_var.get() is True
    assert app.output_panel_visible_var.get() is True
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)

def test_design_inspector_collapses_restores_and_is_view_only(app):
    workspace = app.spatial_workspace
    project_before = copy.deepcopy(app.project.to_dict())

    assert workspace.inspector_visible()

    app.toggle_design_inspector()
    app.root.update()
    assert app.notebook.select() == str(workspace)
    assert not workspace.inspector_visible()

    app.toggle_design_inspector()
    app.root.update()
    assert workspace.inspector_visible()
    assert tuple(str(item) for item in workspace._body.panes())[-1] == str(
        workspace._inspector_frame
    )
    assert app.project.to_dict() == project_before


def test_properties_action_reveals_hidden_design_inspector(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    workspace.set_inspector_visible(False)
    app.root.update()
    assert not workspace.inspector_visible()

    workspace._focus_property("name")
    app.root.update()

    assert workspace.inspector_visible()
    assert workspace._property_entries["name"].focus_get() is not None


def test_reset_panel_layout_restores_design_inspector_too(app):
    workspace = app.spatial_workspace
    workspace.set_inspector_visible(False)
    app.toggle_navigator_panel()
    app.toggle_output_panel()
    app.root.update()

    app.reset_panel_layout()
    app.root.update_idletasks()
    app.root.update()

    assert workspace.inspector_visible()
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)

def test_shell_panel_visibility_persists_across_app_restart(tmp_path):
    state_path = tmp_path / "gui-layout.json"
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")

    first = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root.update()
    first.navigator_panel_visible_var.set(False)
    first._sync_navigator_panel_visibility()
    first.output_panel_visible_var.set(False)
    first._sync_output_panel_visibility()
    first.spatial_workspace.set_inspector_visible(False)
    first._save_ui_layout_state()
    first._autosave_manager.shutdown(wait=False)
    root.destroy()

    root2 = tk.Tk()
    second = CleanroomXApp(
        root2,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root2.update_idletasks()
    root2.update()
    try:
        assert second.navigator_panel_visible_var.get() is False
        assert second.output_panel_visible_var.get() is False
        assert not second._paned_contains(second.main_panes, second.navigator_panel)
        assert not second._paned_contains(
            second.workspace_panes,
            second.output_panel,
        )
        assert not second.spatial_workspace.inspector_visible()
    finally:
        second._autosave_manager.shutdown(wait=False)
        root2.destroy()

def test_theme_switch_is_view_only_and_rethemes_engineering_surfaces(app):
    project_before = copy.deepcopy(app.project.to_dict())

    app.set_theme("dark", persist=False)
    app.root.update_idletasks()
    app.root.update()

    assert app.theme_var.get() == "dark"
    assert app.spatial_workspace.canvas_2d.cget("background") == "#1b222a"
    assert app.spatial_workspace.canvas_3d.cget("background") == "#0d1117"
    assert app.plot_canvas.cget("background") == "#131920"
    assert app.input_text.cget("background") == "#11161c"
    assert app.project.to_dict() == project_before

    app.toggle_theme()
    app.root.update()
    assert app.theme_var.get() == "light"
    assert app.spatial_workspace.canvas_2d.cget("background") == "#f7f9fb"
    assert app.project.to_dict() == project_before


def test_theme_persists_with_ui_layout_across_restart(tmp_path):
    state_path = tmp_path / "gui-theme-layout.json"
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")

    first = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root.update()
    first.set_theme("dark", persist=False)
    first._save_ui_layout_state()
    first._autosave_manager.shutdown(wait=False)
    root.destroy()

    root2 = tk.Tk()
    second = CleanroomXApp(
        root2,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root2.update_idletasks()
    root2.update()
    try:
        assert second.theme_var.get() == "dark"
        assert second.spatial_workspace.canvas_2d.cget("background") == "#1b222a"
        assert second.spatial_workspace.canvas_3d.cget("background") == "#0d1117"
        assert second.plot_canvas.cget("background") == "#131920"
    finally:
        second._autosave_manager.shutdown(wait=False)
        root2.destroy()

def test_application_command_strip_remains_visible_at_minimum_window(app):
    app.root.geometry("1050x680")
    app.root.update()

    buttons = (
        app.toolbar_new_button,
        app.toolbar_open_button,
        app.toolbar_save_button,
        app.toolbar_undo_button,
        app.toolbar_redo_button,
        app.toolbar_fit_button,
        app.toolbar_problems_button,
        app.toolbar_workspace_button,
        app.toolbar_commands_button,
    )
    for button in buttons:
        assert button.winfo_ismapped(), button.cget("text")
        assert button.winfo_x() + button.winfo_width() <= app.commandbar.winfo_width()


def test_guided_workflow_is_visible_at_minimum_window_and_opens_design(app):
    app.root.geometry("1050x680")
    app.root.update()

    buttons = (
        app.workflow_design_button,
        app.workflow_input_button,
        app.workflow_validate_button,
        app.workflow_run_button,
        app.workflow_verify_button,
        app.workflow_report_button,
    )
    for button in buttons:
        assert button.winfo_ismapped(), button.cget("text")
        assert button.winfo_x() + button.winfo_width() <= app.workflowbar.winfo_width()

    app.notebook.select(app.start_center)
    app.workflow_design_button.invoke()
    app.root.update()

    assert app.notebook.select() == str(app.spatial_workspace)
    assert app.workspace_status_var.get() == "Workspace: Split"

    project_before = copy.deepcopy(app.project.to_dict())
    app.workflow_input_button.invoke()
    app.root.update()
    assert app.notebook.select() == str(app.input_tab)
    assert app.workspace_status_var.get() == "Workspace: Analysis Inputs"
    assert app.project.to_dict() == project_before


def test_guided_save_and_verify_saves_dirty_project_before_verification(
    app, monkeypatch, tmp_path
):
    calls: list[str] = []
    app.project_path = tmp_path / "guided.cleanroomx.json"
    dirty_states = iter((True, False))
    monkeypatch.setattr(app, "_has_unsaved_changes", lambda: next(dirty_states))
    monkeypatch.setattr(app, "save_project", lambda: calls.append("save"))
    monkeypatch.setattr(
        app,
        "run_project_requirements_verification",
        lambda: calls.append("verify"),
    )

    app._guided_save_and_verify()

    assert calls == ["save", "verify"]
    assert app.workflow_verify_button.cget("text") == "5  Save & Verify"


def test_navigator_quick_actions_route_to_existing_commands(app, monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(app, "add_analysis", lambda: calls.append("analysis"))
    monkeypatch.setattr(
        app.spatial_workspace,
        "add_room",
        lambda: calls.append("room"),
    )
    monkeypatch.setattr(
        app,
        "import_ifc_spatial_layout",
        lambda: calls.append("ifc"),
    )

    app.navigator_add_analysis_button.invoke()
    app.navigator_add_room_button.invoke()
    app.navigator_import_ifc_button.invoke()

    assert calls == ["analysis", "room", "ifc"]
    assert app.navigator_add_analysis_button.cget("text") == "+ Analysis"
    assert app.navigator_add_room_button.cget("text") == "+ Room"
    assert "Import IFC" in app.navigator_import_ifc_button.cget("text")


def test_panel_header_close_controls_and_problems_navigation(app):
    workspace = app.spatial_workspace

    app.navigator_close_button.invoke()
    app.root.update()
    assert not app._paned_contains(app.main_panes, app.navigator_panel)

    app.output_close_button.invoke()
    app.root.update()
    assert not app._paned_contains(app.workspace_panes, app.output_panel)

    app.show_problems_panel()
    app.root.update()
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.output_notebook.select() == str(app.problems_panel)

    workspace._inspector_close_button.invoke()
    app.root.update()
    assert not workspace.inspector_visible()


def test_command_strip_undo_redo_states_follow_project_history(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"])
    assert str(app.toolbar_undo_button.cget("state")) == "disabled"

    workspace.duplicate_selected()
    app.root.update()
    assert str(app.toolbar_undo_button.cget("state")) == "normal"

    assert app.undo_project_edit()
    app.root.update()
    assert str(app.toolbar_redo_button.cget("state")) == "normal"

def test_focus_workspace_hides_chrome_and_restores_exact_visibility(app):
    workspace = app.spatial_workspace
    project_before = copy.deepcopy(app.project.to_dict())

    app.navigator_panel_visible_var.set(False)
    app._sync_navigator_panel_visibility()
    app.output_panel_visible_var.set(True)
    app._sync_output_panel_visibility()
    workspace.set_inspector_visible(False)
    app.root.update()

    app.set_focus_workspace(True)
    app.root.update()
    assert app.focus_workspace_var.get() is True
    assert not app._paned_contains(app.main_panes, app.navigator_panel)
    assert not app._paned_contains(app.workspace_panes, app.output_panel)
    assert not workspace.inspector_visible()

    app.set_focus_workspace(False)
    app.root.update()
    assert app.focus_workspace_var.get() is False
    assert not app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert not workspace.inspector_visible()
    assert app.project.to_dict() == project_before


def test_focus_workspace_does_not_persist_hidden_panel_state(app):
    workspace = app.spatial_workspace
    app.navigator_panel_visible_var.set(True)
    app._sync_navigator_panel_visibility()
    app.output_panel_visible_var.set(False)
    app._sync_output_panel_visibility()
    workspace.set_inspector_visible(True)
    app.root.update()

    app.set_focus_workspace(True)
    app.root.update()
    state = app._capture_ui_layout_state()

    assert state["navigator_visible"] is True
    assert state["output_visible"] is False
    assert state["inspector_visible"] is True


def test_manual_panel_toggle_exits_focus_workspace_cleanly(app):
    workspace = app.spatial_workspace
    app.set_focus_workspace(True)
    app.root.update()
    assert app.focus_workspace_var.get() is True

    app.toggle_navigator_panel()
    app.root.update()

    assert app.focus_workspace_var.get() is False
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert workspace.inspector_visible()

def test_status_bar_uses_human_readable_spatial_selection_context(app):
    workspace = app.spatial_workspace
    project_before = copy.deepcopy(app.project.to_dict())
    room = workspace.layout["rooms"][0]

    assert workspace.select_item("room", room["id"], notify=True)
    app.root.update()
    room_status = app.selection_status_var.get()
    assert room_status.startswith("Room: ")
    assert str(room["name"]) in room_status
    classification = str(room.get("classification") or "").strip()
    if classification:
        assert classification in room_status

    if workspace.layout["devices"]:
        device = workspace.layout["devices"][0]
        assert workspace.select_item("device", device["id"], notify=True)
        app.root.update()
        device_status = app.selection_status_var.get()
        assert str(device.get("name") or device["id"]) in device_status
        assert str(device.get("type") or "device").replace("_", " ").title() in device_status

    assert app.project.to_dict() == project_before


def test_status_bar_tracks_live_viewport_mode_zoom_and_projection(app):
    workspace = app.spatial_workspace
    workspace.layout["view"]["zoom_2d"] = 1.25
    workspace.layout["view"]["zoom_3d"] = 1.50
    workspace.layout["view"]["projection_mode"] = "perspective"

    workspace.set_workspace_mode("split")
    app.root.update()

    status = app.view_status_var.get()
    assert status == "Split · 2D 125% · 3D 150% · Perspective"

    workspace.set_workspace_mode("2d")
    app.root.update()
    assert app.view_status_var.get().startswith("2D · 2D 125%")

    workspace.set_workspace_mode("3d")
    app.root.update()
    assert app.view_status_var.get().startswith("3D · 2D 125%")

def test_recent_projects_persist_across_application_restart(tmp_path):
    state_path = tmp_path / "gui-layout.json"
    project_a = tmp_path / "alpha.cleanroomx.json"
    project_b = tmp_path / "beta.cleanroomx.json"
    project_a.write_text("{}", encoding="utf-8")
    project_b.write_text("{}", encoding="utf-8")

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")

    first = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root.update()
    first._remember_recent_project(project_a)
    first._remember_recent_project(project_b)
    first._autosave_manager.shutdown(wait=False)
    root.destroy()

    root2 = tk.Tk()
    second = CleanroomXApp(
        root2,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root2.update_idletasks()
    root2.update()
    try:
        assert second._recent_project_paths == [
            project_b.resolve(),
            project_a.resolve(),
        ]
        records = second._recent_project_records()
        assert [record["name"] for record in records] == ["beta", "alpha"]
        assert all(record["modified"] != "Unavailable" for record in records)
    finally:
        second._autosave_manager.shutdown(wait=False)
        root2.destroy()


def test_forget_recent_project_updates_persisted_preferences(app, tmp_path):
    project_a = tmp_path / "alpha.cleanroomx.json"
    project_b = tmp_path / "beta.cleanroomx.json"
    app._recent_project_paths.clear()
    app._save_ui_layout_state()
    app._remember_recent_project(project_a)
    app._remember_recent_project(project_b)

    app._forget_recent_project(project_b)

    assert app._recent_project_paths == [project_a.resolve()]
    state = load_gui_layout_state(app._ui_state_path)
    assert state["recent_projects"] == [str(project_a.resolve())]

def test_window_size_persists_across_application_restart(tmp_path):
    state_path = tmp_path / "gui-window-layout.json"
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")

    first = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root.geometry("1220x760")
    root.update_idletasks()
    root.update()
    first._save_ui_layout_state()
    first._autosave_manager.shutdown(wait=False)
    root.destroy()

    root2 = tk.Tk()
    second = CleanroomXApp(
        root2,
        autosave_interval_seconds=0,
        ui_state_path=state_path,
    )
    root2.update_idletasks()
    root2.update()
    try:
        expected_width = min(1220, root2.winfo_screenwidth())
        expected_height = min(760, root2.winfo_screenheight())
        assert root2.winfo_width() == expected_width
        assert root2.winfo_height() == expected_height
        state = load_gui_layout_state(state_path)
        assert state["window_width"] == expected_width
        assert state["window_height"] == expected_height
    finally:
        second._autosave_manager.shutdown(wait=False)
        root2.destroy()




def test_floor_properties_apply_as_one_transaction_and_preserve_cancel_safety(
    app,
    monkeypatch,
):
    workspace = app.spatial_workspace
    before = copy.deepcopy(workspace.layout)

    class AcceptedDialog:
        result = {
            "name": "Production Level",
            "elevation_m": 1.25,
            "default_ceiling_height_m": 3.6,
            "grid_m": 0.25,
        }

    monkeypatch.setattr(
        spatial_module,
        "FloorPropertiesDialog",
        lambda *args, **kwargs: AcceptedDialog(),
    )
    monkeypatch.setattr(workspace, "wait_window", lambda dialog: None)

    workspace.edit_floor()
    app.root.update()

    assert workspace.layout["floor"]["name"] == "Production Level"
    assert workspace.layout["floor"]["elevation_m"] == 1.25
    assert workspace.layout["floor"]["default_ceiling_height_m"] == 3.6
    assert workspace.layout["grid_m"] == 0.25
    assert app.project.metadata["spatial_layout"] == workspace.layout

    assert app.undo_project_edit()
    assert workspace.layout == before
    assert app.redo_project_edit()
    applied = copy.deepcopy(workspace.layout)

    class CancelledDialog:
        result = None

    monkeypatch.setattr(
        spatial_module,
        "FloorPropertiesDialog",
        lambda *args, **kwargs: CancelledDialog(),
    )
    workspace.edit_floor()
    app.root.update()
    assert workspace.layout == applied

def test_workspace_profiles_switch_surfaces_and_panels_without_project_mutation(app):
    project_before = copy.deepcopy(app.project.to_dict())

    app.activate_workspace_profile("verification", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "verification"
    assert app.notebook.select() == str(app.spatial_workspace)
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.output_notebook.select() == str(app.problems_panel)
    assert app.spatial_workspace.inspector_visible()

    app.activate_workspace_profile("evidence", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "evidence"
    assert app.notebook.select() == str(app.proofgraph_viewer)
    assert app.output_notebook.select() == str(app.evidence_text.master)
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert not app.spatial_workspace.inspector_visible()

    app.activate_workspace_profile("reporting", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "reporting"
    assert app.notebook.select() == str(app.plot_tab)
    assert app.output_notebook.select() == str(app.report_text.master)
    assert not app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert not app.spatial_workspace.inspector_visible()

    assert app.project.to_dict() == project_before


def test_workspace_profiles_preserve_independent_visibility_layouts(app):
    app.activate_workspace_profile("verification", persist=False)
    app.root.update()

    app.navigator_panel_visible_var.set(False)
    app._sync_navigator_panel_visibility()
    app.spatial_workspace.set_inspector_visible(False)
    app.root.update()

    app.activate_workspace_profile("design", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "design"
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert not app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.spatial_workspace.inspector_visible()

    app.activate_workspace_profile("verification", persist=False)
    app.root.update()
    assert app.workspace_profile_var.get() == "verification"
    assert not app._paned_contains(app.main_panes, app.navigator_panel)
    assert app._paned_contains(app.workspace_panes, app.output_panel)
    assert not app.spatial_workspace.inspector_visible()


def test_workspace_profile_reset_only_resets_active_workspace(app):
    app.activate_workspace_profile("verification", persist=False)
    app.navigator_panel_visible_var.set(False)
    app._sync_navigator_panel_visibility()
    app.spatial_workspace.set_inspector_visible(False)
    app.root.update()

    app.activate_workspace_profile("design", persist=False)
    app.root.update()
    verification_before = copy.deepcopy(
        app._ui_layout_state["workspace_layouts"]["verification"]
    )

    app.reset_panel_layout()
    app.root.update()
    assert app.workspace_profile_var.get() == "design"
    assert app._paned_contains(app.main_panes, app.navigator_panel)
    assert not app._paned_contains(app.workspace_panes, app.output_panel)
    assert app.spatial_workspace.inspector_visible()
    assert app._ui_layout_state["workspace_layouts"]["verification"] == verification_before


def test_workspace_profile_rejects_unknown_profile(app):
    with pytest.raises(ValueError, match="unsupported GUI workspace profile"):
        app.activate_workspace_profile("thermal-lab", persist=False)

def test_fullscreen_workspace_is_explicit_reversible_window_state(app):
    app.set_fullscreen_workspace(True)
    app.root.update_idletasks()

    assert app.fullscreen_var.get() is True
    assert bool(app.root.attributes("-fullscreen")) is True
    assert "Full-screen workspace enabled" in app.status_var.get()

    app.exit_fullscreen_workspace()
    app.root.update_idletasks()

    assert app.fullscreen_var.get() is False
    assert bool(app.root.attributes("-fullscreen")) is False

def test_top_level_menus_use_engineering_workflow_names(app):
    end = app.menubar.index("end")
    assert end is not None
    labels = [
        app.menubar.entrycget(index, "label")
        for index in range(end + 1)
    ]

    for label in (
        "File",
        "Edit",
        "Design",
        "Simulation",
        "Verification",
        "Evidence",
        "Reports",
        "Tools",
        "View",
        "Help",
    ):
        assert label in labels
    assert "Analyze" not in labels
    assert "Verify" not in labels
    assert "Report" not in labels

    evidence_index = labels.index("Evidence")
    evidence_menu = app.menubar.nametowidget(
        app.menubar.entrycget(evidence_index, "menu")
    )
    evidence_labels = [
        evidence_menu.entrycget(index, "label")
        for index in range(evidence_menu.index("end") + 1)
        if evidence_menu.type(index) != "separator"
    ]
    assert evidence_labels == [
        "Evidence Workspace",
        "ProofGraph Explorer",
        "Requirements Traceability...",
    ]


def test_multi_selection_inspector_exposes_mixed_values_and_applies_batch_edit(app):
    workspace = app.spatial_workspace
    first, second = workspace.layout["rooms"][:2]
    first["pressure_pa"] = 10.0
    second["pressure_pa"] = 25.0

    workspace._set_selected_hits(
        [_Hit("room", first["id"]), _Hit("room", second["id"])]
    )
    workspace._load_property_panel()
    app.root.update()

    assert workspace._property_vars["pressure_pa"].get() == "— Mixed —"
    assert "2 rooms selected" in workspace._selection_var.get()
    assert "2 selected" in workspace._property_filter_summary_var.get()
    assert str(workspace._property_apply_button.cget("text")) == "Apply to 2 objects"
    assert not workspace._property_rows["name"].winfo_manager()
    assert workspace._property_rows["pressure_pa"].winfo_manager()

    workspace._property_vars["pressure_pa"].set("17.5")
    workspace._on_property_edit()
    assert "modified" in workspace._property_filter_summary_var.get()

    workspace.apply_properties()
    app.root.update()

    current = {room["id"]: room for room in workspace.layout["rooms"]}
    assert current[first["id"]]["pressure_pa"] == pytest.approx(17.5)
    assert current[second["id"]]["pressure_pa"] == pytest.approx(17.5)
    assert "2 rooms selected" in workspace._selection_var.get()


def test_multi_selection_inspector_refuses_cross_kind_batch_edit(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    device = workspace.layout["devices"][0]

    workspace._set_selected_hits(
        [_Hit("room", room["id"]), _Hit("device", device["id"])]
    )
    workspace._load_property_panel()
    app.root.update()

    assert "batch editing requires" in workspace._selection_var.get()
    assert str(workspace._property_apply_button.cget("state")) == "disabled"
    assert workspace._editable_property_fields() == set()


def test_property_draft_survives_selection_change_and_can_be_reverted(app):
    workspace = app.spatial_workspace
    first, second = workspace.layout["rooms"][:2]
    original_name = first["name"]

    workspace.select_item("room", first["id"])
    workspace._property_vars["name"].set("Pending room name")
    workspace._on_property_edit()
    assert "modified" in workspace._property_filter_summary_var.get()
    assert str(workspace._property_revert_button.cget("state")) == "normal"

    workspace.select_item("room", second["id"])
    workspace.select_item("room", first["id"])
    app.root.update()

    assert workspace._property_vars["name"].get() == "Pending room name"
    assert first["name"] == original_name
    assert "modified" in workspace._property_filter_summary_var.get()

    workspace.revert_property_edits()
    app.root.update()

    assert workspace._property_vars["name"].get() == original_name
    assert "modified" not in workspace._property_filter_summary_var.get()
    assert str(workspace._property_revert_button.cget("state")) == "disabled"


def test_canvas_rulers_toggle_without_mutating_spatial_project_data(app):
    workspace = app.spatial_workspace
    before = copy.deepcopy(workspace.layout)

    workspace._show_rulers.set(True)
    workspace.redraw()
    app.root.update()
    assert workspace.canvas_2d.find_withtag("ruler")

    workspace._show_rulers.set(False)
    workspace.redraw()
    app.root.update()
    assert not workspace.canvas_2d.find_withtag("ruler")
    assert workspace.layout == before


def test_device_category_visibility_filters_canvas_without_mutating_project(app):
    workspace = app.spatial_workspace
    device = workspace.layout["devices"][0]
    device_type = device["type"]
    before = copy.deepcopy(workspace.layout)

    assert workspace._is_item_visible("device", device["id"])
    workspace.set_device_type_visible(device_type, False)
    app.root.update()

    assert not workspace._is_item_visible("device", device["id"])
    assert not workspace.canvas_2d.find_withtag(f"device:{device['id']}")
    assert workspace.layout == before
    assert f"/{len(workspace._device_type_visibility_vars)}" in str(
        workspace._device_categories_button.cget("text")
    )

    workspace.set_device_type_visible(device_type, True)
    app.root.update()

    assert workspace._is_item_visible("device", device["id"])
    assert workspace.canvas_2d.find_withtag(f"device:{device['id']}")
    assert workspace.layout == before


def test_device_category_visibility_supports_show_hide_all(app):
    workspace = app.spatial_workspace

    workspace.set_all_device_types_visible(False)
    app.root.update()
    assert workspace._visible_device_type_count() == 0
    assert all(
        not workspace._is_item_visible("device", device["id"])
        for device in workspace.layout["devices"]
    )

    workspace.set_all_device_types_visible(True)
    app.root.update()
    assert workspace._visible_device_type_count() == len(
        workspace._device_type_visibility_vars
    )
    assert all(
        workspace._is_item_visible("device", device["id"])
        for device in workspace.layout["devices"]
    )


def test_multi_selection_drag_moves_group_and_owned_devices_once(app):
    workspace = app.spatial_workspace
    rooms = workspace.layout["rooms"]
    assert len(rooms) >= 2
    first, second = rooms[:2]
    selected_room_ids = {first["id"], second["id"]}
    first_hit = _Hit("room", first["id"])
    second_hit = _Hit("room", second["id"])
    workspace._set_selected_hits([first_hit, second_hit])
    workspace._load_property_panel()

    before_rooms = {
        room["id"]: (room["x_m"], room["y_m"])
        for room in workspace.layout["rooms"]
        if room["id"] in selected_room_ids
    }
    before_devices = {
        device["id"]: (device["x_m"], device["y_m"])
        for device in workspace.layout["devices"]
        if device.get("room_id") in selected_room_ids
    }

    primary = second
    room_item = workspace.canvas_2d.find_withtag(f"room:{primary['id']}")[0]
    for item_id in workspace.canvas_2d.find_withtag("current"):
        workspace.canvas_2d.dtag(item_id, "current")
    workspace.canvas_2d.addtag_withtag("current", room_item)

    center_x = primary["x_m"] + primary["length_m"] / 2
    center_y = primary["y_m"] + primary["width_m"] / 2
    down_x, down_y = workspace._world_to_canvas(center_x, center_y)
    drag_x, drag_y = workspace._world_to_canvas(center_x + 1.0, center_y)
    down = type(
        "Event",
        (),
        {"x": int(down_x), "y": int(down_y), "state": 0},
    )()
    drag = type(
        "Event",
        (),
        {"x": int(drag_x), "y": int(drag_y), "state": 0},
    )()

    workspace._on_left_down(down)
    assert workspace.selected_hits() == (first_hit, second_hit)
    workspace._on_left_drag(drag)
    workspace._on_left_up(drag)
    app.root.update()

    for room in workspace.layout["rooms"]:
        if room["id"] not in selected_room_ids:
            continue
        before_x, before_y = before_rooms[room["id"]]
        assert room["x_m"] == pytest.approx(before_x + 1.0)
        assert room["y_m"] == pytest.approx(before_y)

    for device in workspace.layout["devices"]:
        if device["id"] not in before_devices:
            continue
        before_x, before_y = before_devices[device["id"]]
        assert device["x_m"] == pytest.approx(before_x + 1.0)
        assert device["y_m"] == pytest.approx(before_y)

    assert app.undo_project_edit() is True
    app.root.update()
    for room in workspace.layout["rooms"]:
        if room["id"] in before_rooms:
            assert (room["x_m"], room["y_m"]) == before_rooms[room["id"]]
    for device in workspace.layout["devices"]:
        if device["id"] in before_devices:
            assert (device["x_m"], device["y_m"]) == before_devices[device["id"]]


def test_multi_selection_bulk_hide_delete_and_undo(app):
    workspace = app.spatial_workspace
    rooms = workspace.layout["rooms"]
    assert len(rooms) >= 2
    first_hit = _Hit("room", rooms[0]["id"])
    second_hit = _Hit("room", rooms[1]["id"])
    original_room_count = len(rooms)

    workspace._set_selected_hits([first_hit, second_hit])
    workspace._load_property_panel()
    workspace.hide_selected()
    app.root.update()

    assert not workspace._is_item_visible(first_hit.kind, first_hit.item_id)
    assert not workspace._is_item_visible(second_hit.kind, second_hit.item_id)
    workspace.show_all()
    assert workspace._is_item_visible(first_hit.kind, first_hit.item_id)
    assert workspace._is_item_visible(second_hit.kind, second_hit.item_id)

    workspace.delete_selected()
    app.root.update()

    assert len(workspace.layout["rooms"]) == original_room_count - 2
    assert workspace.selected_hits() == ()
    assert app.undo_project_edit() is True
    app.root.update()
    assert len(workspace.layout["rooms"]) == original_room_count
    assert any(room["id"] == first_hit.item_id for room in workspace.layout["rooms"])
    assert any(room["id"] == second_hit.item_id for room in workspace.layout["rooms"])


def test_marquee_selection_selects_visible_spatial_objects_without_mutation(app):
    workspace = app.spatial_workspace
    rooms = workspace.layout["rooms"]
    assert len(rooms) >= 2
    project_before = copy.deepcopy(app.project.to_dict())

    room_points = []
    for room in rooms[:2]:
        x0, y0 = workspace._world_to_canvas(room["x_m"], room["y_m"])
        x1, y1 = workspace._world_to_canvas(
            room["x_m"] + room["length_m"],
            room["y_m"] + room["width_m"],
        )
        room_points.extend(((x0, y0), (x1, y1)))
    left = int(min(point[0] for point in room_points) - 8)
    top = int(min(point[1] for point in room_points) - 8)
    right = int(max(point[0] for point in room_points) + 8)
    bottom = int(max(point[1] for point in room_points) + 8)

    for item_id in workspace.canvas_2d.find_withtag("current"):
        workspace.canvas_2d.dtag(item_id, "current")
    down = type("Event", (), {"x": left, "y": top, "state": 0})()
    drag = type("Event", (), {"x": right, "y": bottom, "state": 0})()
    up = type("Event", (), {"x": right, "y": bottom, "state": 0})()

    workspace._on_left_down(down)
    workspace._on_left_drag(drag)
    assert workspace.canvas_2d.find_withtag("selection_box")
    workspace._on_left_up(up)
    app.root.update()

    selected = set(workspace.selected_hits())
    assert _Hit("room", rooms[0]["id"]) in selected
    assert _Hit("room", rooms[1]["id"]) in selected
    assert len(selected) >= 2
    assert workspace.canvas_2d.find_withtag("selection_box") == ()
    assert app.selection_status_var.get().startswith(
        f"Selected: {len(selected)} objects ·"
    )
    assert app.project.to_dict() == project_before


def test_shift_and_control_click_support_non_mutating_multi_selection(app):
    workspace = app.spatial_workspace
    rooms = workspace.layout["rooms"]
    assert len(rooms) >= 2
    first, second = rooms[:2]
    project_before = copy.deepcopy(app.project.to_dict())

    assert workspace.select_item("room", first["id"], notify=True)
    first_hit = _Hit("room", first["id"])
    second_hit = _Hit("room", second["id"])
    assert workspace.selected_hits() == (first_hit,)

    second_item = workspace.canvas_2d.find_withtag(f"room:{second['id']}")[0]
    for item_id in workspace.canvas_2d.find_withtag("current"):
        workspace.canvas_2d.dtag(item_id, "current")
    workspace.canvas_2d.addtag_withtag("current", second_item)
    sx, sy = workspace._world_to_canvas(
        second["x_m"] + second["length_m"] / 2,
        second["y_m"] + second["width_m"] / 2,
    )
    shift_event = type(
        "Event",
        (),
        {"x": int(sx), "y": int(sy), "state": 0x0001},
    )()

    workspace._on_left_down(shift_event)
    app.root.update()

    assert workspace.selected == second_hit
    assert workspace.selected_hits() == (first_hit, second_hit)
    assert workspace.selection_status_text().startswith("Selected: 2 objects ·")
    assert app.selection_status_var.get().startswith("Selected: 2 objects ·")
    assert workspace._drag_anchor is None
    assert app.project.to_dict() == project_before

    control_event = type(
        "Event",
        (),
        {"x": int(sx), "y": int(sy), "state": 0x0004},
    )()
    workspace._on_left_down(control_event)
    app.root.update()

    assert workspace.selected == first_hit
    assert workspace.selected_hits() == (first_hit,)
    assert app.project.to_dict() == project_before

    for item_id in workspace.canvas_2d.find_withtag("current"):
        workspace.canvas_2d.dtag(item_id, "current")
    clear_event = type("Event", (), {"x": 0, "y": 0, "state": 0})()
    workspace._on_left_down(clear_event)
    app.root.update()

    assert workspace.selected is None
    assert workspace.selected_hits() == ()
    assert app.selection_status_var.get() == "Selected: —"
    assert app.project.to_dict() == project_before
