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
