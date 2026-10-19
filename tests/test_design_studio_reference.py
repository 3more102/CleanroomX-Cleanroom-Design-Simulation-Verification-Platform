"""Regression coverage for model-backed Design Studio reference controls."""

from __future__ import annotations

import copy
import json
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.studio_summary import dashboard_snapshot, navigator_rectangles


def demo_layout() -> dict:
    payload = json.loads(bundled_demo_project_path().read_text(encoding="utf-8"))
    return payload["project"]["metadata"]["spatial_layout"]


def test_reference_demo_cards_derive_from_model_not_constants():
    layout = demo_layout()
    original = copy.deepcopy(layout)
    snapshot = dashboard_snapshot(layout, "process")
    assert snapshot["room_count"] == 3
    assert snapshot["floor_area_m2"] == pytest.approx(62)
    assert snapshot["volume_m3"] == pytest.approx(186)
    assert snapshot["placed_devices"] == 10
    assert snapshot["device_groups"] == {
        "ffu": 1, "supply": 2, "return_exhaust": 2, "other": 5
    }
    room = snapshot["selected_room"]
    assert room is not None
    assert room["name"] == "Process"
    assert room["length_m"] == pytest.approx(6)
    assert room["width_m"] == pytest.approx(5)
    assert room["height_m"] == pytest.approx(3)
    assert room["floor_area_m2"] == pytest.approx(30)
    assert room["volume_m3"] == pytest.approx(90)
    assert room["device_count"] == 5
    assert room["device_groups"] == {"ffu": 1, "supply": 1, "return_exhaust": 1, "other": 2}
    assert room["pressure_setpoint_pa"] == 30
    assert layout == original


def test_live_metrics_change_with_room_device_modification():
    layout = demo_layout()
    before = dashboard_snapshot(layout, "process")
    layout["rooms"][0]["length_m"] = 8
    layout["devices"].pop()
    after = dashboard_snapshot(layout, "process")
    assert after["floor_area_m2"] == pytest.approx(before["floor_area_m2"] + 10)
    assert after["volume_m3"] == pytest.approx(before["volume_m3"] + 30)
    assert after["placed_devices"] == before["placed_devices"] - 1
    assert after["selected_room"]["floor_area_m2"] == pytest.approx(40)
    layout["rooms"].pop(0)
    assert dashboard_snapshot(layout, "process")["selected_room"] is None


def test_navigator_preserves_geometry_relative_positions_and_bounds():
    layout = demo_layout()
    original = copy.deepcopy(layout)
    rects = navigator_rectangles(layout)
    assert [r["id"] for r in rects] == ["process", "preparation", "ante"]
    assert rects[0]["rect"][2] < rects[1]["rect"][0]
    assert rects[1]["rect"][2] < rects[2]["rect"][0]
    for room in rects:
        x0, y0, x1, y1 = room["rect"]
        assert 0 <= x0 < x1 <= 240
        assert 0 <= y0 < y1 <= 150
    assert rects[0]["floor_area_m2"] == pytest.approx(30)
    assert navigator_rectangles({"rooms": []}) == []
    assert layout == original


