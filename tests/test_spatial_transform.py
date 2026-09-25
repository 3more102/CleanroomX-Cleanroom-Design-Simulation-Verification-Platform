from __future__ import annotations

import math

import pytest

from cleanroomx.spatial_transform import ViewTransform2D, snap_point


def test_model_screen_round_trip_is_precision_safe():
    transform = ViewTransform2D(
        width_px=1200,
        height_px=800,
        zoom=1.75,
        pan_x_px=137.25,
        pan_y_px=-82.5,
    )
    for point in ((0.0, 0.0), (1.25, -4.75), (123.456789, 0.000123)):
        screen = transform.model_to_screen(*point)
        restored = transform.screen_to_model(*screen)
        assert restored == pytest.approx(point, abs=1e-12)


def test_zoom_about_preserves_world_coordinate_under_cursor():
    transform = ViewTransform2D(
        width_px=900,
        height_px=600,
        zoom=0.85,
        pan_x_px=20,
        pan_y_px=-15,
    )
    anchor = (713.5, 144.25)
    world_before = transform.screen_to_model(*anchor)

    zoomed = transform.zoom_about(1.8, *anchor)
    world_after = zoomed.screen_to_model(*anchor)

    assert zoomed.zoom == pytest.approx(1.53)
    assert world_after == pytest.approx(world_before, abs=1e-12)


def test_fit_bounds_centers_geometry_and_keeps_bounds_inside_padding():
    transform = ViewTransform2D.fit_bounds(
        (-2.0, 3.0, 18.0, 13.0),
        width_px=1000,
        height_px=700,
        padding_fraction=0.1,
    )
    center = transform.model_to_screen(8.0, 8.0)
    low = transform.model_to_screen(-2.0, 3.0)
    high = transform.model_to_screen(18.0, 13.0)

    assert center == pytest.approx((500.0, 350.0))
    assert 100 <= low[0] <= 900
    assert 70 <= low[1] <= 630
    assert 100 <= high[0] <= 900
    assert 70 <= high[1] <= 630


def test_snap_point_can_be_enabled_or_disabled():
    assert snap_point(1.24, 2.76, 0.5, enabled=True) == (1.0, 3.0)
    assert snap_point(1.24, 2.76, 0.5, enabled=False) == (1.24, 2.76)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"width_px": 0, "height_px": 100},
        {"width_px": 100, "height_px": 0},
        {"width_px": 100, "height_px": 100, "zoom": 0},
        {"width_px": 100, "height_px": 100, "pan_x_px": math.inf},
    ),
)
def test_transform_rejects_invalid_view_state(kwargs):
    with pytest.raises(ValueError):
        ViewTransform2D(**kwargs)
