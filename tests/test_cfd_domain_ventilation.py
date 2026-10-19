"""Synthetic receipt-binding tests; the real solver check is a separate script."""
import json

import pytest

from cleanroomx.cfd_convergence_triage import diagnose_grid_flux
from cleanroomx.cfd_result_analysis import (
    AnalysisSession, _bind_domain_ventilation, _new_report, build_analysis_graph,
)


def fixture(tmp_path):
    case = tmp_path / "configuration_1"
    (case / "2").mkdir(parents=True)
    (case / "constant/polyMesh").mkdir(parents=True)
    (case / "2/phi").write_text("dimensions [0 3 -1 0 0 0 0];\nboundaryField\n{\n"
                                "inlet\n{\n value uniform -0.1;\n}\noutlet\n{\n value uniform 0.09;\n}\n"
                                "walls\n{\n value uniform 0;\n}\n}\n")
    (case / "constant/polyMesh/boundary").write_text(
        "3\n(\ninlet\n{\n type patch; nFaces 1; startFace 0;\n}\n"
        "outlet\n{\n type patch; nFaces 1; startFace 1;\n}\nwalls\n{\n type wall; nFaces 1; startFace 2;\n}\n)\n")
    flux = diagnose_grid_flux(case, "2", family_root=tmp_path)
    assert flux["status"] == "MEASURED_DIAGNOSTIC_ONLY"
    verified = {"manifest_sha256": "a" * 64, "configuration_hash": "b" * 64}
    receipt = {"schema_version": "cleanroomx.openfoam-execution.v1", "simulation_id": "SYNTHETIC-run",
               "result_synchronization": {"1": verified}, "cases": {"1": {"solver_flux": flux, "stages": [
                   {"program": "checkMesh", "log_sha256": "c" * 64},
                   {"program": "simpleFoam", "log_sha256": "d" * 64}]}}}
    path = tmp_path / "execution-receipt.json"
    path.write_text(json.dumps(receipt))
    report = _new_report("SYNTHETIC-run", "native_three_cases")
    report["snapshots"] = [{"case_id": "configuration_1", "time_name": "2", "volume_m3": 3,
                            "native_source_fields": {"phi": {"sha256": flux["phi_sha256"]}}, "sources": []}]
    report["diagnostics"] = [{"case_id": "configuration_1", "sources": [
        {"role": "mesh_log", "sha256": "c" * 64}, {"role": "solver_log", "sha256": "d" * 64}]}]
    return report, path, receipt, {"configuration_1": verified}


def test_actual_flux_and_verified_volume_determine_ach_not_design_flow(tmp_path):
    report, path, receipt, verified = fixture(tmp_path)
    _bind_domain_ventilation(report, tmp_path, verified)
    assert report["ventilations"][0]["supply_ach_h_inv"] == pytest.approx(120)
    assert report["flow_balances"][0]["relative_flux_imbalance_percent"] == pytest.approx(10)
    session = AnalysisSession(report, None, ())
    for kind in ("flow_balance", "air_change_rate"):
        graph = build_analysis_graph([session], kind=kind)
        assert graph["status"] == "computed_diagnostic"
        assert graph["series"][0]["case_id"] == "configuration_1"
        assert build_analysis_graph([session], kind=kind, case_id="configuration_2")["status"] == "not_available"
        assert build_analysis_graph([session], kind=kind, time_name="1")["status"] == "not_available"
        assert graph["scientific_validation"] == "BLOCKED"


@pytest.mark.parametrize("mutation", ["phi", "boundary", "mesh_log", "simulation_id", "sync_manifest", "time"])
def test_changed_solver_evidence_is_rejected(tmp_path, mutation):
    report, path, receipt, verified = fixture(tmp_path)
    if mutation == "phi":
        with (tmp_path / "configuration_1/2/phi").open("a") as stream:
            stream.write("// changed\n")
    elif mutation == "boundary":
        with (tmp_path / "configuration_1/constant/polyMesh/boundary").open("a") as stream:
            stream.write("// changed\n")
    elif mutation == "mesh_log":
        report["diagnostics"][0]["sources"][0]["sha256"] = "e" * 64
    elif mutation == "simulation_id":
        report["simulation_id"] = "different-run"
    elif mutation == "sync_manifest":
        verified["configuration_1"]["manifest_sha256"] = "f" * 64
    else:
        report["snapshots"][0]["time_name"] = "3"
    with pytest.raises(ValueError):
        _bind_domain_ventilation(report, tmp_path, verified)
