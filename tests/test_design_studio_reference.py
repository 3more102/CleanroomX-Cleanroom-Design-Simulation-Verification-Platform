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
    assert ws.inspector_visible()
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
