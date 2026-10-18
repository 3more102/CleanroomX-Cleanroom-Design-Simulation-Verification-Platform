"""Design Studio model-backed summary and real Tk interaction regression tests."""
from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui_design_studio import (
    studio_snapshot, studio_nav_signature, STUDIO_ROOM_COLORS,
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


def test_navigator_signature_detects_translation_and_area_preserving_resize():
    layout = {
        "rooms": [
            {"id": "r1", "name": "Process", "x_m": 0, "y_m": 0,
             "length_m": 6, "width_m": 5, "height_m": 3},
            {"id": "r2", "name": "Ante", "x_m": 7, "y_m": 0,
             "length_m": 4, "width_m": 3, "height_m": 3},
        ],
        "devices": [],
    }
    rooms = studio_snapshot(layout)["rooms"]
    initial = studio_nav_signature(rooms, "r1")
    assert initial == studio_nav_signature(rooms, "r1")
    assert initial != studio_nav_signature(rooms, "r2")
    assert initial != studio_nav_signature(list(reversed(rooms)), "r1")
    moved = copy.deepcopy(rooms)
    moved[0]["x_m"] += 1.0
    assert studio_nav_signature(moved, "r1") != initial
    resized = copy.deepcopy(rooms)
    resized[0]["length_m"] = 10.0
    resized[0]["width_m"] = 3.0  # same 30 m², different geometry
    assert resized[0]["length_m"] * resized[0]["width_m"] == 30
    assert studio_nav_signature(resized, "r1") != initial


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
        # Guided stage must represent the actual workspace, not a fixed Run CTA.
        assert application._guided_stage == "design"
        assert application.workflow_design_button.cget("style") == "CX.Primary.TButton"
        assert application.workflow_run_button.cget("style") == "CX.Compact.TButton"
        application.workflow_input_button.invoke()
        root.update()
        assert application.notebook.select() == str(application.input_tab)
        assert application._guided_stage == "inputs"
        assert application.workflow_input_button.cget("style") == "CX.Primary.TButton"
        application.workflow_design_button.invoke()
        root.update()
        assert application.notebook.select() == str(workspace)
        assert application._guided_stage == "design"
        assert workspace._workspace_mode.get() == "split"
        # The 3D Studio is still selectable independently of the legacy
        # guided Design command's deliberate Split view.
        workspace.set_workspace_mode("3d")
        root.update()
        # Direct notebook navigation also synchronizes the guided step.
        application._set_guided_workflow_stage("report")
        assert application.workflow_report_button.cget("style") == "CX.Primary.TButton"
        application.notebook.select(application.input_tab)
        root.update()
        assert application._guided_stage == "inputs"
        application.notebook.select(workspace)
        root.update()
        assert application._guided_stage == "design"
        with pytest.raises(ValueError, match="Unsupported guided workflow stage"):
            application._set_guided_workflow_stage("unknown")
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
        assert studio.room_pressure.get().startswith("Layout pressure (not CFD):")
        # Moving a room must invalidate the mini-map even when floor area stays fixed.
        moved_room = workspace.layout["rooms"][0]
        previous_x = moved_room["x_m"]
        old_signature = studio._nav_signature
        moved_room["x_m"] = previous_x + 0.25
        studio.update()
        assert studio._nav_signature != old_signature
        moved_room["x_m"] = previous_x
        studio.update()
        assert studio._nav_signature == old_signature
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
        studio.restore_all_rooms()
        assert workspace._isolated_item is None
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
        studio._set_camera_preset("front")
        assert workspace.layout["rooms"] == original_rooms
        assert workspace.layout["devices"] == original_devices
        assert workspace.canvas_3d.find_withtag("studio_wall3d")
        assert errors == []
    finally:
        application._autosave_manager.shutdown(wait=False)
        root.destroy()
