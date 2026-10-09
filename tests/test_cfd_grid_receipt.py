"""Grid-run receipts are software evidence, never physical CFD validation."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cleanroomx.cfd_grid_family import SCHEMA, generate_grid_family
from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence
from cleanroomx.cfd_grid_runner import run_grid_family


@pytest.fixture
def grid_family(tmp_path):
    spec = {
        "schema_version": SCHEMA,
        "base_case": {
            "schema_version": "cleanroomx.openfoam.v1",
            "name": "SYNTHETIC receipt checker fixture",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    path = tmp_path / "grid_family"
    generate_grid_family(spec, path)
    return path


def synthetic_processes(monkeypatch, *, failure=None):
    import cleanroomx.cfd_grid_runner as runner

    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fake/" + name)

    def run(cmd, **kwargs):
        name = Path(cmd[0]).name
        if name == "foamVersion":
            return SimpleNamespace(returncode=0, stdout="10\n", stderr="")
        case = kwargs["cwd"].relative_to(kwargs["cwd"].parents[1]).as_posix()
        kwargs["stdout"].write(f"SYNTHETIC process fixture {case} {name}\n")
        return SimpleNamespace(
            returncode=1 if (case, name) == failure else 0
        )

    monkeypatch.setattr(runner.subprocess, "run", run)


def test_verify_27_receipted_logs_without_claiming_validation(grid_family, monkeypatch):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == (
        "execution_logs_integrity_verified_requires_scientific_review"
    )
    assert result["cases_checked"] == 9
    assert result["logs_checked"] == 27
    assert result["findings"] == []
    assert result["engineering_review"] == "BLOCKED"
    assert result["physical_validation"] == "not_performed"


def test_modified_solver_log_fails_integrity_screen(grid_family, monkeypatch):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    log = grid_family / "configuration_2/medium/checkMesh.log"
    log.write_bytes(log.read_bytes() + b"tampered")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "log_digest_mismatch:configuration_2/medium:checkMesh" in result["findings"]


def test_modified_source_file_fails_integrity_screen(grid_family, monkeypatch):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    original = grid_family / "configuration_1/fine/0/U"
    original.write_text(original.read_text() + "\n// changed after execution\n")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert any("source_manifest_or_inputs_invalid" in finding for finding in result["findings"])


def test_modified_manifest_fails_receipt_binding(grid_family, monkeypatch):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    manifest = grid_family / "manifest.json"
    manifest.write_text(manifest.read_text() + "\n")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "source_manifest_digest_mismatch" in result["findings"]


def test_false_validation_state_is_never_accepted(grid_family, monkeypatch):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    path = grid_family / "grid_run_evidence.json"
    data = json.loads(path.read_text())
    data["engineering_review"] = "PASSED"
    data["physical_validation"] = "certified"
    path.write_text(json.dumps(data))
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "receipt_review_state_must_be_blocked" in result["findings"]
    assert "receipt_physical_validation_must_be_unperformed" in result["findings"]


def test_failed_stage_integrity_is_not_solver_success(grid_family, monkeypatch):
    synthetic_processes(
        monkeypatch, failure=("configuration_1/coarse", "checkMesh")
    )
    run_grid_family(grid_family, timeout_seconds=60)
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "incomplete_execution_logs_integrity_verified"
    assert result["logs_checked"] == 26
    assert result["findings"] == []
    assert result["engineering_review"] == "BLOCKED"


def test_wrong_log_path_is_rejected_without_following_it(grid_family, monkeypatch, tmp_path):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    path = grid_family / "grid_run_evidence.json"
    receipt = json.loads(path.read_text())
    stage = receipt["cases"]["configuration_1/coarse"]["stages"][0]
    stage["log"] = str(tmp_path / "unrelated.txt")
    path.write_text(json.dumps(receipt))
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert any("invalid_stage_record:configuration_1/coarse:0" == x
               for x in result["findings"])


def test_symlinked_solver_log_is_rejected(grid_family, monkeypatch, tmp_path):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    log = grid_family / "configuration_2/coarse/blockMesh.log"
    original_bytes = log.read_bytes()
    other = tmp_path / "copied.log"
    other.write_bytes(original_bytes)
    log.unlink()
    try:
        log.symlink_to(other)
    except (NotImplementedError, OSError):
        pytest.skip("Symlinks unavailable")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "invalid_log_reference:configuration_2/coarse:blockMesh" in result["findings"]
