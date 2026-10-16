"""Synthetic and mocked integration tests; no OpenFOAM physical run is claimed."""
import json
import math
import runpy
import pytest
from pathlib import Path

from cleanroomx.cfd_scalar import (
    SCHEMA, MESH_FILES, _scalar_files, prepare_scalar_case, run_scalar_case,
    validate_scalar_spec,
)
from cleanroomx.cfd_audit import audit_openfoam_log
from cleanroomx.cfd_pipeline_cli import build_parser


def scalar_spec():
    return {
        "schema_version":SCHEMA,
        "room_m":[3.0,2.0,2.0],
        "source_location_m":[0.75,0.65,0.6],
        "source_strength_m3_s":1e-6,
        "diffusivity_m2_s":1e-5,
        "iterations":100,
        "write_interval":20,
    }


def synthetic_finished_flow(tmp_path):
    root=tmp_path/"airflow"
    mesh=root/"constant"/"polyMesh"
    mesh.mkdir(parents=True)
    for name in MESH_FILES:
        (mesh/name).write_text("synthetic "+name)
    latest=root/"100"
    latest.mkdir()
    (latest/"U").write_text("FoamFile { class volVectorField; } synthetic U")
    return root


def test_validate_scalar_spec_and_v10_dictionary():
    spec=scalar_spec()
    assert validate_scalar_spec(spec) is spec
    files=_scalar_files(spec)
    assert set(files)=={"0/T","system/controlDict","system/fvSchemes",
                        "system/fvSolution","constant/physicalProperties",
                        "constant/fvModels"}
    assert "application scalarTransportFoam;" in files["system/controlDict"]
    assert "type semiImplicitSource;" in files["constant/fvModels"]
    assert "selectionMode points;" in files["constant/fvModels"]
    assert "volumeMode absolute;" in files["constant/fvModels"]
    assert "source" not in files["0/T"]  # scalar is sourced by fvModels, not unverified wall BC
    assert "div(phi,T)" in files["system/fvSchemes"]
    assert "DT DT [0 2 -1 0 0 0 0]" in files["constant/physicalProperties"]


@pytest.mark.parametrize("field,value",[
    ("schema_version","wrong"),
    ("room_m",[0,2,2]),
    ("source_location_m",[3,1,1]),
    ("source_location_m",[0,1,1]),
    ("source_location_m",[float("nan"),1,1]),
    ("source_strength_m3_s",0),
    ("source_strength_m3_s",True),
    ("diffusivity_m2_s",float("inf")),
    ("iterations",2.5),
    ("write_interval",101),
])
def test_invalid_scalar_input_fails_closed(field,value):
    data=scalar_spec()
    data[field]=value
    with pytest.raises(ValueError):
        validate_scalar_spec(data)


def test_prepare_scalar_case_from_computed_flow_and_manifest(tmp_path):
    flow=synthetic_finished_flow(tmp_path)
    output=tmp_path/"scalar"
    manifest=prepare_scalar_case(flow,scalar_spec(),output)
    assert manifest["source_velocity_time"]=="100"
    assert manifest["validation_status"]=="unvalidated_airflow_scalar_setup_only"
    assert (output/"constant/polyMesh/points").read_text()=="synthetic points"
    assert (output/"0/U").read_bytes()==(flow/"100/U").read_bytes()
    assert len(manifest["files"])==12
    assert manifest["source_velocity_sha256"]==manifest["files"]["0/U"]
    assert manifest==json.loads((output/"manifest.json").read_text())
    with pytest.raises(FileExistsError):
        prepare_scalar_case(flow,scalar_spec(),output)


def test_flow_must_have_computed_nonzero_U(tmp_path):
    flow=synthetic_finished_flow(tmp_path)
    (flow/"100/U").unlink()
    (flow/"0").mkdir()
    (flow/"0/U").write_text("FoamFile { class volVectorField; }")
    with pytest.raises(ValueError,match="nonzero"):
        prepare_scalar_case(flow,scalar_spec(),tmp_path/"scalar")


def test_cannot_nest_scalar_output_inside_airflow(tmp_path):
    flow=synthetic_finished_flow(tmp_path)
    with pytest.raises(ValueError,match="nested"):
        prepare_scalar_case(flow,scalar_spec(),flow/"scalar")


def test_scalar_runner_detects_tampered_source_before_executable_discovery(tmp_path):
    flow=synthetic_finished_flow(tmp_path)
    root=tmp_path/"scalar"
    prepare_scalar_case(flow,scalar_spec(),root)
    (root/"0/T").write_text("modified")
    with pytest.raises(ValueError,match="mutated"):
        run_scalar_case(root)


