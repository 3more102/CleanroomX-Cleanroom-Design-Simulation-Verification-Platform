"""Native grid integration with deterministic parser fixtures, never solver claims."""
import json
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("vtk")

from cleanroomx.cfd_analysis_export import export_analysis_bundle
from cleanroomx.cfd_native_binding import GRID_CASES
from cleanroomx.cfd_result_analysis import analyze_selected_result_store, analyze_synced_results, build_analysis_graph
from cleanroomx.proofgraph_io import proofgraph_from_dict
from cfd_analysis_fixtures import sha, write_grid_sync_fixture


FIRST = GRID_CASES[0]


def test_complete_grid_loads_nine_cases_with_original_fields_and_bound_logs(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path)
    result = analyze_synced_results(store, run, case_directory=family, verify_native_sources=True)
    report = result.report
    assert report["mode"] == "native_grid_sync"
    assert [c["case_id"] for c in report["cases"]] == list(GRID_CASES)
    assert len(report["snapshots"]) == 18
    assert len(report["diagnostics"]) == 9
    originals = [s for s in report["sources"] if s["role"] == "native_source_field"]
    assert len(originals) == 54
    assert report["reproducibility"]["native_source_bytes_rehashed"] is True
    assert report["reproducibility"]["native_bytes_verified"] == sum(Path(s["path"]).stat().st_size for s in originals)
    assert all(s["native_source_fields_rehashed"] for s in report["snapshots"])
    assert {c["native_input_scope"] for c in report["cases"]} == {"eight_generated_inputs_excluding_generated_polyMesh"}
    assert {d["log_execution_binding"] for d in report["diagnostics"]} == {"hash_bound_sync_manifest"}
    assert {d["mesh_execution_binding"] for d in report["diagnostics"]} == {"hash_bound_grid_execution_receipt"}
    residuals = build_analysis_graph([result], kind="residual_history", field_name="all")
    assert {s["case_id"] for s in residuals["series"]} == set(GRID_CASES)
    assert {s["case_id"] for s in residuals["sources"]} == set(GRID_CASES)
    comparison = build_analysis_graph([result], kind="comparison", time_name="10")
    assert len(comparison["series"]) == 9
    assert report["scientific_validation"] == "BLOCKED"
    graph = proofgraph_from_dict(result.proofgraph.to_dict())
    assert len(graph.requirement_set.requirements) == 18
    assert {v.status for v in graph.verdicts} == {"pass", "not_checked"}
    assert analyze_selected_result_store(store / run, case_directory=family,
                                          verify_native_sources=True).report == report


