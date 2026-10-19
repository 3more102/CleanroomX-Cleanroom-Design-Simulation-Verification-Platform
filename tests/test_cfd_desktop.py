from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

from cleanroomx import cfd_desktop
from cleanroomx.cfd_desktop import (
    prepare_room_study, read_solver_progress, room_study_context_matches, room_study_input,
)
from cleanroomx.cfd_openfoam import verify_openfoam_case_bundle
from cleanroomx.cfd_runtime import runtime_command, runtime_report, wsl_stop_command
from cleanroomx.gui import bundled_demo_project_path


def demo():
    return json.loads(bundled_demo_project_path().read_text(encoding="utf-8"))


def test_room_study_uses_current_geometry_and_declared_flow_without_mutating_project(tmp_path):
    project = demo()
    project["project"]["metadata"]["spatial_layout"]["rooms"][0]["length_m"] = 8
    before = copy.deepcopy(project)
    source = room_study_input(project, "process")
    assert source["room_m"] == [8, 5, 3]
    assert source["supply_airflow_m3_h"] == 2700
    prepared = prepare_room_study(project, "process", tmp_path / "run", supply_airflow_m3_h=1800,
                                  mesh_cells=[6, 6, 6], max_iterations=80)
    spec = json.loads(Path(prepared["specification"]).read_text())
    assert spec["room_m"] == [8, 5, 3]
    assert spec["supply_flow_m3_s"] == .5
    assert prepared["provenance"]["supply_origin"] == "user_override"
    assert prepared["provenance"]["input_supply_ach_per_h"] == 15
    assert prepared["provenance"]["scientific_validation"] == "BLOCKED"
    assert verify_openfoam_case_bundle(prepared["cases"])["files_checked"] == 24
    assert project == before
    with pytest.raises(FileExistsError):
        prepare_room_study(project, "process", tmp_path / "run", supply_airflow_m3_h=1800,
                           mesh_cells=[6, 6, 6], max_iterations=80)



def test_room_preparation_failure_does_not_publish_partial_run(tmp_path, monkeypatch):
    real_write = Path.write_text

    def fail_project_snapshot(path, *args, **kwargs):
        if path.name == "project-input.json":
            raise OSError("simulated storage failure")
        return real_write(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_project_snapshot)
    with pytest.raises(OSError, match="simulated storage failure"):
        prepare_room_study(
            demo(), "process", tmp_path / "new-run",
            supply_airflow_m3_h=2700, mesh_cells=[6, 6, 6], max_iterations=40,
        )

    assert not (tmp_path / "new-run").exists()
    assert list(tmp_path.glob(".cleanroomx-room-study-*")) == []


def test_room_preparation_preserves_run_directory_created_during_staging(tmp_path, monkeypatch):
    target = tmp_path / "new-run"
    original_export = cfd_desktop.export_openfoam_cases

    def conflicting_export(spec, staging_cases):
        manifest = original_export(spec, staging_cases)
        target.mkdir()
        (target / "external.txt").write_text("someone else's run", encoding="utf-8")
        return manifest

    monkeypatch.setattr(cfd_desktop, "export_openfoam_cases", conflicting_export)
    with pytest.raises(FileExistsError, match="appeared while preparing"):
        prepare_room_study(
            demo(), "process", target,
            supply_airflow_m3_h=2700, mesh_cells=[6, 6, 6], max_iterations=40,
        )

    assert (target / "external.txt").read_text(encoding="utf-8") == "someone else's run"
    assert not (target / "cases").exists()
    assert list(tmp_path.glob(".cleanroomx-room-study-*")) == []


def test_missing_or_conflicting_supply_is_never_replaced_by_a_demo_value():
    project = demo()
    project["analyses"] = []
    assert room_study_input(project, "process")["supply_airflow_m3_h"] is None
    project = demo()
    other = copy.deepcopy(project["analyses"][0])
    other["id"] = "other"
    other["input"]["rooms"][0]["supply_airflow_m3_h"] = 3600
    project["analyses"].append(other)
    source = room_study_input(project, "process")
    assert source["supply_status"] == "conflicting"
    assert source["supply_airflow_m3_h"] is None




def test_room_review_guard_rejects_changed_geometry_or_verification_flow():
    project = demo()
    reviewed = room_study_input(project, "process")
    geometry_changed = copy.deepcopy(project)
    geometry_changed["project"]["metadata"]["spatial_layout"]["rooms"][0]["width_m"] = 9
    assert not room_study_context_matches(
        reviewed, room_study_input(geometry_changed, "process"),
    )

    airflow_changed = copy.deepcopy(project)
    airflow_changed["analyses"][0]["input"]["rooms"][0]["supply_airflow_m3_h"] = 3000
    assert not room_study_context_matches(
        reviewed, room_study_input(airflow_changed, "process"),
    )


def test_room_review_guard_rejects_alias_change_even_with_equal_numeric_flow():
    project = demo()
    reviewed = room_study_input(project, "process")
    renamed = copy.deepcopy(project)
    renamed["project"]["metadata"]["spatial_layout"]["rooms"][0]["analysis_room_name"] = "Other room"
    assert not room_study_context_matches(
        reviewed, room_study_input(renamed, "process"),
    )


