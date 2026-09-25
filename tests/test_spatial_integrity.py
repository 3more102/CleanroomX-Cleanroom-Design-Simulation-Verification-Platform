from __future__ import annotations

import copy

import pytest

from cleanroomx.project import (
    PROJECT_SCHEMA,
    PROJECT_SCHEMA_VERSION,
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    project_from_dict,
    save_project_document,
)
from cleanroomx.spatial import derive_layout_from_analysis, normalize_layout


def _room(**overrides):
    value = {
        "id": "room-a",
        "name": "Room A",
        "x_m": 0.0,
        "y_m": 0.0,
        "length_m": 5.0,
        "width_m": 4.0,
        "height_m": 3.0,
    }
    value.update(overrides)
    return value


def _project_data(layout):
    return {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {
            "name": "Spatial integrity",
            "description": "",
            "metadata": {"spatial_layout": layout},
        },
        "analyses": [],
        "active_analysis_id": None,
    }


def test_tolerant_normalization_repairs_missing_and_duplicate_ids_deterministically():
    source = {
        "rooms": [
            {
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "process",
                "name": "Explicit Process",
                "x_m": 6,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "id": "process",
                "name": "Duplicate Explicit",
                "x_m": 12,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            },
        ],
        "devices": [
            {"type": "sensor", "x_m": 1, "y_m": 1, "z_m": 1},
            {"id": "device-sensor-1", "type": "sensor", "x_m": 2, "y_m": 1, "z_m": 1},
        ],
    }

    first = normalize_layout(copy.deepcopy(source))
    second = normalize_layout(copy.deepcopy(source))

    assert first == second
    room_ids = [room["id"] for room in first["rooms"]]
    device_ids = [device["id"] for device in first["devices"]]
    assert len(room_ids) == len(set(room_ids))
    assert len(device_ids) == len(set(device_ids))
    assert room_ids == ["process-2", "process", "process-copy"]
    assert device_ids == ["device-sensor-1-2", "device-sensor-1"]


def test_derived_layout_duplicate_room_names_have_stable_unique_ids():
    analysis = AnalysisDocument(
        id="verification",
        name="Duplicate names",
        kind="project_verification",
        input={
            "rooms": [
                {"name": "Process", "length_m": 5, "width_m": 4, "height_m": 3},
                {"name": "Process", "length_m": 6, "width_m": 4, "height_m": 3},
            ]
        },
    )

    first = derive_layout_from_analysis(analysis)
    second = derive_layout_from_analysis(analysis)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == ["process", "process-2"]


def test_project_loader_rejects_missing_v1_spatial_room_name():
    room = _room()
    room.pop("name")
    layout = {"version": 1, "rooms": [room], "devices": []}

    with pytest.raises(ProjectFormatError, match="rooms\\[0\\]\\.name must be a non-empty string"):
        project_from_dict(_project_data(layout))


def test_project_loader_rejects_duplicate_persisted_spatial_room_ids():
    layout = {
        "version": 1,
        "rooms": [_room(), _room(name="Room B", x_m=6)],
        "devices": [],
    }

    with pytest.raises(ProjectFormatError, match="duplicate spatial room id"):
        project_from_dict(_project_data(layout))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("length_m", 0, "length_m must be greater than zero"),
        ("width_m", -1, "width_m must be greater than zero"),
    ],
)
def test_project_loader_rejects_invalid_engineering_geometry(field, value, message):
    layout = {
        "version": 1,
        "rooms": [_room(**{field: value})],
        "devices": [],
    }

    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(_project_data(layout))





@pytest.mark.parametrize(("field", "value"), [("height_m", float("inf")), ("x_m", float("nan"))])
def test_project_loader_rejects_non_finite_spatial_values_at_json_boundary(field, value):
    layout = {
        "version": 1,
        "rooms": [_room(**{field: value})],
        "devices": [],
    }

    with pytest.raises(ProjectFormatError, match="strict JSON values"):
        project_from_dict(_project_data(layout))


