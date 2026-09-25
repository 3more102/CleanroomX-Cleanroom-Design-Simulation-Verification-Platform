from __future__ import annotations

import copy

import pytest

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial_mapping import (
    SpatialMappingError,
    engineering_sync_status,
    pressure_relationships,
    pull_analysis_to_layout,
    push_layout_to_analysis,
)


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="verification",
        name="Facility verification",
        kind="project_verification",
        input={
            "name": "Suite",
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 30.0,
                    "supply_airflow_m3_h": 2700.0,
                },
                {
                    "name": "Ante",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 8.0,
                    "supply_airflow_m3_h": 720.0,
                },
            ],
            "pressure_cascade": [
                {
                    "higher_pressure_room": "Process",
                    "lower_pressure_room": "Ante",
                    "min_delta_pa": 10.0,
                }
            ],
        },
    )


def _layout() -> dict:
    return {
        "rooms": [
            {
                "id": "cleanroom",
                "name": "Cleanroom",
                "engineering_ref": "Process",
                "engineering_analysis_id": "verification",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 6.0,
                "width_m": 5.0,
                "height_m": 3.0,
                "elevation_m": 0.0,
                "pressure_pa": 30.0,
            },
            {
                "id": "airlock",
                "name": "Airlock",
                "engineering_ref": "Ante",
                "engineering_analysis_id": "verification",
                "x_m": 6.5,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
                "elevation_m": 0.0,
                "pressure_pa": 8.0,
            },
        ],
        "devices": [],
    }


def test_push_establishes_baseline_and_reports_directional_changes():
    analysis = _analysis()
    layout = _layout()

    assert push_layout_to_analysis(layout, analysis) is True
    assert {item["state"] for item in engineering_sync_status(layout, analysis).values()} == {
        "synchronized"
    }

    layout["rooms"][0]["length_m"] = 7.0
    assert engineering_sync_status(layout, analysis)["cleanroom"]["state"] == "geometry_newer"

    analysis.input["rooms"][0]["width_m"] = 6.0
    assert engineering_sync_status(layout, analysis)["cleanroom"]["state"] == "conflicting"


def test_engineering_newer_and_explicit_pull_restore_synchronization():
    analysis = _analysis()
    layout = _layout()
    push_layout_to_analysis(layout, analysis)

    analysis.input["rooms"][0]["length_m"] = 6.5
    status = engineering_sync_status(layout, analysis)["cleanroom"]
    assert status["state"] == "engineering_data_newer"

    assert pull_analysis_to_layout(layout, analysis) is True
    assert layout["rooms"][0]["length_m"] == 6.5
    assert layout["rooms"][0]["pressure_pa"] == 30.0
    assert engineering_sync_status(layout, analysis)["cleanroom"]["state"] == "synchronized"


def test_unmapped_target_is_explicit_and_does_not_mutate_analysis():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][0]["engineering_ref"] = "Missing"
    original = copy.deepcopy(analysis.input)

    status = engineering_sync_status(layout, analysis)["cleanroom"]
    assert status["state"] == "unmapped"
    assert push_layout_to_analysis(layout, analysis) is True
    assert analysis.input == original


def test_duplicate_spatial_mapping_is_rejected_before_engineering_mutation():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][1]["engineering_ref"] = "Process"
    original = copy.deepcopy(analysis.input)

    with pytest.raises(SpatialMappingError, match="duplicated"):
        push_layout_to_analysis(layout, analysis)

    assert analysis.input == original


def test_pressure_relationships_use_only_available_configured_evidence():
    analysis = _analysis()
    layout = _layout()

    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["actual_delta_pa"] == 22.0
    assert relationship["status"] == "pass"

    layout["rooms"][0]["pressure_pa"] = 12.0
    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["actual_delta_pa"] == 4.0
    assert relationship["status"] == "conflict"

    layout["rooms"][0].pop("pressure_pa")
    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["actual_delta_pa"] is None
    assert relationship["status"] == "unavailable"


def test_legacy_single_room_sync_maps_the_only_engineering_room_without_renaming_it():
    analysis = AnalysisDocument(
        id="room-check",
        name="Room check",
        kind="room_verification",
        input={
            "name": "Engineering Name",
            "length_m": 4.0,
            "width_m": 4.0,
            "height_m": 3.0,
            "observed_pressure_pa": 10.0,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "room-a",
                "name": "Display Name",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
                "pressure_pa": 12.0,
            }
        ]
    }

    assert push_layout_to_analysis(layout, analysis) is True
    assert analysis.input["name"] == "Engineering Name"
    assert analysis.input["length_m"] == 5.0
    assert analysis.input["observed_pressure_pa"] == 12.0
    assert layout["rooms"][0]["engineering_ref"] == "Engineering Name"
