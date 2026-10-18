"""Reference Design Studio acceptance tests against the real Tk application.

Run: xvfb-run -a python -m pytest -q tests/test_gui_design_studio.py
"""
from __future__ import annotations

import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.spatial import _Hit, layout_metrics


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
        root, autosave_interval_seconds=0,
        ui_state_path=tmp_path / "studio-ui.json",
    )
    application.load_project_path(bundled_demo_project_path())
    application.notebook.select(application.spatial_workspace)
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_demo_cards_are_derived_from_layout(app):
    workspace = app.spatial_workspace
    metrics = layout_metrics(workspace.layout)
    assert workspace._studio_cards.values["rooms"].get() == str(metrics["room_count"])
    assert workspace._studio_cards.values["area"].get() == (
        f"{metrics['total_floor_area_m2']:.1f} m²"
    )
    assert workspace._studio_cards.values["volume"].get() == (
        f"{metrics['total_volume_m3']:.1f} m³"
    )
    assert workspace._studio_cards.values["devices"].get() == (
        str(len(workspace.layout["devices"]))
    )
    assert (metrics["room_count"], metrics["total_floor_area_m2"],
            metrics["total_volume_m3"]) == (3, 62.0, 186.0)


def test_navigator_selects_same_room_as_spatial_workspace(app):
    workspace = app.spatial_workspace
    navigator = workspace._room_navigator
    room = workspace.layout["rooms"][1]
    assert navigator.tree.exists(room["id"])
    assert navigator.map_canvas.find_withtag(f"room:{room['id']}")
    navigator.tree.selection_set(room["id"])
    navigator._on_tree_select(None)
    app.root.update()
    assert workspace.selected == _Hit("room", room["id"])
    assert workspace._studio_selected_room.name.get() == room["name"]
    assert tuple(navigator.tree.selection()) == (room["id"],)
    assert "Configured pressure setpoint:" in workspace._studio_selected_room.pressure.get()
    assert "not CFD" in workspace._studio_selected_room.pressure.get()


def test_summary_cards_update_after_room_and_device_edits(app):
    workspace = app.spatial_workspace
    original = layout_metrics(workspace.layout)
    workspace.add_room()
    app.root.update()
    assert workspace._studio_cards.values["rooms"].get() == str(original["room_count"] + 1)
    assert workspace._studio_cards.values["area"].get() == (
        f"{original['total_floor_area_m2'] + 16:.1f} m²"
    )
    new_room_id = workspace.selected.item_id
    assert workspace._room_navigator.tree.exists(new_room_id)
    workspace.add_device("ffu")
    app.root.update()
    assert workspace._studio_cards.values["devices"].get() == (
        str(sum(original["device_counts"].values()) + 1)
    )
    workspace.delete_selected()
    app.root.update()
    assert workspace._studio_cards.values["devices"].get() == (
        str(sum(original["device_counts"].values()))
    )
    assert workspace.select_item("room", new_room_id)
    workspace.delete_selected()
    app.root.update()
    assert workspace._studio_cards.values["rooms"].get() == str(original["room_count"])
    assert not workspace._room_navigator.tree.exists(new_room_id)


def test_room_focus_and_isolation_are_view_only(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    assert workspace.select_item("room", room["id"])
    workspace._focus_selected_room()
    app.root.update()
    assert workspace.selected == _Hit("room", room["id"])
    workspace._isolate_selected_room()
    assert workspace._isolated_item == _Hit("room", room["id"])
    workspace.show_all()
    assert workspace._isolated_item is None


def test_selected_room_and_placed_device_counts_are_live(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    workspace.select_item("room", room["id"], notify=True)
    app.root.update()
    scoped = [d for d in workspace.layout["devices"] if d.get("room_id") == room["id"]]
    assert str(len(scoped)) in workspace._studio_selected_room.details.get()
    assert workspace._studio_placed_devices.scope.get() == f"In {room['name']}"
    assert workspace._studio_placed_devices.counts.get().startswith("FFU ")
    workspace.select_item("device", workspace.layout["devices"][0]["id"], notify=True)
    app.root.update()
    assert workspace._studio_selected_room.name.get() == "No room selected"
    assert workspace._studio_placed_devices.scope.get() == "All rooms"
