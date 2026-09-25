from __future__ import annotations

import copy

import pytest

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial import sync_layout_to_analysis
from cleanroomx.spatial_engineering import (
    engineering_mapping_diagnostics,
    pressure_relationships,
    resolve_room_mapping,
    room_pressure_value,
)


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="verification",
        name="Facility verification",
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
                "engineering_ref": {
                    "analysis_id": "verification",
                    "room_name": "Process",
                },
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 6.0,
                "width_m": 5.0,
                "height_m": 3.0,
                "elevation_m": 0.0,
                "pressure_pa": 99.0,
            },
            {
                "id": "ante",
                "name": "Ante",
                "engineering_ref": {
                    "analysis_id": "verification",
                    "room_name": "Ante",
                },
                "x_m": 6.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
                "elevation_m": 0.0,
            },
        ]
    }


def test_explicit_mapping_survives_spatial_rename_and_prefers_engineering_pressure():
    analysis = _analysis()
    layout = _layout()
    process = layout["rooms"][0]

    target, state = resolve_room_mapping(process, analysis)
    pressure, source = room_pressure_value(process, analysis)

    assert state == "mapped"
    assert target is analysis.input["rooms"][0]
    assert pressure == 30.0
    assert source == "engineering_observed"


def test_mapping_diagnostics_report_synchronized_conflict_and_unmapped_states():
    analysis = _analysis()
    layout = _layout()

    diagnostics = engineering_mapping_diagnostics(layout, analysis)
    assert [item["state"] for item in diagnostics] == ["synchronized", "synchronized"]

    layout["rooms"][0]["length_m"] = 7.0
    diagnostics = engineering_mapping_diagnostics(layout, analysis)
    assert diagnostics[0]["state"] == "conflicting"
    assert diagnostics[0]["differences"] == [
        {
            "field": "length_m",
            "spatial": 7.0,
            "engineering": 6.0,
            "reason": "different",
        }
    ]

    layout["rooms"][1].pop("engineering_ref")
    layout["rooms"][1]["name"] = "No engineering target"
    diagnostics = engineering_mapping_diagnostics(layout, analysis)
    assert diagnostics[1]["state"] == "unmapped"


def test_missing_explicit_target_is_distinct_from_unmapped():
    analysis = _analysis()
    room = _layout()["rooms"][0]
    room["engineering_ref"]["room_name"] = "Removed Room"

    target, state = resolve_room_mapping(room, analysis)

    assert target is None
    assert state == "missing_target"


def test_pressure_relationship_uses_real_observed_values_and_reports_pass():
    relationships = pressure_relationships(_layout(), _analysis())

    assert relationships == [
        {
            "index": 0,
            "higher_pressure_room": "Process",
            "lower_pressure_room": "Ante",
            "min_delta_pa": 10.0,
            "higher_room_id": "process",
            "lower_room_id": "ante",
            "status": "pass",
            "actual_delta_pa": 22.0,
            "higher_pressure_pa": 30.0,
            "lower_pressure_pa": 8.0,
            "higher_pressure_source": "engineering_observed",
            "lower_pressure_source": "engineering_observed",
        }
    ]


def test_pressure_relationship_reports_fail_and_unavailable_without_inventing_values():
    analysis = _analysis()
    analysis.input["rooms"][1]["observed_pressure_pa"] = 25.0
    failed = pressure_relationships(_layout(), analysis)
    assert failed[0]["status"] == "fail"
    assert failed[0]["actual_delta_pa"] == 5.0

    analysis.input["rooms"][1].pop("observed_pressure_pa")
    layout = _layout()
    layout["rooms"][1].pop("pressure_pa", None)
    unavailable = pressure_relationships(layout, analysis)
    assert unavailable[0]["status"] == "unavailable"
    assert unavailable[0]["actual_delta_pa"] is None
    assert unavailable[0]["lower_pressure_pa"] is None


def test_explicit_sync_updates_only_mapped_engineering_fields_and_preserves_identity():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][0]["length_m"] = 7.25
    layout["rooms"][0]["pressure_pa"] = 31.0
    before_cascade = copy.deepcopy(analysis.input["pressure_cascade"])

    changed = sync_layout_to_analysis(layout, analysis)

    assert changed is True
    process = analysis.input["rooms"][0]
    assert process["name"] == "Process"
    assert process["length_m"] == 7.25
    assert process["observed_pressure_pa"] == 31.0
    assert process["supply_airflow_m3_h"] == 2700.0
    assert analysis.input["pressure_cascade"] == before_cascade
