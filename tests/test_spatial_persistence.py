from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.project import (
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    save_project_document,
)
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    empty_layout,
    ensure_project_layout,
    normalize_layout,
)
from cleanroomx.spatial_schema import (
    SPATIAL_LAYOUT_VERSION,
    SpatialLayoutFormatError,
    validate_spatial_layout_document,
)


def _valid_layout() -> dict:
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "process",
            "name": "Process",
            "x_m": 0.0,
            "y_m": 0.0,
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
            "pressure_pa": 30.0,
        }
    ]
    layout["devices"] = [
        {
            "id": "ffu-1",
            "type": "ffu",
            "name": "FFU-1",
            "room_id": "process",
            "x_m": 3.0,
            "y_m": 2.5,
            "z_m": 3.0,
        }
    ]
    return layout


def test_spatial_layout_round_trip_preserves_stable_ids_and_references(tmp_path):
    layout = _valid_layout()
    project = ProjectDocument(
        name="Spatial integrity",
        metadata={SPATIAL_METADATA_KEY: copy.deepcopy(layout)},
    )

    path = save_project_document(tmp_path / "spatial.cleanroomx.json", project)
    loaded = load_project_document(path)

    assert loaded.metadata[SPATIAL_METADATA_KEY] == layout
    assert loaded.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["id"] == "process"
    assert loaded.metadata[SPATIAL_METADATA_KEY]["devices"][0]["room_id"] == "process"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda layout: layout["rooms"].append(copy.deepcopy(layout["rooms"][0])),
            "duplicate room id",
        ),
        (
            lambda layout: layout["rooms"][0].__setitem__("length_m", 0.0),
            "length_m must be greater than zero",
        ),
        (
            lambda layout: layout["devices"][0].__setitem__("type", "mystery"),
            "type must be one of",
        ),
        (
            lambda layout: layout["devices"].append(copy.deepcopy(layout["devices"][0])),
            "duplicate device id",
        ),
        (
            lambda layout: layout["devices"][0].__setitem__("room_id", "missing-room"),
            "references missing room id",
        ),
        (
            lambda layout: layout["rooms"][0].__setitem__("id", " process "),
            "leading or trailing whitespace",
        ),
    ],
)
def test_project_save_rejects_corrupt_spatial_layout(mutator, message, tmp_path):
    layout = _valid_layout()
    mutator(layout)
    project = ProjectDocument(
        name="Corrupt spatial",
        metadata={SPATIAL_METADATA_KEY: layout},
    )

    with pytest.raises(ProjectFormatError, match=message):
        save_project_document(tmp_path / "bad.cleanroomx.json", project)


def test_normalize_layout_keeps_trimmed_room_references_consistent():
    normalized = normalize_layout(
        {
            "rooms": [
                {
                    "id": " process ",
                    "name": " Process ",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": 4,
                    "width_m": 4,
                    "height_m": 3,
                }
            ],
            "devices": [
                {
                    "id": " sensor ",
                    "type": "sensor",
                    "name": " Sensor ",
                    "room_id": " process ",
                    "x_m": 1,
                    "y_m": 1,
                    "z_m": 1,
                }
            ],
        }
    )

    assert normalized["rooms"][0]["id"] == "process"
    assert normalized["devices"][0]["id"] == "sensor"
    assert normalized["devices"][0]["room_id"] == "process"
    assert normalized["devices"][0]["name"] == "Sensor"
    validate_spatial_layout_document(normalized)


def test_project_load_rejects_corrupt_spatial_layout_from_disk(tmp_path):
    project = ProjectDocument(
        name="Corrupt load",
        metadata={SPATIAL_METADATA_KEY: _valid_layout()},
    )
    payload = project.to_dict()
    payload["project"]["metadata"][SPATIAL_METADATA_KEY]["devices"][0]["room_id"] = (
        "missing-room"
    )
    path = tmp_path / "corrupt.cleanroomx.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="references missing room id"):
        load_project_document(path)


def test_project_save_rejects_future_spatial_layout_version(tmp_path):
    layout = _valid_layout()
    layout["version"] = SPATIAL_LAYOUT_VERSION + 1
    project = ProjectDocument(
        name="Future spatial",
        metadata={SPATIAL_METADATA_KEY: layout},
    )

    with pytest.raises(ProjectFormatError, match="future spatial_layout version"):
        save_project_document(tmp_path / "future.cleanroomx.json", project)


def test_ensure_project_layout_rejects_invalid_persisted_metadata_instead_of_repairing():
    layout = _valid_layout()
    layout["devices"][0]["room_id"] = "missing-room"
    project = ProjectDocument(
        name="Invalid in memory",
        metadata={SPATIAL_METADATA_KEY: layout},
    )

    with pytest.raises(SpatialLayoutFormatError, match="references missing room id"):
        ensure_project_layout(project)


def test_normalize_layout_repairs_duplicate_or_missing_ids_deterministically():
    raw = {
        "rooms": [
            {
                "id": "duplicate",
                "name": "A",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "duplicate",
                "name": "B",
                "x_m": 5,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "name": "💨",
                "x_m": 10,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
        ],
        "devices": [
            {
                "id": "device",
                "type": "sensor",
                "name": "One",
                "room_id": "duplicate",
                "x_m": 1,
                "y_m": 1,
                "z_m": 1,
            },
            {
                "id": "device",
                "type": "sensor",
                "name": "Two",
                "room_id": "duplicate",
                "x_m": 2,
                "y_m": 2,
                "z_m": 1,
            },
            {
                "type": "equipment",
                "name": "Three",
                "room_id": None,
                "x_m": 0,
                "y_m": 0,
                "z_m": 0,
            },
        ],
    }

    first = normalize_layout(raw)
    second = normalize_layout(raw)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == ["duplicate", "duplicate-2", "room"]
    assert [device["id"] for device in first["devices"]] == [
        "device",
        "device-2",
        "device-3",
    ]
    validate_spatial_layout_document(first)
