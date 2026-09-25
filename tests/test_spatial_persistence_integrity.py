from __future__ import annotations

import copy
import json

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    save_project_document,
)
from cleanroomx.spatial import (
    SPATIAL_METADATA_KEY,
    derive_layout_from_analysis,
    ensure_project_layout,
    normalize_layout,
)
from cleanroomx.spatial_schema import (
    SPATIAL_LAYOUT_VERSION,
    SpatialLayoutFormatError,
    empty_layout,
    validate_persisted_spatial_layout,
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
            "asset_tag": "ROOM-001",
        }
    ]
    layout["devices"] = [
        {
            "id": "sensor-1",
            "type": "sensor",
            "name": "Sensor 1",
            "room_id": "process",
            "x_m": 1.0,
            "y_m": 1.0,
            "z_m": 1.5,
            "calibration_id": "CAL-7",
        }
    ]
    layout["vendor_extension"] = {"revision": "A"}
    return layout


def test_spatial_layout_round_trip_preserves_ids_references_and_extension_fields(tmp_path):
    layout = _valid_layout()
    project = ProjectDocument(
        name="Spatial integrity",
        metadata={SPATIAL_METADATA_KEY: copy.deepcopy(layout)},
    )

    path = save_project_document(tmp_path / "spatial.cleanroomx.json", project)
    loaded = load_project_document(path)
    persisted = loaded.metadata[SPATIAL_METADATA_KEY]

    assert persisted == layout
    assert persisted["rooms"][0]["id"] == "process"
    assert persisted["devices"][0]["room_id"] == "process"
    assert persisted["rooms"][0]["asset_tag"] == "ROOM-001"
    assert persisted["devices"][0]["calibration_id"] == "CAL-7"
    assert persisted["vendor_extension"] == {"revision": "A"}


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda layout: layout["rooms"].append(copy.deepcopy(layout["rooms"][0])),
            "duplicates room id",
        ),
        (
            lambda layout: layout["devices"].append(copy.deepcopy(layout["devices"][0])),
            "duplicates device id",
        ),
        (
            lambda layout: layout["devices"][0].__setitem__("room_id", "missing-room"),
            "references missing room id",
        ),
        (
            lambda layout: layout["rooms"][0].__setitem__("length_m", 0.0),
            "length_m must be greater than zero",
        ),
        (
            lambda layout: layout["devices"][0].__setitem__("type", "Sensor"),
            "type must be one of",
        ),
        (
            lambda layout: layout["rooms"][0].__setitem__("id", " process "),
            "leading or trailing whitespace",
        ),
        (
            lambda layout: layout.__setitem__("version", SPATIAL_LAYOUT_VERSION + 1),
            "future spatial_layout version",
        ),
    ],
)
def test_project_save_rejects_corrupt_spatial_state_without_replacing_file(
    mutator, message, tmp_path
):
    path = tmp_path / "protected.cleanroomx.json"
    original = ProjectDocument(
        name="Original",
        metadata={SPATIAL_METADATA_KEY: _valid_layout()},
    )
    save_project_document(path, original)
    original_bytes = path.read_bytes()

    invalid = _valid_layout()
    mutator(invalid)
    candidate = ProjectDocument(
        name="Invalid",
        metadata={SPATIAL_METADATA_KEY: invalid},
    )

    with pytest.raises(ProjectFormatError, match=message):
        save_project_document(path, candidate)

    assert path.read_bytes() == original_bytes
    assert load_project_document(path).name == "Original"


def test_project_load_rejects_corrupt_spatial_reference_before_workspace_refresh(tmp_path):
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


def test_project_load_rejects_non_object_spatial_metadata(tmp_path):
    project = ProjectDocument(name="Bad metadata")
    payload = project.to_dict()
    payload["project"]["metadata"][SPATIAL_METADATA_KEY] = []
    path = tmp_path / "bad-spatial.cleanroomx.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="spatial_layout must be an object"):
        load_project_document(path)


def test_ensure_project_layout_refuses_invalid_persisted_state_instead_of_repairing():
    layout = _valid_layout()
    layout["rooms"][0]["width_m"] = -1.0
    project = ProjectDocument(
        name="Invalid in memory",
        metadata={SPATIAL_METADATA_KEY: layout},
    )

    with pytest.raises(SpatialLayoutFormatError, match="width_m must be greater than zero"):
        ensure_project_layout(project)


def test_lenient_normalization_repairs_ids_and_references_deterministically():
    raw = {
        "rooms": [
            {
                "id": " process ",
                "name": " Process ",
                "x_m": 0,
                "y_m": 0,
                "length_m": 4,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": " process ",
                "name": "Process duplicate",
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
                "id": " sensor ",
                "type": "SENSOR",
                "name": " Sensor ",
                "room_id": " process ",
                "x_m": 1,
                "y_m": 1,
                "z_m": 1,
            },
            {
                "id": " sensor ",
                "type": "sensor",
                "name": "Second",
                "room_id": None,
                "x_m": 0,
                "y_m": 0,
                "z_m": 0,
            },
        ],
        "vendor_extension": {"revision": "A"},
    }

    first = normalize_layout(raw)
    second = normalize_layout(raw)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == [
        "process",
        "process-2",
        "room",
    ]
    assert [device["id"] for device in first["devices"]] == [
        "sensor",
        "sensor-2",
    ]
    assert first["devices"][0]["room_id"] == "process"
    assert first["devices"][0]["type"] == "sensor"
    assert first["vendor_extension"] == {"revision": "A"}
    validate_persisted_spatial_layout(first)


def test_derived_layout_uses_unique_deterministic_ids_for_duplicate_room_names():
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 4, "width_m": 4, "height_m": 3},
                {"name": "Process", "length_m": 5, "width_m": 4, "height_m": 3},
                {"name": "💨", "length_m": 3, "width_m": 3, "height_m": 3},
            ]
        },
    )

    first = derive_layout_from_analysis(analysis)
    second = derive_layout_from_analysis(analysis)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == [
        "process",
        "process-2",
        "room",
    ]
    validate_persisted_spatial_layout(first)
