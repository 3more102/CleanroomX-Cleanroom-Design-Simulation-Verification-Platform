from __future__ import annotations

from pathlib import Path

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    save_project_document,
)
from cleanroomx.spatial import SPATIAL_METADATA_KEY, normalize_layout
from cleanroomx.spatial_engineering import engineering_mapping_diagnostics, pressure_relationships


def _project() -> ProjectDocument:
    analysis = AnalysisDocument(
        id="verification",
        name="Verification",
        kind="project_verification",
        input={
            "rooms": [
                {
                    "name": "Room A",
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 15.0,
                    "supply_airflow_m3_h": 1200.0,
                    "min_ach": 20.0,
                },
                {
                    "name": "Room B",
                    "length_m": 3.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 5.0,
                    "supply_airflow_m3_h": 720.0,
                    "min_ach": 20.0,
                },
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Room A",
                    "lower_pressure_room": "Room B",
                    "min_delta_pa": 8.0,
                }
            ],
        },
    )
    layout = normalize_layout(
        {
            "version": 1,
            "grid_m": 0.25,
            "rooms": [
                {
                    "id": "room-a",
                    "name": "Room A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "elevation_m": 1.25,
                    "pressure_pa": 15.0,
                    "classification": "Project classification",
                    "temperature_target_c": 21.5,
                    "humidity_target_percent": 45.0,
                    "notes": "Stable spatial metadata",
                    "engineering_ref": {
                        "analysis_id": "verification",
                        "room_name": "Room A",
                    },
                },
                {
                    "id": "room-b",
                    "name": "Room B",
                    "x_m": 5.0,
                    "y_m": 0.0,
                    "length_m": 3.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "elevation_m": 1.25,
                    "pressure_pa": 5.0,
                    "engineering_ref": {
                        "analysis_id": "verification",
                        "room_name": "Room B",
                    },
                },
            ],
            "devices": [
                {
                    "id": "sensor-a",
                    "type": "sensor",
                    "name": "DP-01",
                    "room_id": "room-a",
                    "x_m": 2.5,
                    "y_m": 2.0,
                    "z_m": 1.5,
                }
            ],
        }
    )
    return ProjectDocument(
        name="Spatial round trip",
        analyses=[analysis],
        active_analysis_id=analysis.id,
        metadata={SPATIAL_METADATA_KEY: layout},
    )


def test_spatial_project_save_open_round_trip_preserves_geometry_ids_mapping_and_pressure(tmp_path):
    project = _project()
    path = tmp_path / "spatial.cleanroomx.json"

    save_project_document(path, project)
    first_bytes = path.read_bytes()
    loaded = load_project_document(path)
    save_project_document(path, loaded)

    assert path.read_bytes() == first_bytes
    assert loaded.metadata[SPATIAL_METADATA_KEY] == project.metadata[SPATIAL_METADATA_KEY]
    layout = loaded.metadata[SPATIAL_METADATA_KEY]
    assert [room["id"] for room in layout["rooms"]] == ["room-a", "room-b"]
    assert layout["rooms"][0]["engineering_ref"] == {
        "analysis_id": "verification",
        "room_name": "Room A",
    }
    assert layout["rooms"][0]["elevation_m"] == 1.25
    active = loaded.analysis_by_id("verification")
    assert [item["state"] for item in engineering_mapping_diagnostics(layout, active)] == [
        "synchronized",
        "synchronized",
    ]
    assert pressure_relationships(layout, active)[0]["status"] == "pass"


def test_old_schema_v1_project_without_spatial_metadata_still_opens(tmp_path):
    path = tmp_path / "old.cleanroomx.json"
    path.write_text(
        """{
  "schema": "cleanroomx.project",
  "schema_version": 1,
  "application_version": "0.100.0",
  "project": {"name": "Legacy v0.100", "description": "", "metadata": {}},
  "analyses": [],
  "active_analysis_id": null
}
""",
        encoding="utf-8",
    )

    loaded = load_project_document(path)

    assert loaded.name == "Legacy v0.100"
    assert SPATIAL_METADATA_KEY not in loaded.metadata


def test_invalid_additive_spatial_room_metadata_fails_closed_on_save(tmp_path):
    project = _project()
    project.metadata[SPATIAL_METADATA_KEY]["rooms"][0]["humidity_target_percent"] = 125.0

    with pytest.raises(ProjectFormatError, match="humidity_target_percent"):
        save_project_document(tmp_path / "bad.cleanroomx.json", project)


def test_future_spatial_layout_version_is_rejected(tmp_path):
    project = _project()
    project.metadata[SPATIAL_METADATA_KEY]["version"] = 999

    with pytest.raises(ProjectFormatError, match="unsupported future spatial layout version"):
        save_project_document(tmp_path / "future.cleanroomx.json", project)