def test_fields_only_grid_reports_missing_cases_and_original_verification_scope(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    result = analyze_synced_results(store, run)
    assert [c["case_id"] for c in result.report["cases"]] == [FIRST]
    assert len([a for a in result.report["availability"] if a["analysis"] == "fields"]) == 8
    assert result.report["reproducibility"]["native_source_bytes_rehashed"] is False
    assert result.report["diagnostics"] == []
    with pytest.raises(ValueError, match="requires.*native case"):
        analyze_synced_results(store, run, verify_native_sources=True)


@pytest.mark.parametrize("target, message", [
    ("0/U", "Generated grid input changed"),
    ("2/U", "Original OpenFOAM field changed"),
    ("2/p", "Original OpenFOAM field changed"),
    ("simpleFoam.log", "Solver log no longer matches"),
    ("checkMesh.log", "Mesh log no longer matches"),
])
def test_changed_native_inputs_fields_or_logs_fail_binding(tmp_path, target, message):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    original = family / FIRST / target
    original.write_bytes(original.read_bytes() + b"changed")
    with pytest.raises(ValueError, match=message):
        analyze_synced_results(store, run, case_directory=family, verify_native_sources=True)


def test_optional_original_verification_and_export_recheck(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    result = analyze_synced_results(store, run, case_directory=family, verify_native_sources=True)
    (family / FIRST / "2/U").unlink()
    with pytest.raises(ValueError, match="Cannot inspect result asset"):
        export_analysis_bundle([result], [build_analysis_graph([result])], tmp_path / "export")
    assert not (tmp_path / "export").exists()
    assert analyze_synced_results(store, run, case_directory=family).report["snapshots"]
    with pytest.raises(ValueError):
        analyze_synced_results(store, run, case_directory=family, verify_native_sources=True)


def test_grid_manifest_and_execution_identity_cannot_be_swapped(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    path = family / "grid_execution_evidence.json"
    receipt = json.loads(path.read_text())
    receipt["cases"][FIRST]["result_synchronization"]["manifest_sha256"] = "f" * 64
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="bind.*manifest"):
        analyze_synced_results(store, run, case_directory=family)
    path.unlink()
    result = analyze_synced_results(store, run, case_directory=family)
    assert result.report["diagnostics"][0]["mesh_execution_binding"] == "unverified_same_generated_inputs_only"
    path = family / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"].pop(FIRST + "/0/U")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="exact nine cases"):
        analyze_synced_results(store, run, case_directory=family)


def test_native_field_time_path_must_match_record_even_with_consistent_receipt(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    path = store / run / FIRST / "sync_manifest.json"
    manifest = json.loads(path.read_text())
    record = manifest["records"]["2"]
    record["source_fields"]["U"]["path"] = "10/U"
    record["input_fingerprint_sha256"] = sha(json.dumps(record["source_fields"], sort_keys=True, separators=(",", ":")).encode())
    receipt_path = path.parent / record["receipt"]["path"]
    receipt = json.loads(receipt_path.read_text())
    receipt["record"] = {k: v for k, v in record.items() if k != "receipt"}
    receipt_path.write_text(json.dumps(receipt))
    record["receipt"]["sha256"] = sha(receipt_path.read_bytes())
    path.write_text(json.dumps(manifest))
    (family / "grid_execution_evidence.json").unlink()
    with pytest.raises(ValueError, match="recorded solver time"):
        analyze_synced_results(store, run, case_directory=family, verify_native_sources=True)


def test_direct_grid_case_binding_protects_whole_family_from_export(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    output = store / run / FIRST
    result = analyze_synced_results(output, run, case_directory=family / FIRST, verify_native_sources=True)
    assert family.resolve() in result.protected_roots
    assert result.report["snapshots"][0]["case_id"] == FIRST
    with pytest.raises(ValueError, match="outside"):
        export_analysis_bundle([result], [build_analysis_graph([result])], family / "analysis")


def test_grid_rejects_mixed_layouts_and_linked_configuration(tmp_path):
    store, run, family = write_grid_sync_fixture(tmp_path, cases=(FIRST,))
    config = store / run / "configuration_1"
    mixed = config / "sync_manifest.json"
    mixed.write_bytes((config / "coarse/sync_manifest.json").read_bytes())
    with pytest.raises(ValueError, match="Cannot mix"):
        analyze_synced_results(store, run)
    mixed.unlink()
    moved = tmp_path / "moved-configuration"
    shutil.move(config, moved)
    try:
        config.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links unavailable")
    with pytest.raises(ValueError, match="regular directory"):
        analyze_synced_results(store, run)


def test_grid_cli_verifies_original_fields_and_exports_all_cases(tmp_path, monkeypatch, capsys):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_pipeline_cli import main
    store, run, family = write_grid_sync_fixture(tmp_path)
    export = tmp_path / "analysis"
    monkeypatch.setattr(sys, "argv", ["cleanroomx-cfd-pipeline", "analyze-results", str(store),
        "--simulation-id", run, "--case-directory", str(family), "--verify-native-fields", "--time", "10",
        "--output", str(export)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["graph_count"] == 3
    reports = json.loads((export / "analysis.json").read_text())
    assert reports[0]["reproducibility"]["native_source_bytes_rehashed"] is True
    assert len(reports[0]["cases"]) == 9
    assert {s["case_id"] for s in json.loads((export / "graphs.json").read_text())[1]["series"]} == set(GRID_CASES)
    proofgraph_from_dict(json.loads((export / "proofgraph-01.json").read_text()))
