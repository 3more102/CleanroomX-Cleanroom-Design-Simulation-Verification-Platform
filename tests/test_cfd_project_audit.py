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



def test_project_room_audit_rejects_log_swap_between_check_and_open(tmp_path, monkeypatch):
    """Synthetic race: a replaced log must not become accepted evidence."""
    from cleanroomx import cfd_audit

    root = _generated(tmp_path)
    _log_fixtures(root)
    victim = root / "room_process/checkMesh.log"
    replacement = root / "room_ante/checkMesh.log"
    try:
        probe = tmp_path / "symlink-probe"
        probe.symlink_to(replacement)
        probe.unlink()
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable")
    original_open = cfd_audit.os.open
    switched = False

    def swap_before_open(path, flags, *args, **kwargs):
        nonlocal switched
        if str(path) == str(victim) and not switched:
            switched = True
            victim.rename(root / "room_process/checkMesh.original")
            victim.symlink_to(replacement)
        return original_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(cfd_audit.os, "open", swap_before_open)
        report = _audit(root)
    assert switched
    assert report["status"] == "incomplete_or_failed"
    assert report["cases"]["process"]["status"] == "incomplete_or_failed"
    assert any("checkMesh" in reason for reason in report["cases"]["process"]["violations"])


def test_solver_log_reader_rejects_oversized_and_nonregular_files(tmp_path):
    """Synthetic fixtures cannot bypass bounded regular-file validation."""
    import os
    from cleanroomx.cfd_audit import MAX_LOG_BYTES, read_bounded_regular_log

    huge = tmp_path / "sparse.log"
    with huge.open("wb") as stream:
        stream.truncate(MAX_LOG_BYTES + 1)
    with pytest.raises(ValueError, match="32 MiB"):
        read_bounded_regular_log(huge)
    if not hasattr(os, "mkfifo"):
        pytest.skip("Named pipes are unavailable")
    pipe = tmp_path / "solver.pipe"
    os.mkfifo(pipe)
    with pytest.raises(ValueError, match="regular file"):
        read_bounded_regular_log(pipe)


def test_project_room_audit_preserves_exact_log_hashes(tmp_path):
    """Audit hashes must identify precisely the bytes used by the parser."""
    import hashlib
    from cleanroomx.cfd_audit import read_bounded_regular_log

    root = _generated(tmp_path)
    _log_fixtures(root)
    report = _audit(root)
    for room in ("process", "preparation", "ante"):
        path = root / f"room_{room}" / "checkMesh.log"
        expected = hashlib.sha256(read_bounded_regular_log(path)).hexdigest()
        assert report["cases"][room]["mesh_logs"]["checkMesh"]["sha256"] == expected



def test_project_room_audit_requires_every_generated_solver_input_receipt(tmp_path):
    """Synthetic manifest omission cannot hide missing critical case inputs."""
    root = _generated(tmp_path)
    _log_fixtures(root)
    manifest = root / "manifest.json"
    source = json.loads(manifest.read_text(encoding="utf-8"))
    key = "room_process/system/controlDict"
    assert key in source["files"]
    source["files"].pop(key)
    manifest.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing case input receipt: " + key):
        _audit(root)


def test_project_room_audit_rejects_duplicate_manifest_keys(tmp_path):
    """Duplicate JSON keys are ambiguous provenance, even with valid logs."""
    root = _generated(tmp_path)
    _log_fixtures(root)
    manifest = root / "manifest.json"
    original = manifest.read_text(encoding="utf-8")
    assert '"warning":' in original
    tampered = original.replace(
        '"warning":', '"warning": "duplicate synthetic test",\n  "warning":', 1
    )
    manifest.write_text(tampered, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        _audit(root)


def test_project_room_audit_hashes_the_same_manifest_snapshot(tmp_path):
    """Published manifest fingerprint covers the bytes that were parsed."""
    import hashlib

    root = _generated(tmp_path)
    _log_fixtures(root)
    manifest = root / "manifest.json"
    report = _audit(root)
    assert report["input_manifest_sha256"] == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()



def test_openfoam_logs_require_terminal_end_after_all_solver_output(tmp_path):
    """End in the middle cannot validate appended/incomplete solver output."""
    root = _generated(tmp_path)
    _log_fixtures(root)
    mesh = root / "room_process/checkMesh.log"
    mesh.write_text(mesh.read_text() + "Mesh might be incomplete\n")
    report = _audit(root)
    assert report["status"] == "incomplete_or_failed"
    assert "checkMesh: missing terminal End marker" in report[
        "cases"]["process"]["violations"]
    assert report["cases"]["process"]["mesh_logs"]["checkMesh"][
        "has_end_marker"] is False

    mesh.write_text("Mesh OK.\nEnd\n")
    log = root / "room_ante/simpleFoam.log"
    log.write_text(log.read_text() + (
        "Solving for Ux, Initial residual = 1e-12, "
        "Final residual = 1e-12\n"
    ))
    report = _audit(root)
    assert report["status"] == "incomplete_or_failed"
    assert "solver log has no terminal End marker" in report[
        "cases"]["ante"]["violations"]


def test_openfoam_recent_residual_samples_preserve_source_order(tmp_path):
    """Log-order drift evidence must not pretend to be SIMPLE iterations."""
    root = _generated(tmp_path)
    _log_fixtures(root)
    source = root / "room_process/simpleFoam.log"
    levels = (1e-8, 2e-8, 3e-8, 4e-8)
    rows = []
    for value in levels:
        rows.append(
            f"GAMG: Solving for p, Initial residual = {value}, "
            "Final residual = 1e-9, No Iterations 1\n"
        )
        rows.append(
            "smoothSolver: Solving for Ux, Initial residual = 1e-8, "
            "Final residual = 1e-9, No Iterations 1\n"
        )
        rows.append(
            "time step continuity errors : sum local = 1e-9, "
            "global = -1e-9, cumulative = -2e-9\n"
        )
    source.write_text("".join(rows) + "End\n")
    report = _audit(root)
    assert report["status"] == "numerically_screened_requires_engineering_review"
    residuals = report["cases"]["process"]["solver_residuals"]
    recent = residuals["fields"]["p"]
    assert recent["recent_initial_residual_samples"] == list(levels[-3:])
    assert recent["recent_final_residual_samples"] == [1e-9] * 3
    assert recent["worst_recent_initial_residual"] == 4e-8
    assert residuals["residual_sample_axis"] == (
        "linear_solver_log_order_not_simple_iterations"
    )
