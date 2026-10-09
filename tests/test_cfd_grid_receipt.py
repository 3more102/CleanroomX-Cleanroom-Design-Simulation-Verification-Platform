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

def test_post_run_symlinked_input_is_rejected_even_if_sha_matches(grid_family, monkeypatch, tmp_path):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    original = grid_family / 'configuration_1/fine/0/U'
    copy = tmp_path / 'same_bytes.txt'
    copy.write_bytes(original.read_bytes())
    original.unlink()
    try:
        original.symlink_to(copy)
    except (OSError, NotImplementedError):
        pytest.skip('Symlinks unavailable')
    result = verify_grid_run_evidence(grid_family)
    assert result['status'] == 'evidence_integrity_failed'
    assert 'source_file_is_symlink:configuration_1/fine/0/U' in result['findings']


def test_malformed_failure_stage_fails_closed_without_crash(grid_family, monkeypatch):
    synthetic_processes(monkeypatch, failure=('configuration_1/coarse', 'checkMesh'))
    run_grid_family(grid_family, timeout_seconds=60)
    receipt_path = grid_family / 'grid_run_evidence.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['cases']['configuration_1/coarse']['stages'][-1] = None
    receipt_path.write_text(json.dumps(receipt))
    result = verify_grid_run_evidence(grid_family)
    assert result['status'] == 'evidence_integrity_failed'
    assert 'invalid_stage_record:configuration_1/coarse:1' in result['findings']


def test_cli_grid_verify_has_distinct_success_and_tamper_exit_codes(
    grid_family, monkeypatch, capsys
):
    import sys
    from cleanroomx.cfd_pipeline_cli import main
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    monkeypatch.setattr(sys, 'argv', ['cleanroomx-cfd-pipeline', 'grid-verify', str(grid_family)])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['engineering_review'] == 'BLOCKED'
    target = grid_family / 'configuration_3/fine/simpleFoam.log'
    target.write_bytes(target.read_bytes() + b'CHANGED')
    assert main() == 3
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'evidence_integrity_failed'


def test_symlinked_configuration_parent_fails_post_run_integrity(
    grid_family, monkeypatch
):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    original = grid_family / "configuration_2"
    backup = grid_family / "configuration_2-original"
    original.rename(backup)
    try:
        original.symlink_to(backup, target_is_directory=True)
    except (OSError, NotImplementedError):
        backup.rename(original)
        pytest.skip("Directory symlinks unavailable")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "source_configuration_is_symlink:configuration_2" in result["findings"]
    # All source and log bytes are unchanged, so hashes alone cannot catch it.
    assert result["logs_checked"] == 27


def test_symlinked_manifest_fails_post_run_integrity(
    grid_family, monkeypatch
):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    original = grid_family / "manifest.json"
    backup = grid_family / "manifest.original.json"
    original.rename(backup)
    try:
        original.symlink_to(backup.name)
    except (OSError, NotImplementedError):
        backup.rename(original)
        pytest.skip("Symlinks unavailable")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "source_manifest_is_symlink" in result["findings"]


@pytest.mark.parametrize("field,value", [
    ("foam_version", "11"),
    ("foam_version", 10),
    ("executables", {}),
    ("source_manifest_sha256", "0" * 64),
])
def test_forged_provenance_fails_closed(grid_family, monkeypatch, field, value):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    receipt_path = grid_family / "grid_run_evidence.json"
    receipt = json.loads(receipt_path.read_text())
    receipt[field] = value
    receipt_path.write_text(json.dumps(receipt))
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert result["engineering_review"] == "BLOCKED"


def test_duplicate_receipt_json_keys_fail_closed(grid_family, monkeypatch):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    receipt_path = grid_family / "grid_run_evidence.json"
    original = receipt_path.read_text()
    receipt_path.write_text('{"schema_version":"forged",' + original.lstrip()[1:])
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert any("unreadable_or_invalid_receipt" in finding for finding in result["findings"])


@pytest.mark.parametrize("tamper", ["missing", "file", "nonempty", "symlink"])
def test_execution_reservation_custody_fail_closed(
    grid_family, monkeypatch, tmp_path, tamper
):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    reservation = grid_family / ".grid_run_reserved"
    assert verify_grid_run_evidence(grid_family)["findings"] == []
    if tamper == "missing":
        reservation.rmdir()
    elif tamper == "file":
        reservation.rmdir()
        reservation.write_text("replaced marker", encoding="utf-8")
    elif tamper == "nonempty":
        (reservation / "unexplained").write_text("tamper", encoding="utf-8")
    elif tamper == "symlink":
        reservation.rmdir()
        try:
            reservation.symlink_to(tmp_path, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Directory symlinks unavailable")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    expected = (
        "execution_reservation_not_empty"
        if tamper == "nonempty"
        else "missing_or_unsafe_execution_reservation"
    )
    assert expected in result["findings"]
    assert result["engineering_review"] == "BLOCKED"
    assert result["physical_validation"] == "not_performed"


