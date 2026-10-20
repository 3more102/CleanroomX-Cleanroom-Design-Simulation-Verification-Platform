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
from cleanroomx.gui import bundled_demo_project_path


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


def test_actual_gui_displays_recorded_fields_vectors_and_residuals(computed_report):
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
