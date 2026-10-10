"""Nine-case executor regressions use fake process exits, not CFD results."""
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cleanroomx.cfd_grid_family import SCHEMA, generate_grid_family
from cleanroomx.cfd_grid_runner import RUN_SCHEMA, run_grid_family


@pytest.fixture
def generated(tmp_path):
    family = {
        "schema_version": SCHEMA,
        "base_case": {
            "schema_version": "cleanroomx.openfoam.v1",
            "name": "SYNTHETIC test geometry (NOT validated)",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [9, 9, 9],
            "fine": [12, 12, 12],
        },
    }
    target = tmp_path / "family"
    generate_grid_family(family, target)
    return target


def fake_tools(monkeypatch, *, failure=None, version="10"):
    import cleanroomx.cfd_grid_runner as runner

    calls = []
    monkeypatch.setattr(runner.shutil, "which", lambda tool: "/fake/" + tool)

    def run(command, **kwargs):
        name = Path(command[0]).name
        if name == "foamVersion":
            return SimpleNamespace(returncode=0, stdout=version + "\n", stderr="")
        key = kwargs["cwd"].relative_to(kwargs["cwd"].parents[1]).as_posix()
        calls.append((key, name))
        kwargs["stdout"].write(f"Synthetic process-exit fixture {key} {name}. Not CFD validation.\n")
        return SimpleNamespace(returncode=1 if (key, name) == failure else 0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    return calls


def test_all_nine_cases_receive_hash_bound_stage_receipts(generated, monkeypatch):
    calls = fake_tools(monkeypatch)
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["schema_version"] == RUN_SCHEMA
    assert report["foam_version"] == "10"
    assert report["status"] == "executed_requires_convergence_review"
    assert report["engineering_review"] == "BLOCKED"
    assert report["physical_validation"] == "not_performed"
    assert len(report["cases"]) == 9
    assert len(calls) == 27
    assert all(len(case["stages"]) == 3 for case in report["cases"].values())
    for case in report["cases"].values():
        assert case["status"] == "executed_requires_convergence_review"
        for stage in case["stages"]:
            expected = hashlib.sha256((generated / stage["log"]).read_bytes()).hexdigest()
            assert stage["log_sha256"] == expected
            assert stage["returncode"] == 0
    assert json.loads((generated / "grid_run_evidence.json").read_text()) == report
    with pytest.raises(FileExistsError):
        run_grid_family(generated)


def test_failed_stage_blocks_review_but_other_cases_remain_recorded(generated, monkeypatch):
    calls = fake_tools(monkeypatch, failure=("configuration_1/coarse", "checkMesh"))
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["status"] == "incomplete"
    assert report["engineering_review"] == "BLOCKED"
    failed = report["cases"]["configuration_1/coarse"]
    assert failed["status"] == "execution_failed"
    assert len(failed["stages"]) == 2
    assert failed["stages"][1]["returncode"] == 1
    assert "simpleFoam" not in [stage["command"] for stage in failed["stages"]]
    assert len(calls) == 26
    assert report["cases"]["configuration_3/fine"]["status"] == "executed_requires_convergence_review"


@pytest.mark.parametrize("relative", [
    "manifest.json",
    "configuration_2/medium/0/U",
])
def test_hardlinked_generated_input_rejected_before_execution(
    generated, monkeypatch, tmp_path, relative
):
    # A hard link retains the input bytes and digest but exposes a second
    # writable name outside the generated family.
    try:
        os.link(generated / relative, tmp_path / "outside_alias")
    except (OSError, NotImplementedError):
        pytest.skip("Hard links unavailable on this filesystem")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="hardlinked"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()
    assert not (generated / ".grid_run_reserved").exists()


def test_input_tampering_fails_preflight_before_execution(generated, monkeypatch):
    changed = generated / "configuration_2/medium/0/U"
    changed.write_text(changed.read_text() + "\n// altered\n")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="changed"):
        run_grid_family(generated)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()


