from __future__ import annotations

import copy

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial_engineering import (
    engineering_sync_report,
    establish_sync_baselines,
    pressure_overlay,
    refresh_sync_baselines,
    synchronize_analysis_to_layout,
)


def _analysis() -> AnalysisDocument:
    return AnalysisDocument(
        id="verification",
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
                    "supply_airflow_m3_h": 2700.0,
                    "min_pressure_pa": 20.0,
                    "observed_pressure_pa": 30.0,
                },
                {
                    "name": "Ante",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "supply_airflow_m3_h": 900.0,
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
        "rooms": [
            {
                "id": "process",
                "name": "Process Suite",
                "analysis_room_name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 6.0,
                "width_m": 5.0,
                "height_m": 3.0,
            },
            {
                "id": "ante",
                "name": "Ante / Airlock",
                "analysis_room_name": "Ante",
                "x_m": 7.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
            },
        ]
    }


def test_sync_baseline_distinguishes_geometry_engineering_and_conflict_states():
    analysis = _analysis()
    layout = _layout()
    assert establish_sync_baselines(layout, analysis) is True

    report = engineering_sync_report(layout, analysis)
    assert report["status"] == "synchronized"
    assert [item["status"] for item in report["rooms"]] == [
        "synchronized",
        "synchronized",
    ]

    layout["rooms"][0]["length_m"] = 6.5
    report = engineering_sync_report(layout, analysis)
    assert report["rooms"][0]["status"] == "geometry_newer"
    assert report["rooms"][0]["differences"] == [
        {"field": "length_m", "geometry": 6.5, "engineering": 6.0}
    ]

    layout["rooms"][0]["length_m"] = 6.0
    analysis.input["rooms"][0]["length_m"] = 6.25
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "engineering_newer"

    layout["rooms"][0]["length_m"] = 6.75
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "conflicting"


def test_missing_link_target_is_unmapped_and_not_silently_rebound():
    analysis = _analysis()
    layout = _layout()
    establish_sync_baselines(layout, analysis)
    layout["rooms"][0]["analysis_room_name"] = "Missing room"
    layout["rooms"][0]["engineering_ref"]["room_name"] = "Missing room"

    entry = engineering_sync_report(layout, analysis)["rooms"][0]

    assert entry["status"] == "unmapped"
    assert entry["mapping_mode"] == "missing_target"
    assert entry["engineering_room_name"] == "Missing room"


def test_explicit_pull_updates_geometry_and_refreshes_baseline_without_touching_xy():
    analysis = _analysis()
    layout = _layout()
    establish_sync_baselines(layout, analysis)
    original_xy = (layout["rooms"][0]["x_m"], layout["rooms"][0]["y_m"])
    analysis.input["rooms"][0]["width_m"] = 5.75
    analysis.input["rooms"][0]["observed_pressure_pa"] = 34.0

    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "engineering_newer"
    assert synchronize_analysis_to_layout(layout, analysis) is True

    assert layout["rooms"][0]["width_m"] == 5.75
    assert layout["rooms"][0]["pressure_pa"] == 34.0
    assert (layout["rooms"][0]["x_m"], layout["rooms"][0]["y_m"]) == original_xy
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "synchronized"


def test_refresh_baseline_after_explicit_push_marks_matching_geometry_synchronized():
    analysis = _analysis()
    layout = _layout()
    establish_sync_baselines(layout, analysis)
    layout["rooms"][0]["length_m"] = 7.5
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "geometry_newer"

    analysis.input["rooms"][0]["length_m"] = 7.5
    assert refresh_sync_baselines(layout, analysis) is True
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "synchronized"


def test_pressure_overlay_prefers_completed_result_and_projects_cascade_status():
    analysis = _analysis()
    layout = _layout()
    establish_sync_baselines(layout, analysis)
    result = {
        "project": "Facility",
        "rooms": [
            {
                "room": "Process",
                "ach": 30.0,
                "findings": [
                    {
                        "code": "PRESSURE",
                        "status": "pass",
                        "actual": 30.0,
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
                "actual_delta_pa": 22.0,
                "limit_pa": 10.0,
            }
        ],
    }

    overlay = pressure_overlay(layout, analysis, result)
    by_id = {item["room_id"]: item for item in overlay["rooms"]}

    assert by_id["process"]["pressure_pa"] == 30.0
    assert by_id["process"]["pressure_target_pa"] == 20.0
    assert by_id["process"]["source"] == "result"
    assert by_id["process"]["status"] == "pass"
    assert by_id["process"]["ach"] == 30.0

    relationship = overlay["relationships"][0]
    assert relationship["higher_room_id"] == "process"
    assert relationship["lower_room_id"] == "ante"
    assert relationship["actual_delta_pa"] == 22.0
    assert relationship["limit_pa"] == 10.0
    assert relationship["status"] == "pass"
    assert relationship["source"] == "result"


def test_pressure_overlay_keeps_missing_result_explicitly_unavailable():
    analysis = _analysis()
    layout = _layout()
    establish_sync_baselines(layout, analysis)

    configured = pressure_overlay(layout, analysis)
    assert configured["rooms"][0]["source"] == "configured"
    assert configured["rooms"][0]["pressure_pa"] == 30.0
    assert configured["relationships"][0]["status"] == "unavailable"
    assert configured["relationships"][0]["actual_delta_pa"] is None

    no_pressure = copy.deepcopy(analysis)
    no_pressure.input["rooms"][0].pop("observed_pressure_pa")
    no_pressure.input["rooms"][1].pop("observed_pressure_pa")
    unavailable = pressure_overlay(layout, no_pressure)
    assert unavailable["rooms"][0]["pressure_pa"] is None
    assert unavailable["rooms"][0]["source"] == "unavailable"
