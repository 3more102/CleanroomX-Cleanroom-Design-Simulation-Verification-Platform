from __future__ import annotations

import pytest

from cleanroomx.spatial_transform import Viewport2D, fit_viewport


def test_model_screen_round_trip_is_precise_under_pan_and_zoom():
    viewport = Viewport2D(
        width_px=1200,
        height_px=800,
        zoom=2.75,
        pan_x_px=137.25,
        pan_y_px=-84.5,
    )
    for point in ((0.0, 0.0), (1.25, -3.75), (-18.125, 9.5), (100.0, 50.0)):
        screen = viewport.model_to_screen(*point)
        assert viewport.screen_to_model(*screen) == pytest.approx(point, abs=1e-12)


def test_zoom_about_preserves_model_coordinate_under_cursor():
    viewport = Viewport2D(1000, 700, zoom=1.0, pan_x_px=35, pan_y_px=-25)
    cursor = (731.5, 288.25)
    model_before = viewport.screen_to_model(*cursor)

    zoomed = viewport.zoom_about(1.8, *cursor)

    assert zoomed.zoom == pytest.approx(1.8)
    assert zoomed.screen_to_model(*cursor) == pytest.approx(model_before, abs=1e-12)


def test_zoom_about_clamps_without_moving_cursor_anchor():
    viewport = Viewport2D(800, 600, zoom=7.9)
    cursor = (220.0, 410.0)
    model_before = viewport.screen_to_model(*cursor)

    zoomed = viewport.zoom_about(10.0, *cursor)

    assert zoomed.zoom == 8.0
    assert zoomed.screen_to_model(*cursor) == pytest.approx(model_before, abs=1e-12)


def test_pan_by_changes_only_pan_offsets():
    viewport = Viewport2D(640, 480, zoom=1.5, pan_x_px=10, pan_y_px=20)
    panned = viewport.pan_by(25, -15)

    assert panned.zoom == viewport.zoom
    assert panned.pan_x_px == 35
    assert panned.pan_y_px == 5
    assert panned.model_to_screen(0, 0) == pytest.approx((355, 245))


def test_fit_viewport_centers_bounds_and_keeps_them_inside_margin():
    viewport = fit_viewport((10.0, -5.0, 30.0, 5.0), width_px=1000, height_px=700)
    center = viewport.model_to_screen(20.0, 0.0)
    low = viewport.model_to_screen(10.0, -5.0)
    high = viewport.model_to_screen(30.0, 5.0)

    assert center == pytest.approx((500.0, 350.0))
    assert 0 < low[0] < 500 < high[0] < 1000
    assert 0 < low[1] < 350 < high[1] < 700


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_px": -1, "height_px": 10},
        {"width_px": 10, "height_px": 10, "zoom": 0},
        {"width_px": 10, "height_px": 10, "pan_x_px": float("inf")},
    ],
)
def test_viewport_rejects_invalid_state(kwargs):
    with pytest.raises(ValueError):
        Viewport2D(**kwargs)
