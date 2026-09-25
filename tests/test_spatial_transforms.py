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
    workspace.canvas_3d = _Canvas(width=900, height=700)
    workspace.redraw = lambda: None
    workspace._draw_3d = lambda: None
    workspace._persist = lambda _message: None
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



def test_fit_views_fits_both_2d_and_3d_and_resets_3d_pan() -> None:
    workspace = _workspace()
    workspace.layout["rooms"] = [
        {
            "id": "large",
            "name": "Large Room",
            "x_m": -10.0,
            "y_m": -5.0,
            "length_m": 30.0,
            "width_m": 20.0,
            "height_m": 6.0,
            "floor_elevation_m": 1.0,
        }
    ]
    workspace.layout["view"].update(
        {
            "zoom_2d": 4.0,
            "zoom_3d": 4.0,
            "pan_3d_x": 125.0,
            "pan_3d_y": -75.0,
        }
    )

    workspace.fit_views()

    assert 0.2 <= workspace.layout["view"]["zoom_2d"] <= 5.0
    assert 0.2 <= workspace.layout["view"]["zoom_3d"] < 1.0
    assert workspace.layout["view"]["pan_3d_x"] == 0.0
    assert workspace.layout["view"]["pan_3d_y"] == 0.0


def test_reset_2d_restores_default_zoom_and_pan() -> None:
    workspace = _workspace()
    workspace.layout["view"].update(
        {"zoom_2d": 3.5, "pan_x": 42.0, "pan_y": -19.0}
    )

    workspace.reset_2d()

    assert workspace.layout["view"]["zoom_2d"] == 1.0
    assert workspace.layout["view"]["pan_x"] == 0.0
    assert workspace.layout["view"]["pan_y"] == 0.0


class _Event:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y


def test_shift_drag_orbit_changes_azimuth_and_elevation_with_bounds() -> None:
    workspace = _workspace()
    start_azimuth = workspace.layout["view"]["azimuth_deg"]
    start_elevation = workspace.layout["view"]["elevation_deg"]

    assert workspace._on_orbit_3d_down(_Event(100, 100)) == "break"
    assert workspace._on_orbit_3d_drag(_Event(160, 60)) == "break"

    assert workspace.layout["view"]["azimuth_deg"] == pytest.approx(
        (start_azimuth + 30.0) % 360
    )
    assert workspace.layout["view"]["elevation_deg"] > start_elevation

    workspace._on_orbit_3d_down(_Event(0, 0))
    workspace._on_orbit_3d_drag(_Event(0, 1000))
    assert workspace.layout["view"]["elevation_deg"] == 5.0
