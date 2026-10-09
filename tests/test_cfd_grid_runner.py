"""Nine-case executor regressions use fake process exits, not CFD results."""
import hashlib
import json
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
        kwargs["stdout"].write("Synthetic process-exit fixture. Not CFD validation.\n")
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


def test_non_v10_version_is_rejected_without_writing_receipt(generated, monkeypatch):
    fake_tools(monkeypatch, version="OpenFOAM-v2312")
    with pytest.raises(RuntimeError, match="Foundation v10"):
        run_grid_family(generated)
    assert not (generated / "grid_run_evidence.json").exists()


def test_missing_binary_prevents_execution(generated, monkeypatch):
    import cleanroomx.cfd_grid_runner as runner
    monkeypatch.setattr(runner.shutil, "which", lambda name: None if name == "simpleFoam" else name)
    with pytest.raises(RuntimeError, match="simpleFoam"):
        run_grid_family(generated)
    assert not (generated / "grid_run_evidence.json").exists()


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
    with pytest.raises(ValueError, match="outside grid family"):
        run_grid_family(generated)
