from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.application import (
    ANALYSIS_SPECS,
    analysis_catalog,
    application_info,
    run_analysis,
    validate_analysis_input,
    validate_application_registry,
)


ROOT = Path(__file__).resolve().parents[1]


def _example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_application_catalog_exposes_major_existing_workflows():
    keys = {item["key"] for item in analysis_catalog()}
    assert {
        "project_verification", "hvac", "fan_operating_point", "loop_flow",
        "variable_friction_loop", "fan_variable_friction_loop",
        "fan_variable_friction_uncertainty", "dossier", "consistency",
    } <= keys
    assert len(keys) == len(ANALYSIS_SPECS)
    assert application_info()["analysis_count"] == len(keys)


@pytest.mark.parametrize(
    ("kind", "example_name"),
    [
        ("room_verification", "basic_room.json"),
        ("project_verification", "facility_project.json"),
        ("hvac", "duct_network_demo.json"),
        ("recovery_test", "recovery_test_demo.json"),
        ("room_uncertainty", "uncertainty_room_demo.json"),
        ("qualification_uncertainty", "qualification_uncertainty_demo.json"),
        ("parallel_flow", "parallel_flow_demo.json"),
        ("loop_flow", "looped_network_demo.json"),
        ("variable_friction_loop", "variable_friction_loop_demo.json"),
        ("thermal_uncertainty", "thermal_uncertainty_demo.json"),
        ("psychrometric_uncertainty", "psychrometric_uncertainty_demo.json"),
        ("fan_operating_point", "fan_operating_point_demo.json"),
        ("fan_system_uncertainty", "fan_uncertainty_demo.json"),
        ("fan_speed", "fan_speed_sweep_demo.json"),
        ("fan_duct_network", "fan_duct_network_demo.json"),
        ("fan_parallel_network", "fan_parallel_network_demo.json"),
        ("fan_loop_network", "fan_loop_network_demo.json"),
        ("fan_loop_uncertainty", "fan_loop_uncertainty_demo.json"),
        ("fan_loop_speed", "fan_loop_speed_demo.json"),
        ("fan_variable_friction_loop", "fan_variable_friction_loop_demo.json"),
        ("fan_variable_friction_speed", "fan_variable_friction_speed_demo.json"),
        ("fan_variable_friction_uncertainty", "fan_variable_friction_uncertainty_demo.json"),
        ("damper_study", "damper_study_demo.json"),
    ],
)
def test_registered_backend_workflows_run_through_application_layer(kind, example_name):
    run = run_analysis(kind, _example(example_name), base_dir=ROOT / "examples")
    assert run.kind == kind
    assert isinstance(run.result, dict)
    assert run.result
    assert isinstance(run.status, str) and run.status
    assert isinstance(run.markdown, str) and run.markdown.strip()
    json.dumps(run.to_dict(), allow_nan=False)


def test_application_registry_resolves_every_declared_backend_binding():
    validate_application_registry()
    assert application_info()["bindings_valid"] is True


def test_hvac_application_service_reuses_real_backend():
    run = run_analysis("hvac", _example("duct_network_demo.json"))
    assert run.kind == "hvac"
    assert run.result["project"]
    assert run.result["total_governing_airflow_m3_h"] > 0
    assert "# CleanroomX HVAC Report" in run.markdown
    json.dumps(run.to_dict(), allow_nan=False)


def test_fan_operating_point_application_service_produces_real_plot_model():
    run = run_analysis("fan_operating_point", _example("fan_operating_point_demo.json"))
    assert run.status == "solved"
    assert run.result["operating_point"] is not None
    assert run.plot is not None
    assert run.plot["series"][0]["x"]
    assert run.plot["markers"][0]["name"] == "Operating point"


def test_application_validation_uses_existing_domain_parser():
    with pytest.raises((KeyError, TypeError, ValueError)):
        validate_analysis_input("hvac", {})


def test_unknown_analysis_kind_is_rejected():
    with pytest.raises(ValueError, match="unsupported analysis kind"):
        run_analysis("does-not-exist", {})


def test_consistency_adapter_resolves_relative_project_files():
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    run = run_analysis("consistency", payload, base_dir=ROOT / "examples")
    assert run.result["shared_room_count"] > 0
    assert run.status in {"pass", "fail", "pass_with_scope_difference", "not_comparable"}
    assert "consistency" in run.markdown.lower()