def test_missing_executable_rejected_without_running(tmp_path,monkeypatch):
    flow=synthetic_finished_flow(tmp_path)
    root=tmp_path/"scalar"
    prepare_scalar_case(flow,scalar_spec(),root)
    monkeypatch.setattr("cleanroomx.cfd_scalar.shutil.which",lambda name:None)
    with pytest.raises(RuntimeError,match="not found"):
        run_scalar_case(root)


def test_runner_mock_preserves_log_and_source_hashes(tmp_path,monkeypatch):
    flow=synthetic_finished_flow(tmp_path)
    root=tmp_path/"scalar"
    manifest=prepare_scalar_case(flow,scalar_spec(),root)
    monkeypatch.setattr("cleanroomx.cfd_scalar.shutil.which",lambda name:"/fake/scalarTransportFoam")
    class Completed:
        returncode=0
    def mocked_run(command,**kw):
        assert command==["/fake/scalarTransportFoam"]
        kw["stdout"].write("Solving for T, Initial residual = 1e-8, Final residual = 1e-11, No Iterations 3\nEnd\n")
        return Completed()
    monkeypatch.setattr("cleanroomx.cfd_scalar.subprocess.run",mocked_run)
    report=run_scalar_case(root)
    assert report["status"]=="executed_requires_residual_and_field_validation"
    assert report["source_velocity_sha256"]==manifest["source_velocity_sha256"]
    assert (root/"scalarTransportFoam.log").exists()


def test_runner_can_incrementally_synchronize_scalar_solver_outputs(tmp_path,monkeypatch):
    flow=synthetic_finished_flow(tmp_path)
    root=tmp_path/"scalar"
    manifest=prepare_scalar_case(flow,scalar_spec(),root)
    monkeypatch.setattr("cleanroomx.cfd_scalar.shutil.which",lambda name:"/fake/scalarTransportFoam")
    class FakeSynchronizer:
        case_directory=root.resolve()
        def finish(self,*,solver_returncode,solver_log):
            assert solver_returncode==0
            assert solver_log.read_text(encoding="utf-8")=="End\n"
            return {"status":"results_synced","record_count":2,"scientific_validation":"BLOCKED"}
    def mocked_run(command,**kwargs):
        assert command==["/fake/scalarTransportFoam"]
        assert kwargs["cwd"]==root.resolve()
        kwargs["log_path"].write_text("End\n",encoding="utf-8")
        return 0
    monkeypatch.setattr(
        "cleanroomx.cfd_openfoam_runtime_sync.run_solver_with_sync",mocked_run
    )

    report=run_scalar_case(root,synchronizer=FakeSynchronizer())

    assert report["status"]=="executed_requires_residual_and_field_validation"
    assert report["source_velocity_sha256"]==manifest["source_velocity_sha256"]
    assert report["result_synchronization"]["record_count"]==2


def test_scalar_run_cli_exposes_live_result_synchronization():
    args=build_parser().parse_args([
        "scalar-run","./scalar_case","--sync-results","./scalar_results",
        "--field-map-file","examples/cfd_scalar_field_map.example.json",
        "--simulation-id","scalar-demo",
    ])
    assert args.sync_results=="./scalar_results"
    assert args.field_map_file=="examples/cfd_scalar_field_map.example.json"
    assert args.simulation_id=="scalar-demo"


def test_audit_positive_numerical_screen(tmp_path):
    log=tmp_path/"simpleFoam.log"
    entries=[]
    for i in range(5):
        for field in ("Ux","Uy","Uz","p"):
            entries.append(f"smoothSolver: Solving for {field}, Initial residual = 2e-7, Final residual = 1e-10, No Iterations 3")
        entries.append("time step continuity errors : sum local = 1e-9, global = -1e-10, cumulative = 1e-8")
    log.write_text("\n".join(entries)+"\nEnd\n")
    report=audit_openfoam_log(log,fields=("Ux","Uy","Uz","p"),max_initial_residual=1e-6,
                              max_final_residual=1e-8,max_global_continuity=1e-8,window=3)
    assert report["status"]=="numerically_screened"
    assert report["continuity_samples"]==5
    assert not report["violations"]


def test_audit_truncated_and_missing_field_fail_closed(tmp_path):
    path=tmp_path/"log"
    path.write_text("Solving for p, Initial residual = 1e-9, Final residual = 1e-10\n")
    result=audit_openfoam_log(path,fields=("p","Ux"),max_initial_residual=1e-6,
                               max_final_residual=1e-8)
    assert result["status"]=="incomplete_or_failed"
    assert any("Ux" in error for error in result["violations"])
    assert any("End" in error for error in result["violations"])


