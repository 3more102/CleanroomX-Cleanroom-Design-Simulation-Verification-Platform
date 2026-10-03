from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import pytest

import cleanroomx.application as application_module
from cleanroomx.application import (
    ANALYSIS_SPECS,
    AnalysisRun,
    ExternalDependencyChangedError,
    ExternalDependencySnapshotError,
    analysis_catalog,
    analysis_run_matches_input,
    application_info,
    rebase_analysis_file_references,
    run_analysis,
    validate_analysis_input,
    validate_application_registry,
    verify_analysis_run_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


def _example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_application_catalog_exposes_major_existing_workflows():
    keys = {item["key"] for item in analysis_catalog()}
    assert {
        "project_verification", "hvac", "fan_operating_point", "loop_flow",
        "pressure_network", "variable_friction_loop", "fan_variable_friction_loop",
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


def test_analysis_run_matches_only_its_exact_canonical_input():
    payload = _example("basic_room.json")
    run = run_analysis("room_verification", payload)

    reordered = dict(reversed(list(payload.items())))
    assert analysis_run_matches_input(run, "room_verification", reordered) is True

    changed = dict(payload)
    changed["_freshness_probe"] = True
    assert analysis_run_matches_input(run, "room_verification", changed) is False
    assert analysis_run_matches_input(run, "hvac", payload) is False


def test_analysis_run_input_match_fails_closed_without_valid_provenance():
    payload = _example("basic_room.json")
    run = run_analysis("room_verification", payload)
    corrupted = application_module.AnalysisRun(
        kind=run.kind,
        title=run.title,
        status=run.status,
        result=run.result,
        markdown=run.markdown,
        diagnostics={},
        plot=run.plot,
    )

    assert analysis_run_matches_input(
        corrupted, "room_verification", payload
    ) is False


def test_analysis_run_snapshots_reject_recursive_mutation_and_remain_serializable():
    run = run_analysis("fan_operating_point", _example("fan_operating_point_demo.json"))

    assert isinstance(run.result, dict)
    assert isinstance(run.diagnostics, dict)
    assert isinstance(run.plot, dict)

    with pytest.raises(TypeError, match="immutable"):
        run.result["tampered"] = True
    with pytest.raises(TypeError, match="immutable"):
        run.result["curve_point_checks"].append({})
    with pytest.raises(TypeError, match="immutable"):
        run.diagnostics["application_execution_provenance"]["input_sha256"] = "0" * 64
    with pytest.raises(TypeError, match="immutable"):
        run.plot["series"].clear()

    json.dumps(run.result, allow_nan=False)
    json.dumps(run.diagnostics, allow_nan=False)
    json.dumps(run.plot, allow_nan=False)
    json.dumps(run.to_dict(), allow_nan=False)


def test_analysis_run_snapshot_breaks_source_aliases():
    result = {"nested": {"value": 1}, "items": [{"value": 2}]}
    diagnostics = {"audit": {"state": "original"}}
    plot = {"series": [{"x": [1.0], "y": [2.0]}]}

    run = application_module.AnalysisRun(
        kind="test",
        title="Test",
        status="complete",
        result=result,
        markdown="report",
        diagnostics=diagnostics,
        plot=plot,
    )

    result["nested"]["value"] = 99
    result["items"][0]["value"] = 88
    diagnostics["audit"]["state"] = "changed"
    plot["series"][0]["x"].append(3.0)

    assert run.result["nested"]["value"] == 1
    assert run.result["items"][0]["value"] == 2
    assert run.diagnostics["audit"]["state"] == "original"
    assert run.plot["series"][0]["x"] == [1.0]


def test_analysis_run_to_dict_returns_detached_ordinary_mutable_containers():
    run = run_analysis("fan_operating_point", _example("fan_operating_point_demo.json"))

    exported = run.to_dict()
    assert type(exported["result"]) is dict
    assert type(exported["diagnostics"]) is dict
    assert type(exported["plot"]) is dict
    assert type(exported["plot"]["series"]) is list

    exported["result"]["tampered"] = True
    exported["diagnostics"]["application_execution_provenance"]["input_sha256"] = "0" * 64
    exported["plot"]["series"].clear()

    assert "tampered" not in run.result
    assert run.diagnostics["application_execution_provenance"]["input_sha256"] != "0" * 64
    assert run.plot["series"]



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
    ("design_requirements", "design_requirements_demo.json"),
    ("air_system_design", "air_system_design_demo.json"),
    ("design_consistency", "design_consistency_demo.json"),
    ("pressure_design_consistency", "pressure_design_consistency_demo.json"),
    ("compliance_check", "compliance_rulepack_demo.json"),
    ("design_assurance", "design_assurance_demo.json"),
    ("hvac", "duct_network_demo.json"),
    ("recovery_test", "recovery_test_demo.json"),
    ("room_uncertainty", "uncertainty_room_demo.json"),
    ("qualification_uncertainty", "qualification_uncertainty_demo.json"),
    ("parallel_flow", "parallel_flow_demo.json"),
    ("loop_flow", "looped_network_demo.json"),
    ("pressure_network", "pressure_network_demo.json"),
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


def _copy_example(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes((ROOT / "examples" / name).read_bytes())


def test_file_backed_analysis_discards_result_when_dependency_changes_during_run(
    tmp_path, monkeypatch
):
    _copy_example(tmp_path, "facility_project.json")
    _copy_example(tmp_path, "consistency_hvac_demo.json")
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    original = application_module._run_consistency

    def run_then_change_dependency(run_payload, base_dir):
        result = original(run_payload, base_dir)
        dependency = base_dir / "consistency_hvac_demo.json"
        dependency.write_text(
            dependency.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        application_module,
        "_run_consistency",
        run_then_change_dependency,
    )

    with pytest.raises(
        ExternalDependencyChangedError,
        match="result was discarded",
    ) as raised:
        run_analysis("consistency", payload, base_dir=tmp_path)

    assert [item["field"] for item in raised.value.changes] == ["hvac_project"]
    assert raised.value.changes[0]["status"] == "changed_during_run"
    assert (
        raised.value.changes[0]["sha256_before"]
        != raised.value.changes[0]["sha256_after"]
    )


def test_file_backed_analysis_discards_result_when_dependency_disappears(
    tmp_path, monkeypatch
):
    _copy_example(tmp_path, "facility_project.json")
    _copy_example(tmp_path, "consistency_hvac_demo.json")
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
    }
    original = application_module._run_consistency

    def run_then_remove_dependency(run_payload, base_dir):
        result = original(run_payload, base_dir)
        (base_dir / "facility_project.json").unlink()
        return result

    monkeypatch.setattr(
        application_module,
        "_run_consistency",
        run_then_remove_dependency,
    )

    with pytest.raises(
        ExternalDependencyChangedError,
        match="verification_project",
    ) as raised:
        run_analysis("consistency", payload, base_dir=tmp_path)

    assert raised.value.changes == (
        {
            "field": "verification_project",
            "declared_path": "facility_project.json",
            "status": "unavailable_or_unstable",
        },
    )


def test_file_backed_dependency_change_reporting_is_deterministic(
    tmp_path, monkeypatch
):
    _copy_example(tmp_path, "facility_project.json")
    _copy_example(tmp_path, "consistency_hvac_demo.json")
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
    }
    original = application_module._run_consistency

    def run_then_change_both_dependencies(run_payload, base_dir):
        result = original(run_payload, base_dir)
        for name in ("facility_project.json", "consistency_hvac_demo.json"):
            dependency = base_dir / name
            dependency.write_text(
                dependency.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(
        application_module,
        "_run_consistency",
        run_then_change_both_dependencies,
    )

    with pytest.raises(ExternalDependencyChangedError) as raised:
        run_analysis("consistency", payload, base_dir=tmp_path)

    assert [item["field"] for item in raised.value.changes] == [
        "verification_project",
        "hvac_project",
    ]


def test_stable_file_backed_run_records_revision_timestamps(tmp_path):
    _copy_example(tmp_path, "facility_project.json")
    _copy_example(tmp_path, "consistency_hvac_demo.json")
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
    }

    run = run_analysis("consistency", payload, base_dir=tmp_path)

    provenance = run.diagnostics["application_execution_provenance"]
    assert provenance["external_dependencies_stable"] is True
    assert provenance["external_dependency_count"] == 2
    for dependency in provenance["external_dependencies"]:
        assert dependency["mtime_ns_before"] == dependency["mtime_ns_after"]
        assert dependency["mtime_ns_before"] > 0


def test_dossier_analysis_uses_same_external_dependency_guard(tmp_path, monkeypatch):
    _copy_example(tmp_path, "facility_project.json")
    payload = {
        "name": "Revision-stability regression",
        "verification_project": "facility_project.json",
    }
    original = application_module._run_dossier

    def run_then_change_dependency(run_payload, base_dir):
        result = original(run_payload, base_dir)
        dependency = base_dir / "facility_project.json"
        dependency.write_text(
            dependency.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(
        application_module,
        "_run_dossier",
        run_then_change_dependency,
    )

    with pytest.raises(ExternalDependencyChangedError) as raised:
        run_analysis("dossier", payload, base_dir=tmp_path)

    assert [item["field"] for item in raised.value.changes] == [
        "verification_project"
    ]
    assert raised.value.changes[0]["status"] == "changed_during_run"


def test_external_dependency_fingerprint_uses_shared_stable_file_authority(
    tmp_path, monkeypatch
):
    target = tmp_path / "dependency.json"
    target.write_bytes(b'{"value":1}\n')
    metadata = target.stat()
    expected = hashlib.sha256(target.read_bytes()).hexdigest()
    calls = []

    def shared_stable_hash(path, *, attempts, max_bytes):
        calls.append((Path(path), attempts, max_bytes))
        return metadata, expected

    monkeypatch.setattr(
        application_module,
        "stable_file_sha256",
        shared_stable_hash,
    )

    fingerprint = application_module._stable_file_fingerprint(target)

    assert calls == [
        (
            target,
            application_module._DEPENDENCY_FINGERPRINT_ATTEMPTS,
            application_module.STRICT_JSON_FILE_MAX_BYTES,
        )
    ]
    assert fingerprint == {
        "size_bytes": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "sha256": expected,
    }


def test_external_dependency_fingerprint_rejects_oversized_json_before_read(
    tmp_path, monkeypatch
):
    target = tmp_path / "oversized-dependency.json"
    with target.open("wb") as stream:
        stream.truncate(application_module.STRICT_JSON_FILE_MAX_BYTES + 1)

    original_open = Path.open

    def reject_dependency_read(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(self) == target and mode == "rb":
            raise AssertionError("oversized dependency must be rejected before reading")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_dependency_read)

    with pytest.raises(OSError, match="exceeds supported size limit"):
        application_module._stable_file_fingerprint(target)


def test_external_dependency_capture_preserves_typed_size_failure(
    tmp_path, monkeypatch
):
    dependency = tmp_path / "dependency.json"
    dependency.write_text('{"value":1}\n', encoding="utf-8")
    limit = application_module.STRICT_JSON_FILE_MAX_BYTES

    def fail_with_size_limit(path, *, attempts, max_bytes):
        assert Path(path) == dependency
        assert attempts == application_module._DEPENDENCY_FINGERPRINT_ATTEMPTS
        assert max_bytes == limit
        raise application_module.StableFileSizeError(path, limit + 1, limit)

    monkeypatch.setattr(
        application_module,
        "stable_file_sha256",
        fail_with_size_limit,
    )

    with pytest.raises(
        ExternalDependencySnapshotError,
        match="input exceeds supported size limit while fingerprinting",
    ) as raised:
        application_module._capture_external_dependencies(
            "dossier",
            {"verification_project": "dependency.json"},
            tmp_path,
        )

    assert raised.value.field == "verification_project"
    assert raised.value.declared_path == "dependency.json"
    assert isinstance(raised.value.__cause__, application_module.StableFileSizeError)


def test_external_dependency_snapshot_preserves_typed_size_failure(
    tmp_path, monkeypatch
):
    dependency = tmp_path / "dependency.json"
    dependency.write_text('{"value":1}\n', encoding="utf-8")
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    metadata = dependency.stat()
    digest = hashlib.sha256(dependency.read_bytes()).hexdigest()
    limit = application_module.STRICT_JSON_FILE_MAX_BYTES
    snapshot_calls = []

    def stable_hash(path, *, attempts, max_bytes):
        assert Path(path) == dependency
        assert attempts == application_module._DEPENDENCY_FINGERPRINT_ATTEMPTS
        assert max_bytes == limit
        return metadata, digest

    @contextmanager
    def fail_snapshot(path, *, attempts, max_bytes, suffix=""):
        snapshot_calls.append((Path(path), attempts, max_bytes, suffix))
        raise application_module.StableFileSizeError(path, limit + 1, limit)
        yield

    monkeypatch.setattr(application_module, "stable_file_sha256", stable_hash)
    monkeypatch.setattr(application_module, "stable_file_snapshot", fail_snapshot)

    with pytest.raises(
        ExternalDependencySnapshotError,
        match="input exceeds supported size limit while creating execution snapshot",
    ) as raised:
        application_module._prepare_external_dependency_snapshot(
            "dossier",
            {"verification_project": "dependency.json"},
            tmp_path,
            snapshot_dir,
        )

    assert snapshot_calls == [
        (
            dependency,
            application_module._DEPENDENCY_FINGERPRINT_ATTEMPTS,
            limit,
            ".json",
        )
    ]
    assert isinstance(raised.value.__cause__, application_module.StableFileSizeError)


def test_external_dependency_snapshot_uses_bounded_stable_authority(
    tmp_path, monkeypatch
):
    dependency = tmp_path / "dependency.json"
    dependency.write_text('{"value":1}\n', encoding="utf-8")
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    calls = []
    original = application_module.stable_file_snapshot

    @contextmanager
    def bounded_snapshot(path, *, attempts, max_bytes, suffix=""):
        calls.append((Path(path), attempts, max_bytes, suffix))
        with original(
            path,
            attempts=attempts,
            max_bytes=max_bytes,
            suffix=suffix,
        ) as snapshot:
            yield snapshot

    monkeypatch.setattr(
        application_module,
        "stable_file_snapshot",
        bounded_snapshot,
    )

    execution_payload, dependencies, aliases = (
        application_module._prepare_external_dependency_snapshot(
            "dossier",
            {"verification_project": "dependency.json"},
            tmp_path,
            snapshot_dir,
        )
    )

    assert calls == [
        (
            dependency,
            application_module._DEPENDENCY_FINGERPRINT_ATTEMPTS,
            application_module.STRICT_JSON_FILE_MAX_BYTES,
            ".json",
        )
    ]
    assert len(dependencies) == 1
    assert execution_payload["verification_project"].endswith("dependency-0000.json")
    assert aliases


def test_analysis_run_preserves_legacy_positional_constructor_shape():
    run = AnalysisRun("kind", "title", "status", {}, "", {}, None)
    assert run.input_snapshot == {}


def test_run_bundle_captures_immutable_input_and_verifies():
    payload = _example("basic_room.json")
    submitted = json.loads(json.dumps(payload))
    run = run_analysis("room_verification", payload)
    payload["name"] = "mutated after execution"

    bundle = run.to_dict()
    verification = verify_analysis_run_bundle(bundle)

    assert run.to_dict() == bundle
    assert bundle["schema"] == "cleanroomx.analysis-run"
    assert bundle["schema_version"] == 1
    assert bundle["input_snapshot"] == submitted
    assert run.input_snapshot == submitted
    assert len(bundle["integrity"]["sha256"]) == 64
    assert verification["status"] == "ok"
    assert verification["analysis_kind"] == "room_verification"
    assert verification["input_sha256"] == run.diagnostics[
        "application_execution_provenance"
    ]["input_sha256"]
    assert verification["bundle_sha256"] == bundle["integrity"]["sha256"]


def test_run_bundle_verification_is_independent_of_current_registry(monkeypatch):
    bundle = run_analysis("room_verification", _example("basic_room.json")).to_dict()
    reduced = dict(application_module.ANALYSIS_SPECS)
    reduced.pop("room_verification")
    monkeypatch.setattr(application_module, "ANALYSIS_SPECS", reduced)

    verification = verify_analysis_run_bundle(bundle)

    assert verification["status"] == "ok"
    assert verification["analysis_kind"] == "room_verification"


def test_run_bundle_verification_detects_document_tampering():
    bundle = run_analysis("room_verification", _example("basic_room.json")).to_dict()
    bundle["status"] = "tampered"

    with pytest.raises(ValueError, match="content has changed"):
        verify_analysis_run_bundle(bundle)


def test_run_bundle_verification_rejects_missing_required_fields():
    bundle = run_analysis("room_verification", _example("basic_room.json")).to_dict()
    bundle.pop("result")
    unsigned = dict(bundle)
    unsigned.pop("integrity")
    bundle["integrity"]["sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="missing required field"):
        verify_analysis_run_bundle(bundle)


def test_run_bundle_verification_detects_input_provenance_mismatch_even_if_resigned():
    bundle = run_analysis("room_verification", _example("basic_room.json")).to_dict()
    bundle["input_snapshot"]["name"] = "different submitted input"

    unsigned = dict(bundle)
    unsigned.pop("integrity")
    bundle["integrity"]["sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="input snapshot does not match"):
        verify_analysis_run_bundle(bundle)
