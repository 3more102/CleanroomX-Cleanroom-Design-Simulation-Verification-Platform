from __future__ import annotations

import copy
import json
from pathlib import Path

from cleanroomx.spatial import (
    SpatialDesignWorkspace,
    _Hit,
    design_studio_snapshot,
    navigator_room_rectangles,
)


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "src" / "cleanroomx" / "demo" / "gui_demo.cleanroomx.json"


def demo_layout() -> dict:
    return json.loads(DEMO.read_text(encoding="utf-8"))["project"]["metadata"]["spatial_layout"]


def test_reference_demo_metrics_are_derived_from_model() -> None:
    snapshot = design_studio_snapshot(demo_layout())
    assert snapshot["room_count"] == 3
    assert snapshot["floor_area_m2"] == 62.0
    assert snapshot["volume_m3"] == 186.0
    assert snapshot["placed_devices"] == 10
    assert snapshot["device_buckets"] == {
        "ffu": 1, "supply": 2, "return_exhaust": 2, "other": 5,
    }
    assert snapshot["selected_room"] is None


def test_selected_room_inspector_distinguishes_design_setpoint_from_solver() -> None:
    snapshot = design_studio_snapshot(demo_layout(), "process")
    selected = snapshot["selected_room"]
    assert selected["name"] == "Process"
    assert selected["dimensions_m"] == (6.0, 5.0, 3.0)
    assert selected["floor_area_m2"] == 30
    assert selected["volume_m3"] == 90
    assert selected["device_count"] == 5
    assert selected["design_pressure_pa"] == 30.0
    assert "computed_pressure_pa" not in selected
    assert snapshot["device_buckets"] == {
        "ffu": 1, "supply": 1, "return_exhaust": 1, "other": 2,
    }


def test_live_cards_follow_room_edits_and_device_additions() -> None:
    layout = copy.deepcopy(demo_layout())
    before = design_studio_snapshot(layout)
    layout["rooms"][0]["length_m"] = 7.0
    layout["devices"].append({
        "id": "sensor-new", "name": "Sensor", "room_id": "process",
        "type": "sensor", "x_m": 1, "y_m": 1, "z_m": 1,
    })
    after = design_studio_snapshot(layout, "process")
    assert after["floor_area_m2"] == before["floor_area_m2"] + 5
    assert after["volume_m3"] == before["volume_m3"] + 15
    assert after["placed_devices"] == before["placed_devices"] + 1
    assert after["selected_room"]["device_count"] == 6
    assert after["device_buckets"]["other"] == 3
    layout["rooms"] = [room for room in layout["rooms"] if room["id"] != "process"]
    after_delete = design_studio_snapshot(layout, "process")
    assert after_delete["room_count"] == 2
    assert after_delete["selected_room"] is None


def test_navigator_rectangles_preserve_layout_and_fit_canvas() -> None:
    rooms = design_studio_snapshot(demo_layout())["navigator_rooms"]
    rects = navigator_room_rectangles(rooms, 238, 98)
    assert len(rects) == 3
    assert all(0 <= x0 < x1 <= 238 and 0 <= y0 < y1 <= 98 for x0, y0, x1, y1 in rects)
    assert rects[0][0] < rects[1][0] < rects[2][0]
    assert navigator_room_rectangles([], 238, 98) == []


class Var:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


def test_studio_refresh_updates_cards_selected_room_and_navigator_without_tk() -> None:
    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = demo_layout()
    workspace.selected = _Hit("room", "process")
    workspace._studio_metric_vars = {key: Var() for key in (
        "rooms", "floor_area", "volume", "devices",
    )}
    workspace._studio_selected_var = Var()
    workspace._studio_devices_var = Var()
    workspace._navigator_canvas = object()
    received = []
    workspace._draw_room_navigator = lambda snapshot: received.append(snapshot)
    workspace._update_studio_panels()
    assert [workspace._studio_metric_vars[key].value for key in (
        "rooms", "floor_area", "volume", "devices",
    )] == ["3", "62.0 m²", "186.0 m³", "10"]
    assert "Design pressure setpoint: 30 Pa" in workspace._studio_selected_var.value
    assert "FFU 1" in workspace._studio_devices_var.value
    assert len(received) == 1
    assert received[0]["selected_room"]["id"] == "process"


def test_navigator_click_uses_existing_synchronized_select_item_path() -> None:
    class Canvas:
        def find_overlapping(self, *_args) -> tuple[int, ...]:
            return (3, 4)

    class Event:
        x = 10
        y = 12

    workspace = object.__new__(SpatialDesignWorkspace)
    workspace._navigator_canvas = Canvas()
    workspace._navigator_hit_rooms = {4: "process"}
    selections = []
    workspace.select_item = lambda kind, item_id, *, notify: (
        selections.append((kind, item_id, notify)) or True
    )
    assert workspace._on_navigator_click(Event()) == "break"
    assert selections == [("room", "process", True)]
