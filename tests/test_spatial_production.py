from __future__ import annotations

import copy

from cleanroomx.project import AnalysisDocument, project_from_dict
from cleanroomx.spatial import (
    ensure_project_layout,
    normalize_layout,
    spatial_engineering_status,
    spatial_pressure_overlay,
    sync_analysis_to_layout,
    sync_layout_to_analysis,
    validate_layout,
)
from cleanroomx.spatial_integrity import validate_spatial_layout_document


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="facility-verification",
        name="Facility verification",
        kind="project_verification",
        input={
            "name": "Facility",
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "supply_airflow_m3_h": 2700.0,
                    "min_pressure_pa": 20.0,
                    "observed_pressure_pa": 30.0,
                }
            ],
            "pressure_cascade": [],
        },
    )


def _layout() -> dict:
    return normalize_layout(
        {
            "version": 1,
            "rooms": [
                {
                    "id": "process",
                    "name": "ISO Process",
                    "analysis_room_name": "Process",
                    "x_m": 1.0,
                    "y_m": 2.0,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "floor_elevation_m": 0.25,
                    "pressure_pa": 30.0,
                    "pressure_target_pa": 20.0,
                    "temperature_target_c": 21.0,
                    "humidity_target_rh_pct": 45.0,
                    "classification": "ISO 7",
                    "engineering_zone_id": "AHU-1-Z1",
                    "airflow_ref": "facility-verification:Process",
                    "notes": "Primary process room",
                    "metadata": {"owner": "operations"},
                }
            ],
            "devices": [
                {
                    "id": "window-1",
                    "type": "window",
                    "name": "Observation Window",
                    "room_id": "process",
                    "x_m": 2.0,
                    "y_m": 2.0,
                    "z_m": 1.0,
                    "width_m": 1.2,
                    "height_m": 1.0,
                    "orientation_deg": 0.0,
                    "wall_side": "south",
                    "metadata": {"rated": False},
                }
            ],
        }
    )


def test_raw_validation_reports_invalid_dimensions_before_normalization_can_repair_them():
    bad = _layout()
    bad["rooms"][0]["length_m"] = 0.0
    bad["rooms"][0]["width_m"] = -2.0

    issues = validate_layout(bad)

    invalid = [issue for issue in issues if issue["code"] == "invalid_room_geometry"]
    assert [(issue["item_ids"], issue["field"]) for issue in invalid] == [
        (["process"], "length_m"),
        (["process"], "width_m"),
    ]


def test_raw_validation_reports_duplicate_room_and_object_ids_deterministically():
    bad = _layout()
    second = copy.deepcopy(bad["rooms"][0])
    second["name"] = "Second"
    second["x_m"] = 20.0
    bad["rooms"].append(second)
    bad["devices"].append(copy.deepcopy(bad["devices"][0]))

    codes = [issue["code"] for issue in validate_layout(bad)]

    assert codes[:2] == ["duplicate_room_id", "duplicate_device_id"]


def test_additive_spatial_metadata_survives_normalization_and_project_round_trip():
    layout = _layout()
    analysis = _analysis()
    sync_layout_to_analysis(layout, analysis)
    validate_spatial_layout_document(layout)
    project_data = {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "application_version": "test",
        "project": {
            "name": "Production spatial round trip",
            "description": "",
            "metadata": {"spatial_layout": layout},
        },
        "analyses": [
            {
                "id": analysis.id,
                "name": analysis.name,
                "kind": analysis.kind,
                "input": analysis.input,
            }
        ],
        "active_analysis_id": analysis.id,
    }

    loaded = project_from_dict(project_data)
    restored = loaded.to_dict()["project"]["metadata"]["spatial_layout"]
    room = restored["rooms"][0]
    window = restored["devices"][0]

    assert room["id"] == "process"
    assert room["analysis_room_name"] == "Process"
    assert room["engineering_zone_id"] == "AHU-1-Z1"
    assert room["pressure_target_pa"] == 20.0
    assert room["temperature_target_c"] == 21.0
    assert room["humidity_target_rh_pct"] == 45.0
    assert room["notes"] == "Primary process room"
    assert room["metadata"] == {"owner": "operations"}
    assert room["engineering_ref"]["analysis_id"] == analysis.id
    assert room["engineering_ref"]["room_name"] == "Process"
    assert window["id"] == "window-1"
    assert window["type"] == "window"
    assert window["metadata"] == {"rated": False}