def test_existing_logs_block_rerun_before_execution(generated, monkeypatch):
    (generated / "configuration_3/fine/simpleFoam.log").write_text("existing evidence")
    calls = fake_tools(monkeypatch)
    with pytest.raises(FileExistsError, match="Existing OpenFOAM stage log"):
        run_grid_family(generated)
    assert calls == []


@pytest.mark.parametrize("artifact", [
    "constant/polyMesh/points",
    "100/U",
    "postProcessing/residuals.dat",
    "0/U.stale",
])
def test_preexisting_solver_artifacts_block_all_execution(generated, monkeypatch, artifact):
    # A zero-exit solver must never borrow mesh, time or postprocessing data
    # from an earlier execution without recording that prior run as evidence.
    stale = generated / "configuration_2/medium" / artifact
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("stale prior-run CFD output; not generated input")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="unexpected pre-existing solver artifacts"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()
    stale.unlink()
    if stale.parent.name in ("polyMesh", "100", "postProcessing"):
        stale.parent.rmdir()
    assert len(fake_tools(monkeypatch)) == 0
    assert run_grid_family(generated, timeout_seconds=60)["status"] == (
        "executed_requires_convergence_review"
    )


def test_symlinked_generated_case_directory_is_rejected(generated, monkeypatch):
    # Even a symlink staying inside the family must not masquerade as
    # a pristine, independently generated OpenFOAM source directory.
    case = generated / "configuration_1/fine"
    original = case / "0"
    replacement = case / "zero-original"
    try:
        original.rename(replacement)
        original.symlink_to(replacement, target_is_directory=True)
    except (OSError, NotImplementedError):
        if not original.exists() and replacement.exists():
            replacement.rename(original)
        pytest.skip("Directory symlinks unavailable")
    fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="(outside grid family|real directory|unexpected pre-existing)"):
        run_grid_family(generated, timeout_seconds=60)
    assert not (generated / "grid_run_evidence.json").exists()


def test_non_v10_version_is_rejected_without_writing_receipt(generated, monkeypatch):
    fake_tools(monkeypatch, version="OpenFOAM-v2312")
    with pytest.raises(ValueError, match="Foundation v10"):
        run_grid_family(generated)
    assert not (generated / "grid_run_evidence.json").exists()


def test_missing_binary_prevents_execution(generated, monkeypatch):
    import cleanroomx.cfd_grid_runner as runner
    monkeypatch.setattr(runner.shutil, "which", lambda name: None if name == "simpleFoam" else name)
    with pytest.raises(ValueError, match="simpleFoam"):
        run_grid_family(generated)
    assert not (generated / "grid_run_evidence.json").exists()


def test_invalid_openfoam_does_not_reserve_family(generated, monkeypatch):
    """Failed preflight must permit a later valid first execution."""
    fake_tools(monkeypatch, version="OpenFOAM-v2312")
    with pytest.raises(ValueError, match="Foundation v10"):
        run_grid_family(generated, timeout_seconds=60)
    assert not (generated / ".grid_run_reserved").exists()
    assert not (generated / "grid_run_evidence.json").exists()
    calls = fake_tools(monkeypatch, version="10")
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["status"] == "executed_requires_convergence_review"
    assert len(calls) == 27


def test_invalid_timeout_is_rejected(generated):
    with pytest.raises(ValueError, match="timeout_seconds"):
        run_grid_family(generated, timeout_seconds=True)


def test_symlinked_solver_input_outside_family_is_rejected(generated, tmp_path):
    original = generated / "configuration_1/fine/0/U"
    outside = tmp_path / "outside.txt"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    try:
        original.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="must not be a symlink"):
        run_grid_family(generated)


def test_cli_missing_binary_reports_clean_error(generated, monkeypatch, capsys):
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_pipeline_cli import main
    monkeypatch.setattr(runner.shutil, "which", lambda tool: None)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-cfd-pipeline", "grid-run", str(generated)])
    assert main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "foamVersion is not available" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("relative", [
    "configuration_1", "configuration_2/fine",
])
def test_symlinked_configuration_or_case_root_is_rejected(
    generated, monkeypatch, relative
):
    # The target stays inside the grid family with byte-identical inputs.
    # Symlinked parent directories must not silently relabel run evidence.
    original = generated / relative
    backup = original.with_name(original.name + "-original")
    original.rename(backup)
    try:
        original.symlink_to(backup, target_is_directory=True)
    except (OSError, NotImplementedError):
        backup.rename(original)
        pytest.skip("Directory symlinks unavailable")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="(Configuration root|Case root).*real directory"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()


