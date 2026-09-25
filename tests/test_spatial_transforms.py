from __future__ import annotations

import math

import pytest

from cleanroomx.spatial_transforms import (
    MAX_ZOOM,
    MIN_ZOOM,
    model_to_screen_2d,
    project_3d,
    screen_to_model_2d,
    zoom_2d_at,
)


VIEW = {
    "width_px": 1200.0,
    "height_px": 800.0,
    "zoom": 1.75,
    "pan_x_px": 83.0,
    "pan_y_px": -47.0,
}


@pytest.mark.parametrize("point", [(0.0, 0.0), (2.5, -1.25), (-8.125, 14.75), (1000.0, -1000.0)])
def test_model_screen_round_trip_is_precise(point):
    screen = model_to_screen_2d(*point, **VIEW)
    assert screen_to_model_2d(*screen, **VIEW) == pytest.approx(point, abs=1e-12)


def test_pan_is_a_pure_screen_translation():
    point = (3.0, 4.0)
    base = model_to_screen_2d(
        *point, width_px=1000, height_px=600, zoom=1.0, pan_x_px=0, pan_y_px=0
    )
    shifted = model_to_screen_2d(
        *point, width_px=1000, height_px=600, zoom=1.0, pan_x_px=125, pan_y_px=-80
    )
    assert shifted[0] - base[0] == pytest.approx(125)
    assert shifted[1] - base[1] == pytest.approx(-80)


def test_zoom_at_preserves_model_coordinate_under_cursor():
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


def test_zoom_clamps_supported_range_and_rejects_invalid_factor():
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


def test_3d_projection_is_deterministic_and_elevation_moves_vertical_screen_position():
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
