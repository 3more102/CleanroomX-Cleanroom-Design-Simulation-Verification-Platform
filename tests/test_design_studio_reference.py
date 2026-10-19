"""Regression coverage for model-backed Design Studio reference controls."""

from __future__ import annotations

import copy
import json
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.studio_summary import dashboard_snapshot, device_snapshot, navigator_device_markers, navigator_rectangles


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



def test_navigator_device_positions_follow_rooms_and_never_mutate_model():
    layout = demo_layout()
    original = copy.deepcopy(layout)
    markers = navigator_device_markers(
        layout, width_px=240, height_px=128, padding_px=20, header_px=48,
    )
    assert markers
    by_id = {marker["id"]: marker for marker in markers}
    assert len(by_id) == len(markers)
    for marker in markers:
        assert marker["id"] in {device["id"] for device in layout["devices"]}
        x, y = marker["point"]
        assert 20 <= x <= 220
        assert 48 <= y <= 108
    # Changing a room's position moves all attached devices only when their
    # coordinates are changed too; markers are derived from world coordinates.
    device = next(d for d in layout["devices"] if d["id"] in by_id)
    original_point = by_id[device["id"]]["point"]
    device["x_m"] += 0.1
    moved = {marker["id"]: marker for marker in navigator_device_markers(
        layout, width_px=240, height_px=128, padding_px=20, header_px=48,
    )}
    assert moved[device["id"]]["point"][0] > original_point[0]
    assert layout["devices"][0]["id"] == original["devices"][0]["id"]
    assert navigator_device_markers({"rooms": [], "devices": layout["devices"]}) == []


def test_navigator_device_markers_reject_degenerate_room_geometry():
    layout = demo_layout()
    layout["rooms"][0]["length_m"] = 0
    assert navigator_device_markers(layout) == []

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
    assert ws._studio_metrics_canvas.itemcget("studio-metric-value:rooms", "text") == "4"
    assert ws._studio_metrics_canvas.itemcget("studio-metric-value:area", "text") == "92.0"
    assert ws._studio_metrics_canvas.itemcget("studio-metric-value:volume", "text") == "276.0"


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
    # Room miniatures can contain legitimate equipment markers at their centers.
    # Click an unobstructed room corner to exercise room-selection semantics.
    if tag.startswith("navigator-room:"):
        x, y = round(x0 + min(3, (x1 - x0) / 5)), round(y0 + min(3, (y1 - y0) / 5))
    else:
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


def test_studio_action_hover_and_camera_selection_have_visible_feedback(gui):
    gui.open_design_studio()
    gui.root.update()
    ws, canvas = gui.spatial_workspace, gui.spatial_workspace.canvas_3d
    geometry = copy.deepcopy((ws.layout["rooms"], ws.layout["devices"]))
    original = canvas.itemcget("studio-action-bg:focus", "fill")
    x0, y0, x1, y1 = canvas.bbox("studio-action:focus")
    canvas.event_generate("<Motion>", x=round((x0 + x1) / 2), y=round((y0 + y1) / 2))
    gui.root.update()
    assert canvas.itemcget("studio-action-bg:focus", "fill") != original
    assert canvas.cget("cursor") == "hand2"
    canvas.event_generate("<Leave>")
    gui.root.update()
    assert canvas.itemcget("studio-action-bg:focus", "fill") == original
    assert (ws.layout["rooms"], ws.layout["devices"]) == geometry
    click_tag(canvas, "studio-action:top")
    canvas.event_generate("<Leave>")
    assert canvas.itemcget("studio-action-bg:top", "fill") == ws._theme_palette["selection"]
    assert canvas.itemcget("studio-action-bg:iso", "fill") != ws._theme_palette["selection"]


