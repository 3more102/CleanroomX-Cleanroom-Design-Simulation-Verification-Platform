"""Design Studio model-backed summary and real Tk interaction regression tests."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui_design_studio import (
    studio_snapshot, studio_navigator_signature, STUDIO_ROOM_COLORS,
    studio_shade, studio_blend,
)
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


def test_studio_snapshot_real_geometry_and_device_ownership():
    layout = {
        "rooms": [
            {"id": "r1", "name": "Process", "length_m": 6, "width_m": 5,
             "height_m": 3, "pressure_pa": 30, "classification": "Process"},
            {"id": "r2", "name": "Ante", "length_m": 4, "width_m": 3,
             "height_m": 3, "pressure_pa": 8},
        ],
        "devices": [
            {"id": "f", "type": "ffu", "room_id": "r1"},
            {"id": "s", "type": "supply", "room_id": "r1"},
            {"id": "e", "type": "exhaust", "room_id": "r1"},
            {"id": "x", "type": "door", "room_id": "r2"},
        ],
    }
    before = copy.deepcopy(layout)
    data = studio_snapshot(layout, "r1")
    assert data["room_count"] == 2
    assert data["floor_area_m2"] == 42
    assert data["volume_m3"] == 126
    assert data["placed_devices"] == 4
    assert data["selected_room"]["device_counts"] == {
        "ffu": 1, "supply": 1, "return_exhaust": 1, "other": 0,
    }
    assert data["rooms"][0]["color"] == STUDIO_ROOM_COLORS[0]
    assert studio_shade("#ff8040", 0.5) == "#804020"
    assert studio_blend("#ffffff", "#000000", 0.5) == "#808080"
    with pytest.raises(ValueError, match="opacity"):
        studio_blend("#ffffff", "#000000", -0.1)
    assert studio_snapshot(layout, "r2")["selected_room"]["devices"] == 1
    assert layout == before


def test_studio_snapshot_empty_and_missing_selection():
    assert studio_snapshot({"rooms": [], "devices": []})["selected_room"] is None


def test_navigator_signature_tracks_movement_and_equal_area_resize():
    layout = {
        "rooms": [{"id": "r1", "name": "Process", "x_m": 0, "y_m": 0,
                   "length_m": 6, "width_m": 5, "height_m": 3}],
        "devices": [],
    }
    original = studio_snapshot(layout, "r1")
    before = studio_navigator_signature(original["rooms"], "r1")
    layout["rooms"][0]["x_m"] = 2
    moved = studio_snapshot(layout, "r1")
    assert moved["floor_area_m2"] == original["floor_area_m2"]
    assert studio_navigator_signature(moved["rooms"], "r1") != before
    layout["rooms"][0]["x_m"] = 0
    layout["rooms"][0]["length_m"] = 5
    layout["rooms"][0]["width_m"] = 6
    rotated_footprint = studio_snapshot(layout, "r1")
    assert rotated_footprint["floor_area_m2"] == original["floor_area_m2"]
    assert studio_navigator_signature(rotated_footprint["rooms"], "r1") != before


def test_live_studio_selection_metrics_and_real_3d(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Display unavailable: {exc}")
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    application = CleanroomXApp(
        root, autosave_interval_seconds=0,
        ui_state_path=tmp_path / "studio-layout.json",
    )
    try:
        application.load_project_path(bundled_demo_project_path())
        application.notebook.select(application.spatial_workspace)
        root.update()
        workspace = application.spatial_workspace
        studio = workspace._studio
        assert studio.enabled
        assert studio.metric_vars["rooms"].get() == str(len(workspace.layout["rooms"]))
        assert studio.metric_vars["devices"].get() == str(len(workspace.layout["devices"]))
        assert set(studio.nav_buttons) == {str(r["id"]) for r in workspace.layout["rooms"]}
        assert workspace.canvas_3d.winfo_ismapped()
        assert workspace.canvas_3d.find_withtag("room3d")
        assert len(workspace.canvas_3d.find_withtag("studio_floor3d")) == len(workspace.layout["rooms"])
        assert len(workspace.canvas_3d.find_withtag("studio_wall3d")) == 2 * len(workspace.layout["rooms"])
        assert len(workspace.canvas_3d.find_withtag("studio_room_label")) == len(workspace.layout["rooms"])
        assert len(workspace.canvas_3d.find_withtag("studio_backdrop")) == 24
        assert workspace.canvas_3d.find_withtag("opening3d")
        assert workspace.canvas_3d.find_withtag("studio_device3d")
        assert studio.mini_plan.find_withtag("floorplan:" + str(workspace.layout["rooms"][0]["id"]))
        before = copy.deepcopy(application.project.to_dict())
        room = workspace.layout["rooms"][-1]
        studio.nav_buttons[str(room["id"])].invoke()
        root.update()
        assert workspace.selected.kind == "room"
        assert workspace.selected.item_id == str(room["id"])
        assert studio.room_name.get() == room["name"]
        assert application.project.to_dict() == before
        assert studio.room_pressure.get().startswith("Configured pressure:")
        # A relocation with unchanged area must invalidate and redraw the mini-plan.
        moved_room = workspace.layout["rooms"][0]
        plan_tag = "floorplan:" + str(moved_room["id"])
        old_rect = studio.mini_plan.find_withtag(plan_tag)[0]
        old_coords = tuple(studio.mini_plan.coords(old_rect))
        old_signature = studio._nav_signature
        old_x = moved_room["x_m"]
        try:
            moved_room["x_m"] = old_x + 9.0
            studio.update()
            new_rect = studio.mini_plan.find_withtag(plan_tag)[0]
            assert studio._nav_signature != old_signature
            assert tuple(studio.mini_plan.coords(new_rect)) != old_coords
        finally:
            moved_room["x_m"] = old_x
            studio.update()
        original_rooms = copy.deepcopy(workspace.layout["rooms"])
        original_devices = copy.deepcopy(workspace.layout["devices"])
        original_view = copy.deepcopy(workspace.layout["view"])
        studio.focus_room()
        assert workspace.layout["view"] != original_view
        assert workspace.layout["rooms"] == original_rooms
        assert workspace.layout["devices"] == original_devices
        assert "3D focus:" in application.status_var.get()
        studio.isolate_room()
        assert workspace._isolated_item.item_id == str(room["id"])
        studio.restore_button.invoke()
        assert workspace._isolated_item is None
        assert workspace.layout["rooms"] == original_rooms
        studio.isolate_room()
        other = workspace.layout["rooms"][0]
        studio.nav_buttons[str(other["id"])].invoke()
        root.update()
        assert workspace.selected.item_id == str(other["id"])
        assert workspace._isolated_item is None
        # Search should reveal a room that is hidden by an earlier isolate.
        studio.isolate_room()
        monkeypatch.setattr(
            "cleanroomx.gui_design_studio.simpledialog.askstring",
            lambda *_args, **_kwargs: room["name"],
        )
        studio.find_item()
        assert workspace.selected.kind == "room"
        assert workspace.selected.item_id == str(room["id"])
        assert workspace._isolated_item is None
        # The same guarantee applies when a device belongs to another room.
        studio.isolate_room()
        target_device = next(
            d for d in workspace.layout["devices"] if d["name"] == "Process Tool"
        )
        monkeypatch.setattr(
            "cleanroomx.gui_design_studio.simpledialog.askstring",
            lambda *_args, **_kwargs: target_device["name"],
        )
        studio.find_item()
        assert workspace.selected.kind == "device"
        assert workspace.selected.item_id == str(target_device["id"])
        assert workspace._isolated_item is None
        studio.studio_view()
        root.update()
        assert application.focus_workspace_var.get()
        # Responsive overlays must remain usable at minimum desktop size.
        root.geometry("1050x680")
        root.update()
        assert studio._compact_layout is True
        assert studio.nav.winfo_width() == 230
        assert studio.sidebar.winfo_width() == 250
        root.geometry("1536x960")
        root.update()
        assert studio._compact_layout is False
        assert studio.nav.winfo_width() == 270
        assert studio.sidebar.winfo_width() == 330
        studio.toggle_advanced()
        root.update()
        assert studio._advanced_visible is True
        assert studio.advanced_actions_bar.winfo_ismapped()
        commands = [w.cget("text") for w in studio.advanced_actions_bar.winfo_children()]
        assert commands == [
            "Reset 2D", "Floor…", "Pull from analysis", "Push to analysis",
        ]
        studio.toggle_advanced()
        root.update()
        assert studio._advanced_visible is False
        assert not studio.advanced_actions_bar.winfo_ismapped()
        studio.balance_view()
        assert workspace._workspace_mode.get() == "3d"
        assert workspace._isolated_item is None
        studio._set_camera_preset("front")
        assert workspace.layout["rooms"] == original_rooms
        assert workspace.layout["devices"] == original_devices
        assert workspace.canvas_3d.find_withtag("studio_wall3d")
        assert errors == []
    finally:
        application._autosave_manager.shutdown(wait=False)
        root.destroy()
