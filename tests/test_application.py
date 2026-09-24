from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cleanroomx.application import (
    ANALYSIS_SPECS,
    analysis_catalog,
    application_info,
    rebase_analysis_file_references,
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


def test_application_registry_resolves_every_declared_backend_binding():
    validation = validate_application_registry()
    expected_target_count = sum(
        target is not None
        for spec in ANALYSIS_SPECS.values()
        for target in (spec.parser, spec.runner, spec.reporter)
    )
    assert validation["status"] == "ok"
    assert validation["analysis_count"] == len(ANALYSIS_SPECS)
    assert validation["callable_target_count"] == expected_target_count
    assert set(validation["custom_adapters"]) == {"consistency", "dossier"}
    info = application_info()
    assert info["bindings_valid"] is True
    assert info["registry_validation"] == validation


def test_application_registry_rejects_duplicate_keys(monkeypatch):
    import cleanroomx.application as application_module

    monkeypatch.setattr(
        application_module,
        "_ANALYSES",
        application_module._ANALYSES + (application_module._ANALYSES[0],),
    )
    with pytest.raises(RuntimeError, match="duplicate application analysis keys"):
        application_module.validate_application_registry()


def test_application_registry_enforces_custom_adapter_contract(monkeypatch):
    import cleanroomx.application as application_module
    from dataclasses import replace

    specs = tuple(
        replace(spec, parser=("io", "project_from_dict"))
        if spec.key == "consistency"
        else spec
        for spec in application_module._ANALYSES
    )
    monkeypatch.setattr(application_module, "_ANALYSES", specs)
    with pytest.raises(RuntimeError, match="consistency must use its registered custom"):
        application_module.validate_application_registry()



def test_application_registry_rejects_catalog_mapping_drift(monkeypatch):
    import cleanroomx.application as application_module

    reduced = dict(application_module.ANALYSIS_SPECS)
    reduced.pop("hvac")
    monkeypatch.setattr(application_module, "ANALYSIS_SPECS", reduced)
    with pytest.raises(RuntimeError, match="mapping is inconsistent with the catalog"):
        application_module.validate_application_registry()


def test_application_registry_rejects_standard_workflow_without_parser_runner(monkeypatch):
    import cleanroomx.application as application_module
    from dataclasses import replace

    specs = tuple(
        replace(spec, parser=None) if spec.key == "hvac" else spec
        for spec in application_module._ANALYSES
    )
    monkeypatch.setattr(application_module, "_ANALYSES", specs)
    with pytest.raises(RuntimeError, match="hvac must define both parser and runner"):
        application_module.validate_application_registry()

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
    assert [series["name"] for series in run.plot["series"]] == [
        "Fan curve",
        "System curve",
    ]
    assert run.plot["series"][0]["x"]
    assert run.plot["series"][1]["x"] == run.plot["series"][0]["x"]
    assert run.plot["series"][1]["y"] == [
        point["system_pressure_pa"] for point in run.result["curve_point_checks"]
    ]
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

    provenance = run.diagnostics["application_execution_provenance"]
    assert provenance["analysis_kind"] == "consistency"
    assert provenance["external_dependency_count"] == 2
    assert provenance["external_dependencies_stable"] is True
    dependencies = {item["field"]: item for item in provenance["external_dependencies"]}
    for field, filename in (
        ("verification_project", "facility_project.json"),
        ("hvac_project", "consistency_hvac_demo.json"),
    ):
        expected = hashlib.sha256((ROOT / "examples" / filename).read_bytes()).hexdigest()
        assert dependencies[field]["declared_path"] == filename
        assert dependencies[field]["sha256_before"] == expected
        assert dependencies[field]["sha256_after"] == expected
        assert dependencies[field]["stable_during_run"] is True


def test_application_execution_provenance_hashes_inline_input_canonically():
    payload = _example("basic_room.json")
    reordered = dict(reversed(list(payload.items())))
    first = run_analysis("room_verification", payload)
    second = run_analysis("room_verification", reordered)

    first_provenance = first.diagnostics["application_execution_provenance"]
    second_provenance = second.diagnostics["application_execution_provenance"]
    expected = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert first_provenance["schema"] == "cleanroomx.application-execution-provenance"
    assert first_provenance["schema_version"] == 1
    assert first_provenance["input_sha256"] == expected
    assert second_provenance["input_sha256"] == expected
    assert first_provenance["external_dependency_count"] == 0
    assert first_provenance["external_dependencies_stable"] is True


def test_rebase_analysis_file_references_preserves_consistency_referents(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "moved" / "project"
    source.mkdir()
    target.mkdir(parents=True)
    payload = {
        "verification_project": "inputs/facility.json",
        "hvac_project": "../shared/hvac.json",
    }

    rebased = rebase_analysis_file_references(
        "consistency",
        payload,
        source_base=source,
        target_base=target,
    )

    for key in ("verification_project", "hvac_project"):
        assert (target / rebased[key]).resolve() == (source / payload[key]).resolve()
    assert payload["verification_project"] == "inputs/facility.json"


def test_rebase_analysis_file_references_handles_dossier_lists_and_unsaved_target(tmp_path):
    source = tmp_path / "import"
    source.mkdir()
    payload = {
        "name": "Portable dossier",
        "verification_project": "facility.json",
        "recovery_tests": ["recovery/a.json", "recovery/b.json"],
        "fan_loop_speed_studies": ["studies/speed.json"],
    }

    rebased = rebase_analysis_file_references(
        "dossier",
        payload,
        source_base=source,
        target_base=None,
    )

    assert Path(rebased["verification_project"]).is_absolute()
    assert all(Path(value).is_absolute() for value in rebased["recovery_tests"])
    assert Path(rebased["fan_loop_speed_studies"][0]).is_absolute()
    assert Path(rebased["verification_project"]).resolve() == (source / "facility.json").resolve()


def test_rebase_analysis_file_references_leaves_absolute_and_non_file_workflows_unchanged(tmp_path):
    absolute = str((tmp_path / "facility.json").resolve())
    payload = {"verification_project": absolute, "hvac_project": "hvac.json"}
    rebased = rebase_analysis_file_references(
        "consistency",
        payload,
        source_base=tmp_path,
        target_base=tmp_path / "other",
    )
    assert rebased["verification_project"] == absolute

    ordinary = {"path_like_note": "not-a-file-reference.json"}
    assert rebase_analysis_file_references(
        "hvac", ordinary, source_base=tmp_path, target_base=tmp_path / "other"
    ) == ordinary


def test_dossier_adapter_runs_real_file_referenced_workflow():
    payload = _example("dossier_variable_friction_uncertainty_demo.json")
    run = run_analysis("dossier", payload, base_dir=ROOT / "examples")
    assert run.result["dossier"] == payload["name"]
    assert run.status == run.result["executive_summary"]["state"]
    assert "CleanroomX Engineering Dossier" in run.markdown
    provenance = run.diagnostics["application_execution_provenance"]
    assert provenance["external_dependency_count"] > 0
    assert provenance["external_dependencies_stable"] is True
    assert all(
        len(item["sha256_before"]) == 64
        and item["sha256_before"] == item["sha256_after"]
        and item["stable_during_run"] is True
        for item in provenance["external_dependencies"]
    )
    json.dumps(run.result, allow_nan=False)


def test_dossier_adapter_supports_absolute_references_without_saved_project():
    payload = _example("dossier_variable_friction_uncertainty_demo.json")
    payload["fan_variable_friction_uncertainty_analyses"] = [
        str((ROOT / "examples" / value).resolve())
        for value in payload["fan_variable_friction_uncertainty_analyses"]
    ]

    run = run_analysis("dossier", payload)

    assert run.result["dossier"] == payload["name"]
    assert run.status == run.result["executive_summary"]["state"]
    assert run.diagnostics["application_execution_provenance"][
        "external_dependencies_stable"
    ] is True
    json.dumps(run.to_dict(), allow_nan=False)


def test_dossier_adapter_rejects_relative_references_without_saved_project():
    payload = _example("dossier_variable_friction_uncertainty_demo.json")

    with pytest.raises(ValueError, match="relative file references require"):
        run_analysis("dossier", payload)


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
    provenance = run.diagnostics["application_execution_provenance"]
    assert provenance["analysis_kind"] == kind
    assert len(provenance["input_sha256"]) == 64
    assert provenance["external_dependencies_stable"] is True
    json.dumps(run.to_dict(), allow_nan=False)


def test_application_end_to_end_matrix_covers_entire_catalog():
    covered = {kind for kind, _ in _APPLICATION_EXAMPLES} | {"consistency"}
    assert covered == set(ANALYSIS_SPECS)
