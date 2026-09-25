from __future__ import annotations

import copy

import pytest

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial import SpatialSyncError, sync_layout_to_analysis
from cleanroomx.spatial_engineering import (
    engineering_mapping_diagnostics,
    pressure_relationships,
    resolve_room_mapping,
    room_pressure_value,
)


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="verification",
        name="Facility",
        kind="project_verification",
        input={
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
                "id": "process",
                "name": "ISO Process",
                "analysis_room_name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 6.0,
                "width_m": 5.0,
                "height_m": 3.0,
                "pressure_pa": 30.0,
            },
            {
                "id": "ante",
                "name": "Ante",
                "analysis_room_name": "Ante",
                "x_m": 6.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
            },
        ]
    }


def test_stable_analysis_room_link_survives_spatial_rename_and_uses_engineering_pressure():
    analysis = _analysis()
    room = _layout()["rooms"][0]
    room["pressure_pa"] = 99.0
    target, state = resolve_room_mapping(room, analysis)
    pressure, source = room_pressure_value(room, analysis)

    assert state == "mapped"
    assert target is analysis.input["rooms"][0]
    assert pressure == 30.0
    assert source == "engineering_observed"


def test_mapping_diagnostics_distinguish_synchronized_conflicting_unmapped_and_missing():
    analysis = _analysis()
    layout = _layout()
    assert [item["state"] for item in engineering_mapping_diagnostics(layout, analysis)] == [
        "synchronized",
        "synchronized",
    ]

    layout["rooms"][0]["length_m"] = 7.0
    diagnostics = engineering_mapping_diagnostics(layout, analysis)
    assert diagnostics[0]["state"] == "conflicting"
    assert [item["field"] for item in diagnostics[0]["differences"]] == ["length_m"]

    layout["rooms"][1].pop("analysis_room_name")
    layout["rooms"][1]["name"] = "No target"
    assert engineering_mapping_diagnostics(layout, analysis)[1]["state"] == "unmapped"

    layout["rooms"][1]["analysis_room_name"] = "Removed"
    assert engineering_mapping_diagnostics(layout, analysis)[1]["state"] == "missing_target"


def test_pressure_relationship_uses_observed_values_and_reports_pass_fail_unavailable():
    analysis = _analysis()
    layout = _layout()

    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["status"] == "pass"
    assert relationship["actual_delta_pa"] == 22.0

    analysis.input["rooms"][1]["observed_pressure_pa"] = 25.0
    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["status"] == "fail"
    assert relationship["actual_delta_pa"] == 5.0

    analysis.input["rooms"][1].pop("observed_pressure_pa")
    relationship = pressure_relationships(layout, analysis)[0]
    assert relationship["status"] == "unavailable"
    assert relationship["actual_delta_pa"] is None


def test_explicit_geometry_sync_preserves_engineering_identity_and_non_geometry_fields():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][0]["length_m"] = 7.25
    layout["rooms"][0]["pressure_pa"] = 31.0
    cascade = copy.deepcopy(analysis.input["pressure_cascade"])

    assert sync_layout_to_analysis(layout, analysis) is True
    process = analysis.input["rooms"][0]
    assert process["name"] == "Process"
    assert process["length_m"] == 7.25
    assert process["observed_pressure_pa"] == 31.0
    assert process["supply_airflow_m3_h"] == 2700.0
    assert analysis.input["pressure_cascade"] == cascade



def test_project_sync_preflights_all_mappings_before_mutating():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][0]["length_m"] = 7.25
    layout["rooms"][1]["analysis_room_name"] = "Removed"
    before = copy.deepcopy(analysis.input)

    with pytest.raises(SpatialSyncError, match="does not exist"):
        sync_layout_to_analysis(layout, analysis)

    assert analysis.input == before

def test_room_verification_sync_uses_explicit_mapping_instead_of_first_spatial_room():
    analysis = AnalysisDocument(
        id="room-check",
        name="Single room",
        kind="room_verification",
        input={
            "name": "Target",
            "length_m": 1.0,
            "width_m": 1.0,
            "height_m": 2.5,
            "observed_pressure_pa": 7.0,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "other",
                "name": "Other",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 9.0,
                "width_m": 9.0,
                "height_m": 9.0,
                "pressure_pa": 99.0,
            },
            {
                "id": "mapped",
                "name": "Renamed spatial display",
                "analysis_room_name": "Target",
                "x_m": 10.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
                "pressure_pa": 12.0,
            },
        ]
    }

    assert sync_layout_to_analysis(layout, analysis) is True
    assert analysis.input["name"] == "Target"
    assert analysis.input["length_m"] == 5.0
    assert analysis.input["width_m"] == 4.0
    assert analysis.input["height_m"] == 3.0
    assert analysis.input["observed_pressure_pa"] == 12.0


def test_room_verification_sync_rejects_missing_mapping_without_mutating():
    analysis = AnalysisDocument(
        id="room-check",
        name="Single room",
        kind="room_verification",
        input={
            "name": "Target",
            "length_m": 1.0,
            "width_m": 1.0,
            "height_m": 2.5,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "other",
                "name": "Other",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
            }
        ]
    }
    before = copy.deepcopy(analysis.input)

    with pytest.raises(SpatialSyncError, match="no spatial room maps"):
        sync_layout_to_analysis(layout, analysis)

    assert analysis.input == before


def test_room_verification_sync_rejects_multiple_spatial_rooms_mapped_to_target():
    analysis = AnalysisDocument(
        id="room-check",
        name="Single room",
        kind="room_verification",
        input={
            "name": "Target",
            "length_m": 1.0,
            "width_m": 1.0,
            "height_m": 2.5,
        },
    )
    layout = {
        "rooms": [
            {
                "id": "a",
                "name": "A",
                "analysis_room_name": "Target",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
            },
            {
                "id": "b",
                "name": "B",
                "analysis_room_name": "Target",
                "x_m": 6.0,
                "y_m": 0.0,
                "length_m": 5.0,
                "width_m": 4.0,
                "height_m": 3.0,
            },
        ]
    }

    with pytest.raises(SpatialSyncError, match="multiple spatial rooms"):
        sync_layout_to_analysis(layout, analysis)

