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
from cleanroomx.spatial import ensure_project_layout
from cleanroomx.spatial_schema import (
    SPATIAL_LAYOUT_VERSION,
    SpatialLayoutFormatError,
    normalize_layout,
    validate_persisted_spatial_layout,
)


def _valid_layout() -> dict:
    return {
        "version": SPATIAL_LAYOUT_VERSION,
        "grid_m": 0.5,
        "rooms": [
            {
                "id": "room-a",
                "name": "Room A",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 2.8,
                "pressure_pa": 12.0,
            }
        ],
        "devices": [
            {
                "id": "sensor-a",
                "type": "sensor",
                "name": "Sensor A",
                "room_id": "room-a",
                "x_m": 1.0,
                "y_m": 1.0,
                "z_m": 1.5,
            }
        ],
        "view": {
            "zoom_2d": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "azimuth_deg": 35.0,
            "elevation_deg": 28.0,
            "zoom_3d": 1.0,
            "pan_3d_x": 0.0,
            "pan_3d_y": 0.0,
        },
    }


def _project_dict(layout: dict) -> dict:
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


def test_persisted_spatial_layout_accepts_valid_referentially_complete_v1():
    validate_persisted_spatial_layout(_valid_layout())


@pytest.mark.parametrize(
    ("mutate", "message"),
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
            lambda layout: layout["devices"][0].update({"room_id": "missing-room"}),
            "references missing room",
        ),
        (
            lambda layout: layout["rooms"][0].update({"length_m": 0.0}),
            "greater than zero",
        ),
        (
            lambda layout: layout["rooms"][0].update({"x_m": float("inf")}),
            "finite number",
        ),
        (
            lambda layout: layout["devices"][0].update({"type": "unknown-device"}),
            "type must be one of",
        ),
        (
            lambda layout: layout["rooms"][0].update({"id": " room-a "}),
            "leading or trailing whitespace",
        ),
        (
            lambda layout: layout.pop("grid_m"),
            "grid_m must be a finite number",
        ),
        (
            lambda layout: layout.pop("view"),
            "view must be an object",
        ),
        (
            lambda layout: layout["view"].update({"zoom_2d": 9.0}),
            "zoom_2d must be between",
        ),
        (
            lambda layout: layout["view"].update({"elevation_deg": 90.0}),
            "elevation_deg must be between",
        ),
        (
            lambda layout: layout.pop("version"),
            "version must be an integer",
        ),
        (
            lambda layout: layout.update({"version": SPATIAL_LAYOUT_VERSION - 1}),
            "legacy spatial layout version",
        ),
        (
            lambda layout: layout.update({"version": SPATIAL_LAYOUT_VERSION + 1}),
            "future spatial layout version",
        ),
    ],
)
def test_persisted_spatial_layout_rejects_invalid_identity_geometry_and_version(
    mutate, message
):
    layout = _valid_layout()
    mutate(layout)

    with pytest.raises(SpatialLayoutFormatError, match=message):
        validate_persisted_spatial_layout(layout)


def test_project_loader_rejects_corrupt_spatial_metadata_before_workspace_refresh():
    layout = _valid_layout()
    layout["devices"][0]["room_id"] = "deleted-room"

    with pytest.raises(ProjectFormatError, match="invalid spatial project metadata"):
        project_from_dict(_project_dict(layout))


def test_project_save_rejects_invalid_spatial_state_without_replacing_existing_file(tmp_path):
    path = tmp_path / "protected.cleanroomx.json"
    original = ProjectDocument(name="Original", metadata={"spatial_layout": _valid_layout()})
    save_project_document(path, original)
    original_bytes = path.read_bytes()

    invalid = _valid_layout()
    invalid["rooms"][0]["width_m"] = -1.0
    candidate = ProjectDocument(name="Invalid", metadata={"spatial_layout": invalid})

    with pytest.raises(ProjectFormatError, match="invalid spatial project metadata"):
        save_project_document(path, candidate)

    assert path.read_bytes() == original_bytes
    assert load_project_document(path).name == "Original"


def test_valid_spatial_round_trip_preserves_stable_ids_and_references(tmp_path):
    path = tmp_path / "stable.cleanroomx.json"
    project = ProjectDocument(name="Stable", metadata={"spatial_layout": _valid_layout()})

    save_project_document(path, project)
    loaded = load_project_document(path)
    layout = loaded.metadata["spatial_layout"]

    assert layout["rooms"][0]["id"] == "room-a"
    assert layout["devices"][0]["id"] == "sensor-a"
    assert layout["devices"][0]["room_id"] == "room-a"


def test_lenient_normalization_is_deterministic_and_deduplicates_ids():
    source = {
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
        ],
        "devices": [
            {"id": "same", "type": "sensor", "name": "S1", "x_m": 1, "y_m": 1, "z_m": 1},
            {"id": "same", "type": "sensor", "name": "S2", "x_m": 2, "y_m": 2, "z_m": 1},
        ],
    }

    first = normalize_layout(source)
    second = normalize_layout(source)

    assert first == second
    assert [room["id"] for room in first["rooms"]] == ["duplicate", "room-2"]
    assert [device["id"] for device in first["devices"]] == ["same", "device-2"]


def test_workspace_refresh_keeps_valid_persisted_layout_unmodified():
    layout = _valid_layout()
    layout["vendor_extension"] = {"revision": "A"}
    layout["rooms"][0]["asset_tag"] = "ROOM-001"
    project = ProjectDocument(
        name="Stable refresh",
        metadata={"spatial_layout": copy.deepcopy(layout)},
    )

    refreshed = ensure_project_layout(project)

    assert refreshed == layout
    assert project.metadata["spatial_layout"] == layout


def test_normalization_preserves_extension_metadata():
    source = _valid_layout()
    source["vendor_extension"] = {"revision": "A"}
    source["rooms"][0]["asset_tag"] = "ROOM-001"
    source["devices"][0]["calibration_id"] = "CAL-7"
    source["view"]["workspace_extension"] = {"snap_mode": "edge"}

    normalized = normalize_layout(source)

    assert normalized["vendor_extension"] == {"revision": "A"}
    assert normalized["rooms"][0]["asset_tag"] == "ROOM-001"
    assert normalized["devices"][0]["calibration_id"] == "CAL-7"
    assert normalized["view"]["workspace_extension"] == {"snap_mode": "edge"}
