from __future__ import annotations

import copy

from cleanroomx.project import AnalysisDocument
from cleanroomx.spatial_engineering import (
    engineering_sync_report,
    link_layout_to_analysis,
    pressure_overlay,
    synchronize_analysis_to_layout,
    synchronize_layout_to_analysis,
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
                "name": "Process",
                "x_m": 0.0,
                "y_m": 0.0,
                "length_m": 6.0,
                "width_m": 5.0,
                "height_m": 3.0,
            },
            {
                "id": "ante",
                "name": "Ante",
                "x_m": 7.0,
                "y_m": 0.0,
                "length_m": 4.0,
                "width_m": 3.0,
                "height_m": 3.0,
            },
        ]
    }


def test_mapping_baseline_distinguishes_geometry_engineering_and_dual_conflicts():
    analysis = _analysis()
    layout = _layout()
    assert link_layout_to_analysis(layout, analysis) is True

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


def test_missing_explicit_mapping_target_is_unmapped_not_silently_rebound():
    analysis = _analysis()
    layout = _layout()
    layout["rooms"][0]["engineering_ref"] = {
        "analysis_id": analysis.id,
        "room_name": "Missing room",
        "baseline_geometry": {
            "length_m": 6,
            "width_m": 5,
            "height_m": 3,
        },
    }

    first = engineering_sync_report(layout, analysis)["rooms"][0]

    assert first["status"] == "unmapped"
    assert first["mapping_mode"] == "missing_target"
    assert first["engineering_room_name"] == "Missing room"


def test_explicit_push_and_pull_are_bidirectional_and_preserve_other_engineering_fields():
    analysis = _analysis()
    layout = _layout()
    link_layout_to_analysis(layout, analysis)
    layout["rooms"][0]["length_m"] = 7.5
    layout["rooms"][0]["pressure_pa"] = 32.0

    assert synchronize_layout_to_analysis(layout, analysis) is True
    target = analysis.input["rooms"][0]
    assert target["length_m"] == 7.5
    assert target["observed_pressure_pa"] == 32.0
    assert target["supply_airflow_m3_h"] == 2700.0
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "synchronized"

    target["width_m"] = 5.75
    target["observed_pressure_pa"] = 34.0
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "engineering_newer"
    assert synchronize_analysis_to_layout(layout, analysis) is True
    assert layout["rooms"][0]["width_m"] == 5.75
    assert layout["rooms"][0]["pressure_pa"] == 34.0
    assert engineering_sync_report(layout, analysis)["rooms"][0]["status"] == "synchronized"


def test_pressure_overlay_prefers_completed_result_and_projects_cascade_status():
    analysis = _analysis()
    layout = _layout()
    link_layout_to_analysis(layout, analysis)
    result = {
        "project": "Facility",
        "rooms": [
            {
                "room": "Process",
                "ach": 30,
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
                "ach": 25,
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


def test_pressure_overlay_reports_configured_and_unavailable_without_inventing_results():
    analysis = _analysis()
    layout = _layout()
    link_layout_to_analysis(layout, analysis)

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