def test_explicit_push_then_divergence_then_pull_has_visible_sync_state():
    layout = _layout()
    analysis = _analysis()

    assert sync_layout_to_analysis(layout, analysis) is True
    assert spatial_engineering_status(layout, analysis)["rooms"][0]["status"] == "synchronized"

    layout["rooms"][0]["length_m"] = 7.0
    assert spatial_engineering_status(layout, analysis)["rooms"][0]["status"] == "geometry_newer"

    analysis.input["rooms"][0]["width_m"] = 5.5
    assert spatial_engineering_status(layout, analysis)["rooms"][0]["status"] == "conflicting"

    assert sync_analysis_to_layout(layout, analysis) is True
    assert layout["rooms"][0]["length_m"] == 6.0
    assert layout["rooms"][0]["width_m"] == 5.5
    assert spatial_engineering_status(layout, analysis)["rooms"][0]["status"] == "synchronized"


def test_pressure_projection_does_not_use_stale_or_invented_solver_values():
    layout = _layout()
    analysis = _analysis()
    sync_layout_to_analysis(layout, analysis)

    configured = spatial_pressure_overlay(layout, analysis)
    assert configured["rooms"][0]["pressure_pa"] == 30.0
    assert configured["rooms"][0]["source"] == "configured"

    result = {
        "project": "Facility",
        "rooms": [
            {
                "room": "Process",
                "ach": 30.0,
                "findings": [
                    {
                        "code": "PRESSURE",
                        "status": "fail",
                        "message": "below target",
                        "actual": 18.0,
                        "limit": 20.0,
                        "unit": "Pa",
                    }
                ],
            }
        ],
        "pressure_cascade": [],
    }
    resolved = spatial_pressure_overlay(layout, analysis, result)
    assert resolved["rooms"][0]["pressure_pa"] == 18.0
    assert resolved["rooms"][0]["pressure_target_pa"] == 20.0
    assert resolved["rooms"][0]["source"] == "result"
    assert resolved["rooms"][0]["status"] == "fail"


def test_opening_existing_layout_does_not_invent_sync_provenance():
    analysis = _analysis()
    layout = _layout()
    assert "engineering_ref" not in layout["rooms"][0]

    class Project:
        metadata = {"spatial_layout": layout}
        analyses = [analysis]

    opened = ensure_project_layout(Project(), analysis)

    assert "engineering_ref" not in opened["rooms"][0]
    assert spatial_engineering_status(opened, analysis)["rooms"][0]["status"] == "synchronized"

    analysis.input["rooms"][0]["length_m"] = 6.25
    assert spatial_engineering_status(opened, analysis)["rooms"][0]["status"] == "conflicting"


def test_spatial_push_preflights_all_links_before_mutating_engineering_input():
    analysis = _analysis()
    original_length = analysis.input["rooms"][0]["length_m"]
    layout = _layout()
    layout["rooms"][0]["length_m"] = 7.0
    layout["rooms"].append(
        {
            "id": "missing",
            "name": "Missing",
            "analysis_room_name": "No such engineering room",
            "x_m": 20.0,
            "y_m": 0.0,
            "length_m": 2.0,
            "width_m": 2.0,
            "height_m": 3.0,
        }
    )

    import pytest
    from cleanroomx.spatial import SpatialSyncError

    with pytest.raises(SpatialSyncError, match="does not exist"):
        sync_layout_to_analysis(layout, analysis)

    assert analysis.input["rooms"][0]["length_m"] == original_length
