"""Closed-door geometry independent of Tk, CFD and pressure solver."""
from __future__ import annotations

import copy

import pytest

from cleanroomx.door_geometry import (
    adjoining_room, door_aperture, opening_corners,
    solid_wall_panels, wall_point,
)
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import load_project_document


def _room(name="r1", x=0.0, y=0.0, length=4.0, width=3.0, height=3.0):
    return dict(id=name, x_m=x, y_m=y, length_m=length,
                width_m=width, height_m=height, floor_elevation_m=0.0)


def _door(room_id="r1", side="east", x=4.0, y=1.5, width=1.0):
    return dict(id="door-1", type="door", name="Door", room_id=room_id,
                wall_side=side, x_m=x, y_m=y, z_m=0.0,
                width_m=width, height_m=2.1, swing="left")


def test_east_shared_wall_is_a_full_width_floor_aperture():
    room = _room()
    door = _door()
    assert door_aperture(room, door) == dict(
        side="east", u0=1.0, u1=2.0, z0=0.0, z1=2.1,
    )
    corners = opening_corners(room, door_aperture(room, door))
    assert corners == (
        (4.0, 1.0, 0.0), (4.0, 2.0, 0.0),
        (4.0, 2.0, 2.1), (4.0, 1.0, 2.1),
    )
    assert adjoining_room(room, door, [
        room, _room("r2", x=4.0, y=0.0)
    ])["id"] == "r2"


def test_north_wall_and_west_wall_both_use_the_correct_axis():
    room = _room()
    north = _door(side="north", x=2.0, y=3.0)
    west = _door(side="west", x=0.0, y=1.5)
    assert door_aperture(room, north) == dict(
        side="north", u0=1.5, u1=2.5, z0=0.0, z1=2.1
    )
    assert wall_point(room, "north", 1.5, 2.1) == (1.5, 3.0, 2.1)
    assert door_aperture(room, west)["u0"] == pytest.approx(1.0)
    assert adjoining_room(room, north, [
        room, _room("r2", x=0, y=3, length=4)
    ])["id"] == "r2"
    assert adjoining_room(room, west, [
        room, _room("r3", x=-4, y=0)
    ])["id"] == "r3"


def test_outside_and_off_wall_doors_do_not_cut_surfaces():
    room = _room()
    door = _door()
    for update in (
        {"x_m": 3.8},
        {"y_m": 0.2},
        {"height_m": 3.1},
        {"width_m": 0.0},
        {"z_m": -0.1},
        {"wall_side": "diagonal"},
        {"room_id": "other"},
        {"x_m": float("nan")},
    ):
        bad = {**door, **update}
        assert door_aperture(room, bad) is None
    assert adjoining_room(room, door, [room]) is None


def test_wall_panel_partition_subtracts_closed_door_and_keeps_lintel():
    aperture = door_aperture(_room(), _door())
    panels = solid_wall_panels(3.0, 3.0, [aperture])
    assert panels == [
        (0.0, 1.0, 0.0, 3.0),
        (1.0, 2.0, 2.1, 3.0),
        (2.0, 3.0, 0.0, 3.0),
    ]
    solid_area = sum((u1 - u0) * (z1 - z0) for u0, u1, z0, z1 in panels)
    assert solid_area == pytest.approx(9 - 2.1)


def test_multiple_apertures_and_sections_cannot_repaint_door_void():
    first = dict(side="east", u0=0.5, u1=1.0, z0=0.0, z1=2.1)
    second = dict(side="east", u0=2.0, u1=2.5, z0=0.0, z1=2.1)
    panels = solid_wall_panels(3, 3, [first, second])
    area = sum((u1 - u0) * (z1 - z0) for u0, u1, z0, z1 in panels)
    assert area == pytest.approx(9 - 2 * 0.5 * 2.1)
    clipped = [{**first, "z1": 1.5}, {**second, "z1": 1.5}]
    assert sum(
        (u1-u0)*(z1-z0)
        for u0, u1, z0, z1 in solid_wall_panels(3, 1.5, clipped)
    ) == pytest.approx(4.5 - 1.5)


def test_bundled_demo_all_three_doors_connect_to_one_real_neighbor():
    project = load_project_document(bundled_demo_project_path())
    layout = project.metadata["spatial_layout"]
    rooms = layout["rooms"]
    room_by_id = {item["id"]: item for item in rooms}
    expected = ["preparation", "ante", "corridor"]
    actual = []
    for door in (item for item in layout["devices"] if item["type"] == "door"):
        owner = room_by_id[door["room_id"]]
        assert door_aperture(owner, door) is not None
        neighbor = adjoining_room(owner, door, rooms)
        assert neighbor is not None
        actual.append(neighbor["id"])
        assert owner["pressure_pa"] - neighbor["pressure_pa"] == pytest.approx(5.0)
    assert actual == expected


def test_ambiguous_neighbors_are_not_accepted_as_a_unique_door_link():
    owner = _room()
    door = _door()
    neighbors = [_room("a", x=4), _room("b", x=4)]
    assert adjoining_room(owner, door, [owner, *neighbors]) is None
