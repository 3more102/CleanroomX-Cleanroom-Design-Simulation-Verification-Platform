from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.application import ANALYSIS_SPECS, run_analysis


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


_WORKFLOW_EXAMPLES = {
    "room_verification": "basic_room.json",
    "project_verification": "facility_project.json",
    "hvac": "duct_network_demo.json",
    "recovery_test": "recovery_test_demo.json",
    "room_uncertainty": "uncertainty_room_demo.json",
    "qualification_uncertainty": "qualification_uncertainty_demo.json",
    "parallel_flow": "parallel_flow_demo.json",
    "loop_flow": "looped_network_demo.json",
    "variable_friction_loop": "variable_friction_loop_demo.json",
    "thermal_uncertainty": "thermal_uncertainty_demo.json",
    "psychrometric_uncertainty": "psychrometric_uncertainty_demo.json",
    "fan_operating_point": "fan_operating_point_demo.json",
    "fan_system_uncertainty": "fan_uncertainty_demo.json",
    "fan_speed": "fan_speed_sweep_demo.json",
    "fan_duct_network": "fan_duct_network_demo.json",
    "fan_parallel_network": "fan_parallel_network_demo.json",
    "fan_loop_network": "fan_loop_network_demo.json",
    "fan_loop_uncertainty": "fan_loop_uncertainty_demo.json",
    "fan_loop_speed": "fan_loop_speed_demo.json",
    "fan_variable_friction_loop": "fan_variable_friction_loop_demo.json",
    "fan_variable_friction_speed": "fan_variable_friction_speed_demo.json",
    "fan_variable_friction_uncertainty": "fan_variable_friction_uncertainty_demo.json",
    "damper_study": "damper_study_demo.json",
}


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_e2e_fixture_map_covers_every_direct_application_workflow():
    assert set(_WORKFLOW_EXAMPLES) == set(ANALYSIS_SPECS) - {"consistency", "dossier"}


@pytest.mark.parametrize("kind,example_name", sorted(_WORKFLOW_EXAMPLES.items()))
def test_every_direct_application_workflow_executes_real_example(kind: str, example_name: str):
    run = run_analysis(kind, _example(example_name), base_dir=EXAMPLES)
    assert run.kind == kind
    assert isinstance(run.status, str) and run.status
    assert isinstance(run.result, dict) and run.result
    assert isinstance(run.markdown, str) and run.markdown
    json.dumps(run.to_dict(), sort_keys=True, allow_nan=False)


def test_consistency_application_workflow_executes_end_to_end():
    run = run_analysis(
        "consistency",
        {
            "verification_project": "facility_project.json",
            "hvac_project": "consistency_hvac_demo.json",
            "room_airflow_abs_tolerance_m3_h": 0.0,
            "require_same_room_set": True,
        },
        base_dir=EXAMPLES,
    )
    assert run.kind == "consistency"
    assert isinstance(run.result, dict) and run.result
    assert isinstance(run.markdown, str) and run.markdown
    json.dumps(run.to_dict(), sort_keys=True, allow_nan=False)


def test_dossier_application_workflow_executes_end_to_end():
    run = run_analysis(
        "dossier",
        _example("dossier_variable_friction_uncertainty_demo.json"),
        base_dir=EXAMPLES,
    )
    assert run.kind == "dossier"
    assert isinstance(run.result, dict) and run.result
    assert isinstance(run.markdown, str) and run.markdown
    json.dumps(run.to_dict(), sort_keys=True, allow_nan=False)
