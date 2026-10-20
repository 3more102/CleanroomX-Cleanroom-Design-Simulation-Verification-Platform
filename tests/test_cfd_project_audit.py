"""Synthetic log fixtures: numerical screening, never physical CFD evidence."""
from __future__ import annotations

import json

import pytest

from cleanroomx.cfd_pipeline_cli import build_parser
from cleanroomx.cfd_project_audit import audit_project_room_cases
from cleanroomx.cfd_project_rooms import generate_project_room_cases
from cleanroomx.gui import bundled_demo_project_path


def _generated(tmp_path):
    root = tmp_path / "cases"
    generate_project_room_cases(
        bundled_demo_project_path(), root,
        kinematic_viscosity_m2_s=1.5e-5,
    )
    return root


def _log_fixtures(root):
    residual = (
        "smoothSolver: Solving for Ux, Initial residual = 1e-8, "
        "Final residual = 1e-9, No Iterations 1\n"
        "GAMG: Solving for p, Initial residual = 1e-8, "
        "Final residual = 1e-9, No Iterations 1\n"
        "time step continuity errors : sum local = 1e-9, "
        "global = -1e-9, cumulative = -2e-9\n"
    )
    for room in ("process", "preparation", "ante"):
        path = root / f"room_{room}"
        (path / "blockMesh.log").write_text("Mesh generated\nEnd\n")
        (path / "checkMesh.log").write_text("Mesh OK.\nEnd\n")
        (path / "simpleFoam.log").write_text(residual * 3 + "End\n")


def _audit(root):
    return audit_project_room_cases(
        root, fields=("p", "Ux"),
        max_initial_residual=1e-5,
        max_final_residual=1e-6,
        max_global_continuity=1e-5, window=3,
    )


def test_project_room_audit_fail_closed_without_solver_logs(tmp_path):
    root = _generated(tmp_path)
    report = _audit(root)
    assert report["status"] == "incomplete_or_failed"
    assert report["case_count"] == 3
    assert all(
        record["status"] == "incomplete_or_failed"
        for record in report["cases"].values()
    )
    assert report["input_manifest_sha256"]


def test_project_room_audit_requires_checked_mesh_and_explicit_residuals(tmp_path):
    root = _generated(tmp_path)
    _log_fixtures(root)
    report = _audit(root)
    assert report["status"] == "numerically_screened_requires_engineering_review"
    assert set(report["cases"]) == {"process", "preparation", "ante"}
    assert all(
        item["solver_residuals"]["fields"]["p"]["sample_count"] == 3
        and item["mesh_logs"]["checkMesh"]["mesh_ok_marker"]
        for item in report["cases"].values()
    )
    assert "No coupled multizone CFD" in report["limitations"][0]
    # A "Mesh OK" marker must be sourced from an actual log file, not assumed.
    (root / "room_ante/checkMesh.log").write_text("Skipped mesh check\nEnd\n")
    bad = _audit(root)
    assert bad["status"] == "incomplete_or_failed"
    assert "checkMesh: no Mesh OK marker" in bad["cases"]["ante"]["violations"]


def test_project_room_audit_detects_fatal_solver_log_and_changed_inputs(tmp_path):
    root = _generated(tmp_path)
    _log_fixtures(root)
    path = root / "room_process/simpleFoam.log"
    path.write_text(path.read_text() + "FOAM FATAL ERROR\n")
    status = _audit(root)
    assert status["status"] == "incomplete_or_failed"
    assert status["cases"]["process"]["solver_residuals"]["fatal_or_nonfinite_marker"]
    source = root / "room_process/0/U"
    source.write_text(source.read_text() + "\n//changed")
    with pytest.raises(ValueError, match="Generated solver input changed"):
        _audit(root)


def test_project_room_audit_rejects_symlink_log_and_unsafe_manifest(tmp_path):
    root = _generated(tmp_path)
    _log_fixtures(root)
    target = root / "room_process/simpleFoam.log"
    target.unlink()
    try:
        target.symlink_to(root / "room_ante/simpleFoam.log")
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable in test environment")
    report = _audit(root)
    assert report["status"] == "incomplete_or_failed"
    assert "Log must be a regular file" in str(report["cases"]["process"]["violations"])
    manifest = root / "manifest.json"
    payload = json.loads(manifest.read_text())
    payload["files"]["../unsafe"] = "0" * 64
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Unsafe manifest path"):
        _audit(root)


def test_project_room_audit_cli_requires_user_thresholds():
    parser = build_parser()
    args = parser.parse_args([
        "project-rooms-audit", "somecase",
        "--fields", "p", "Ux",
        "--max-initial-residual", "0.00001",
        "--max-final-residual", "0.000001",
    ])
    assert args.command == "project-rooms-audit"
    assert args.fields == ["p", "Ux"]
    assert args.max_initial_residual == pytest.approx(1e-5)
    with pytest.raises(SystemExit):
        parser.parse_args(["project-rooms-audit", "somecase"])
