from __future__ import annotations

import json

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    project_from_dict,
    save_project_document,
)
from cleanroomx.spatial import empty_layout, normalize_layout, validate_layout
from cleanroomx.spatial_integrity import (
    SpatialLayoutFormatError,
    validate_spatial_layout_document,
)


def test_extended_room_and_opening_fields_survive_normalization():
    layout = normalize_layout(
        {
            **empty_layout(),
            "rooms": [
                {
                    "id": "r1",
                    "name": "ISO Room A",
                    "x_m": 1,
                    "y_m": 2,
                    "length_m": 6,
                    "width_m": 5,
                    "height_m": 3,
                    "elevation_m": 0.5,
                    "classification": "ISO 7 design basis",
                    "pressure_pa": 25,
                    "pressure_target_pa": 20,
                    "temperature_target_c": 22,
                    "humidity_target_percent": 45,
                    "airflow_ref": "AHU-01 / 2700 m3/h",
                    "engineering_ref": "Process",
                    "engineering_analysis_id": "verification",
                    "notes": "Production suite",
                    "metadata": {"discipline": "architectural"},
                    "engineering_snapshot": {
                        "analysis_id": "verification",
                        "room_ref": "Process",
                        "length_m": 6,
                        "width_m": 5,
                        "height_m": 3,
                        "observed_pressure_pa": 25,
                    },
                }
            ],
            "devices": [
                {
                    "id": "w1",
                    "type": "window",
                    "name": "Observation window",
                    "room_id": "r1",
                    "x_m": 2,
                    "y_m": 2,
                    "z_m": 1,
                    "width_m": 1.2,
                    "height_m": 1.0,
                    "orientation_deg": 90,
                    "metadata": {"fire_rating": "not specified"},
                }
            ],
        }
    )

    room = layout["rooms"][0]
    assert room["elevation_m"] == 0.5
    assert room["classification"] == "ISO 7 design basis"
    assert room["pressure_target_pa"] == 20.0
    assert room["humidity_target_percent"] == 45.0
    assert room["engineering_ref"] == "Process"
    assert room["metadata"] == {"discipline": "architectural"}
    assert layout["devices"][0]["type"] == "window"
    assert layout["devices"][0]["orientation_deg"] == 90.0


def test_spatial_integrity_rejects_zero_dimension_bad_humidity_and_duplicate_ids():
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "r1",
            "name": "A",
            "x_m": 0,
            "y_m": 0,
            "length_m": 0,
            "width_m": 4,
            "height_m": 3,
            "humidity_target_percent": 101,
        }
    ]
    with pytest.raises(SpatialLayoutFormatError, match="length_m"):
        validate_spatial_layout_document(layout)

    layout["rooms"][0]["length_m"] = 4
    with pytest.raises(SpatialLayoutFormatError, match="humidity_target_percent"):
        validate_spatial_layout_document(layout)

    layout["rooms"][0]["humidity_target_percent"] = 45
    layout["rooms"].append(dict(layout["rooms"][0]))
    with pytest.raises(SpatialLayoutFormatError, match="duplicates room id"):
        validate_spatial_layout_document(layout)


def test_advisory_validation_reports_raw_invalid_dimensions_before_normalization():
    issues = validate_layout(
        {
            "rooms": [
                {
                    "id": "bad",
                    "name": "Bad room",
                    "x_m": 0,
                    "y_m": 0,
                    "length_m": -1,
                    "width_m": 0,
                    "height_m": float("nan"),
                }
            ]
        }
    )
    fields = [item.get("field") for item in issues if item["code"] == "invalid_room_dimension"]
    assert fields == ["length_m", "width_m", "height_m"]


def test_extended_spatial_project_round_trip_is_deterministic(tmp_path):
    project = ProjectDocument(
        name="Spatial round trip",
        analyses=[
            AnalysisDocument(
                id="verification",
                name="Verification",
                kind="room_verification",
                input={
                    "name": "Room A",
                    "length_m": 5,
                    "width_m": 4,
                    "height_m": 3,
                    "observed_pressure_pa": 15,
                },
            )
        ],
        active_analysis_id="verification",
        metadata={
            "spatial_layout": normalize_layout(
                {
                    **empty_layout(),
                    "rooms": [
                        {
                            "id": "room-a",
                            "name": "Room A",
                            "x_m": 0,
                            "y_m": 0,
                            "length_m": 5,
                            "width_m": 4,
                            "height_m": 3,
                            "elevation_m": 0,
                            "engineering_ref": "Room A",
                            "engineering_analysis_id": "verification",
                            "classification": "Project basis",
                        }
                    ],
                }
            )
        },
    )
    first_path = tmp_path / "first.cleanroomx.json"
    second_path = tmp_path / "second.cleanroomx.json"

    save_project_document(first_path, project)
    loaded = project_from_dict(json.loads(first_path.read_text(encoding="utf-8")))
    save_project_document(second_path, loaded)

    assert first_path.read_bytes() == second_path.read_bytes()
    assert loaded.metadata["spatial_layout"]["rooms"][0]["id"] == "room-a"
    assert loaded.metadata["spatial_layout"]["rooms"][0]["engineering_ref"] == "Room A"