def test_manifest_symlink_inside_family_is_rejected_before_execution(
    generated, monkeypatch
):
    original = generated / "manifest.json"
    backup = generated / "manifest.original.json"
    original.rename(backup)
    try:
        original.symlink_to(backup.name)
    except (OSError, NotImplementedError):
        backup.rename(original)
        pytest.skip("Symlinks unavailable")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="manifest must be a real file"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()


def test_duplicate_manifest_keys_fail_closed(generated, monkeypatch):
    manifest = generated / "manifest.json"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace('"schema_version":', '"schema_version": "invalid", "schema_version":', 1), encoding="utf-8")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        run_grid_family(generated, timeout_seconds=60)
    assert not calls
    assert not (generated / "grid_run_evidence.json").exists()


def test_symlinked_family_root_rejected_for_run_and_verify(generated, tmp_path, monkeypatch):
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence
    linked = tmp_path / "linked-family"
    try:
        linked.symlink_to(generated, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks unavailable")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="root must not be a symlink"):
        run_grid_family(linked, timeout_seconds=60)
    with pytest.raises(ValueError, match="root must not be a symlink"):
        verify_grid_run_evidence(linked)
    assert not calls
    assert not (generated / "grid_run_evidence.json").exists()


def test_existing_execution_reservation_blocks_solver_launch(generated, monkeypatch):
    (generated / ".grid_run_reserved").mkdir()
    calls = fake_tools(monkeypatch)
    with pytest.raises(FileExistsError, match="reservation"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()


def test_execution_reservation_persists_after_run(generated, monkeypatch):
    fake_tools(monkeypatch)
    run_grid_family(generated, timeout_seconds=60)
    assert (generated / ".grid_run_reserved").is_dir()
    with pytest.raises(FileExistsError):
        run_grid_family(generated, timeout_seconds=60)


def test_stage_launch_oserror_is_recorded_and_remaining_cases_continue(generated, monkeypatch):
    import cleanroomx.cfd_grid_runner as runner
    calls = fake_tools(monkeypatch)
    original = runner.subprocess.run

    def launch(command, **kwargs):
        if Path(command[0]).name == "checkMesh" and kwargs.get("cwd") == generated / "configuration_1/coarse":
            raise OSError("synthetic executable launch failure")
        return original(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", launch)
    report = run_grid_family(generated, timeout_seconds=60)
    failed = report["cases"]["configuration_1/coarse"]
    assert report["status"] == "incomplete"
    assert failed["status"] == "execution_failed"
    assert failed["stages"][-1]["status"] == "launch_failed"
    assert failed["stages"][-1]["returncode"] is None
    assert len(report["cases"]["configuration_3/fine"]["stages"]) == 3
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence
    verified = verify_grid_run_evidence(generated)
    assert verified["status"] == "incomplete_execution_logs_integrity_verified"
    assert verified["engineering_review"] == "BLOCKED"


def test_solver_timeout_is_receipted_and_later_cases_continue(generated, monkeypatch):
    import subprocess
    import cleanroomx.cfd_grid_runner as runner
    fake_tools(monkeypatch)
    original = runner.subprocess.run

    def timeout_one(command, **kwargs):
        if (Path(command[0]).name == "simpleFoam"
                and kwargs.get("cwd") == generated / "configuration_2/medium"):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return original(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", timeout_one)
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["status"] == "incomplete"
    failed = report["cases"]["configuration_2/medium"]
    assert failed["status"] == "execution_failed"
    assert failed["stages"][-1]["status"] == "timed_out"
    assert failed["stages"][-1]["returncode"] is None
    assert len(report["cases"]["configuration_3/fine"]["stages"]) == 3
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence
    verification = verify_grid_run_evidence(generated)
    assert verification["status"] == "incomplete_execution_logs_integrity_verified"
    assert verification["engineering_review"] == "BLOCKED"


def test_version_probe_timeout_never_launches_solver(generated, monkeypatch):
    import subprocess
    import cleanroomx.cfd_grid_runner as runner
    monkeypatch.setattr(runner.shutil, "which", lambda tool: "/fake/" + tool)
    invoked = []

    def timeout_version(command, **kwargs):
        invoked.append(Path(command[0]).name)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", timeout_version)
    with pytest.raises(ValueError, match="foamVersion timed out"):
        run_grid_family(generated, timeout_seconds=60)
    assert invoked == ["foamVersion"]
    assert not (generated / "grid_run_evidence.json").exists()
    assert not (generated / ".grid_run_reserved").exists()


def test_nonzero_version_probe_rejected_before_solver(generated, monkeypatch):
    import cleanroomx.cfd_grid_runner as runner
    monkeypatch.setattr(runner.shutil, "which", lambda tool: "/fake/" + tool)
    invoked = []

    def failed_version(command, **kwargs):
        invoked.append(Path(command[0]).name)
        return SimpleNamespace(returncode=1, stdout="10\\n", stderr="error")

    monkeypatch.setattr(runner.subprocess, "run", failed_version)
    with pytest.raises(ValueError, match="Foundation v10"):
        run_grid_family(generated, timeout_seconds=60)
    assert invoked == ["foamVersion"]
    assert not (generated / "grid_run_evidence.json").exists()


def test_version_probe_launch_failure_is_cleanly_rejected(generated, monkeypatch):
    import cleanroomx.cfd_grid_runner as runner
    monkeypatch.setattr(runner.shutil, "which", lambda tool: "/fake/" + tool)
    invoked = []

    def cannot_launch(command, **kwargs):
        invoked.append(Path(command[0]).name)
        raise OSError("synthetic missing executable")

    monkeypatch.setattr(runner.subprocess, "run", cannot_launch)
    with pytest.raises(ValueError, match="foamVersion could not be launched"):
        run_grid_family(generated, timeout_seconds=60)
    assert invoked == ["foamVersion"]
    assert not (generated / "grid_run_evidence.json").exists()
    assert not (generated / ".grid_run_reserved").exists()


def test_same_family_symlinked_input_is_rejected_before_solver(generated, monkeypatch):
    original = generated / "configuration_1/fine/0/U"
    backup = original.with_name("U-original")
    original.rename(backup)
    try:
        original.symlink_to(backup.name)
    except (OSError, NotImplementedError):
        backup.rename(original)
        pytest.skip("Symlinks unavailable")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="must not be a symlink"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()


def test_solver_digest_streams_without_path_read_bytes(tmp_path, monkeypatch):
    """Large solver logs must be hashed incrementally, not read all at once."""
    import cleanroomx.cfd_grid_runner as runner
    source = tmp_path / "solver.log"
    payload = b"CFD synthetic fixture, not validated output.\n" * 40000
    source.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    original = Path.read_bytes

    def reject_whole_file_read(path):
        if path == source:
            raise AssertionError("whole-file read is prohibited for solver logs")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", reject_whole_file_read)
    assert runner._hash(source) == expected


@pytest.mark.parametrize("digest_source", ["runner", "receipt"])
def test_streamed_cfd_evidence_hash_fails_on_concurrent_append(
    tmp_path, monkeypatch, digest_source
):
    """A changed file must not pass merely because pre-read bytes hash cleanly."""
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_grid_receipt import _file_digest

    source = tmp_path / "case-stage.log"
    source.write_bytes(b"synthetic CFD software test only\\n")
    real_fstat = runner.os.fstat
    calls = 0

    def inject_mutation(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            with source.open("ab") as stream:
                stream.write(b"mutated after hash read")
        return real_fstat(fd)

    monkeypatch.setattr(runner.os, "fstat", inject_mutation)
    with pytest.raises(ValueError, match="changed during hashing"):
        if digest_source == "runner":
            runner._hash(source)
        else:
            _file_digest(source)


def test_zero_exit_empty_output_is_failed_before_next_solver_stage(
    generated, monkeypatch
):
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence

    calls = fake_tools(monkeypatch)
    original = runner.subprocess.run

    def zero_output(command, **kwargs):
        if (Path(command[0]).name == "checkMesh"
                and kwargs.get("cwd") == generated / "configuration_1/coarse"):
            calls.append(("configuration_1/coarse", "checkMesh"))
            return SimpleNamespace(returncode=0)
        return original(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", zero_output)
    report = run_grid_family(generated, timeout_seconds=60)
    failed = report["cases"]["configuration_1/coarse"]
    assert report["status"] == "incomplete"
    assert failed["status"] == "execution_failed"
    assert len(failed["stages"]) == 2
    assert failed["stages"][-1]["status"] == "empty_output"
    assert failed["stages"][-1]["returncode"] == 0
    assert ("configuration_1/coarse", "simpleFoam") not in calls
    assert report["cases"]["configuration_3/fine"]["status"] == (
        "executed_requires_convergence_review"
    )
    verification = verify_grid_run_evidence(generated)
    assert verification["status"] == "incomplete_execution_logs_integrity_verified"
    assert verification["findings"] == []
    assert verification["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("tamper", [
    "unknown_claim", "invalid_spec_hash", "wrong_family_status",
    "swapped_case_identity", "forged_validation_limitations",
    "negative_face_area",
])
def test_tampered_family_manifest_metadata_blocks_all_execution(
    generated, monkeypatch, tamper
):
    manifest_path = generated / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = manifest["case_inputs"]["configuration_1/coarse"]
    if tamper == "unknown_claim":
        metadata["certified"] = True
    elif tamper == "invalid_spec_hash":
        manifest["family_spec_sha256"] = "invalid"
    elif tamper == "wrong_family_status":
        manifest["status"] = "validated"
    elif tamper == "swapped_case_identity":
        metadata["configuration"] = 2
    elif tamper == "forged_validation_limitations":
        metadata["limitations"] = ["certified particle cleanliness"]
    elif tamper == "negative_face_area":
        metadata["mesh"]["inlet_area_m2"] = -1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    calls = fake_tools(monkeypatch)
    with pytest.raises(ValueError, match="(manifest|metadata|quantity|face count)"):
        run_grid_family(generated, timeout_seconds=60)
    assert calls == []
    assert not (generated / "grid_run_evidence.json").exists()
    assert not (generated / ".grid_run_reserved").exists()


@pytest.mark.parametrize("unexpected", [
    "system/fvOptions", "0/U.extra", "constant/turbulenceProperties",
    "constant/polyMesh",
])
def test_unmanifested_source_artifact_during_blockmesh_blocks_run(
    generated, monkeypatch, unexpected
):
    """Even byte-perfect listed inputs cannot authorize added dictionaries."""
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence

    calls = fake_tools(monkeypatch)
    previous = runner.subprocess.run

    def inject(command, **kwargs):
        finished = previous(command, **kwargs)
        if (Path(command[0]).name == "blockMesh"
                and kwargs.get("cwd") == generated / "configuration_1/coarse"):
            target = kwargs["cwd"] / unexpected
            target.write_text("UNTRACKED synthetic source; not OpenFOAM evidence")
        return finished

    monkeypatch.setattr(runner.subprocess, "run", inject)
    report = run_grid_family(generated, timeout_seconds=60)
    assert calls == [("configuration_1/coarse", "blockMesh")]
    first = report["cases"]["configuration_1/coarse"]
    assert first["status"] == "execution_failed"
    assert first["stages"][-1]["status"] == "source_drift"
    assert report["status"] == "incomplete"
    verification = verify_grid_run_evidence(generated)
    assert verification["status"] == "evidence_integrity_failed"
    assert any(x.startswith(
        "unexpected_or_unsafe_source_tree:configuration_1/coarse:"
    ) for x in verification["findings"])


def test_generated_polymesh_is_permitted_without_extra_dictionaries(
    generated, monkeypatch
):
    """The known blockMesh output must not be mistaken for source tampering."""
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence

    calls = fake_tools(monkeypatch)
    previous = runner.subprocess.run

    def emit_mesh(command, **kwargs):
        completed = previous(command, **kwargs)
        if Path(command[0]).name == "blockMesh":
            mesh = kwargs["cwd"] / "constant/polyMesh"
            mesh.mkdir()
            (mesh / "points").write_text("Synthetic output; not a CFD mesh")
        return completed

    monkeypatch.setattr(runner.subprocess, "run", emit_mesh)
    receipt = run_grid_family(generated, timeout_seconds=60)
    assert len(calls) == 27
    assert receipt["status"] == "executed_requires_convergence_review"
    report = verify_grid_run_evidence(generated)
    assert report["status"] == "execution_logs_integrity_verified_requires_scientific_review"
    assert report["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("injection", ["version_probe", "after_block_mesh"])
@pytest.mark.parametrize("target", ["manifest", "solver_input"])
def test_stage_source_revalidation_blocks_midrun_tampering(
    generated, monkeypatch, injection, target
):
    """A valid initial preflight must not authorize later modified inputs."""
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence

    calls = fake_tools(monkeypatch)
    original = runner.subprocess.run

    def tampering_subprocess(command, **kwargs):
        program = Path(command[0]).name
        result = original(command, **kwargs)
        if (injection == "version_probe" and program == "foamVersion"
                or injection == "after_block_mesh" and program == "blockMesh"
                and kwargs.get("cwd") == generated / "configuration_1/coarse"):
            source = (
                generated / "manifest.json"
                if target == "manifest"
                else generated / "configuration_1/coarse/0/U"
            )
            source.write_bytes(source.read_bytes() + b"\\n// synthetic in-run mutation\\n")
        return result

    monkeypatch.setattr(runner.subprocess, "run", tampering_subprocess)
    if injection == "version_probe":
        with pytest.raises(ValueError, match="(manifest|input) changed during execution"):
            run_grid_family(generated, timeout_seconds=60)
    else:
        result = run_grid_family(generated, timeout_seconds=60)
        assert result["status"] == "incomplete"
        first_stage = result["cases"]["configuration_1/coarse"]["stages"][0]
        assert first_stage["status"] == "source_drift"
        assert first_stage["returncode"] == 0
        assert result["cases"]["configuration_1/coarse"]["status"] == "execution_failed"
    assert calls == (
        [] if injection == "version_probe"
        else [("configuration_1/coarse", "blockMesh")]
    )
    assert ("configuration_1/coarse", "checkMesh") not in calls
    receipt_path = generated / "grid_run_evidence.json"
    assert receipt_path.is_file()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "incomplete"
    assert receipt["engineering_review"] == "BLOCKED"
    assert len(receipt["cases"]["configuration_1/coarse"]["stages"]) == len(calls)
    assert (generated / ".grid_run_reserved").is_dir()
    verification = verify_grid_run_evidence(generated)
    assert verification["status"] == "evidence_integrity_failed"
    assert verification["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("restore_sources", [False, True])
def test_last_solver_stage_source_drift_blocks_success_and_later_claims(
    generated, monkeypatch, restore_sources
):
    """Detect tampering even when there is no next solver stage to preflight."""
    import cleanroomx.cfd_grid_runner as runner
    from cleanroomx.cfd_grid_receipt import verify_grid_run_evidence

    calls = fake_tools(monkeypatch)
    original = runner.subprocess.run
    source = generated / "configuration_3/fine/0/U"
    original_source = source.read_bytes()

    def modified_last_stage(command, **kwargs):
        result = original(command, **kwargs)
        if (Path(command[0]).name == "simpleFoam"
                and kwargs.get("cwd") == generated / "configuration_3/fine"):
            source.write_bytes(original_source + b"\n// injected during final solver stage\n")
        return result

    monkeypatch.setattr(runner.subprocess, "run", modified_last_stage)
    report = run_grid_family(generated, timeout_seconds=60)
    last_case = report["cases"]["configuration_3/fine"]
    assert len(calls) == 27
    assert report["status"] == "incomplete"
    assert last_case["status"] == "execution_failed"
    assert len(last_case["stages"]) == 3
    assert last_case["stages"][-1]["status"] == "source_drift"
    assert last_case["stages"][-1]["returncode"] == 0
    assert report["engineering_review"] == "BLOCKED"
    assert (generated / "grid_run_evidence.json").is_file()
    assert (generated / ".grid_run_reserved").is_dir()

    if restore_sources:
        # Restoring the original bytes cannot launder the failed run.
        source.write_bytes(original_source)
    verification = verify_grid_run_evidence(generated)
    assert verification["status"] == "evidence_integrity_failed"
    assert (
        "stage_source_drift_recorded:configuration_3/fine:simpleFoam"
    ) in verification["findings"]
    assert verification["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("link_type", ["symlink", "hardlink"])
def test_blockmesh_output_link_alias_fails_closed(
    generated, monkeypatch, tmp_path, link_type
):
    """A solver-generated mesh must never alias an external writable file."""
    import cleanroomx.cfd_grid_runner as runner

    fake_tools(monkeypatch)
    fake_run = runner.subprocess.run
    external = tmp_path / "external_mesh_points"
    external.write_text("SYNTHETIC untrusted mesh output")
    target_case = generated / "configuration_1/coarse"

    def linked_mesh(command, **kwargs):
        completed = fake_run(command, **kwargs)
        if Path(command[0]).name == "blockMesh" and kwargs["cwd"] == target_case:
            mesh = target_case / "constant/polyMesh"
            mesh.mkdir()
            try:
                if link_type == "symlink":
                    (mesh / "points").symlink_to(external)
                else:
                    os.link(external, mesh / "points")
            except (OSError, NotImplementedError):
                pytest.skip("Link creation unavailable on this filesystem")
        return completed

    monkeypatch.setattr(runner.subprocess, "run", linked_mesh)
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["status"] == "incomplete"
    first = report["cases"]["configuration_1/coarse"]
    assert first["status"] == "execution_failed"
    assert first["stages"][0]["status"] == "source_drift"
    assert report["cases"]["configuration_1/medium"]["status"] == "not_run"
    assert (generated / "grid_run_evidence.json").exists()


def test_regular_generated_polymesh_files_remain_permitted(generated, monkeypatch):
    """A normal generated mesh is not mistaken for untracked dictionaries."""
    import cleanroomx.cfd_grid_runner as runner

    fake_tools(monkeypatch)
    fake_run = runner.subprocess.run

    def normal_mesh(command, **kwargs):
        completed = fake_run(command, **kwargs)
        if Path(command[0]).name == "blockMesh":
            mesh = kwargs["cwd"] / "constant/polyMesh"
            mesh.mkdir()
            (mesh / "points").write_text("SYNTHETIC mesh fixture")
        return completed

    monkeypatch.setattr(runner.subprocess, "run", normal_mesh)
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["status"] == "executed_requires_convergence_review"


def test_generated_mesh_file_hashes_are_in_v2_receipt(generated, monkeypatch):
    """The synthetic mesh bytes are bound, not merely link-checked."""
    import cleanroomx.cfd_grid_runner as runner

    fake_tools(monkeypatch)
    fake_run = runner.subprocess.run

    def with_mesh(command, **kwargs):
        result = fake_run(command, **kwargs)
        if Path(command[0]).name == "blockMesh":
            mesh = kwargs["cwd"] / "constant/polyMesh"
            mesh.mkdir()
            (mesh / "points").write_bytes(b"SYNTHETIC mesh bytes")
        return result

    monkeypatch.setattr(runner.subprocess, "run", with_mesh)
    report = run_grid_family(generated, timeout_seconds=60)
    assert report["status"] == "executed_requires_convergence_review"
    for case in report["cases"].values():
        assert case["mesh_files"] == {
            "points": hashlib.sha256(b"SYNTHETIC mesh bytes").hexdigest()
        }
