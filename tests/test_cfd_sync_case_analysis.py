"""Standalone native-sync parser fixtures; these never execute OpenFOAM."""
import csv
import hashlib
import io
import json
import shutil
import sys

import pytest

pytest.importorskip("vtk")

from cleanroomx.cfd_analysis_export import export_analysis_bundle, graph_csv
from cleanroomx.cfd_openfoam_runtime_sync import hash_case_configuration
from cleanroomx.cfd_result_analysis import (
    analyze_selected_result_store, analyze_synced_results, build_analysis_graph,
)
from cleanroomx.proofgraph_io import proofgraph_from_dict
from cfd_analysis_fixtures import write_sync_store, residual_log


RUN = "SYNTHETIC-standalone-run"
CASE_ID = "Lab West/thermal-zone"


def standalone(tmp_path, *, times=("2", "10")):
    case = write_sync_store(tmp_path / "layout", run=RUN, case_id=CASE_ID, times=times)
    output = tmp_path / "arbitrary-output-name"
    shutil.move(case, output)
    return output


def update_identity(output, **changes):
    """Keep receipt links valid while constructing explicit identity fixtures."""
    path = output / "sync_manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(changes)
    for record in manifest["records"].values():
        receipt_path = output / record["receipt"]["path"]
        receipt = json.loads(receipt_path.read_text())
        receipt.update({k: v for k, v in changes.items() if k in ("case_id", "configuration_hash", "simulation_id")})
        receipt_path.write_text(json.dumps(receipt, sort_keys=True))
        record["receipt"]["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest, sort_keys=True))


def test_standalone_named_case_reuses_verified_evidence_without_ghost_configurations(tmp_path):
    output = standalone(tmp_path)
    result = analyze_synced_results(output, RUN)
    assert result.report["mode"] == "native_case_sync"
    assert [c["case_id"] for c in result.report["cases"]] == [CASE_ID]
    assert [s["time_name"] for s in result.report["snapshots"]] == ["2", "10"]
    assert result.report["snapshots"][0]["statistics"]["speed"]["mean"] == pytest.approx(50 / 3)
    assert all(s["case_id"] == CASE_ID for s in result.report["sources"])
    assert "no room cell mask" in result.report["snapshots"][0]["region"]
    graph = proofgraph_from_dict(result.proofgraph.to_dict())
    assert len(graph.requirement_set.requirements) == 2
    assert graph.evidence[0].value["configuration_number"] is None
    assert graph.evidence[0].subject_ref == RUN + "/" + CASE_ID
    assert {v.status for v in graph.verdicts} == {"pass", "not_checked"}
    assert result.report["scientific_validation"] == "BLOCKED"
    assert analyze_selected_result_store(output).report == result.report


def test_legacy_run_folder_selection_keeps_three_configuration_findings(tmp_path):
    write_sync_store(tmp_path / "store")
    selected = analyze_selected_result_store(tmp_path / "store" / "SYNTHETIC-run-a")
    assert selected.report["mode"] == "native_runtime_sync"
    assert len(selected.proofgraph.requirement_set.requirements) == 6


@pytest.mark.parametrize("bad_id", ["../escape", "/absolute", "a//b", "a/./b", "a\\b", "a\nb", "x" * 257])
def test_standalone_unsafe_case_identifiers_fail_before_graph_creation(tmp_path, bad_id):
    output = standalone(tmp_path)
    update_identity(output, case_id=bad_id)
    with pytest.raises(ValueError, match="safe relative identifier"):
        analyze_synced_results(output, RUN)


def test_standalone_simulation_receipt_and_asset_identity_remain_required(tmp_path):
    output = standalone(tmp_path)
    with pytest.raises(ValueError, match="identity"):
        analyze_synced_results(output, "different-run")
    manifest_path = output / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    record = manifest["records"]["2"]
    receipt_path = output / record["receipt"]["path"]
    receipt = json.loads(receipt_path.read_text())
    receipt["case_id"] = "other-case"
    receipt_path.write_text(json.dumps(receipt))
    record["receipt"]["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="receipt"):
        analyze_synced_results(output, RUN)
    receipt["case_id"] = CASE_ID
    receipt_path.write_text(json.dumps(receipt))
    record["receipt"]["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    asset = output / next(a["path"] for a in record["assets"] if a["path"].endswith(".vtk"))
    asset.write_bytes(asset.read_bytes() + b"\nchanged\n")
    with pytest.raises(ValueError, match="(size|hash)"):
        analyze_synced_results(output, RUN)


def test_standalone_log_diagnostics_bind_actual_case_inputs_and_log_bytes(tmp_path):
    output = standalone(tmp_path)
    case = tmp_path / "native-case"
    for dirname, filename in (("system", "controlDict"), ("constant", "transportProperties"), ("0", "U")):
        (case / dirname).mkdir(parents=True)
        (case / dirname / filename).write_text("SYNTHETIC static input\n")
    log = case / "simpleFoam.log"
    log.write_text(residual_log())
    update_identity(output, configuration_hash=hash_case_configuration(case),
                    solver_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    result = analyze_synced_results(output, RUN, case_directory=case)
    assert result.report["diagnostics"][0]["log_execution_binding"] == "hash_bound_sync_manifest"
    assert len([s for s in result.report["sources"] if s["role"] == "case_input"]) == 3
    assert build_analysis_graph([result], kind="residual_history", field_name="all")["series"]
    log.write_text(residual_log() + "changed\n")
    with pytest.raises(ValueError, match="no longer matches"):
        analyze_synced_results(output, RUN, case_directory=case)
    log.write_text(residual_log())
    (case / "0" / "U").write_text("changed static input\n")
    with pytest.raises(ValueError, match="inputs do not match"):
        analyze_synced_results(output, RUN, case_directory=case)
    with pytest.raises(ValueError, match="source changed"):
        export_analysis_bundle([result], [build_analysis_graph([result])], tmp_path / "changed-export")
    assert not (tmp_path / "changed-export").exists()


def test_standalone_cli_exports_parsed_results_and_roundtrippable_proofgraph(tmp_path, monkeypatch, capsys):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_pipeline_cli import main
    output = standalone(tmp_path)
    export = tmp_path / "analysis-export"
    monkeypatch.setattr(sys, "argv", ["cleanroomx-cfd-pipeline", "analyze-results", str(output),
                                     "--simulation-id", RUN, "--output", str(export)])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["scientific_validation"] == "BLOCKED"
    proofgraph_from_dict(json.loads((export / "proofgraph-01.json").read_text()))
    rows = list(csv.DictReader(io.StringIO((export / "graphs.csv").read_text())))
    assert {r["case_id"] for r in rows} == {CASE_ID}


def test_exact_solver_times_select_correct_spatial_export_and_csv(tmp_path):
    pytest.importorskip("matplotlib")
    precise_time = "1.0000000000000001"
    output = standalone(tmp_path, times=("1", precise_time))
    result = analyze_synced_results(output, RUN)
    graph = build_analysis_graph([result], kind="cell_3d", case_id=CASE_ID, time_name=precise_time)
    export = export_analysis_bundle([result], [graph], tmp_path / "precise-export")
    rows = list(csv.DictReader(io.StringIO((export / "cell-data-01.csv").read_text())))
    assert {r["time_name"] for r in rows} == {precise_time}
    history = build_analysis_graph([result])
    rows = list(csv.DictReader(io.StringIO(graph_csv([history]))))
    assert [r["x"] for r in rows] == ["1", precise_time]


def test_standalone_symbolic_store_or_manifest_is_rejected(tmp_path):
    output = standalone(tmp_path)
    link = tmp_path / "linked-output"
    try:
        link.symlink_to(output, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links unavailable")
    with pytest.raises(ValueError, match="regular directory"):
        analyze_synced_results(link, RUN)
    original = output / "sync_manifest.json"
    moved = output / "saved-manifest.json"
    original.rename(moved)
    original.symlink_to(moved)
    with pytest.raises(ValueError, match="non-linked"):
        analyze_synced_results(output, RUN)
