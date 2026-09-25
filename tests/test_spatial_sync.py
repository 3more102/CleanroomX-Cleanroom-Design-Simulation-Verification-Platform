from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from cleanroomx.spatial import normalize_layout, sync_layout_to_analysis
from cleanroomx.spatial_integrity import SpatialLayoutFormatError, validate_spatial_layout_document
from cleanroomx.spatial_sync import (
    pressure_relationship_records,
    spatial_sync_status,
    sync_analysis_to_layout,
)


def _analysis():
    return SimpleNamespace(
        kind="project_verification",
        name="Suite verification",
        input={
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "supply_airflow_m3_h": 2700.0,
                    "min_ach": 25.0,
                    "observed_pressure_pa": 30.0,
                },
                {
                    "name": "Ante",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "supply_airflow_m3_h": 720.0,
                    "min_ach": 20.0,
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


def _layout():
    return normalize_layout(
        {
            "version": 1,
            "rooms": [
                {
                    "id": "process",
                    "name": "ISO Process",
                    "analysis_room_name": "Process",
                    "engineering_baseline": {
                        "length_m": 6.0,
                        "width_m": 5.0,
                        "height_m": 3.0,
                        "pressure_pa": 30.0,
                    },
                    "x_m": 0.0,
                    "y_m": 0.0,
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "pressure_pa": 30.0,
                },
                {
                    "id": "ante",
                    "name": "Airlock",
                    "analysis_room_name": "Ante",
                    "engineering_baseline": {
                        "length_m": 4.0,
                        "width_m": 3.0,
                        "height_m": 3.0,
                        "pressure_pa": 8.0,
                    },
                    "x_m": 7.0,
                    "y_m": 0.0,
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "pressure_pa": 8.0,
                },
            ],
            "devices": [],
        }
    )


def _states(layout, analysis):
    return {
        record["room_id"]: record["state"]
        for record in spatial_sync_status(layout, analysis)
    }


def test_sync_status_distinguishes_provenance_states():
    analysis = _analysis()
    layout = _layout()
    assert _states(layout, analysis) == {
        "process": "synchronized",
        "ante": "synchronized",
    }

    geometry_newer = copy.deepcopy(layout)
    geometry_newer["rooms"][0]["length_m"] = 6.5
    assert _states(geometry_newer, analysis)["process"] == "geometry_newer"

    engineering_newer = _analysis()
    engineering_newer.input["rooms"][0]["length_m"] = 6.5
    assert _states(layout, engineering_newer)["process"] == "engineering_data_newer"

    both_changed = copy.deepcopy(layout)
    both_changed["rooms"][0]["length_m"] = 6.25
    assert _states(both_changed, engineering_newer)["process"] == "conflicting"


def test_sync_status_handles_unmapped_missing_and_unknown_baseline():
    analysis = _analysis()
    layout = _layout()

    layout["rooms"][0].pop("analysis_room_name")
    assert _states(layout, analysis)["process"] == "unmapped"

    layout = _layout()
    layout["rooms"][0]["analysis_room_name"] = "Deleted room"
    assert _states(layout, analysis)["process"] == "missing_target"

    layout = _layout()
    layout["rooms"][0].pop("engineering_baseline")
    layout["rooms"][0]["length_m"] = 6.5
    assert _states(layout, analysis)["process"] == "conflicting"


def test_engineering_to_geometry_sync_changes_only_spatial_side_and_records_baseline():
    analysis = _analysis()
    analysis.input["rooms"][0]["length_m"] = 6.75
    original_analysis = copy.deepcopy(analysis.input)
    layout = _layout()

    assert sync_analysis_to_layout(layout, analysis) is True

    process = next(room for room in layout["rooms"] if room["id"] == "process")
    assert process["length_m"] == 6.75
    assert process["engineering_baseline"]["length_m"] == 6.75
    assert analysis.input == original_analysis
    assert _states(layout, analysis)["process"] == "synchronized"


def test_geometry_to_engineering_sync_records_new_baseline_without_touching_other_inputs():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][0]["length_m"] = 6.5
    original_airflow = analysis.input["rooms"][0]["supply_airflow_m3_h"]
    original_min_ach = analysis.input["rooms"][0]["min_ach"]

    assert sync_layout_to_analysis(layout, analysis) is True

    target = analysis.input["rooms"][0]
    process = next(room for room in layout["rooms"] if room["id"] == "process")
    assert target["length_m"] == 6.5
    assert target["supply_airflow_m3_h"] == original_airflow
    assert target["min_ach"] == original_min_ach
    assert process["engineering_baseline"]["length_m"] == 6.5
    assert _states(layout, analysis)["process"] == "synchronized"


def test_pressure_relationship_records_report_pass_fail_and_unavailable_without_inventing_values():
    analysis = _analysis()
    layout = _layout()

    record = pressure_relationship_records(layout, analysis)[0]
    assert record["state"] == "pass"
    assert record["delta_pa"] == 22.0
    assert record["min_delta_pa"] == 10.0

    analysis.input["rooms"][0]["observed_pressure_pa"] = 12.0
    record = pressure_relationship_records(layout, analysis)[0]
    assert record["state"] == "fail"
    assert record["delta_pa"] == 4.0

    analysis.input["rooms"][0].pop("observed_pressure_pa")
    record = pressure_relationship_records(layout, analysis)[0]
    assert record["state"] == "unavailable"
    assert record["delta_pa"] is None


def test_normalization_preserves_sync_baseline_and_persistence_boundary_validates_it():
    layout = _layout()
    normalized = normalize_layout(copy.deepcopy(layout))
    assert normalized["rooms"][0]["engineering_baseline"] == {
        "length_m": 6.0,
        "width_m": 5.0,
        "height_m": 3.0,
        "pressure_pa": 30.0,
    }
    validate_spatial_layout_document(normalized)

    normalized["rooms"][0]["engineering_baseline"]["length_m"] = -1.0
    with pytest.raises(SpatialLayoutFormatError, match="must be greater than zero"):
        validate_spatial_layout_document(normalized)


def test_room_verification_sync_is_explicit_and_does_not_map_extra_rooms():
    analysis = SimpleNamespace(
        kind="room_verification",
        name="Single room",
        input={
            "name": "Process",
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
            "observed_pressure_pa": 30.0,
        },
    )
    layout = _layout()
    records = spatial_sync_status(layout, analysis)
    assert records[0]["state"] == "synchronized"
    assert records[1]["state"] == "unmapped"
