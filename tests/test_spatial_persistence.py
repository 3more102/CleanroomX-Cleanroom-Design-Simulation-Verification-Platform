from __future__ import annotations

import pytest

from cleanroomx.project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFormatError,
    load_project_document,
    save_project_document,
)
from cleanroomx.spatial import SPATIAL_METADATA_KEY, normalize_layout
from cleanroomx.spatial_engineering import engineering_mapping_diagnostics


def _project() -> ProjectDocument:
    analysis = AnalysisDocument(
        id="verification",
        name="Facility",
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
                }
            ]
        },
    )
    layout = normalize_layout(
        {
            "floor": {
                "id": "floor-1",
                "name": "Production",
                "elevation_m": 1.25,
                "default_ceiling_height_m": 3.0,
                "units": "m",
            },
            "grid_m": 0.25,
            "rooms": [
                {
                    "id": "room-a",
                    "name": "Room A",
                    "analysis_room_name": "Room A",
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 5.0,
                    "width_m": 4.0,
                    "height_m": 3.0,
                    "floor_elevation_m": 1.25,
                    "pressure_pa": 15.0,
                    "classification": "Project-defined",
                }
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
        name="Spatial persistence",
        analyses=[analysis],
        active_analysis_id="verification",
        metadata={SPATIAL_METADATA_KEY: layout},
    )


def test_spatial_save_open_save_is_deterministic_and_preserves_identity_mapping_and_geometry(tmp_path):
    project = _project()
    path = tmp_path / "spatial.cleanroomx.json"

    save_project_document(path, project)
    first = path.read_bytes()
    loaded = load_project_document(path)
    save_project_document(path, loaded)

    assert path.read_bytes() == first
    layout = loaded.metadata[SPATIAL_METADATA_KEY]
    assert layout == project.metadata[SPATIAL_METADATA_KEY]
    assert layout["rooms"][0]["id"] == "room-a"
    assert layout["rooms"][0]["analysis_room_name"] == "Room A"
    assert layout["rooms"][0]["floor_elevation_m"] == 1.25
    assert engineering_mapping_diagnostics(
        layout, loaded.analysis_by_id("verification")
    )[0]["state"] == "synchronized"


def test_v0100_schema_v1_project_without_spatial_metadata_still_opens(tmp_path):
    path = tmp_path / "v0100.cleanroomx.json"
    path.write_text(
        """{
  "schema": "cleanroomx.project",
  "schema_version": 1,
  "application_version": "0.100.0",
  "project": {"name": "v0.100 project", "description": "", "metadata": {}},
  "analyses": [],
  "active_analysis_id": null
}
""",
        encoding="utf-8",
    )
    loaded = load_project_document(path)
    assert loaded.name == "v0.100 project"
    assert SPATIAL_METADATA_KEY not in loaded.metadata


def test_future_spatial_layout_version_fails_closed(tmp_path):
    project = _project()
    project.metadata[SPATIAL_METADATA_KEY]["version"] = 999
    with pytest.raises(ProjectFormatError, match="unsupported future spatial layout version"):
        save_project_document(tmp_path / "future.cleanroomx.json", project)