def test_studio_room_actions_use_the_room_of_a_selected_device(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    assert ws.select_item("device", "supply-process", notify=True)
    click_tag(ws.canvas_3d, "studio-action:focus")
    assert ws.selected.kind == "room" and ws.selected.item_id == "process"
    assert ws.select_item("device", "supply-process", notify=True)
    click_tag(ws.canvas_3d, "studio-action:isolate")
    assert ws._is_item_visible("room", "process")
    assert not ws._is_item_visible("room", "preparation")
    click_tag(ws.canvas_3d, "studio-action:restore")
    assert ws._is_item_visible("room", "preparation")


def test_studio_edit_card_opens_the_actual_room_inspector(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    assert ws.select_item("device", "supply-process", notify=True)
    click_tag(ws.canvas_3d, "studio-action:properties")
    gui.root.update()
    assert ws.selected.kind == "room" and ws.selected.item_id == "process"
    assert ws.inspector_visible()
    assert ws._property_entries["name"].winfo_ismapped()
    assert ws._property_vars["name"].get() == "Process"


def test_studio_minimap_device_selection_and_room_keyboard_context(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    markers = ws.navigator_canvas.find_withtag("navigator-device")
    assert markers, "Actual placed devices must appear in the navigator"
    for room_id, count in (("process", 5), ("preparation", 3), ("ante", 2)):
        items = ws.navigator_canvas.find_withtag(f"navigator-room-data:{room_id}")
        assert items
        assert ws.navigator_canvas.itemcget(items[0], "text").startswith(f"{count} dev")
    first_device = next(
        d for d in ws.layout["devices"]
        if ws.navigator_canvas.find_withtag(f'navigator-device:{d["id"]}')
        and d.get("room_id") in {room["id"] for room in ws.layout["rooms"]}
    )
    device_id, room_id = first_device["id"], first_device["room_id"]
    click_tag(ws.navigator_canvas, f"navigator-device:{device_id}")
    assert ws.selected.kind == "device"
    assert ws.selected.item_id == device_id
    assert room_id in {room["id"] for room in ws.layout["rooms"]}
    assert ws.canvas_3d.find_withtag(f"device:{device_id}")
    assert ws.canvas_3d.find_withtag("studio-room-panel")
    active_id = next(room["id"] for room in ws.layout["rooms"] if room["id"] == room_id)
    index = next(i for i, room in enumerate(ws.layout["rooms"]) if room["id"] == active_id)
    ws._navigate_studio_room(1)
    assert ws.selected.kind == "room"
    assert ws.selected.item_id == ws.layout["rooms"][(index + 1) % len(ws.layout["rooms"])]["id"]
    click_tag(ws.navigator_canvas, f"navigator-room:{room_id}")
    assert ws.selected.kind == "room"
    assert ws.selected.item_id == room_id


def test_device_layer_category_has_stable_model_type_mapping():
    from cleanroomx.studio_summary import device_layer_category
    assert device_layer_category({"type": "FFU"}) == "air"
    assert device_layer_category({"type": "Exhaust"}) == "air"
    assert device_layer_category({"type": "window"}) == "opening"
    assert device_layer_category({"type": "TRANSFER"}) == "opening"
    assert device_layer_category({"type": "sensor"}) == "other"
    assert device_layer_category({}) == "other"


def test_studio_device_layers_filter_3d_and_navigator_only(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    original = copy.deepcopy((ws.layout["rooms"], ws.layout["devices"]))
    assert ws.canvas_3d.find_withtag("device:supply-process")
    assert ws.navigator_canvas.find_withtag("navigator-device:supply-process")
    assert ws.canvas_3d.find_withtag("studio-opening")
    assert ws.select_item("device", "supply-process", notify=True)

    # Display layer visibility is view-local. It must not discard equipment,
    # modify source metadata or invalidate an existing inspector selection.
    ws._studio_device_layers["air"].set(False)
    ws._on_studio_device_layers_changed()
    assert not ws.canvas_3d.find_withtag("device:supply-process")
    assert not ws.navigator_canvas.find_withtag("navigator-device:supply-process")
    assert ws.canvas_3d.find_withtag("device:door-process")
    assert ws.navigator_canvas.find_withtag("navigator-device:door-process")
    assert ws.selected.kind == "device" and ws.selected.item_id == "supply-process"
    assert (ws.layout["rooms"], ws.layout["devices"]) == original

    ws._studio_device_layers["opening"].set(False)
    ws._on_studio_device_layers_changed()
    assert not ws.canvas_3d.find_withtag("studio-opening")
    assert not ws.navigator_canvas.find_withtag("navigator-device:door-process")
    assert ws.canvas_3d.find_withtag("room:process")

    ws._studio_device_layers["air"].set(True)
    ws._studio_device_layers["opening"].set(True)
    ws._on_studio_device_layers_changed()
    assert ws.canvas_3d.find_withtag("device:supply-process")
    assert ws.navigator_canvas.find_withtag("navigator-device:door-process")
    assert (ws.layout["rooms"], ws.layout["devices"]) == original


def test_selected_device_model_snapshot_is_live_and_read_only():
    layout = demo_layout()
    unchanged = copy.deepcopy(layout)
    device = device_snapshot(layout, "supply-process")
    assert device is not None
    assert device["id"] == "supply-process"
    assert device["type"] == "supply"
    assert device["room_id"] == "process"
    assert device["room_name"] == "Process"
    assert device["x_m"] == pytest.approx(1.5)
    assert device["y_m"] == pytest.approx(2.0)
    assert layout == unchanged
    assert device_snapshot(layout, "nonexistent-device") is None
    assert device_snapshot(layout, None) is None
    layout["devices"][1]["x_m"] += 1
    assert device_snapshot(layout, "supply-process")["x_m"] == pytest.approx(2.5)


def test_studio_device_inspection_card_uses_shared_selection(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    assert ws.select_item("device", "supply-process", notify=True)
    gui.root.update()
    canvas = ws.canvas_3d
    selected_name = canvas.find_withtag("studio-selected-device-name")
    position = canvas.find_withtag("studio-selected-device-position")
    assert selected_name and position
    assert canvas.itemcget(selected_name[0], "text") == "supply-process" or (
        "supply" in canvas.itemcget(selected_name[0], "text").lower()
    )
    assert "X 1.5 m" in canvas.itemcget(position[0], "text")
    assert "Y 2 m" in canvas.itemcget(position[0], "text")
    before_zoom = ws.layout["view"]["zoom_3d"]
    click_tag(canvas, "studio-action:focus-device")
    assert ws.selected.kind == "device"
    assert ws.selected.item_id == "supply-process"
    assert ws.layout["view"]["zoom_3d"] > before_zoom
    click_tag(canvas, "studio-action:inspect-device")
    gui.root.update()
    assert ws.selected.kind == "device"
    assert ws.selected.item_id == "supply-process"
    assert ws.inspector_visible()
    assert ws._property_entries["name"].winfo_ismapped()
    assert ws._property_vars["name"].get() == (
        next(d["name"] for d in ws.layout["devices"] if d["id"] == "supply-process")
    )


def test_studio_navigator_device_and_room_hover_reveals_real_names(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    canvas = ws.navigator_canvas
    device_id = "supply-process"
    items = canvas.find_withtag(f"navigator-device:{device_id}")
    assert items
    x0, y0, x1, y1 = canvas.bbox(items[-1])
    canvas.event_generate("<Motion>", x=round((x0 + x1) / 2), y=round((y0 + y1) / 2))
    gui.root.update()
    hint = canvas.find_withtag("navigator-hint")
    assert hint
    assert "Process Supply" in canvas.itemcget(hint[0], "text")
    assert canvas.cget("cursor") == "hand2"
    assert ws.selected.kind == "room", "Hover alone must not select equipment"
    canvas.event_generate("<Leave>")
    gui.root.update()
    assert "Air" in canvas.itemcget(canvas.find_withtag("navigator-hint")[0], "text")
    assert canvas.cget("cursor") == ""


def test_studio_3d_uses_real_device_type_glyphs(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    canvas = ws.canvas_3d
    for kind, device_id in (("ffu", "ffu-process"),
                            ("supply", "supply-process"),
                            ("return", "return-process"),
                            ("equipment", "equipment-process")):
        assert canvas.find_withtag(f"studio-device-glyph:{kind}")
        assert canvas.find_withtag(f"device:{device_id}")
    assert ws.select_item("device", "ffu-process", notify=True)
    assert canvas.find_withtag("studio-device-selected")
    assert canvas.find_withtag("studio-device-glyph:ffu")
    assert canvas.find_withtag("studio-floor")


def test_studio_3d_layer_chips_toggle_graphics_not_model(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    canvas = ws.canvas_3d
    before = copy.deepcopy((ws.layout["rooms"], ws.layout["devices"]))
    assert canvas.find_withtag("studio-action:layer-air")
    assert canvas.find_withtag("studio-action:layer-opening")
    assert canvas.find_withtag("studio-action:layer-other")
    assert ws._studio_device_layers["air"].get()
    click_tag(canvas, "studio-action:layer-air")
    assert not ws._studio_device_layers["air"].get()
    assert not canvas.find_withtag("device:supply-process")
    assert canvas.find_withtag("device:door-process")
    assert ws.navigator_canvas.find_withtag("navigator-device:door-process")
    assert (ws.layout["rooms"], ws.layout["devices"]) == before
    click_tag(canvas, "studio-action:layer-air")
    assert ws._studio_device_layers["air"].get()
    assert canvas.find_withtag("device:supply-process")
    assert (ws.layout["rooms"], ws.layout["devices"]) == before



def test_device_schedule_search_filter_and_geometry_are_read_only():
    from cleanroomx.studio_device_schedule import equipment_schedule_rows
    layout = demo_layout()
    unchanged = copy.deepcopy(layout)
    all_rows = equipment_schedule_rows(layout)
    assert len(all_rows) == 10
    assert len({r["id"] for r in all_rows}) == 10
    assert len(equipment_schedule_rows(layout, category="air")) == 5
    assert len(equipment_schedule_rows(layout, category="opening")) == 4
    assert len(equipment_schedule_rows(layout, category="other")) == 1
    assert len(equipment_schedule_rows(layout, room_id="process")) == 5
    filtered = equipment_schedule_rows(layout, query="supply", room_id="process")
    assert [r["id"] for r in filtered] == ["supply-process"]
    assert filtered[0]["x_m"] == pytest.approx(1.5)
    assert filtered[0]["y_m"] == pytest.approx(2.0)
    assert filtered[0]["z_offset_m"] == pytest.approx(3.0)
    assert equipment_schedule_rows(layout, query="unknown-room-id") == []
    with pytest.raises(ValueError, match="Unsupported device category"):
        equipment_schedule_rows(layout, category="fake")
    assert layout == unchanged


def test_equipment_schedule_csv_exports_only_filtered_source_and_escapes_formulas(tmp_path):
    import csv
    from cleanroomx.studio_device_schedule import (
        equipment_schedule_rows, export_equipment_schedule,
    )
    layout = demo_layout()
    layout["devices"][1]["name"] = "=HYPERLINK(\"http://unsafe.test\")"
    rows = equipment_schedule_rows(layout, category="air", room_id="process")
    output = tmp_path / "visible_equipment.csv"
    export_equipment_schedule(output, rows)
    with output.open(newline="", encoding="utf-8-sig") as handle:
        result = list(csv.reader(handle))
    assert len(result) == 4  # One header, three air devices in Process
    assert result[0][0:3] == ["Device ID", "Name", "Type"]
    exported_name = next(item[1] for item in result[1:] if item[0] == "supply-process")
    assert exported_name.startswith("'=HYPERLINK")
    assert all(item[4] == "Process" for item in result[1:])
    assert layout["devices"][1]["name"].startswith("=")


def test_live_device_schedule_select_focus_export_and_reveal(gui, tmp_path, monkeypatch):
    from cleanroomx.studio_device_schedule import export_equipment_schedule
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    schedule = ws.open_device_schedule()
    gui.root.update()
    assert schedule.winfo_exists()
    assert ws.open_device_schedule() is schedule
    assert len(schedule.table.get_children()) == 10

    schedule._query_var.set("supply")
    schedule.refresh_rows()
    assert len(schedule.table.get_children()) == 2
    schedule._query_var.set("")
    schedule._category_var.set("air")
    schedule.refresh_rows()
    assert len(schedule.table.get_children()) == 5
    schedule._category_var.set("all")
    schedule.refresh_rows()

    row_id = next(
        iid for iid in schedule.table.get_children()
        if schedule._row_ids[iid] == "supply-process"
    )
    schedule.table.selection_set(row_id)
    assert schedule.select_current()
    assert ws.selected.kind == "device"
    assert ws.selected.item_id == "supply-process"
    assert "Device schedule" in schedule.title()

    # CSV output is explicitly user-directed and covers the displayed rows.
    output = tmp_path / "schedule.csv"
    monkeypatch.setattr(
        "cleanroomx.studio_device_schedule.filedialog.asksaveasfilename",
        lambda **_kwargs: str(output),
    )
    schedule.export_current()
    assert output.read_text(encoding="utf-8-sig").count("supply-process") == 1

    ws._studio_device_layers["air"].set(False)
    ws._on_studio_device_layers_changed()
    assert not ws.canvas_3d.find_withtag("device:supply-process")
    before_zoom = ws.layout["view"]["zoom_3d"]
    assert schedule.focus_current()
    assert ws._studio_device_layers["air"].get()
    assert ws.canvas_3d.find_withtag("device:supply-process")
    assert ws.layout["view"]["zoom_3d"] >= before_zoom
    assert not schedule.winfo_exists()
    assert ws.selected.item_id == "supply-process"

    again = ws.open_device_schedule()
    assert again.winfo_exists()
    assert len(again.table.get_children()) == 10
    again.destroy()


def test_device_schedule_auto_refreshes_on_model_redraw(gui):
    gui.open_design_studio()
    gui.root.update()
    ws = gui.spatial_workspace
    schedule = ws.open_device_schedule()
    assert len(schedule.table.get_children()) == 10
    ws.layout["devices"].pop()
    ws.redraw()
    assert len(schedule.table.get_children()) == 9
    assert "9 of 9" in schedule._status_var.get()
    schedule.destroy()
