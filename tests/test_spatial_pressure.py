from __future__ import annotations

from cleanroomx.application import run_analysis
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import AnalysisDocument, load_project_document
from cleanroomx.spatial import SPATIAL_METADATA_KEY, derive_layout_from_analysis, pressure_overlay_state


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
                    "min_pressure_pa": 25.0,
                },
                {
                    "name": "Ante",
                    "length_m": 4.0,
                    "width_m": 3.0,
                    "height_m": 3.0,
                    "observed_pressure_pa": 8.0,
                    "min_pressure_pa": 5.0,
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


def _result(*, cascade_status: str = "pass") -> dict:
    return {
        "rooms": [
            {
                "room": "Process",
                "ach": 24.0,
                "findings": [
                    {
                        "code": "PRESSURE",
                        "status": "pass",
                        "actual": 31.0,
                        "limit": 25.0,
                    }
                ],
            },
            {
                "room": "Ante",
                "ach": 18.0,
                "findings": [
                    {
                        "code": "PRESSURE",
                        "status": "pass",
                        "actual": 8.0,
                        "limit": 5.0,
                    }
                ],
            },
        ],
        "pressure_cascade": [
            {
                "higher_pressure_room": "Process",
                "lower_pressure_room": "Ante",
                "actual_delta_pa": 23.0 if cascade_status == "pass" else 5.0,
                "status": cascade_status,
            }
        ],
    }


def test_pressure_overlay_prefers_verified_result_and_projects_cascade_evidence() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)

    overlay = pressure_overlay_state(layout, analysis, _result())

    process = overlay["rooms"][0]
    assert process["pressure_pa"] == 31.0
    assert process["pressure_target_pa"] == 25.0
    assert process["source"] == "result"
    assert process["status"] == "pass"
    assert process["ach"] == 24.0
    assert process["engineering_state"] == "synchronized"

    relationship = overlay["relationships"][0]
    assert relationship["actual_delta_pa"] == 23.0
    assert relationship["limit_pa"] == 10.0
    assert relationship["status"] == "pass"
    assert relationship["source"] == "result"


def test_pressure_overlay_keeps_configured_intent_distinct_from_calculated_result() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)

    overlay = pressure_overlay_state(layout, analysis, None)

    assert [room["source"] for room in overlay["rooms"]] == [
        "configured",
        "configured",
    ]
    assert [room["pressure_pa"] for room in overlay["rooms"]] == [30.0, 8.0]
    relationship = overlay["relationships"][0]
    assert relationship["actual_delta_pa"] is None
    assert relationship["status"] == "unavailable"
    assert relationship["source"] == "configured_requirement"


def test_pressure_overlay_surfaces_failed_and_unavailable_solver_evidence() -> None:
    analysis = _analysis()
    layout = derive_layout_from_analysis(analysis)

    failed = pressure_overlay_state(layout, analysis, _result(cascade_status="fail"))
    assert failed["relationships"][0]["status"] == "fail"
    assert failed["relationships"][0]["actual_delta_pa"] == 5.0

    result = _result()
    result["rooms"][1]["findings"] = []
    unavailable = pressure_overlay_state(layout, analysis, result)
    assert unavailable["rooms"][1]["source"] == "configured"
    assert unavailable["rooms"][1]["pressure_pa"] == 8.0


def test_packaged_demo_real_run_projects_solver_pressure_into_spatial_overlay() -> None:
    path = bundled_demo_project_path()
    project = load_project_document(path)
    analysis = project.analysis_by_id(project.active_analysis_id)
    run = run_analysis(analysis.kind, analysis.input, base_dir=path.parent)

    overlay = pressure_overlay_state(
        project.metadata[SPATIAL_METADATA_KEY], analysis, run.result
    )

    assert [room["source"] for room in overlay["rooms"]] == [
        "result", "result", "result"
    ]
    assert [room["pressure_pa"] for room in overlay["rooms"]] == [30.0, 16.0, 8.0]
    assert [item["source"] for item in overlay["relationships"]] == [
        "result", "result"
    ]
    assert [item["status"] for item in overlay["relationships"]] == [
        "pass", "pass"
    ]
