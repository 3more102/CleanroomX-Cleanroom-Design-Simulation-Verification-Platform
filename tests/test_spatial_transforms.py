from __future__ import annotations

import pytest

from cleanroomx.spatial import SpatialDesignWorkspace, empty_layout
from cleanroomx.spatial_transforms import (
    MAX_ZOOM,
    MIN_ZOOM,
    model_to_screen_2d,
    project_3d,
    screen_to_model_2d,
    zoom_2d_at,
)


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


def test_pure_2d_transform_round_trip_and_zoom_anchor() -> None:
    view = {
        "width_px": 1200.0,
        "height_px": 800.0,
        "zoom": 1.75,
        "pan_x_px": 83.0,
        "pan_y_px": -47.0,
    }
    point = (-8.125, 14.75)
    screen = model_to_screen_2d(*point, **view)
    assert screen_to_model_2d(*screen, **view) == pytest.approx(point, abs=1e-12)

    anchor = (731.25, 244.5)
    before = screen_to_model_2d(*anchor, **view)
    zoom, pan_x, pan_y = zoom_2d_at(1.6, *anchor, **view)
    after = screen_to_model_2d(
        *anchor,
        width_px=view["width_px"],
        height_px=view["height_px"],
        zoom=zoom,
        pan_x_px=pan_x,
        pan_y_px=pan_y,
    )
    assert after == pytest.approx(before, abs=1e-12)


def test_pure_zoom_clamps_supported_range() -> None:
    common = {
        "width_px": 1000.0,
        "height_px": 600.0,
        "zoom": 1.0,
        "pan_x_px": 0.0,
        "pan_y_px": 0.0,
    }
    assert zoom_2d_at(0.0001, 500, 300, **common)[0] == MIN_ZOOM
    assert zoom_2d_at(1000, 500, 300, **common)[0] == MAX_ZOOM


def test_3d_projection_is_deterministic_and_elevation_moves_up_screen() -> None:
    view = {
        "width_px": 900.0,
        "height_px": 600.0,
        "azimuth_deg": 35.0,
        "elevation_deg": 28.0,
        "zoom": 1.2,
        "pan_x_px": 10.0,
        "pan_y_px": -5.0,
    }
    floor = project_3d(2.0, 3.0, 0.0, **view)
    elevated = project_3d(2.0, 3.0, 2.0, **view)
    assert floor == project_3d(2.0, 3.0, 0.0, **view)
    assert elevated[0] == pytest.approx(floor[0])
    assert elevated[1] < floor[1]
