"""Design Studio model-backed summary and real Tk interaction regression tests."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui_design_studio import (
    studio_snapshot, STUDIO_ROOM_COLORS, studio_shade, studio_blend,
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


def test_live_studio_selection_metrics_and_real_3d(tmp_path):
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
        assert studio.mini_plan.find_withtag("floorplan:" + str(workspace.layout["rooms"][0]["id"]))
        # A relocation or changed aspect ratio must invalidate the mini-plan
        # even when room identifiers, labels and floor areas do not change.
        plan_room = workspace.layout["rooms"][1]
        plan_tag = "floorplan:" + str(plan_room["id"])
        original_plan_box = studio.mini_plan.coords(plan_tag)
        assert len(original_plan_box) == 4
        plan_room["x_m"] += 0.5
        studio.update()
        assert studio.mini_plan.coords(plan_tag) != original_plan_box
        plan_room["x_m"] -= 0.5
        studio.update()
        assert studio.mini_plan.coords(plan_tag) == original_plan_box
        plan_room["length_m"], plan_room["width_m"] = (
            plan_room["width_m"], plan_room["length_m"],
        )
        studio.update()
        assert studio.mini_plan.coords(plan_tag) != original_plan_box
        plan_room["length_m"], plan_room["width_m"] = (
            plan_room["width_m"], plan_room["length_m"],
        )
        studio.update()
        assert studio.mini_plan.coords(plan_tag) == original_plan_box
        before = copy.deepcopy(application.project.to_dict())
        room = workspace.layout["rooms"][-1]
        studio.nav_buttons[str(room["id"])].invoke()
        root.update()
        assert workspace.selected.kind == "room"
        assert workspace.selected.item_id == str(room["id"])
        assert studio.room_name.get() == room["name"]
        assert studio.room_pressure.get() == "Configured pressure: +8 Pa"
        assert application.project.to_dict() == before
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
        other = workspace.layout["rooms"][0]
        studio.nav_buttons[str(other["id"])].invoke()
        root.update()
        assert workspace.selected.item_id == str(other["id"])
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
        assert errors == []
    finally:
        application._autosave_manager.shutdown(wait=False)
        root.destroy()
