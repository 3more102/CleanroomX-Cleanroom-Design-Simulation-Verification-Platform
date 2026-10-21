"""Actual Foundation v10 executions; skipped when that runtime is unavailable.

These tests assert execution/ingestion contracts, not CFD physical validation.
No synthetic field values or successful solver logs stand in for execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tkinter as tk

import pytest

from cleanroomx.cfd_multizone import generate_multizone_open_door_case, run_multizone_open_door_case
from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow, slice_samples
from cleanroomx.cfd_multizone_results import analyze_multizone_case, export_multizone_report, read_ascii_field
from cleanroomx.cfd_multizone_review import review_recorded_multizone
from cleanroomx.cfd_multizone_stability import (
    analyze_recorded_iteration_history, compare_recorded_iterations,
    export_recorded_iteration_history,
)
from cleanroomx.cfd_streamlines import ComputedVelocityGrid, trace_computed_streamline
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.cfd_closed_door_sensitivity import sweep_closed_door_leakage
from cleanroomx.cfd_closed_door_comparison import (
    compare_closed_network_with_open_cfd,write_closed_door_scenario_template,
    load_closed_door_network_scenario,export_closed_door_comparison,
)



def _require_runtime():
    available=all(shutil.which(name) for name in ("blockMesh","checkMesh","simpleFoam","postProcess"))
    if available:
        version=subprocess.run(["simpleFoam","-help"],capture_output=True,text=True,check=False,timeout=30)
        available="Using: OpenFOAM-10 " in version.stdout+version.stderr
    if not available:
        if os.environ.get("CLEANROOMX_REQUIRE_OPENFOAM")=="1":
            pytest.fail("Required OpenFOAM Foundation v10 runtime is missing")
        pytest.skip("Actual OpenFOAM Foundation v10 execution requires its sourced environment")


@pytest.fixture(scope="module")
def executed_case(tmp_path_factory):
    _require_runtime()
    configured=os.environ.get("CLEANROOMX_CFD_EVIDENCE_DIR")
    base=Path(configured) if configured else tmp_path_factory.mktemp("actual-multizone")
    base.mkdir(parents=True,exist_ok=True)
    root=base/"case"
    generate_multizone_open_door_case(
        bundled_demo_project_path(),root,door_mode="open",kinematic_viscosity_m2_s=1.5e-5,
        max_iterations=100,output_interval=25,
    )
    events=[]
    receipt=run_multizone_open_door_case(root,timeout_seconds=120,on_progress=events.append)
    assert receipt["status"]=="executed_requires_convergence_review", receipt
    assert [e["event"] for e in events]==["started","finished"]*4
    return root


@pytest.fixture(scope="module")
def computed_report(executed_case):
    return analyze_multizone_case(executed_case,density_kg_m3=1.2,reference_room_id="corridor")


def test_actual_mesh_solver_outputs_and_provenance(executed_case,computed_report):
    report=computed_report
    assert report["mesh"]["mesh_ok"]
    assert report["mesh"]["cells"]==len(report["cells"])==13210
    assert report["mesh"]["regions"]==1
    assert report["time_name"]=="100"
    assert report["available_times"]==["25","50","75","100"]
    assert {h["field"] for h in report["residual_history"]}=={"p","Ux","Uy","Uz"}
    log=(executed_case/"simpleFoam.log").read_text()
    assert report["solver_reported_convergence"]==("SIMPLE solution converged" in log)
    assert report["provenance"]["run_receipt_sha256"]==hashlib.sha256((executed_case/"run-receipt.json").read_bytes()).hexdigest()
    for cell in report["cells"]:
        assert len(cell["velocity_m_s"])==3
        assert all(math.isfinite(v) for v in cell["velocity_m_s"])


def test_true_openfoam_saved_iteration_history_uses_p_u_and_phi_snapshots(
    executed_case, computed_report, tmp_path,
):
    """Four genuine recorded SIMPLE outputs, never artificial physical times."""
    history=analyze_recorded_iteration_history(
        executed_case,density_kg_m3=1.2,reference_room_id="corridor")
    assert [entry["iteration"] for entry in history["snapshots"]]==["25","50","75","100"]
    assert history["source_run_receipt_sha256"]==computed_report["provenance"]["run_receipt_sha256"]
    assert history["source_manifest_sha256"]==computed_report["provenance"]["manifest_sha256"]
    assert not history["closed_door_5pa_demonstrated"]
    assert history["engineering_release"]=="HOLD"
    assert history["latest_solver_reported_convergence"] is computed_report["solver_reported_convergence"]
    for name,door in computed_report["doors"].items():
        assert history["snapshots"][-1]["doors"][name]["delta_pa"]==pytest.approx(
            door["computed_delta_pressure_pa"])
        assert history["snapshots"][-1]["doors"][name]["net_m3_s"]==pytest.approx(
            door["computed_net_transfer_m3_s"])
    assert history["snapshots"][-1]["sum_absolute_cell_imbalance_m3_s"]==pytest.approx(
        computed_report["flow_balance"]["sum_absolute_cell_imbalance_m3_s"])
    assert history["snapshots"][-1]["change_from_previous_recorded_iteration"] is not None
    report_path=export_recorded_iteration_history(history,tmp_path/"iteration-review")
    assert report_path.is_file()
    assert "latest_solver_reported_convergence" in report_path.read_text()
    from cleanroomx.cfd_convergence_triage import (
        TRIAGE_SCHEMA, triage_recorded_convergence, export_convergence_triage,
    )
    triage=triage_recorded_convergence(
        history,pressure_drift_limit_pa=.01,
        transfer_drift_limit_m3_s=1e-5,
        cell_imbalance_limit_m3_s=.001,consecutive_changes=2)
    assert triage["schema"]==TRIAGE_SCHEMA
    assert triage["source_manifest_sha256"]==computed_report["provenance"]["manifest_sha256"]
    assert triage["source_run_receipt_sha256"]==computed_report["provenance"]["run_receipt_sha256"]
    assert triage["latest_iteration"]=="100"
    assert len(triage["reviewed_changes"])==2
    assert triage["engineering_release"]=="HOLD"
    assert triage["closed_door_5pa_demonstrated"] is False
    if not computed_report["solver_reported_convergence"]:
        assert triage["numerical_screening"]=="solver_not_converged"
    assert export_convergence_triage(
        triage,tmp_path/"actual-solver-triage.json").is_file()


def test_alternative_simple_relaxation_executes_as_an_independent_provenanced_case(tmp_path,monkeypatch):
    """A REAL Foundation v10 short run; checks execution, not convergence improvement.

    New-case settings must be documented by fvSolution and the input manifest,
    and every solver field must be hash-linked to the independent run receipt.
    """
    _require_runtime()
    case=tmp_path/"alternate-relaxation"
    generated=generate_multizone_open_door_case(
        bundled_demo_project_path(),case,door_mode="open",
        kinematic_viscosity_m2_s=1.5e-5,
        max_iterations=10,output_interval=5,
        pressure_relaxation=.2,velocity_relaxation=.5,
    )
    assert generated["case"]["numerical_controls"]["pressure_field_relaxation"]==.2
    assert generated["case"]["numerical_controls"]["velocity_equation_relaxation"]==.5
    assert "fields { p 0.2; }" in (case/"system/fvSolution").read_text()
    assert "equations { U 0.5; }" in (case/"system/fvSolution").read_text()
    run=run_multizone_open_door_case(case,timeout_seconds=120)
    assert run["status"]=="executed_requires_convergence_review",run
    assert [step["command"] for step in run["stages"]]==[
        "blockMesh","checkMesh","simpleFoam","postProcess"]
    report=analyze_multizone_case(case,density_kg_m3=1.2,reference_room_id="corridor")
    assert report["time_name"]=="10"
    assert report["available_times"]==["5","10"]
    assert len(report["cells"])==13210
    assert report["provenance"]["manifest_sha256"]==hashlib.sha256(
        (case/"manifest.json").read_bytes()).hexdigest()
    assert report["provenance"]["run_receipt_sha256"]==hashlib.sha256(
        (case/"run-receipt.json").read_bytes()).hexdigest()
    assert all(math.isfinite(row["initial"]) for row in report["residual_history"])
    # Deliberately no assertion that this setting converges better or
    # achieves 5 Pa: that requires a controlled study of full solver runs.
    assert report["scenario"]=="all_doors_open"
    # Use an INDEPENDENT default-control OpenFOAM execution at precisely
    # the same SIMPLE iteration labels for an apples-to-apples numerical
    # sensitivity audit. This is *not* solver convergence or physical evidence.
    baseline_dir=tmp_path/"baseline-relaxation"
    generate_multizone_open_door_case(
        bundled_demo_project_path(),baseline_dir,door_mode="open",
        kinematic_viscosity_m2_s=1.5e-5,
        max_iterations=10,output_interval=5,
    )
    baseline_run=run_multizone_open_door_case(
        baseline_dir,timeout_seconds=120)
    assert baseline_run["status"]=="executed_requires_convergence_review"
    from cleanroomx.cfd_relaxation_comparison import (
        compare_independent_relaxation_cases,
        export_independent_relaxation_comparison,
    )
    compared=compare_independent_relaxation_cases(
        baseline_dir,case,density_kg_m3=1.2,reference_room_id="corridor")
    assert compared["scenario"]=="all_doors_open"
    assert compared["selected_simple_iteration"]=="10"
    assert compared["available_identical_saved_iterations"]==["5","10"]
    assert compared["same_geometry_and_other_solver_inputs_verified"]
    assert compared["comparison_status"]=="two_real_runs_numerical_differences_only"
    assert compared["baseline"]["controls"]["pressure_field_relaxation"]==.3
    assert compared["variant"]["controls"]["velocity_equation_relaxation"]==.5
    assert compared["mesh_cells"]==13210
    assert len(compared["door_comparison"])==3
    assert len(compared["room_comparison"])==4
    assert set(compared["solver_numerical_evidence"])=={"baseline","variant"}
    assert compared["engineering_release"]=="HOLD"
    assert not compared["numerical_convergence_or_improvement_proven"]
    assert not compared["closed_door_5pa_demonstrated"]
    out=tmp_path/"numerical-control-comparison.json"
    assert export_independent_relaxation_comparison(compared,out)==out
    assert json.loads(out.read_text())["source_project_sha256"]==(
        generated["project_source_sha256"])
    # An edited result must be detected against the TWO independently
    # reimported, verified run receipts; never export a fabricated improvement.
    modified=json.loads(json.dumps(compared))
    first_room=next(iter(modified["room_comparison"]))
    modified["room_comparison"][first_room]["variant_minus_baseline_pressure_pa"]+=5
    with pytest.raises(ValueError,match="changed after source-linked"):
        export_independent_relaxation_comparison(
            modified,tmp_path/"forged-numerical-evidence.json")
    from cleanroomx.cfd_pipeline_cli import main as cfd_pipeline_main
    cli_out=tmp_path/"cli-paired-relaxation.json"
    monkeypatch.setattr("sys.argv",[
        "cleanroomx-cfd-pipeline",
        "multizone-compare-relaxation",str(baseline_dir),str(case),
        "--density-kg-m3","1.2","--reference-room-id","corridor",
        "--output",str(cli_out),
    ])
    assert cfd_pipeline_main()==0
    assert json.loads(cli_out.read_text())["engineering_release"]=="HOLD"
    with pytest.raises(FileExistsError):
        export_independent_relaxation_comparison(compared,out)
    with pytest.raises(ValueError,match="two different"):
        compare_independent_relaxation_cases(
            baseline_dir,baseline_dir,density_kg_m3=1.2,
            reference_room_id="corridor")


def test_actual_fluxes_units_reference_and_door_pressure(computed_report,executed_case):
    report=computed_report
    rooms=report["rooms"]
    assert rooms["corridor"]["mean_pressure_pa_relative_to_reference"]==0
    for rid,flow in (("process",2700),("preparation",1200),("ante",720)):
        assert rooms[rid]["supply_inflow_m3_s"]*3600==pytest.approx(flow,rel=1e-8)
    assert sum(r["net_outward_imbalance_m3_s"] for r in rooms.values())==pytest.approx(report["global_net_outward_imbalance_m3_s"],abs=1e-10)
    for door in report["doors"].values():
        assert door["computed_face_count"]==door["open_face_count"]==70
        assert door["computed_net_transfer_m3_s"]==pytest.approx(door["computed_forward_m3_s"]-door["computed_reverse_m3_s"])
        assert door["computed_delta_pressure_pa"]==pytest.approx(
            rooms[door["from_room"]]["mean_pressure_pa_relative_to_reference"]-
            rooms[door["to_room"]]["mean_pressure_pa_relative_to_reference"])
        assert door["design_delta_pressure_target_pa"]==5
    denser=analyze_multizone_case(executed_case,density_kg_m3=2.4,reference_room_id="process")
    assert denser["rooms"]["process"]["mean_pressure_pa_relative_to_reference"]==0
    assert denser["rooms"]["process"]["design_pressure_relative_to_reference_pa"]==0
    for name,door in denser["doors"].items():
        assert door["computed_delta_pressure_pa"]==pytest.approx(report["doors"][name]["computed_delta_pressure_pa"]*2)
    balance=report["flow_balance"]
    assert balance["boundary_inflow_m3_s"]-balance["boundary_outflow_m3_s"]==pytest.approx(-report["global_net_outward_imbalance_m3_s"],abs=1e-12)
    assert sum(r["sum_absolute_cell_imbalance_m3_s"] for r in rooms.values())==pytest.approx(balance["sum_absolute_cell_imbalance_m3_s"])
    assert max(r["max_absolute_cell_imbalance_m3_s"] for r in rooms.values())==balance["max_absolute_cell_imbalance_m3_s"]
    for r in rooms.values():
        assert r["total_face_outflow_m3_s"]-r["total_face_inflow_m3_s"]==pytest.approx(r["net_outward_imbalance_m3_s"],abs=1e-12)
        assert r["sum_absolute_cell_imbalance_m3_s"]+1e-12 >= abs(r["net_outward_imbalance_m3_s"])


def test_actual_time_sections_and_reproducible_report(executed_case,computed_report,tmp_path):
    earlier=analyze_multizone_case(executed_case,density_kg_m3=1.2,reference_room_id="corridor",time_name="25")
    assert earlier["time_name"]=="25"
    assert earlier["cells"]!=computed_report["cells"]
    samples=slice_samples(computed_report,"z",1.35,"process")
    assert samples and all(s["center_m"][2]==pytest.approx(1.35) and s["room_id"]=="process" for s in samples)
    report_dir=tmp_path/"report"
    path=export_multizone_report(computed_report,report_dir)
    assert path.name=="report.html"
    summary=json.loads((report_dir/"report.json").read_text())
    assert summary["provenance"]==computed_report["provenance"]
    assert len((report_dir/"cells.csv").read_text().splitlines())==13211
    assert len((report_dir/"room-balances.csv").read_text().splitlines())==5
    assert summary["numerics"]["selected_iteration"]==100
    assert "Solver reported convergence" in path.read_text()
    assert "Engineering decision: HOLD" in path.read_text()
    engineering=json.loads((report_dir/"engineering-review.json").read_text())
    assert engineering["engineering_release"]=="HOLD"
    assert engineering["source_iteration"]==computed_report["time_name"]
    assert engineering["source_manifest_sha256"]==computed_report["provenance"]["manifest_sha256"]
    assert len(engineering["doors"])==3
    assert not engineering["closed_door_5pa_demonstrated"]
    with pytest.raises(FileExistsError):
        export_multizone_report(computed_report,report_dir)
    with pytest.raises(FileExistsError,match="already"):
        run_multizone_open_door_case(executed_case)


def test_actual_field_ingestion_rejects_output_log_and_receipt_tampering(executed_case,tmp_path):
    for name in ("100/p","simpleFoam.log","manifest.json"):
        copied=tmp_path/name.replace("/","_")
        shutil.copytree(executed_case,copied)
        target=copied/name
        target.write_text(target.read_text()+"\n ")
        with pytest.raises(ValueError,match="changed"):
            analyze_multizone_case(copied,density_kg_m3=1.2,reference_room_id="corridor")
    with pytest.raises(ValueError,match="density"):
        analyze_multizone_case(executed_case,density_kg_m3=float("nan"),reference_room_id="corridor")
    with pytest.raises(ValueError,match="reference"):
        analyze_multizone_case(executed_case,density_kg_m3=1.2,reference_room_id="absent")
    with pytest.raises(ValueError,match="lacks recorded"):
        analyze_multizone_case(executed_case,density_kg_m3=1.2,reference_room_id="corridor",time_name="0")


def test_actual_solver_failure_is_recorded_and_never_importable(tmp_path):
    _require_runtime()
    root=tmp_path/"invalid-solver-dictionary"
    generate_multizone_open_door_case(bundled_demo_project_path(),root,door_mode="open",kinematic_viscosity_m2_s=1.5e-5,max_iterations=5,output_interval=5)
    path=root/"system/fvSchemes"
    path.write_text(path.read_text().replace("div((nuEff*dev2(T(grad(U))))) Gauss linear;",""))
    manifest=json.loads((root/"manifest.json").read_text())
    manifest["files"]["system/fvSchemes"]=hashlib.sha256(path.read_bytes()).hexdigest()
    (root/"manifest.json").write_text(json.dumps(manifest))
    receipt=run_multizone_open_door_case(root,timeout_seconds=120)
    assert receipt["status"]=="incomplete"
    assert receipt["stages"][-1]["command"]=="simpleFoam"
    assert receipt["stages"][-1]["returncode"]!=0
    assert json.loads((root/"run-receipt.json").read_text())==receipt
    with pytest.raises(ValueError,match="successful recorded"):
        analyze_multizone_case(root,density_kg_m3=1.2,reference_room_id="corridor")


def test_timeout_injection_records_failure_without_success_evidence(tmp_path,monkeypatch):
    """Failure injection only; this test contributes no real solver evidence."""
    _require_runtime()
    root=tmp_path/"timeout"
    generate_multizone_open_door_case(bundled_demo_project_path(),root,door_mode="open",kinematic_viscosity_m2_s=1.5e-5)
    original=subprocess.run
    def fail_mesh(arguments,**kwargs):
        if arguments==["blockMesh"]:
            raise subprocess.TimeoutExpired(arguments,60)
        return original(arguments,**kwargs)
    monkeypatch.setattr("cleanroomx.cfd_multizone.subprocess.run",fail_mesh)
    receipt=run_multizone_open_door_case(root,timeout_seconds=60)
    assert receipt["status"]=="incomplete"
    assert receipt["stages"][0]["returncode"] is None
    assert "timed out" in receipt["stages"][0]["failure"]
    assert receipt["outputs"]=={}


def test_actual_gui_displays_recorded_fields_vectors_and_residuals(computed_report,executed_case):
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Real Tk display required: {exc}")
    errors=[]
    root.report_callback_exception=lambda *args:errors.append(args)
    window=MultizoneCFDWindow(root)
    try:
        root.update()
        window.load_report(computed_report)
        root.update()
        assert len(window.room_table.get_children())==4
        assert len(window.door_table.get_children())==3
        assert window.engineering_review["engineering_release"]=="HOLD"
        assert len(window.engineering_table.get_children())==3
        assert "5 Pa CLOSED-DOOR PERFORMANCE NOT DEMONSTRATED" in window.engineering_verdict.get()
        assert "OPEN_DOOR_SCENARIO" in window.engineering_text.get("1.0","end")
        # Reuse real OpenFOAM room/door references with intentionally assumed
        # leakage only to test UI mapping; no physical validation is claimed.
        synthetic_model,synthetic_sources=_explicit_hypothetical_closed_door_network(
            computed_report)
        closed=compare_closed_network_with_open_cfd(
            computed_report,synthetic_model,synthetic_sources)
        window.load_closed_door_comparison(closed)
        root.update()
        assert len(window.closed_door_table.get_children())==3
        assert "TWO DIFFERENT MODELS" in window.closed_door_details.get("1.0","end")
        wrong_iteration=dict(closed)
        wrong_iteration["open_cfd_provenance"]={
            **closed["open_cfd_provenance"],"selected_iteration":"75"}
        with pytest.raises(ValueError,match="another CFD run/iteration"):
            window.load_closed_door_comparison(wrong_iteration)
        assert len(window.closed_door_table.get_children())==3
        wrong_manifest=dict(closed)
        wrong_manifest["open_cfd_provenance"]={
            **closed["open_cfd_provenance"],"manifest_sha256":"0"*64}
        with pytest.raises(ValueError,match="another CFD run/iteration"):
            window.load_closed_door_comparison(wrong_manifest)
        assert "ENGINEERING HOLD" in window.closed_door_status.get()
        window.closed_door_model=synthetic_model
        window.closed_door_evidence=synthetic_sources
        window.run_closed_leakage_sensitivity()
        root.update()
        assert len(window.closed_sweep_table.get_children())==9
        assert len(window.closed_sweep_canvas.find_withtag("leakage-solved-point"))==9
        assert len(window.closed_sweep_canvas.find_withtag("leakage-design-target"))==3
        assert len(window.closed_sweep_canvas.find_withtag("leakage-factor-marker"))==3
        assert len(window.closed_sweep_canvas.find_withtag("leakage-legend"))==3
        assert "Hypothetical leakage sensitivity" in window.closed_door_status.get()
        assert window.closed_door_sensitivity["engineering_release"]=="HOLD"

        earlier=analyze_multizone_case(
            executed_case,density_kg_m3=1.2,reference_room_id="corridor",
            time_name="25")
        history=compare_recorded_iterations([earlier,computed_report])
        window.load_iteration_history(history)
        root.update()
        assert len(window.history_table.get_children())==2
        assert len(window.history_pressure_canvas.find_withtag("computed-iteration-point"))==6
        assert len(window.history_balance_canvas.find_withtag("computed-iteration-point"))==2
        assert len(window.history_pressure_canvas.find_withtag("snapshot-visual-guide"))==3
        assert "ENGINEERING HOLD" in window.history_status.get()
        assert "NOT physical time" in history["interpretation"]
        assert len(window.pressure_canvas.find_withtag("computed-pressure"))==4
        window.tabs.select(1)
        root.update()
        window.draw_section()
        assert window.section_canvas.find_withtag("computed-cell")
        assert window.section_canvas.find_withtag("computed-vector")
        window.tabs.select(2)
        root.update()
        assert len(window.residual_canvas.find_withtag("computed-residual"))==4
        assert len(window.residual_table.get_children())==4
        assert len(window.residual_canvas.find_withtag("selected-iteration"))==1
        assert ("NOT CONVERGED" in window.status.get()) != computed_report["solver_reported_convergence"]
        assert errors==[]
    finally:
        window.close()
        root.destroy()


def test_real_ascii_field_units_are_required(executed_case):
    data=(executed_case/"100/p").read_text()
    with pytest.raises(ValueError,match="dimensions"):
        read_ascii_field(data,13210,(0,1,-1,0,0,0,0))
    with pytest.raises(ValueError,match="count"):
        read_ascii_field(data,123,(0,2,-2,0,0,0,0))


def test_actual_low_flow_convergence_applies_only_to_its_final_fields(tmp_path):
    """Deliberately reduced supply is a numerical regression, not the design case."""
    _require_runtime()
    configured=os.environ.get("CLEANROOMX_CFD_EVIDENCE_DIR")
    base=Path(configured)/"low-flow" if configured else tmp_path
    base.mkdir(parents=True,exist_ok=True)
    raw=json.loads(bundled_demo_project_path().read_text())
    verification=next(a for a in raw["analyses"] if a["id"]=="verification")
    for room in verification["input"]["rooms"]:
        room["supply_airflow_m3_h"]*=.001
    source=base/"low-flow-project.json"
    source.write_text(json.dumps(raw))
    case=base/"case"
    generate_multizone_open_door_case(source,case,door_mode="open",kinematic_viscosity_m2_s=1.5e-5,
                                    max_iterations=400,output_interval=50)
    receipt=run_multizone_open_door_case(case,timeout_seconds=120)
    assert receipt["status"]=="executed_requires_convergence_review", receipt
    final=analyze_multizone_case(case,density_kg_m3=1.2,reference_room_id="corridor")
    assert final["solver_reported_convergence"]
    assert final["numerics"]["selected_initial_residuals_below_limits"]
    assert final["numerics"]["solver_convergence_iteration"]==float(final["time_name"]) < 400
    first=final["available_times"][0]
    assert float(first)<float(final["time_name"])
    earlier=analyze_multizone_case(case,density_kg_m3=1.2,reference_room_id="corridor",time_name=first)
    assert earlier["numerics"]["run_reported_convergence"]
    assert not earlier["solver_reported_convergence"]
    assert earlier["numerics"]["selected_iteration"]==float(first)
    assert earlier["flow_balance"]["sum_absolute_cell_imbalance_m3_s"]>final["flow_balance"]["sum_absolute_cell_imbalance_m3_s"]


def test_real_openfoam_cell_velocity_drives_bounded_3d_streamline(computed_report):
    """Actual solver fields, not synthetic air velocities or time animation."""
    report = computed_report
    seed = report["cells"][len(report["cells"])//2]["center_m"]
    trace = trace_computed_streamline(report,seed,max_integration_s=2)
    assert trace["source_manifest_sha256"] == report["provenance"]["manifest_sha256"]
    assert trace["source_run_receipt_sha256"] == report["provenance"]["run_receipt_sha256"]
    assert trace["source_iteration"] == report["time_name"]
    assert not trace["validated_particle_tracking"]
    assert 1 <= len(trace["points"]) <= 801
    grid = ComputedVelocityGrid(report)
    for point in trace["points"]:
        sample = grid.cell_at(point["xyz_m"])
        assert sample is not None  # Every retained trace point is in solved fluid.
        assert point["speed_m_s"] == pytest.approx(math.dist((0,0,0),sample[0]))
    if len(trace["points"]) > 1:
        assert trace["points"][-1]["integration_parameter_s"] > 0


def test_real_solver_computed_fields_feed_true_vtk_3d(computed_report):
    """Source VTK point scalars/vectors from actual validated OpenFOAM U/p.

    VTK is an optional rendering dependency; this check runs when installed.
    This does not establish physical mesh or convergence validity.
    """
    pytest.importorskip("vtk")
    from cleanroomx.cfd_multizone_vtk import (
        computed_field_polydata, sampled_velocity_glyph_actor,
        build_multizone_vtk_renderer, select_recorded_cells,
        seed_streamline_from_displayed_point,
    )
    actual=computed_report
    points=computed_field_polydata(actual)
    assert points.GetNumberOfPoints()==actual["mesh"]["cells"]==13210
    assert points.GetNumberOfVerts()==13210
    for index in (0, 6605, 13209):
        cell=actual["cells"][index]
        assert points.GetPoint(index)==pytest.approx(cell["center_m"])
        assert points.GetPointData().GetArray("Computed U (m/s)").GetTuple3(index)==pytest.approx(cell["velocity_m_s"])
        assert points.GetPointData().GetArray("Computed pressure relative (Pa)").GetTuple1(index)==pytest.approx(
            cell["pressure_pa_relative_to_reference"])
    scene=build_multizone_vtk_renderer(actual,[],field="pressure",vectors=False)
    assert scene.GetActors().GetNumberOfItems()>=6
    # A genuine OpenFOAM layer imports its existing field values verbatim.
    seed=actual["cells"][0]
    axis_position=seed["center_m"][2]
    selected=select_recorded_cells(
        actual,room_id=seed["room_id"],plane_axis="z",
        plane_position_m=axis_position)
    assert selected
    assert all(cell["room_id"]==seed["room_id"] for cell in selected)
    assert all(cell["center_m"][2]==pytest.approx(axis_position) for cell in selected)
    selected_vtk=computed_field_polydata(
        actual,room_id=seed["room_id"],plane_axis="z",
        plane_position_m=axis_position)
    assert selected_vtk.GetNumberOfPoints()==len(selected)
    for i in (0,len(selected)//2,len(selected)-1):
        assert selected_vtk.GetPoint(i)==pytest.approx(selected[i]["center_m"])
        assert selected_vtk.GetPointData().GetArray(
            "Computed U (m/s)").GetTuple3(i)==pytest.approx(selected[i]["velocity_m_s"])
    arrows=sampled_velocity_glyph_actor(actual,max_arrows=60)
    arrows.GetMapper().Update()
    assert arrows.GetMapper().GetInput().GetNumberOfPoints()>0
    # The real 3D selection can seed only a recorded cell, preserving source receipt.
    picked=seed_streamline_from_displayed_point(
        actual,[],0,room_id=seed["room_id"],plane_axis="z",
        plane_position_m=axis_position,max_integration_s=1.)
    assert picked["points"][0]["xyz_m"]==selected[0]["center_m"]
    assert picked["source_iteration"]==actual["time_name"]
    assert picked["source_run_receipt_sha256"]==actual["provenance"]["run_receipt_sha256"]
    assert not picked["validated_particle_tracking"]


def test_real_openfoam_drives_one_way_particle_screening(computed_report):
    """Actual computed OpenFOAM U controls an inertial screening particle.

    One-way frozen-field integration only. This does NOT validate turbulent
    dispersion, cleanroom contamination risk or deposited particle fractions.
    """
    from cleanroomx.cfd_particles import trace_screening_particle
    from cleanroomx.cfd_multizone_vtk import (
        seed_particle_from_displayed_point, computed_particle_polydata,
        select_recorded_cells,
    )
    report=computed_report
    fluid=report["cells"][len(report["cells"])//2]
    seed=fluid["center_m"]
    track=trace_screening_particle(report,seed,
        diameter_um=5.,max_time_s=.1)
    assert track["source_iteration"]==report["time_name"]
    assert track["source_run_receipt_sha256"]==report["provenance"]["run_receipt_sha256"]
    assert 1<=len(track["points"])<=4001
    assert track["validated_particle_transport"] is False
    assert track["frozen_steady_velocity_no_solver_transient"]
    lookup=ComputedVelocityGrid(report)
    for item in track["points"]:
        actual=lookup.cell_at(item["xyz_m"])
        assert actual is not None
        assert item["recorded_gas_velocity_m_s"]==pytest.approx(actual[0])
        assert all(math.isfinite(v) for v in item["particle_velocity_m_s"])
    assert track["termination"] in (
        "max_particle_time","fluid_boundary_contact_unresolved","max_steps")
    axis_position=fluid["center_m"][2]
    samples=select_recorded_cells(
        report,room_id=fluid["room_id"],plane_axis="z",
        plane_position_m=axis_position)
    from_point=seed_particle_from_displayed_point(
        report,[],0,room_id=fluid["room_id"],plane_axis="z",
        plane_position_m=axis_position,max_time_s=.05)
    assert from_point["points"][0]["xyz_m"]==samples[0]["center_m"]
    vtk_track=computed_particle_polydata(report,[track])
    assert vtk_track.GetNumberOfPoints()==len(track["points"])
    # Independent diagnostics ingest ONLY the actual Foundation v10 field
    # samples used by this particle; these are not physical validation.
    from cleanroomx.cfd_particle_diagnostics import analyze_particle_trajectories
    diagnostic=analyze_particle_trajectories(report,[track,from_point])
    assert diagnostic["number_of_screening_tracks"]==2
    assert diagnostic["engineering_release"]=="HOLD"
    assert not diagnostic["validated_particle_transport"]
    assert diagnostic["source_run_receipt_sha256"]==report["provenance"]["run_receipt_sha256"]
    assert diagnostic["tracks"][0]["start_room_id"]==fluid["room_id"]
    assert diagnostic["tracks"][0]["sample_count"]==len(track["points"])
    assert diagnostic["aggregate"]["sum_polygonal_path_length_m"]>=0
    from cleanroomx.cfd_particle_ensemble import inject_recorded_particle_ensemble
    chosen=inject_recorded_particle_ensemble(
        report,[],count=2,room_id=fluid["room_id"],max_time_s=.03,
    )
    assert chosen["engineering_release"]=="HOLD"
    assert chosen["sampling"]["nonstatistical_geometry_sampling"]
    assert len(chosen["new_tracks"])==2
    assert all(p["source_run_receipt_sha256"]==
               report["provenance"]["run_receipt_sha256"]
               for p in chosen["new_tracks"])
    assert chosen["noncertifying_diagnostics"]["number_of_screening_tracks"]==2
    from cleanroomx.cfd_particle_refinement import analyze_particle_timestep_refinement
    numerical=analyze_particle_timestep_refinement(
        report,track,endpoint_tolerance_m=.001)
    assert numerical["source_iteration"]==report["time_name"]
    assert numerical["source_run_receipt_sha256"]==report["provenance"]["run_receipt_sha256"]
    assert numerical["engineering_release"]=="HOLD"
    assert len(numerical["runs"])==3
    assert numerical["not_physical_convergence"]


def test_true_openfoam_fields_produce_noncertifying_design_pressure_review(computed_report):
    """No claim that computed open-door 5 Pa design targets are verified."""
    actual=computed_report
    review=review_recorded_multizone(actual)
    assert review["engineering_release"]=="HOLD"
    assert not review["closed_door_5pa_demonstrated"]
    assert review["source_iteration"]==actual["time_name"]
    assert review["source_run_receipt_sha256"]==actual["provenance"]["run_receipt_sha256"]
    assert review["numerical_convergence_at_selected_iteration"] is actual["solver_reported_convergence"]
    assert len(review["doors"])==len(actual["doors"])==3
    for door in review["doors"]:
        source=actual["doors"][door["door"]]
        expected=source["computed_delta_pressure_pa"]-source["design_delta_pressure_target_pa"]
        assert door["delta_minus_target_pa"]==pytest.approx(expected)
        assert door["computed_forward_m3_s"]==pytest.approx(source["computed_forward_m3_s"])
        assert door["computed_reverse_m3_s"]==pytest.approx(source["computed_reverse_m3_s"])
    assert all(door["target_delta_pa"]==5. for door in review["doors"])
    assert "OPEN_DOOR_SCENARIO" in {item["code"] for item in review["reasons"]}


def _explicit_hypothetical_closed_door_network(computed_report):
    """Unit contract only, NOT sourced project leakage or an OpenFOAM execution."""
    from cleanroomx.pressure_network import (
        PressureNode,PressurePath,PressureTarget,RoomPressureNetwork,
    )
    report=computed_report
    reference=report["pressure_reference"]["room_id"]
    nodes=tuple(PressureNode(
        name=rid,supply_m3_h=0.,return_m3_h=0.,exhaust_m3_h=0.,
        fixed_pressure_pa=0. if rid==reference else None
    ) for rid in sorted(report["rooms"]))
    paths=tuple(PressurePath(
        name=name,start_node=door["from_room"],end_node=door["to_room"],
        kind="door",model="power_law",coefficient_m3_s_pa_n=.01,exponent=.65
    ) for name,door in sorted(report["doors"].items()))
    targets=tuple(PressureTarget(
        name="Nominal "+name,high_node=door["from_room"],
        low_node=door["to_room"],
        minimum_delta_pa=door["design_delta_pressure_target_pa"]
    ) for name,door in sorted(report["doors"].items()))
    evidence={name:{"basis":"engineering_assumption",
                    "reference":"SYNTHETIC contract test coefficient only, not measured"}
              for name in report["doors"]}
    return RoomPressureNetwork(
        name="Synthetic closed-door data mapping test",nodes=nodes,
        paths=paths,targets=targets),evidence


def test_real_openfoam_room_inventory_maps_to_explicit_closed_leakage_network(
    computed_report,tmp_path
):
    """Real OpenFOAM cell/door identities vs deliberately SYNTHETIC network.

    The zeros and coefficients used here are test-only values, not real
    project leakage evidence; model does NOT certify any 5 Pa performance.
    """
    source=computed_report
    template=tmp_path/"closed-input-template.json"
    write_closed_door_scenario_template(source,template)
    payload=json.loads(template.read_text())
    assert {node["name"] for node in payload["network"]["nodes"]}==set(source["rooms"])
    assert {path["name"] for path in payload["network"]["paths"]}==set(source["doors"])
    assert all(p["coefficient_m3_s_pa_n"] is None for p in payload["network"]["paths"])
    with pytest.raises(ValueError,match="Fill every room"):
        load_closed_door_network_scenario(template)
    model,evidence=_explicit_hypothetical_closed_door_network(source)
    comparison=compare_closed_network_with_open_cfd(source,model,evidence)
    assert comparison["engineering_release"]=="HOLD"
    assert not comparison["closed_door_5pa_cfd_demonstrated"]
    assert len(comparison["door_comparison"])==len(source["doors"])==3
    assert comparison["open_cfd_provenance"]["run_receipt_sha256"]==(
        source["provenance"]["run_receipt_sha256"])
    for door in comparison["door_comparison"]:
        assert door["open_door_cfd_delta_pa"]==pytest.approx(
            source["doors"][door["door"]]["computed_delta_pressure_pa"])
        assert door["closed_door_network_delta_pa"]==pytest.approx(0)
    out=export_closed_door_comparison(
        comparison,tmp_path/"two-model-review.json")
    assert json.loads(out.read_text())["engineering_release"]=="HOLD"
    assert len(comparison["mechanical_airflow_boundary_comparison"])==4
    for item in comparison["mechanical_airflow_boundary_comparison"]:
        rid=item["room"]
        assert item["open_cfd_supply_m3_h"]==pytest.approx(
            source["rooms"][rid]["supply_inflow_m3_s"]*3600)
        assert item["open_cfd_return_m3_h"]==pytest.approx(
            source["rooms"][rid]["return_outflow_m3_s"]*3600)
        assert item["closed_network_supply_input_m3_h"]==0.
    sweep=sweep_closed_door_leakage(
        source,model,evidence,factors=(.5,1.,2.))
    assert sweep["engineering_release"]=="HOLD"
    assert not sweep["closed_door_cfd_demonstrated"]
    assert len(sweep["factor_results"])==3
    assert all(len(scenario["door_results"])==3
               for scenario in sweep["factor_results"])