def test_replayed_solver_log_with_rewritten_receipt_digest_is_rejected(
    grid_family, monkeypatch
):
    # Even a mutually consistent forged log + receipt is not independent
    # grid evidence when simpleFoam outputs match byte-for-byte.
    import hashlib

    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    first = grid_family / "configuration_1/coarse/simpleFoam.log"
    replayed = grid_family / "configuration_1/fine/simpleFoam.log"
    replayed.write_bytes(first.read_bytes())
    path = grid_family / "grid_run_evidence.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(replayed.read_bytes()).hexdigest()
    receipt["cases"]["configuration_1/fine"]["stages"][2]["log_sha256"] = digest
    path.write_text(json.dumps(receipt), encoding="utf-8")

    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert result["logs_checked"] == 27
    assert (
        "replayed_solver_log_across_grids:"
        "configuration_1/fine:configuration_1/coarse"
    ) in result["findings"]
    assert result["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("staging_kind", ["file", "directory", "symlink"])
def test_uncommitted_receipt_staging_blocks_integrity_verification(
    grid_family, monkeypatch, tmp_path, staging_kind
):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    staging = grid_family / ".grid_run_evidence.json.tmp"
    if staging_kind == "file":
        staging.write_text("SYNTHETIC partial JSON write", encoding="utf-8")
    elif staging_kind == "directory":
        staging.mkdir()
    else:
        try:
            staging.symlink_to(tmp_path / "missing.json")
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks unavailable")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "uncommitted_receipt_staging_present" in result["findings"]
    assert result["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("field,value", [
    ("certified", True),
    ("warning", "ISO certification accepted"),
])
def test_forged_receipt_claims_fail_closed(grid_family, monkeypatch, field, value):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    path = grid_family / "grid_run_evidence.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt[field] = value
    path.write_text(json.dumps(receipt), encoding="utf-8")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    expected = ("invalid_receipt_warning" if field == "warning"
                else "unexpected_receipt_fields")
    assert expected in result["findings"]
    assert result["engineering_review"] == "BLOCKED"


def test_unreceipted_last_stage_log_is_not_integrity_verified(
    grid_family, monkeypatch
):
    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    receipt_path = grid_family / "grid_run_evidence.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    # A malicious or damaged receipt claims the last stage never began
    # and consistently downgrades both statuses to an incomplete attempt.
    case = receipt["cases"]["configuration_2/fine"]
    case["stages"].pop()
    case["status"] = "running"
    receipt["status"] = "incomplete"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "unreceipted_stage_log:configuration_2/fine:simpleFoam" in result["findings"]
    assert result["engineering_review"] == "BLOCKED"


def test_interruption_between_log_creation_and_receipt_is_flagged(
    grid_family, monkeypatch
):
    import cleanroomx.cfd_grid_runner as runner

    synthetic_processes(monkeypatch)
    original = runner.subprocess.run

    def interrupted(command, **kwargs):
        if (Path(command[0]).name == "checkMesh"
                and kwargs.get("cwd") == grid_family / "configuration_1/coarse"):
            kwargs["stdout"].write("SYNTHETIC interrupted process, no solver result\n")
            raise KeyboardInterrupt("synthetic interruption")
        return original(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt, match="synthetic interruption"):
        run_grid_family(grid_family, timeout_seconds=60)
    receipt = json.loads((grid_family / "grid_run_evidence.json").read_text())
    assert receipt["status"] == "incomplete"
    assert receipt["cases"]["configuration_1/coarse"]["status"] == "running"
    assert len(receipt["cases"]["configuration_1/coarse"]["stages"]) == 1
    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert "unreceipted_stage_log:configuration_1/coarse:checkMesh" in result["findings"]
    assert result["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("stage", ["blockMesh", "checkMesh", "simpleFoam"])
def test_empty_successful_stage_log_with_forged_matching_digest_fails(
    grid_family, monkeypatch, stage
):
    import hashlib

    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    case_key = "configuration_3/medium"
    log = grid_family / case_key / (stage + ".log")
    log.write_bytes(b"")
    path = grid_family / "grid_run_evidence.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    index = ("blockMesh", "checkMesh", "simpleFoam").index(stage)
    report["cases"][case_key]["stages"][index]["log_sha256"] = (
        hashlib.sha256(b"").hexdigest()
    )
    path.write_text(json.dumps(report), encoding="utf-8")

    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert f"empty_completed_stage_log:{case_key}:{stage}" in result["findings"]
    assert result["engineering_review"] == "BLOCKED"


def test_replayed_solver_log_across_configurations_is_rejected(
    grid_family, monkeypatch
):
    import hashlib

    synthetic_processes(monkeypatch)
    run_grid_family(grid_family, timeout_seconds=60)
    original = grid_family / "configuration_1/coarse/simpleFoam.log"
    substitute = grid_family / "configuration_2/fine/simpleFoam.log"
    substitute.write_bytes(original.read_bytes())
    path = grid_family / "grid_run_evidence.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["cases"]["configuration_2/fine"]["stages"][2]["log_sha256"] = (
        hashlib.sha256(substitute.read_bytes()).hexdigest()
    )
    path.write_text(json.dumps(report), encoding="utf-8")

    result = verify_grid_run_evidence(grid_family)
    assert result["status"] == "evidence_integrity_failed"
    assert (
        "replayed_solver_log_across_configurations:"
        "configuration_2/fine:configuration_1/coarse"
    ) in result["findings"]
    assert result["engineering_review"] == "BLOCKED"
