from __future__ import annotations

import copy

import pytest

from cleanroomx.spatial import normalize_layout
from cleanroomx.spatial_editing import duplicate_spatial_item, update_spatial_properties
from cleanroomx.spatial_integrity import SpatialLayoutFormatError, validate_spatial_layout_document


def _layout() -> dict:
    return normalize_layout(
        {
            "rooms": [
                {
                    "id": "process",
                    "name": "Process",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "zone": "Critical Process",
                    "classification": "Project class",
                },
                {
                    "id": "ante",
                    "name": "Ante",
                    "x_m": 7.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "zone": "Transition",
                },
            ],
            "devices": [],
        }
    )


def test_zone_is_preserved_by_normalization_and_validation() -> None:
    layout = _layout()

    assert [room["zone"] for room in layout["rooms"]] == [
        "Critical Process",
        "Transition",
    ]
    validate_spatial_layout_document(layout)


def test_zone_edit_and_clear_are_atomic_optional_room_properties() -> None:
    layout = _layout()

    edited = update_spatial_properties(
        layout,
        "room",
        "process",
        {"zone": "ISO Processing"},
    )
    assert edited["rooms"][0]["zone"] == "ISO Processing"
    assert layout["rooms"][0]["zone"] == "Critical Process"

    cleared = update_spatial_properties(
        edited,
        "room",
        "process",
        {"zone": "   "},
    )
    assert "zone" not in cleared["rooms"][0]


def test_room_duplicate_preserves_zone_but_not_engineering_evidence() -> None:
    layout = _layout()
    layout["rooms"][0]["pressure_pa"] = 20.0
    layout["rooms"][0]["analysis_room_name"] = "Process engineering"

    duplicated, duplicate_id = duplicate_spatial_item(layout, "room", "process")
    duplicate = next(room for room in duplicated["rooms"] if room["id"] == duplicate_id)

    assert duplicate["zone"] == "Critical Process"
    assert "pressure_pa" not in duplicate
    assert "analysis_room_name" not in duplicate


def test_persistence_boundary_rejects_blank_zone() -> None:
    layout = _layout()
    invalid = copy.deepcopy(layout)
    invalid["rooms"][0]["zone"] = " "

    with pytest.raises(SpatialLayoutFormatError, match=r"rooms\[0\]\.zone"):
        validate_spatial_layout_document(invalid)