def test_audit_fatal_or_high_residual_rejected(tmp_path):
    path=tmp_path/"log"
    path.write_text("Solving for T, Initial residual = 0.1, Final residual = 0.0001\n"
                    "Solving for T, Initial residual = 0.1, Final residual = 0.0001\n"
                    "Solving for T, Initial residual = 0.1, Final residual = 0.0001\n"
                    "FOAM FATAL ERROR\nEnd\n")
    result=audit_openfoam_log(path,fields=["T"],max_initial_residual=1e-6,
                              max_final_residual=1e-8)
    assert result["status"]=="incomplete_or_failed"
    assert result["fatal_or_nonfinite_marker"]


@pytest.mark.parametrize("value",[-1,0,True,float("nan"),float("inf")])
def test_invalid_audit_threshold_rejected(tmp_path,value):
    path=tmp_path/"log";path.write_text("End\n")
    with pytest.raises(ValueError):
        audit_openfoam_log(path,fields=["T"],max_initial_residual=value,
                          max_final_residual=1e-5)


def test_audit_missing_continuity_when_required(tmp_path):
    path=tmp_path/"log"
    path.write_text(
        "Solving for T, Initial residual = 1e-9, Final residual = 1e-11\n"*3+"End\n"
    )
    result=audit_openfoam_log(path,fields=["T"],max_initial_residual=1e-6,
                             max_final_residual=1e-8,max_global_continuity=1e-7)
    assert result["status"]=="incomplete_or_failed"
    assert any("continuity" in msg for msg in result["violations"])


def test_log_symlinks_not_accepted(tmp_path):
    original=tmp_path/"orig.log";original.write_text("End")
    alias=tmp_path/"alias.log";alias.symlink_to(original)
    with pytest.raises(ValueError,match="symlink"):
        audit_openfoam_log(alias,fields=["T"],max_initial_residual=1e-4,
                          max_final_residual=1e-7)


def test_scalar_smoke_accepts_runtime_sync_import_status():
    module = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts" / "openfoam_v10_scalar_sync_smoke.py")
    )
    record = {
        "import_status": "PASS_DIAGNOSTIC_ONLY",
        "scientific_validation": "BLOCKED",
        "fields": {
            "T": {"dimensions": "[0 0 0 0 0 0 0]"},
            "U": {"units": "m/s"},
        },
        "native_vtk_parity": {"U": {"status": "PASS"}, "T": {"status": "PASS"}},
        "cleanroomx_analysis_import": {
            "field_data_names": ["normalized_tracer"],
            "has_temperature_field": False,
        },
    }

    assert module["_scalar_record_is_valid"](record)
    record["import_status"] = "imported"
    assert not module["_scalar_record_is_valid"](record)


def test_scalar_smoke_failure_evidence_keeps_solver_error_and_blocked_status(tmp_path):
    module = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts" / "openfoam_v10_scalar_sync_smoke.py")
    )
    summarize = module["_scalar_failure_diagnostics"]
    case_root = Path("/runner/temp/scalar")
    log_text = (
        "--> FOAM FATAL IO ERROR:\n"
        "wrong token type - expected word, found on line 10 punctuation token '['\n"
        "file: /runner/temp/scalar/constant/physicalProperties/DT at line 10.\n"
        "FOAM exiting\n"
    )
    report = summarize(
        {
            "status": "solver_failed",
            "exit_code": 1,
            "log_sha256": "a" * 64,
            "result_synchronization": {
                "status": "no_results_available",
                "errors": ["sync " + "x" * 800],
            },
        },
        log_text,
        case_root,
    )

    assert report["status"] == "execution_failure_diagnostic_only"
    assert report["failure_stage"] == "solver"
    assert report["solver_exit_code"] == 1
    assert report["result_synchronization_status"] == "no_results_available"
    assert report["result_synchronization_errors"] == ["sync " + "x" * 495]
    assert report["scientific_validation"] == "BLOCKED"
    assert any("FOAM FATAL IO ERROR" in line for line in report["solver_diagnostic_excerpt"])
    assert any("physicalProperties/DT" in line for line in report["solver_diagnostic_excerpt"])
    assert all("/runner/temp/scalar" not in line for line in report["solver_diagnostic_excerpt"])
    assert all(len(line) <= 500 for line in report["solver_diagnostic_excerpt"])
