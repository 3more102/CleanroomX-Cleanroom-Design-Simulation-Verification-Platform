from __future__ import annotations

import math

import pytest

from cleanroomx.spatial import SpatialDesignWorkspace, empty_layout
from cleanroomx.spatial_transforms import (
    MAX_ZOOM,
    MIN_ZOOM,
    fit_3d_view,
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
    workspace.canvas_3d = _Canvas(1200, 760)
    workspace.redraw = lambda: None
    workspace._persist = lambda message: None
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


VIEW = {
    "width_px": 1200.0,
    "height_px": 800.0,
    "zoom": 1.75,
    "pan_x_px": 83.0,
    "pan_y_px": -47.0,
}


@pytest.mark.parametrize(
    "point",
    [(0.0, 0.0), (2.5, -1.25), (-8.125, 14.75), (1000.0, -1000.0)],
)
def test_pure_model_screen_round_trip_is_precise(point):
    screen = model_to_screen_2d(*point, **VIEW)
    assert screen_to_model_2d(*screen, **VIEW) == pytest.approx(point, abs=1e-12)


def test_pure_zoom_at_preserves_model_coordinate_and_clamps():
    anchor = (731.25, 244.5)
    before = screen_to_model_2d(*anchor, **VIEW)
    zoom, pan_x, pan_y = zoom_2d_at(1.6, *anchor, **VIEW)
    after = screen_to_model_2d(
        *anchor,
        width_px=VIEW["width_px"],
        height_px=VIEW["height_px"],
        zoom=zoom,
        pan_x_px=pan_x,
        pan_y_px=pan_y,
    )
    assert after == pytest.approx(before, abs=1e-12)

    low, _, _ = zoom_2d_at(
        0.0001, 500, 300,
        width_px=1000, height_px=600, zoom=1.0, pan_x_px=0, pan_y_px=0,
    )
    high, _, _ = zoom_2d_at(
        1000, 500, 300,
        width_px=1000, height_px=600, zoom=1.0, pan_x_px=0, pan_y_px=0,
    )
    assert low == MIN_ZOOM
    assert high == MAX_ZOOM
    with pytest.raises(ValueError, match="finite positive"):
        zoom_2d_at(
            math.nan, 500, 300,
            width_px=1000, height_px=600, zoom=1.0, pan_x_px=0, pan_y_px=0,
        )


def test_pure_3d_projection_is_deterministic_and_elevation_moves_upward():
    args = {
        "width_px": 900,
        "height_px": 600,
        "azimuth_deg": 35,
        "elevation_deg": 28,
        "zoom": 1.2,
        "pan_x_px": 10,
        "pan_y_px": -5,
    }
    floor = project_3d(2.0, 3.0, 0.0, **args)
    elevated = project_3d(2.0, 3.0, 2.0, **args)
    assert floor == project_3d(2.0, 3.0, 0.0, **args)
    assert elevated[0] == pytest.approx(floor[0])
    assert elevated[1] < floor[1]


def test_fit_3d_view_keeps_room_extents_inside_requested_padding():
    points = [
        (x, y, z)
        for x in (-8.0, 8.0)
        for y in (-3.0, 3.0)
        for z in (0.0, 3.5)
    ]
    width = 1200
    height = 760
    zoom, pan_x, pan_y = fit_3d_view(
        points,
        width_px=width,
        height_px=height,
        azimuth_deg=35,
        elevation_deg=28,
        padding_fraction=0.10,
    )
    projected = [
        project_3d(
            *point,
            width_px=width,
            height_px=height,
            azimuth_deg=35,
            elevation_deg=28,
            zoom=zoom,
            pan_x_px=pan_x,
            pan_y_px=pan_y,
        )
        for point in points
    ]

    assert all(width * 0.10 - 1e-9 <= x <= width * 0.90 + 1e-9 for x, _ in projected)
    assert all(height * 0.10 - 1e-9 <= y <= height * 0.90 + 1e-9 for _, y in projected)


def test_workspace_fit_views_updates_3d_camera_from_geometry():
    workspace = _workspace()
    workspace.layout["rooms"] = [
        {
            "id": "large-room",
            "name": "Large Room",
            "x_m": 0.0,
            "y_m": 0.0,
            "length_m": 40.0,
            "width_m": 20.0,
            "height_m": 4.0,
            "floor_elevation_m": 1.5,
        }
    ]

    workspace.fit_views()

    assert workspace.layout["view"]["zoom_3d"] < 1.0
    assert math.isfinite(workspace.layout["view"]["pan_3d_x"])
    assert math.isfinite(workspace.layout["view"]["pan_3d_y"])