@pytest.fixture
def gui(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    app = CleanroomXApp(root, autosave_interval_seconds=0,
                        ui_state_path=tmp_path / "studio-layout.json")
    app.load_project_path(bundled_demo_project_path())
    app.notebook.select(app.spatial_workspace)
    root.update()
    try:
        yield app
        assert errors == []
    finally:
        root.destroy()


def test_gui_cards_and_room_inspector_are_live(gui):
    ws = gui.spatial_workspace
    assert {key: var.get() for key, var in ws._studio_card_vars.items()} == {
        "rooms": "3", "area": "62.0", "volume": "186.0", "devices": "10"
    }
    assert set(ws._navigator_item_to_room.values()) == {
        r["id"] for r in ws.layout["rooms"]
    }
    assert ws.select_item("room", "process", notify=True)
    assert "Process" in ws._studio_room_var.get()
    assert "30 Pa (configured)" in ws._studio_room_var.get()
    assert "FFU 1" in ws._studio_devices_var.get()
    ws.duplicate_selected()
    gui.root.update()
    assert ws._studio_card_vars["rooms"].get() == "4"
    assert ws._studio_card_vars["area"].get() == "92.0"
    assert ws._studio_card_vars["volume"].get() == "276.0"


def test_gui_focus_isolate_restore_and_studio_view(gui):
    ws = gui.spatial_workspace
    assert ws.select_item("room", "process", notify=True)
    ws.focus_room()
    ws.isolate_room()
    assert ws._is_item_visible("room", "process")
    assert not ws._is_item_visible("room", "preparation")
    ws.show_all()
    assert ws._is_item_visible("room", "preparation")
    ws.studio_view()
    gui.root.update()
    assert ws._workspace_mode.get() == "3d"
    assert not ws.inspector_visible()  # Live room cards occupy the viewport instead.
    assert ws.canvas_3d.find_withtag("studio-ui")
    assert not gui.navigator_panel_visible_var.get()
    assert not gui.output_panel_visible_var.get()


def test_room_device_search_uses_shared_selection(gui):
    ws = gui.spatial_workspace
    ws._studio_search_var.set("Ante")
    assert ws.find_design_item()
    assert ws.selected is not None
    assert ws.selected.kind == "room"
    assert ws.selected.item_id == "ante"
    assert "Ante / Airlock" in ws._studio_room_var.get()
    ws._studio_search_var.set("no such device")
    assert not ws.find_design_item()
    assert ws.selected.item_id == "ante"

def test_guided_stage_tracks_design_and_inputs_instead_of_highlighting_run(gui):
    gui.notebook.select(gui.spatial_workspace)
    gui.root.update()
    assert gui.workflow_design_button.cget("style") == "CX.Primary.TButton"
    assert gui.workflow_run_button.cget("style") == "CX.Compact.TButton"

    gui.notebook.select(gui.input_tab)
    gui.root.update()
    assert gui.workflow_input_button.cget("style") == "CX.Primary.TButton"
    assert gui.workflow_design_button.cget("style") == "CX.Compact.TButton"

    gui.notebook.select(gui.spatial_workspace)
    gui.root.update()
    assert gui.workflow_design_button.cget("style") == "CX.Primary.TButton"

def test_real_3d_scene_renders_camera_oriented_xyz_axis_widget(gui):
    gui.root.geometry("1920x1080")
    ws = gui.spatial_workspace
    ws.studio_view()
    ws.show_inspector()  # Leaves room for the axis widget on small native displays.
    gui.root.update()
    axes = ws.canvas_3d.find_withtag("studio-axis")
    assert len(axes) >= 7  # lines + labels for X/Y/Z, and origin marker
    before = [ws.canvas_3d.coords(item) for item in axes[:2]]
    ws.rotate_3d(15)
    gui.root.update()
    after = [ws.canvas_3d.coords(item) for item in ws.canvas_3d.find_withtag("studio-axis")[:2]]
    assert before != after

def test_dark_engineering_legend_respects_studio_palette(gui):
    gui.set_theme("dark", persist=False)
    ws = gui.spatial_workspace
    ws.redraw()
    gui.root.update()
    legend = ws.canvas_3d.find_withtag("overlay_legend")
    assert legend
    assert ws.canvas_3d.itemcget(legend[0], "fill") == ws._theme_palette["panel"]


def click_tag(canvas, tag):
    items = canvas.find_withtag(tag)
    assert items, f"Missing visible control: {tag}"
    x0, y0, x1, y1 = canvas.bbox(items[-1])
    x, y = round((x0 + x1) / 2), round((y0 + y1) / 2)
    canvas.event_generate("<Motion>", x=x, y=y)
    canvas.update()
    canvas.event_generate("<Button-1>", x=x, y=y)
    canvas.update()


def test_studio_entry_opens_reference_chrome_and_true_cutaway_geometry(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    assert gui.theme_var.get() == "dark"
    assert gui.workspace_status_var.get() == "Workspace: Design"
    assert ws._studio_active
    assert len(ws.canvas_3d.find_withtag("studio-wall")) == 6
    assert len(ws.canvas_3d.find_withtag("studio-floor")) == 3
    assert len(ws.canvas_3d.find_withtag("studio-opening")) == 4
    assert len(ws.canvas_3d.find_withtag("studio-room-label")) == 6
    assert not ws.canvas_3d.find_withtag("studio-roof")
    assert not ws._viewbar.winfo_ismapped()
    assert ws._studio_find_button.winfo_ismapped()
    assert not gui.root.cget("menu")
    assert ws.selected.item_id == "process"
    ws._interior_3d.set(False)
    ws._draw_3d()
    assert len(ws.canvas_3d.find_withtag("studio-roof")) == 3


def test_real_navigator_and_scene_clicks_share_room_selection(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    click_tag(ws.navigator_canvas, "navigator-room:preparation")
    assert ws.selected.item_id == "preparation"
    assert "Preparation" in ws._studio_room_var.get()
    assert "FFU 0" in ws._studio_devices_var.get()
    click_tag(ws.canvas_3d, "room:ante")
    assert ws.selected.item_id == "ante"
    assert "Other 2" in ws._studio_devices_var.get()
    ws._navigate_studio_room(1)
    assert ws.selected.item_id == "process"
    assert "Supply 1" in ws._studio_devices_var.get()


def test_visible_focus_isolate_restore_and_camera_buttons_are_functional(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    initial_zoom = ws.layout["view"]["zoom_3d"]
    click_tag(ws.canvas_3d, "studio-action:focus")
    assert ws.layout["view"]["zoom_3d"] > initial_zoom
    click_tag(ws.canvas_3d, "studio-action:isolate")
    assert ws.canvas_3d.find_withtag("room:process")
    assert not ws.canvas_3d.find_withtag("room:preparation")
    click_tag(ws.canvas_3d, "studio-action:restore")
    assert ws.canvas_3d.find_withtag("room:preparation")
    click_tag(ws.canvas_3d, "studio-action:top")
    assert ws.layout["view"]["elevation_deg"] == 90
    click_tag(ws.canvas_3d, "studio-action:iso")
    assert ws.layout["view"]["elevation_deg"] == 28


def test_studio_orbit_zoom_and_section_use_real_geometry(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    canvas = ws.canvas_3d
    before = ws.layout["view"]["azimuth_deg"]
    canvas.event_generate("<Shift-Button-1>", x=500, y=200)
    canvas.event_generate("<Shift-B1-Motion>", x=550, y=220)
    gui.root.update()
    assert ws.layout["view"]["azimuth_deg"] != before
    zoom = ws.layout["view"]["zoom_3d"]
    canvas.event_generate("<MouseWheel>", x=500, y=200, delta=120)
    gui.root.update()
    assert ws.layout["view"]["zoom_3d"] > zoom
    canvas.focus_force()
    canvas.event_generate("<f>")
    gui.root.update()
    assert ws.layout["view"]["zoom_3d"] != zoom * 1.1
    ws._section_height_var.set("1.5")
    ws._apply_section_height()
    ws._section_enabled.set(True)
    ws._toggle_section_plane()
    assert len(canvas.find_withtag("section_plane")) == 3
    assert not canvas.find_withtag("device:supply-process")  # Above the cut plane.
    assert canvas.find_withtag("device:door-process")


@pytest.mark.parametrize("size", [(1280, 800), (1536, 960), (1920, 1080)])
def test_studio_resizes_without_rooms_overlapping_room_panels(gui, size):
    from cleanroomx.studio_canvas import studio_regions
    gui.root.geometry(f"{size[0]}x{size[1]}+0+0")
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    canvas = ws.canvas_3d
    width, height = canvas.winfo_width(), canvas.winfo_height()
    panels_left = width - studio_regions(width, height)["card_width"] - 14
    nav_right = ws.navigator_canvas.winfo_x() + ws.navigator_canvas.winfo_width()
    for room in ws.layout["rooms"]:
        x0, y0, x1, y1 = canvas.bbox(f'room:{room["id"]}')
        assert nav_right < x0 < x1 < panels_left
        assert 0 < y0 < y1 < height - 43
    panel = canvas.bbox("studio-room-panel")
    assert panel is not None
    assert 0 <= panel[1] < panel[3] < height
    axes = canvas.bbox("studio-axis")
    dimensions = canvas.bbox("studio-dimension-labels")
    if axes:
        assert panel[3] < axes[1]
        assert dimensions is not None and axes[3] < dimensions[1]
    if dimensions:
        assert panel[3] < dimensions[1]
    for action in ("focus", "isolate"):
        bounds = canvas.bbox(f"studio-action:{action}")
        assert bounds is not None and 0 <= bounds[1] < bounds[3] < height


def test_studio_edit_save_reload_keeps_live_metrics_and_room_assignments(gui, tmp_path, monkeypatch):
    import cleanroomx.gui as gui_module
    gui.open_design_studio()
    ws = gui.spatial_workspace
    ws._property_vars["length_m"].set("6.5")
    ws.apply_properties()
    gui.root.update()
    assert ws._studio_card_vars["area"].get() == "64.5"
    assert ws._studio_card_vars["volume"].get() == "193.5"
    target = tmp_path / "edited-studio.cleanroomx.json"
    monkeypatch.setattr(gui_module.filedialog, "asksaveasfilename", lambda **kw: str(target))
    gui.save_project_as()
    assert target.is_file()
    gui.load_project_path(target)
    gui.open_design_studio()
    gui.root.update()
    assert ws.layout["rooms"][0]["length_m"] == 6.5
    assert ws._studio_card_vars["area"].get() == "64.5"
    room = dashboard_snapshot(ws.layout, "process")["selected_room"]
    assert room["device_count"] == 5
    assert room["device_groups"]["supply"] == 1


def test_studio_editing_tools_and_2d_split_views_remain_accessible(gui):
    gui.open_design_studio()
    ws = gui.spatial_workspace
    ws._studio_more_tools.set(True)
    ws._apply_studio_chrome()
    gui.root.update()
    assert ws._viewbar.winfo_ismapped()
    assert ws._overlaybar.winfo_ismapped()
    assert gui.root.cget("menu")
    ws.show_inspector()
    gui.root.update()
    assert ws.inspector_visible()
    assert ws._property_entries["length_m"].winfo_ismapped()
    ws.set_workspace_mode("split")
    gui.root.update()
    assert not ws._studio_active
    assert ws.canvas_2d.winfo_ismapped()
    assert ws.canvas_3d.winfo_ismapped()
    assert ws.canvas_3d.find_withtag("room3d")
