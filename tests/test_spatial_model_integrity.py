from __future__ import annotations

import copy

import pytest

from cleanroomx.project import (
    PROJECT_SCHEMA,
    PROJECT_SCHEMA_VERSION,
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    project_from_dict,
    save_project_document,
)
from cleanroomx.spatial_model import (
    SPATIAL_METADATA_KEY,
    empty_layout,
    ensure_project_layout,
    normalize_layout,
)


def _valid_layout() -> dict:
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "process",
            "name": "Process",
            "x_m": 0.0,
            "y_m": 0.0,
            "length_m": 5.0,
            "width_m": 4.0,
            "height_m": 3.0,
            "pressure_pa": 25.0,
        }
    ]
    layout["devices"] = [
        {
            "id": "sensor-1",
            "type": "sensor",
            "name": "Pressure sensor",
            "room_id": "process",
            "x_m": 2.0,
            "y_m": 2.0,
            "z_m": 1.5,
        }
    ]
    return layout


def _project_payload(layout: dict) -> dict:
    return {
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": {
            "name": "Spatial integrity",
            "description": "",
            "metadata": {SPATIAL_METADATA_KEY: layout},
        },
        "analyses": [],
        "active_analysis_id": None,
    }


def test_normalize_layout_repairs_ids_deterministically_and_uniquely():
    source = {
        "rooms": [
            {"id": "room-a", "name": "A"},
            {"id": "room-a", "name": "B"},
            {"name": "C"},
            {"name": "C"},
        ],
        "devices": [
            {"id": "device-a", "type": "sensor"},
            {"id": "device-a", "type": "sensor"},
            {"type": "sensor"},
        ],
    }

    first = normalize_layout(source)
    second = normalize_layout(copy.deepcopy(source))

    assert first == second
    assert [room["id"] for room in first["rooms"]] == [
        "room-a",
        "room-a-2",
        "c",
        "c-2",
    ]
    assert [device["id"] for device in first["devices"]] == [
        "device-a",
        "device-a-2",
        "device-3",
    ]


def test_ensure_project_layout_does_not_mutate_existing_metadata_on_refresh():
    raw = _valid_layout()
    project = ProjectDocument(
        name="Read only refresh",
        metadata={SPATIAL_METADATA_KEY: copy.deepcopy(raw)},
    )
    before = copy.deepcopy(project.metadata)

    layout = ensure_project_layout(project)

    assert project.metadata == before
    assert layout == normalize_layout(raw)
    assert layout is not project.metadata[SPATIAL_METADATA_KEY]
    layout["rooms"][0]["x_m"] = 99.0
    assert project.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["x_m"] == 0.0


def test_project_loader_rejects_duplicate_spatial_room_ids():
    layout = _valid_layout()
    layout["rooms"].append(
        {
            **layout["rooms"][0],
            "name": "Duplicate identity",
        }
    )

    with pytest.raises(ProjectFormatError, match="duplicates spatial room id"):
        project_from_dict(_project_payload(layout))


def test_project_loader_rejects_duplicate_spatial_device_ids():
    layout = _valid_layout()
    layout["devices"].append(
        {
            **layout["devices"][0],
            "name": "Duplicate identity",
        }
    )

    with pytest.raises(ProjectFormatError, match="duplicates spatial device id"):
        project_from_dict(_project_payload(layout))


def test_project_loader_rejects_orphan_spatial_device_reference():
    layout = _valid_layout()
    layout["devices"][0]["room_id"] = "missing-room"

    with pytest.raises(ProjectFormatError, match="references missing spatial room id"):
        project_from_dict(_project_payload(layout))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("length_m", 0.0, "must be greater than zero"),
        ("width_m", float("inf"), "finite number"),
        ("x_m", float("nan"), "finite number"),
    ],
)
def test_project_loader_rejects_invalid_spatial_geometry(field, value, message):
    layout = _valid_layout()
    layout["rooms"][0][field] = value

    with pytest.raises(ProjectFormatError, match=message):
        project_from_dict(_project_payload(layout))


def test_project_loader_rejects_unknown_spatial_layout_version():
    layout = _valid_layout()
    layout["version"] = 2

    with pytest.raises(ProjectFormatError, match="version must be 1"):
        project_from_dict(_project_payload(layout))


def test_invalid_spatial_save_does_not_touch_existing_project_file(tmp_path):
    target = tmp_path / "protected.cleanroomx.json"
    target.write_text("existing project bytes\n", encoding="utf-8")
    layout = _valid_layout()
    layout["devices"][0]["room_id"] = "missing-room"
    project = ProjectDocument(
        name="Invalid spatial state",
        metadata={SPATIAL_METADATA_KEY: layout},
    )

    with pytest.raises(ProjectFormatError, match="references missing spatial room id"):
        save_project_document(target, project)

    assert target.read_text(encoding="utf-8") == "existing project bytes\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_valid_spatial_layout_round_trips_without_identity_changes(tmp_path):
    layout = _valid_layout()
    project = ProjectDocument(
        name="Valid spatial state",
        metadata={SPATIAL_METADATA_KEY: copy.deepcopy(layout)},
    )

    path = save_project_document(tmp_path / "valid.cleanroomx.json", project)
    loaded = load_project_document(path)

    assert loaded.metadata[SPATIAL_METADATA_KEY] == layout
