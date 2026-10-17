"""Regression tests for the presentation-only 3D metric rulers and zone tints."""
from __future__ import annotations

import math

import pytest

from cleanroomx.spatial_3d_presentation import (
    ZONE_COLORS,
    axis_ticks,
    draw_3d_reference,
    draw_3d_zone_legend,
    room_zone_colors,
)


class RecordingCanvas:
    def __init__(self):
        self.items = []

    def _record(self, kind, *args, **kwargs):
        self.items.append((kind, args, kwargs))
        return len(self.items)

    def create_line(self, *args, **kwargs):
        return self._record("line", *args, **kwargs)

    def create_text(self, *args, **kwargs):
        return self._record("text", *args, **kwargs)

    def create_rectangle(self, *args, **kwargs):
        return self._record("rectangle", *args, **kwargs)

    def tag_raise(self, *args, **kwargs):
        self._record("raise", *args, **kwargs)

    def winfo_height(self):
        return 520


def test_axis_ticks_use_nice_metric_steps_and_are_bounded():
    assert axis_ticks(0, 10, limit=6) == (0, 2, 4, 6, 8, 10)
    assert axis_ticks(-1, 1, limit=5) == (-1, -0.5, 0, 0.5, 1)
    assert axis_ticks(2, 2) == (2,)
    assert len(axis_ticks(-10_000, 30_000, limit=7)) <= 7
    for a, b in ((math.nan, 2), (0, math.inf), (2, 1)):
        with pytest.raises(ValueError):
            axis_ticks(a, b)
    with pytest.raises(ValueError):
        axis_ticks(0, 1, limit=1)


def test_reference_cage_has_grid_rulers_and_real_z_ticks():
    canvas = RecordingCanvas()
    draw_3d_reference(
        canvas,
        lambda x, y, z: (x * 10 + y * 2, y * 10 - z * 15),
        bounds=(0, 0, 12, 8),
        bottom_z=0,
        top_z=3,
        show_grid=True,
    )
    labels = [item[2]["text"] for item in canvas.items if item[0] == "text"]
    assert {"Length X (m)", "Width Y (m)", "Height Z (m)"} <= set(labels)
    assert "0" in labels and "3" in labels
    tags = [tag for _, _, attrs in canvas.items
            for tag in attrs.get("tags", ())]
    assert "grid3d" in tags
    assert "axis3d" in tags
    assert len(canvas.items) < 100

    no_grid = RecordingCanvas()
    draw_3d_reference(no_grid, lambda x, y, z: (x, y - z),
                      bounds=(0, 0, 12, 8),
                      bottom_z=0, top_z=3, show_grid=False)
    assert not any("grid3d" in kw.get("tags", ())
                   for _, _, kw in no_grid.items)
    assert any("axis3d" in kw.get("tags", ())
               for _, _, kw in no_grid.items)


def test_zone_colors_are_deterministic_for_same_room_ids():
    rooms = [{"id": "c", "name": "C"}, {"id": "a", "name": "A"},
             {"id": "b", "name": "B"}]
    first = room_zone_colors(rooms)
    assert first == room_zone_colors(list(reversed(rooms)))
    assert set(first.values()) <= set(ZONE_COLORS)
    assert len(set(first.values())) == 3


def test_zone_legend_is_explicitly_not_an_engineering_result():
    rooms = [{"id": f"room-{i}", "name": f"Room {i}"} for i in range(9)]
    canvas = RecordingCanvas()
    draw_3d_zone_legend(canvas, rooms, room_zone_colors(rooms))
    texts = [kw.get("text", "") for kind, _, kw in canvas.items
             if kind == "text"]
    assert "DESIGN ZONES" in texts
    assert any("more zones" in text for text in texts)
    assert any("not CFD or ISO verification" in text for text in texts)
    assert len([item for item in canvas.items
                if item[0] == "rectangle"]) == 8


def test_invalid_cage_extents_fail_before_canvas_mutation():
    canvas = RecordingCanvas()
    with pytest.raises(ValueError):
        draw_3d_reference(canvas, lambda x, y, z: (x, y),
                          bounds=(2, 0, 1, 1),
                          bottom_z=0, top_z=3, show_grid=True)
    assert not canvas.items