def test_room_review_guard_ignores_unrelated_project_metadata():
    project = demo()
    reviewed = room_study_input(project, "process")
    changed = copy.deepcopy(project)
    changed["project"]["metadata"]["review_annotation"] = "Updated project notes"
    current = room_study_input(changed, "process")
    assert reviewed["project_sha256"] != current["project_sha256"]
    assert room_study_context_matches(reviewed, current)


def test_duplicate_engineering_room_names_require_explicit_airflow(tmp_path):
    project = demo()
    layout = project["project"]["metadata"]["spatial_layout"]
    duplicate = copy.deepcopy(layout["rooms"][0])
    duplicate["id"] = "process-other"
    duplicate["x_m"] = 30
    layout["rooms"].append(duplicate)

    original = room_study_input(project, "process")
    other = room_study_input(project, "process-other")
    assert original["supply_airflow_m3_h"] is None
    assert other["supply_airflow_m3_h"] is None
    assert original["supply_status"] == other["supply_status"] == "ambiguous_room_identity"
    assert original["supply_sources"]
    prepared = prepare_room_study(
        project, "process", tmp_path / "run",
        supply_airflow_m3_h=1800, mesh_cells=[6, 6, 6], max_iterations=50,
    )
    assert prepared["provenance"]["supply_origin"] == "user_override"
    assert prepared["provenance"]["supply_status"] == "ambiguous_room_identity"


def test_distinct_analysis_room_aliases_are_not_falsely_ambiguous():
    project = demo()
    layout = project["project"]["metadata"]["spatial_layout"]
    another = copy.deepcopy(layout["rooms"][0])
    another["id"] = "process-other"
    another["x_m"] = 30
    another["analysis_room_name"] = "A different engineering room"
    layout["rooms"].append(another)
    current = room_study_input(project, "process")
    assert current["supply_status"] == "declared"
    assert current["supply_airflow_m3_h"] == 2700


@pytest.mark.parametrize("flow,mesh,iterations", [(float("nan"), [6, 6, 6], 10),
                                                   (100, [80, 80, 80], 10),
                                                   (100, [6, 6, 6], 0)])
def test_invalid_room_settings_do_not_publish_a_case(tmp_path, flow, mesh, iterations):
    with pytest.raises(ValueError):
        prepare_room_study(demo(), "process", tmp_path / "bad", supply_airflow_m3_h=flow,
                           mesh_cells=mesh, max_iterations=iterations)
    assert not (tmp_path / "bad").exists()


def test_progress_reports_written_solver_iterations_and_residuals(tmp_path):
    case = tmp_path / "configuration_1"
    case.mkdir()
    (case / "blockMesh.log").write_text("real mesh log\nEnd\n")
    (case / "simpleFoam.log").write_text("sigFpe: Enabling floating point exception trapping (FOAM_SIGFPE).\nTime = 42\nsmoothSolver: Solving for Uy, Initial residual = 0.0012, Final residual = 7e-08, No Iterations 2\n")
    progress = read_solver_progress(tmp_path)
    assert progress["completed_stages"] == 1
    assert progress["latest"]["iteration"] == "42"
    assert progress["latest"]["residual"] == ("Uy", "0.0012", "7e-08")
    assert not progress["latest"]["ended"]
    assert not progress["latest"]["fatal_error"]
    with (case / "simpleFoam.log").open("a") as stream:
        stream.write("FOAM FATAL ERROR\n")
    assert read_solver_progress(tmp_path)["latest"]["fatal_error"]




def test_full_log_audit_detects_fatal_message_outside_live_tail(tmp_path):
    case = tmp_path / "configuration_1"
    case.mkdir()
    (case / "simpleFoam.log").write_text(
        "FOAM FATAL ERROR\n"
        + "Time = 1\n"
        + ("normal solver output " * 3000) + "\nEnd\n",
        encoding="utf-8",
    )
    live = read_solver_progress(tmp_path)
    audited = read_solver_progress(tmp_path, full_scan=True)
    assert live["completed_stages"] == 1  # Tail-only UI is not authoritative.
    assert audited["completed_stages"] == 0
    assert audited["issues"][0]["case"] == 1
    assert audited["issues"][0]["program"] == "simpleFoam"


def test_full_log_audit_catches_nonfinite_early_residual(tmp_path):
    case = tmp_path / "configuration_1"
    case.mkdir()
    (case / "simpleFoam.log").write_text(
        "Time = 1\n"
        + "smoothSolver: Solving for Ux, Initial residual = nan, Final residual = 1e-2, No Iterations 2\n"
        + ("normal solver output " * 3000) + "\nEnd\n",
        encoding="utf-8",
    )
    audited = read_solver_progress(tmp_path, full_scan=True)
    assert audited["completed_stages"] == 0
    assert "non-finite" in audited["issues"][0]["reason"]


