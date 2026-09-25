from __future__ import annotations

import copy

import pytest

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial import (
    SpatialSyncError,
    engineering_sync_status,
    pressure_overlay_state,
    sync_analysis_to_layout,
    sync_layout_to_analysis,
    validate_layout,
)


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="facility",
        name="Facility",
        kind="project_verification",
        input={
            "name": "Facility",
            "rooms": [
                {
                    "name": "Process",
                    "length_m": 6.0,
                    "width_m": 5.0,
                    "height_m": 3.0,
                    "min_pressure_pa": 20.0,
                    "observed_pressure_pa": 30.0,
                },
                {
                    "name": "Ante",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "min_pressure_pa": 5.0,
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
        "version": 1,
        "grid_m": 0.5,
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
                "pressure_pa": 30.0,
            },
            {
                "id": "ante",
                "name": "Ante / Airlock",
                "analysis_room_name": "Ante",
                "x_m": 8.0,
                "y_m": 2.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
                "pressure_pa": 8.0,
            },
        ],
        "devices": [],
    }


def test_pressure_overlay_prefers_completed_solver_evidence_and_cascade_status():
    layout = _layout()
    analysis = _analysis()
    result = {
        "project": "Facility",
        "rooms": [
            {
                "room": "Process",
                "ach": 31.0,
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
            },
            {
                "room": "Ante",
                "ach": 25.0,
                "findings": [
                    {
                        "code": "PRESSURE",
                        "status": "pass",
                        "message": "ok",
                        "actual": 8.0,
                        "limit": 5.0,
                        "unit": "Pa",
                    }
                ],
            },
        ],
        "pressure_cascade": [
            {
                "code": "PRESSURE_CASCADE",
                "status": "pass",
                "message": "ok",
                "higher_pressure_room": "Process",
                "lower_pressure_room": "Ante",
                "actual_delta_pa": 10.0,
                "limit_pa": 10.0,
            }
        ],
    }

    overlay = pressure_overlay_state(layout, analysis, result)
    rooms = {item["room_id"]: item for item in overlay["rooms"]}

    assert rooms["process"]["pressure_pa"] == 18.0
    assert rooms["process"]["pressure_target_pa"] == 20.0
    assert rooms["process"]["source"] == "result"
    assert rooms["process"]["status"] == "fail"
    assert rooms["process"]["ach"] == 31.0
    assert overlay["minimum_pressure_pa"] == 8.0
    assert overlay["maximum_pressure_pa"] == 18.0

    relationship = overlay["relationships"][0]
    assert relationship["higher_room_id"] == "process"
    assert relationship["lower_room_id"] == "ante"
    assert relationship["actual_delta_pa"] == 10.0
    assert relationship["limit_pa"] == 10.0
    assert relationship["status"] == "pass"
    assert relationship["source"] == "result"


def test_pressure_overlay_marks_missing_result_as_configured_or_unavailable():
    layout = _layout()
    analysis = _analysis()

    configured = pressure_overlay_state(layout, analysis)
    by_id = {item["room_id"]: item for item in configured["rooms"]}
    assert by_id["process"]["pressure_pa"] == 30.0
    assert by_id["process"]["source"] == "configured"
    assert configured["relationships"][0]["status"] == "unavailable"
    assert configured["relationships"][0]["actual_delta_pa"] is None

    analysis.input["rooms"][0].pop("observed_pressure_pa")
    layout["rooms"][0].pop("pressure_pa")
    unresolved = pressure_overlay_state(layout, analysis)
    process = {item["room_id"]: item for item in unresolved["rooms"]}["process"]
    assert process["pressure_pa"] is None
    assert process["availability"] == "unavailable"
    assert process["source"] == "unavailable"


def test_validate_layout_reports_raw_invalid_geometry_before_normalization():
    layout = _layout()
    layout["rooms"][0]["length_m"] = 0.0
    layout["rooms"][0]["width_m"] = -2.0

    issues = validate_layout(layout)
    invalid = [item for item in issues if item["code"] == "invalid_room_geometry"]

    assert [(item["item_ids"], item["field"]) for item in invalid] == [
        (["process"], "length_m"),
        (["process"], "width_m"),
    ]


def test_validate_layout_reports_duplicate_ids_without_silently_reidentifying():
    layout = _layout()
    duplicate_room = copy.deepcopy(layout["rooms"][1])
    duplicate_room["id"] = "process"
    duplicate_room["x_m"] = 20.0
    layout["rooms"].append(duplicate_room)
    layout["devices"] = [
        {
            "id": "sensor",
            "type": "sensor",
            "name": "S1",
            "room_id": "process",
            "x_m": 2.0,
            "y_m": 3.0,
            "z_m": 1.0,
        },
        {
            "id": "sensor",
            "type": "sensor",
            "name": "S2",
            "room_id": "ante",
            "x_m": 9.0,
            "y_m": 3.0,
            "z_m": 1.0,
        },
    ]

    codes = [item["code"] for item in validate_layout(layout)]

    assert "duplicate_room_id" in codes
    assert "duplicate_device_id" in codes


def test_explicit_pull_preserves_xy_updates_dimensions_and_records_sync_baseline():
    layout = _layout()
    analysis = _analysis()
    original_xy = (layout["rooms"][0]["x_m"], layout["rooms"][0]["y_m"])
    layout["rooms"][0]["length_m"] = 7.0

    assert sync_analysis_to_layout(layout, analysis) is True

    assert layout["rooms"][0]["length_m"] == 6.0
    assert (layout["rooms"][0]["x_m"], layout["rooms"][0]["y_m"]) == original_xy
    assert layout["engineering_sync"]["analysis_id"] == analysis.id
    assert engineering_sync_status(layout, analysis)["overall"] == "synchronized"


def test_pull_preflight_is_all_or_nothing_for_missing_explicit_mapping():
    layout = _layout()
    analysis = _analysis()
    layout["rooms"][0]["length_m"] = 7.0
    layout["rooms"][1]["analysis_room_name"] = "Missing"
    before = copy.deepcopy(layout)

    with pytest.raises(SpatialSyncError, match="does not exist"):
        sync_analysis_to_layout(layout, analysis)

    assert layout == before


def test_push_records_baseline_even_when_dimensions_already_match():
    layout = _layout()
    analysis = _analysis()

    assert sync_layout_to_analysis(layout, analysis) is False

    assert layout["engineering_sync"]["analysis_id"] == analysis.id
    assert engineering_sync_status(layout, analysis)["overall"] == "synchronized"
