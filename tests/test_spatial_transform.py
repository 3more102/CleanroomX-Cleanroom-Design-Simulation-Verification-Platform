from __future__ import annotations

import math

import pytest

from cleanroomx.spatial_transform import IsometricProjector3D, ViewTransform2D


def test_view_transform_round_trip_precision():
    transform = ViewTransform2D(
        1280,
        720,
        zoom=2.75,
        pan_x_px=113.25,
        pan_y_px=-47.5,
    )

    for point in ((0.0, 0.0), (1.25, -3.5), (-11.2, 8.75), (100.0, 0.001)):
        screen = transform.model_to_screen(*point)
        recovered = transform.screen_to_model(*screen)
        assert recovered == pytest.approx(point, abs=1e-12)


def test_zoom_about_preserves_model_point_under_cursor():
    transform = ViewTransform2D(
        900,
        600,
        zoom=1.2,
        pan_x_px=25.0,
        pan_y_px=-30.0,
    )
    anchor = (317.0, 241.0)
    world_before = transform.screen_to_model(*anchor)

    zoomed = transform.zoom_about(1.75, *anchor)

    assert zoomed.zoom == pytest.approx(2.1)
    assert zoomed.screen_to_model(*anchor) == pytest.approx(world_before, abs=1e-12)


def test_zoom_about_clamps_and_rejects_invalid_factor():
    transform = ViewTransform2D(800, 600, zoom=7.5)
    assert transform.zoom_about(2.0, 400, 300).zoom == 8.0
    assert transform.zoom_about(0.001, 400, 300).zoom == 0.2

    with pytest.raises(ValueError):
        transform.zoom_about(0.0, 400, 300)


def test_isometric_projection_is_deterministic_and_height_moves_up():
    projector = IsometricProjector3D(
        1000,
        700,
        azimuth_deg=35.0,
        elevation_deg=28.0,
        zoom=1.5,
        pan_x_px=12.0,
        pan_y_px=-9.0,
    )

    first = projector.project(2.0, 3.0, 0.0)
    second = projector.project(2.0, 3.0, 0.0)
    elevated = projector.project(2.0, 3.0, 2.5)

    assert first == second
    assert all(math.isfinite(value) for value in first)
    assert elevated[0] == pytest.approx(first[0])
    assert elevated[1] < first[1]
