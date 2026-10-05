from __future__ import annotations

import math

import pytest

from cleanroomx.gui_plot import (
    finite_marker_points,
    finite_series_points,
    linear_ticks,
    nearest_screen_point,
    padded_plot_bounds,
)


def test_finite_series_points_preserves_only_real_backend_samples() -> None:
    plot = {
        "series": [
            {
                "name": "Fan curve",
                "x": [0, 1, "bad", 3, math.inf, True],
                "y": [10, 8, 7, None, 2, 1],
            },
            {"name": "System", "x": [0, 2], "y": [0, 6]},
        ]
    }
    points = finite_series_points(plot)
    assert [(item["series"], item["x"], item["y"]) for item in points] == [
        ("Fan curve", 0.0, 10.0),
        ("Fan curve", 1.0, 8.0),
        ("System", 0.0, 0.0),
        ("System", 2.0, 6.0),
    ]


def test_finite_marker_points_does_not_invent_invalid_markers() -> None:
    plot = {
        "markers": [
            {"name": "Operating point", "x": 2, "y": 6},
            {"name": "Invalid", "x": "bad", "y": 1},
        ]
    }
    assert finite_marker_points(plot) == [
        {"marker_index": 0, "name": "Operating point", "x": 2.0, "y": 6.0}
    ]


def test_padded_plot_bounds_includes_explicit_markers() -> None:
    series = [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 20.0}]
    markers = [{"x": 20.0, "y": 40.0}]
    bounds = padded_plot_bounds(series, markers)
    assert bounds is not None
    xmin, xmax, ymin, ymax = bounds
    assert xmin < 0.0
    assert xmax > 20.0
    assert ymin < 0.0
    assert ymax > 40.0


def test_padded_plot_bounds_handles_single_point() -> None:
    bounds = padded_plot_bounds([{"x": 5.0, "y": -2.0}])
    assert bounds is not None
    xmin, xmax, ymin, ymax = bounds
    assert xmin < 5.0 < xmax
    assert ymin < -2.0 < ymax


def test_linear_ticks_are_deterministic_and_include_endpoints() -> None:
    ticks = linear_ticks(-2.0, 8.0, count=6)
    assert ticks == pytest.approx((-2.0, 0.0, 2.0, 4.0, 6.0, 8.0))


def test_nearest_screen_point_respects_pixel_threshold() -> None:
    points = [
        {"series": "A", "x": 1.0, "y": 2.0, "px": 100.0, "py": 100.0},
        {"series": "B", "x": 2.0, "y": 3.0, "px": 130.0, "py": 100.0},
    ]
    assert nearest_screen_point(points, 104.0, 102.0, max_distance=8.0) == points[0]
    assert nearest_screen_point(points, 115.0, 100.0, max_distance=8.0) is None