def test_project_loader_rejects_duplicate_persisted_spatial_device_ids():
    layout = {
        "version": 1,
        "rooms": [_room()],
        "devices": [
            {
                "id": "sensor-a",
                "type": "sensor",
                "name": "Sensor A",
                "room_id": "room-a",
                "x_m": 1,
                "y_m": 1,
                "z_m": 1,
            },
            {
                "id": "sensor-a",
                "type": "sensor",
                "name": "Sensor B",
                "room_id": "room-a",
                "x_m": 2,
                "y_m": 1,
                "z_m": 1,
            },
        ],
    }

    with pytest.raises(ProjectFormatError, match="duplicate spatial device id"):
        project_from_dict(_project_data(layout))


def test_project_loader_rejects_orphan_spatial_device_reference():
    layout = {
        "version": 1,
        "rooms": [_room()],
        "devices": [
            {
                "id": "sensor-a",
                "type": "sensor",
                "name": "Sensor A",
                "room_id": "missing-room",
                "x_m": 1,
                "y_m": 1,
                "z_m": 1,
            }
        ],
    }

    with pytest.raises(ProjectFormatError, match="references missing room id"):
        project_from_dict(_project_data(layout))


def test_project_loader_rejects_future_spatial_schema_version():
    layout = {"version": 2, "rooms": [], "devices": []}

    with pytest.raises(ProjectFormatError, match="future spatial layout version"):
        project_from_dict(_project_data(layout))


def test_unversioned_spatial_layout_migrates_missing_ids_deterministically():
    legacy = {
        "grid_m": 0.25,
        "rooms": [
            {
                "name": "Process",
                "x_m": 0,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            },
            {
                "name": "Process",
                "x_m": 6,
                "y_m": 0,
                "length_m": 5,
                "width_m": 4,
                "height_m": 3,
            },
        ],
        "devices": [],
    }

    first = project_from_dict(_project_data(copy.deepcopy(legacy)))
    second = project_from_dict(_project_data(copy.deepcopy(legacy)))
    first_layout = first.metadata["spatial_layout"]
    second_layout = second.metadata["spatial_layout"]

    assert first_layout == second_layout
    assert first_layout["version"] == 1
    assert [room["id"] for room in first_layout["rooms"]] == ["process", "process-2"]


def test_valid_v1_spatial_layout_preserves_unknown_extension_fields():
    layout = {
        "version": 1,
        "grid_m": 0.5,
        "rooms": [
            {
                **_room(),
                "vendor_extension": {"asset_tag": "A-17"},
            }
        ],
        "devices": [],
        "extension_namespace": {"revision": 4},
    }

    project = project_from_dict(_project_data(copy.deepcopy(layout)))

    assert project.metadata["spatial_layout"] == layout
    assert project.metadata["spatial_layout"] is not layout


def test_valid_spatial_layout_round_trip_preserves_ids_and_geometry(tmp_path):
    layout = {
        "version": 1,
        "grid_m": 0.25,
        "rooms": [_room()],
        "devices": [
            {
                "id": "sensor-a",
                "type": "sensor",
                "name": "Sensor A",
                "room_id": "room-a",
                "x_m": 1.0,
                "y_m": 1.5,
                "z_m": 2.0,
            }
        ],
    }
    project = project_from_dict(_project_data(layout))

    path = save_project_document(tmp_path / "spatial.cleanroomx.json", project)
    loaded = load_project_document(path)

    assert loaded.metadata["spatial_layout"] == project.metadata["spatial_layout"]
    assert loaded.metadata["spatial_layout"]["rooms"][0]["id"] == "room-a"
    assert loaded.metadata["spatial_layout"]["devices"][0]["room_id"] == "room-a"


def test_failed_spatial_validation_does_not_overwrite_existing_project(tmp_path):
    path = tmp_path / "existing.cleanroomx.json"
    original = ProjectDocument(name="Existing")
    save_project_document(path, original)
    before = path.read_bytes()

    corrupt = ProjectDocument(
        name="Corrupt",
        metadata={
            "spatial_layout": {
                "version": 1,
                "rooms": [_room(length_m=-5)],
                "devices": [],
            }
        },
    )
    with pytest.raises(ProjectFormatError, match="length_m must be greater than zero"):
        save_project_document(path, corrupt)

    assert path.read_bytes() == before
    assert load_project_document(path) == original