def test_dossier_adapter_runs_real_file_referenced_workflow():
    payload = _example("dossier_variable_friction_uncertainty_demo.json")
    run = run_analysis("dossier", payload, base_dir=ROOT / "examples")
    assert run.result["dossier"] == payload["name"]
    assert run.status == run.result["executive_summary"]["state"]
    assert "CleanroomX Engineering Dossier" in run.markdown
    json.dumps(run.result, allow_nan=False)


def test_dossier_validation_rejects_manifest_without_analysis_sources():
    with pytest.raises(ValueError, match="at least one analysis input file"):
        validate_analysis_input(
            "dossier",
            {"name": "Empty dossier"},
            base_dir=ROOT / "examples",
        )


def test_dossier_validation_rejects_invalid_consistency_configuration():
    payload = _example("dossier_variable_friction_uncertainty_demo.json")
    payload["consistency_checks"] = {"verification_hvac_airflow": []}
    with pytest.raises(ValueError, match="must be an object"):
        validate_analysis_input("dossier", payload, base_dir=ROOT / "examples")


_APPLICATION_EXAMPLES = (
    ("room_verification", "basic_room.json"),
    ("project_verification", "facility_project.json"),
    ("hvac", "duct_network_demo.json"),
    ("recovery_test", "recovery_test_demo.json"),
    ("room_uncertainty", "uncertainty_room_demo.json"),
    ("qualification_uncertainty", "qualification_uncertainty_demo.json"),
    ("parallel_flow", "parallel_flow_demo.json"),
    ("loop_flow", "looped_network_demo.json"),
    ("variable_friction_loop", "variable_friction_loop_demo.json"),
    ("thermal_uncertainty", "thermal_uncertainty_demo.json"),
    ("psychrometric_uncertainty", "psychrometric_uncertainty_demo.json"),
    ("fan_operating_point", "fan_operating_point_demo.json"),
    ("fan_system_uncertainty", "fan_uncertainty_demo.json"),
    ("fan_speed", "fan_speed_sweep_demo.json"),
    ("fan_duct_network", "fan_duct_network_demo.json"),
    ("fan_parallel_network", "fan_parallel_network_demo.json"),
    ("fan_loop_network", "fan_loop_network_demo.json"),
    ("fan_loop_uncertainty", "fan_loop_uncertainty_demo.json"),
    ("fan_loop_speed", "fan_loop_speed_demo.json"),
    ("fan_variable_friction_loop", "fan_variable_friction_loop_demo.json"),
    ("fan_variable_friction_speed", "fan_variable_friction_speed_demo.json"),
    ("fan_variable_friction_uncertainty", "fan_variable_friction_uncertainty_demo.json"),
    ("damper_study", "damper_study_demo.json"),
    ("dossier", "dossier_variable_friction_uncertainty_demo.json"),
)


@pytest.mark.parametrize(("kind", "example_name"), _APPLICATION_EXAMPLES)
def test_every_catalog_workflow_runs_end_to_end_through_application_service(
    kind, example_name
):
    run = run_analysis(kind, _example(example_name), base_dir=ROOT / "examples")
    assert run.kind == kind
    assert run.result
    json.dumps(run.to_dict(), allow_nan=False)


def test_application_end_to_end_matrix_covers_entire_catalog():
    covered = {kind for kind, _ in _APPLICATION_EXAMPLES} | {"consistency"}
    assert covered == set(ANALYSIS_SPECS)



_CATALOG_EXAMPLE_BY_KIND = {
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
    "dossier": "dossier_demo.json",
}


def test_application_example_matrix_covers_every_registered_workflow():
    assert set(_CATALOG_EXAMPLE_BY_KIND) | {"consistency"} == set(ANALYSIS_SPECS)


@pytest.mark.parametrize(
    ("kind", "filename"),
    sorted(_CATALOG_EXAMPLE_BY_KIND.items()),
)
def test_registered_workflow_runs_end_to_end_from_repository_example(kind, filename):
    run = run_analysis(kind, _example(filename), base_dir=ROOT / "examples")
    assert run.kind == kind
    assert run.result
    assert run.markdown
    json.dumps(run.to_dict(), allow_nan=False)