def test_full_log_audit_requires_complete_end_line(tmp_path):
    case = tmp_path / "configuration_1"
    case.mkdir()
    (case / "blockMesh.log").write_text("mesh generated\nEnd", encoding="utf-8")
    audited = read_solver_progress(tmp_path, full_scan=True)
    assert audited["completed_stages"] == 0
    assert audited["latest"]["ended"] is False


def test_nonfinite_residual_is_not_counted_as_completed_even_after_end(tmp_path):
    case = tmp_path / "configuration_1"
    case.mkdir()
    (case / "simpleFoam.log").write_text(
        "Time = 6\n"
        "smoothSolver: Solving for Ux, Initial residual = nan, Final residual = 0.1, No Iterations 2\n"
        "End\n", encoding="utf-8",
    )
    progress = read_solver_progress(tmp_path)
    assert progress["completed_stages"] == 0
    assert progress["latest"]["fatal_error"]
    assert progress["latest"]["ended"] is False
    assert len(progress["issues"]) == 1
    assert "Invalid/non-finite" in progress["issues"][0]["reason"]


def test_earlier_solver_failure_remains_visible_when_later_case_logs_exist(tmp_path):
    first = tmp_path / "configuration_1"
    second = tmp_path / "configuration_2"
    first.mkdir()
    second.mkdir()
    (first / "simpleFoam.log").write_text("FOAM FATAL ERROR\nEnd\n", encoding="utf-8")
    (second / "blockMesh.log").write_text(
        "sigFpe: Enabling floating point exception trapping (FOAM_SIGFPE).\nEnd\n",
        encoding="utf-8",
    )
    progress = read_solver_progress(tmp_path)
    assert progress["latest"]["case"] == 2
    assert progress["latest"]["fatal_error"] is False
    assert progress["completed_stages"] == 1
    assert len(progress["issues"]) == 1
    assert progress["issues"][0]["case"] == 1
    assert progress["issues"][0]["program"] == "simpleFoam"


def test_partial_residual_line_does_not_trigger_false_numerical_alarm(tmp_path):
    case = tmp_path / "configuration_1"
    case.mkdir()
    (case / "simpleFoam.log").write_text(
        "Time = 4\n"
        "smoothSolver: Solving for Ux, Initial residual = 0.001, Final residual = na",
        encoding="utf-8",
    )
    progress = read_solver_progress(tmp_path)
    assert progress["issues"] == []
    assert progress["latest"]["iteration"] == "4"


def test_native_runtime_wrapper_keeps_shell_metacharacters_in_arguments(tmp_path):
    if os.name == "nt":
        command = [sys.executable, "-c", "pass"]
        assert runtime_command(command, mode="native", bashrc="") == command
        return
    bashrc = tmp_path / "runtime with ' quotes ; $(ignored)"
    bashrc.write_text("export WM_PROJECT=OpenFOAM\nexport WM_PROJECT_VERSION=10\n")
    import subprocess
    command = [sys.executable, "-c", "import sys;print(sys.argv[1])", "case ' ; $(not-a-command)"]
    wrapped = runtime_command(command, mode="native", bashrc=str(bashrc))
    result = subprocess.run(wrapped, capture_output=True, text=True, check=True)
    assert result.stdout.strip() == command[-1]


def test_wsl_runtime_uses_host_package_and_translates_only_path_arguments(monkeypatch, tmp_path):
    from cleanroomx import cfd_runtime
    monkeypatch.setattr(cfd_runtime.shutil, "which", lambda name: "wsl.exe")
    case, results = str(tmp_path / "case folder"), str(tmp_path / "result folder")
    command = ["python.exe", "-m", "cleanroomx.cfd_pipeline_cli", "run", case,
               "--sync-results", results, "--simulation-id", "run-01"]
    wrapped = runtime_command(command, mode="wsl", bashrc="/opt/openfoam10/etc/bashrc",
                              distribution="Ubuntu ' test", path_mapper=lambda path: "mapped:" + path,
                              wsl_python="/home/operator/solver env/bin/python")
    assert wrapped[:3] == ["wsl.exe", "--distribution", "Ubuntu ' test"]
    assert wrapped[-8:] == ["-m", "cleanroomx.cfd_pipeline_cli", "run", "mapped:" + case,
                           "--sync-results", "mapped:" + results, "--simulation-id", "run-01"]
    assert "/home/operator/solver env/bin/python" in wrapped
    assert "PYTHONPATH" in wrapped[wrapped.index("-c") + 1]
    stopped = wsl_stop_command(wrapped, 1234)
    assert stopped[:3] == wrapped[:3]
    assert stopped[-4:] == ["kill", "-TERM", "--", "-1234"]
    with pytest.raises(ValueError):
        wsl_stop_command(wrapped, -1)


def test_runtime_check_reports_missing_runtime_instead_of_simulated_success(monkeypatch):
    from cleanroomx import cfd_runtime
    monkeypatch.setattr(cfd_runtime.shutil, "which", lambda name: None)
    monkeypatch.delenv("WM_PROJECT", raising=False)
    report = runtime_report()
    assert report["status"] == "unavailable"
    assert any("blockMesh" in issue for issue in report["issues"])
