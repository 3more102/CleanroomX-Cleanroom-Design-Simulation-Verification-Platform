from __future__ import annotations

import pytest

from cleanroomx.spatial import SpatialDesignWorkspace, empty_layout


class _Canvas:
    def __init__(self, width: int = 800, height: int = 600):
        self._width = width
        self._height = height

    def winfo_width(self) -> int:
        return self._width

    def winfo_height(self) -> int:
        return self._height


def _workspace() -> SpatialDesignWorkspace:
    workspace = object.__new__(SpatialDesignWorkspace)
    workspace.layout = empty_layout()
    workspace.canvas_2d = _Canvas()
    workspace.redraw = lambda: None
    return workspace


def test_model_to_screen_and_screen_to_model_round_trip() -> None:
    workspace = _workspace()

    screen = workspace._world_to_canvas(2.0, -1.0)
    assert screen == pytest.approx((510.0, 245.0))

    model = workspace._canvas_to_world(*screen)
    assert model == pytest.approx((2.0, -1.0), abs=1e-12)


def test_coordinate_round_trip_preserves_precision_with_zoom_and_pan() -> None:
    workspace = _workspace()
    workspace.layout["view"].update(
        {
            "zoom_2d": 2.75,
            "pan_x": 37.5,
            "pan_y": -22.25,
        }
    )

    for point in ((0.0, 0.0), (-12.375, 7.625), (100.125, -83.875)):
        screen = workspace._world_to_canvas(*point)
        restored = workspace._canvas_to_world(*screen)
        assert restored == pytest.approx(point, abs=1e-12)


def test_zoom_keeps_model_point_under_cursor_fixed() -> None:
    workspace = _workspace()
    cursor = (615.0, 427.0)
    before = workspace._canvas_to_world(*cursor)

    workspace._zoom_at(1.25, *cursor)

    assert workspace.layout["view"]["zoom_2d"] == pytest.approx(1.25)
    after = workspace._canvas_to_world(*cursor)
    assert after == pytest.approx(before, abs=1e-12)
