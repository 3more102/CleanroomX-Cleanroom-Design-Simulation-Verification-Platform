"""Read-only 3D scene finder index tests."""
from __future__ import annotations

import copy
import pytest

from cleanroomx.spatial_scene_finder import scene_entries


@pytest.fixture
def layout():
    return {
        "rooms": [
            {"id": "processing", "name": "Processing", "length_m": 6},
            {"id": "airlock", "name": "Gowning Airlock"},
        ],
        "devices": [
            {"id": "s1", "name": "Ceiling supply", "type": "supply",
             "room_id": "processing"},
            {"id": "d1", "name": "Transfer opening", "type": "transfer",
             "room_id": "airlock"},
            {"id": "loose", "name": "Room sensor", "type": "sensor"},
        ],
    }


def test_finder_lists_named_rooms_before_placed_devices_without_mutating(layout):
    before = copy.deepcopy(layout)
    result = scene_entries(layout)
    assert [(r["kind"], r["id"]) for r in result] == [
        ("room", "airlock"), ("room", "processing"),
        ("device", "s1"), ("device", "loose"), ("device", "d1"),
    ]
    assert result[2]["room"] == "Processing"
    assert result[3]["room"] == "Unassigned"
    assert layout == before


def test_finder_matches_parent_room_type_and_id(layout):
    assert [r["id"] for r in scene_entries(layout, "processing supply")] == ["s1"]
    assert [r["id"] for r in scene_entries(layout, "  AIRLOCK transfer")] == ["d1"]
    assert [r["id"] for r in scene_entries(layout, "d1")] == ["d1"]
    assert [r["id"] for r in scene_entries(layout, "sensor")] == ["loose"]
    assert scene_entries(layout, "nonexistent") == []


def test_finder_bounds_results_and_invalid_limit(layout):
    assert len(scene_entries(layout, "", limit=2)) == 2
    with pytest.raises(ValueError, match="positive"):
        scene_entries(layout, limit=0)
