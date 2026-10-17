"""Deterministic GUI legibility tests; no display server or CFD solver required."""
from __future__ import annotations

import math

from cleanroomx.spatial_3d_legibility import (
    draw_room_details_hud,
    draw_device_details_hud,
    room_area_volume,
    draw_room_label_chips,
    place_room_label_chips,
    room_hud_bounds,
)


class CanvasRecorder:
    def __init__(self):
        self.items = []

    def _add(self, kind, *args, **kwargs):
        self.items.append((kind, args, kwargs))

    def create_line(self, *args, **kwargs):
        self._add("line", *args, **kwargs)

    def create_rectangle(self, *args, **kwargs):
        self._add("rect", *args, **kwargs)

    def create_text(self, *args, **kwargs):
        self._add("text", *args, **kwargs)

    def tag_raise(self, *args, **kwargs):
        self._add("raise", *args, **kwargs)


def intersects(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def test_colliding_room_titles_get_distinct_viewport_positions():
    entries = [
        {"room_id": "z", "text": "Long Preparation Room", "anchor": (320, 200)},
        {"room_id": "b", "text": "Gowning Airlock", "anchor": (325, 207)},
        {"room_id": "a", "text": "Process", "anchor": (322, 202), "priority": 2},
    ]
    reserved = [(0, 0, 205, 115), (720, 370, 900, 460)]
    placements = place_room_label_chips(
        entries, width=900, height=460, reserved=reserved,
    )
    assert len(placements) == 3
    assert placements[0]["room_id"] == "a"
    assert placements == place_room_label_chips(
        reversed(entries), width=900, height=460, reserved=reserved,
    )
    for i, item in enumerate(placements):
        x0, y0, x1, y1 = item["box"]
        assert 0 <= x0 < x1 <= 900
        assert 0 <= y0 < y1 <= 460
        assert all(not intersects(item["box"], box) for box in reserved)
        assert all(not intersects(item["box"], other["box"])
                   for other in placements[i + 1:])


def test_label_positioning_respects_narrow_view_and_bad_anchors():
    assert not place_room_label_chips(
        [{"room_id": "r", "text": "Room", "anchor": (20, 20)}],
        width=60, height=80,
    )
    assert not place_room_label_chips(
        [{"room_id": "r", "text": "Room", "anchor": (math.nan, 50)}],
        width=900, height=500,
    )
    entries = [
        {"room_id": "duplicate", "text": "original", "anchor": (210, 210)},
        {"room_id": "duplicate", "text": "new", "anchor": (250, 250)},
    ]
    assert len(place_room_label_chips(entries, width=700, height=500)) == 1


def test_chips_keep_room_hit_tags_and_do_not_mutate_model_data():
    entries = [{"room_id": "process", "text": "Process", "anchor": (250, 200)}]
    positions = place_room_label_chips(entries, width=900, height=500)
    canvas = CanvasRecorder()
    draw_room_label_chips(canvas, positions, {"process": "#23bca1"})
    assert any("room:process" in attrs.get("tags", ())
               for _, _, attrs in canvas.items)
    assert any(attrs.get("text") == "Process"
               for kind, _, attrs in canvas.items if kind == "text")
    assert entries == [{"room_id": "process", "text": "Process",
                        "anchor": (250, 200)}]


def test_room_details_hud_displays_only_supplied_measurement_or_overlay():
    room = {
        "id": "r1", "name": "Process", "classification": "Unverified design zone",
        "length_m": 6.0, "width_m": 5.0, "height_m": 3.0,
    }
    canvas = CanvasRecorder()
    bbox = draw_room_details_hud(
        canvas, room, width=920, height=540,
        selected=True, overlay_title="Pressure",
        overlay_label="Pressure: +30 Pa",
    )
    assert bbox == room_hud_bounds(920, 540, active=True)
    labels = [
        attrs.get("text", "") for kind, _, attrs in canvas.items
        if kind == "text"
    ]
    assert "SELECTED ROOM" in labels
    assert any("6" in label and "5" in label and "3" in label for label in labels)
    assert any("+30 Pa" in label for label in labels)
    assert not any("ISO certified" in label for label in labels)
    assert room["name"] == "Process"


def test_small_view_hides_hud_without_drawing_outside_canvas():
    canvas = CanvasRecorder()
    room = {"name": "R", "length_m": 1, "width_m": 1, "height_m": 2}
    assert draw_room_details_hud(
        canvas, room, width=280, height=210, selected=False,
        overlay_title="None", overlay_label="",
    ) is None
    assert canvas.items == []


def test_room_dimensions_are_exact_and_reject_invalid_geometry():
    import pytest
    area, volume = room_area_volume(
        {"length_m": 6, "width_m": 5, "height_m": 3}
    )
    assert area == 30
    assert volume == 90
    with pytest.raises(ValueError):
        room_area_volume({"length_m": -2, "width_m": 5, "height_m": 3})
    with pytest.raises(ValueError):
        room_area_volume({"length_m": float("nan"), "width_m": 5, "height_m": 3})


def test_room_hud_includes_exact_area_volume_and_device_count():
    room = {
        "id": "zone", "name": "Process", "classification": "Unverified",
        "length_m": 6, "width_m": 5, "height_m": 3,
    }
    canvas = CanvasRecorder()
    bounds = draw_room_details_hud(
        canvas, room, width=900, height=480, selected=True,
        overlay_title="None", overlay_label="", device_count=4,
    )
    assert bounds is not None
    labels = [kwargs["text"] for kind, _, kwargs in canvas.items
              if kind == "text"]
    assert any("30 m²" in item and "90 m³" in item for item in labels)
    assert any("Placed devices: 4" in item for item in labels)
    assert all("CFD validated" not in item for item in labels)


def test_device_details_hud_displays_only_placed_device_values():
    device = {
        "id": "d1", "name": "Supply diffuser", "type": "supply",
        "room_id": "r", "x_m": 2, "y_m": 1.25, "z_m": 2.8,
        "width_m": 0.4, "height_m": 0.15,
    }
    canvas = CanvasRecorder()
    result = draw_device_details_hud(
        canvas, device, width=900, height=540,
        selected=True, room_name="Process",
    )
    assert result is not None
    labels = [kwargs["text"] for kind, _, kwargs in canvas.items if kind == "text"]
    assert "SELECTED DEVICE" in labels
    assert any("Process" in item for item in labels)
    assert any("1.25" in item and "2.8" in item for item in labels)
    assert any("no CFD result inferred" in item for item in labels)
    assert not any("m³/s" in item for item in labels)
