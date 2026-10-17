#!/usr/bin/env python3
"""Run a pinned OpenFOAM Foundation v10 tutorial through CleanroomX result sync.

This is an integration smoke test. It does not establish cleanroom performance,
solver convergence, mesh independence, or physical validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from cleanroomx.cfd_openfoam_runtime_sync import (
    OpenFOAMResultSynchronizer,
    hash_case_configuration,
    run_solver_with_sync,
)

UPSTREAM_REPOSITORY = "OpenFOAM/OpenFOAM-10"
UPSTREAM_COMMIT = "89f925dc708d068f84f51e8317e3bebcda64f5cb"
UPSTREAM_CASE = "tutorials/incompressible/simpleFoam/pitzDaily"
UPSTREAM_MESH = "tutorials/incompressible/simpleFoam/pitzDaily/system/blockMeshDict"
SCHEMA = "cleanroomx.openfoam-v10-tutorial-run.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")


def _build_identity(log_text: str) -> str | None:
    match = re.search(r"(?m)^\s*Build\s*:\s*(\S+)\s*$", log_text)
    return match.group(1) if match else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_logged(
    name: str,
    command: list[str],
    *,
    case_directory: Path,
    log_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    returncode = 127
    error = None
    try:
        with log_path.open("xb") as log:
            try:
                result = subprocess.run(
                    command,
                    cwd=case_directory,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=timeout_seconds,
                )
                returncode = result.returncode
            except subprocess.TimeoutExpired:
                returncode = 124
                error = f"timed out after {timeout_seconds} seconds"
            except OSError as exc:
                error = f"{type(exc).__name__}: {exc}"
    except OSError as exc:
        error = f"{type(exc).__name__}: {exc}"

    log_sha256 = _sha256(log_path) if log_path.is_file() else None
    return {
        "name": name,
        "argv": command,
        "returncode": returncode,
        "log": log_path.name,
        "log_sha256": log_sha256,
        "error": error,
    }


def validate_receipt(receipt: dict[str, Any]) -> None:
    """Reject a PASS receipt unless every runtime and provenance gate is met."""
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise ValueError("unexpected tutorial evidence schema")
    if receipt.get("status") != "PASS":
        raise ValueError("tutorial run did not pass")
    if receipt.get("upstream_repository") != UPSTREAM_REPOSITORY:
        raise ValueError("tutorial source repository is not the pinned Foundation source")
    if receipt.get("upstream_commit") != UPSTREAM_COMMIT:
        raise ValueError("tutorial source commit is not pinned")
    if receipt.get("source_case_path") != UPSTREAM_CASE:
        raise ValueError("tutorial case path is not the pinned pitzDaily case")
    if receipt.get("case_type") != "upstream_foundation_tutorial":
        raise ValueError("case is not identified as an upstream tutorial")
    stages = receipt.get("stages")
    if type(stages) is not dict or set(stages) != {"blockMesh", "checkMesh", "simpleFoam"}:
        raise ValueError("tutorial run is missing a required solver stage")
    for name, stage in stages.items():
        if (
            type(stage) is not dict
            or type(stage.get("returncode")) is not int
            or stage["returncode"] != 0
            or type(stage.get("log_sha256")) is not str
            or _HASH.fullmatch(stage["log_sha256"]) is None
        ):
            raise ValueError(f"{name} did not complete with a hash-bound log")
    if receipt.get("mesh_ok") is not True:
        raise ValueError("checkMesh did not report Mesh OK")
    if receipt.get("solver_log_completed") is not True:
        raise ValueError("simpleFoam log did not end with End")
    sync = receipt.get("result_sync")
    if (
        type(sync) is not dict
        or sync.get("status") != "results_synced"
        or type(sync.get("record_count")) is not int
        or sync["record_count"] < 1
        or type(sync.get("times")) is not list
        or type(sync.get("manifest_sha256")) is not str
        or _HASH.fullmatch(sync["manifest_sha256"]) is None
    ):
        raise ValueError("CleanroomX did not synchronize a hash-bound nonzero-time result")
    try:
        numeric_times = [float(value) for value in sync["times"]]
    except (TypeError, ValueError):
        raise ValueError("CleanroomX synchronized an invalid solver time") from None
    if not any(math.isfinite(value) and value > 0 for value in numeric_times):
        raise ValueError("CleanroomX did not synchronize a hash-bound nonzero-time result")
    environment = receipt.get("environment")
    if (
        type(environment) is not dict
        or environment.get("WM_PROJECT") != "OpenFOAM"
        or environment.get("WM_PROJECT_VERSION") != "10"
        or not isinstance(environment.get("openfoam_package_version"), str)
        or not environment["openfoam_package_version"].strip()
        or not isinstance(environment.get("simpleFoam_executable"), str)
        or not environment["simpleFoam_executable"].strip()
        or not isinstance(environment.get("foamToVTK_executable"), str)
        or not environment["foamToVTK_executable"].strip()
    ):
        raise ValueError("Foundation v10 runtime identity is incomplete")
    if (
        not isinstance(receipt.get("solver_build"), str)
        or not receipt["solver_build"].strip()
        or not isinstance(receipt.get("foamToVTK_build"), str)
        or receipt["foamToVTK_build"] != receipt["solver_build"]
    ):
        raise ValueError("simpleFoam and foamToVTK build identities do not match")
    if receipt.get("scientific_validation") != "BLOCKED":
        raise ValueError("tutorial evidence cannot declare physical validation")


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run(args: argparse.Namespace) -> dict[str, Any]:
    upstream_root = args.upstream_root.resolve(strict=True)
    actual_commit = subprocess.run(
        ["git", "-C", str(upstream_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_commit != UPSTREAM_COMMIT:
        raise ValueError(f"expected pinned source {UPSTREAM_COMMIT}, got {actual_commit}")

    source_case_candidate = upstream_root / UPSTREAM_CASE
    source_mesh_candidate = upstream_root / UPSTREAM_MESH
    if source_case_candidate.is_symlink() or source_mesh_candidate.is_symlink():
        raise ValueError("pinned upstream inputs must not be symbolic links")
    source_case = source_case_candidate.resolve(strict=True)
    source_mesh = source_mesh_candidate.resolve(strict=True)
    if not source_case.is_dir() or not source_mesh.is_file():
        raise ValueError("pinned upstream tutorial or its mesh dictionary is missing")
    environment = {
        "WM_PROJECT": os.environ.get("WM_PROJECT"),
        "WM_PROJECT_VERSION": os.environ.get("WM_PROJECT_VERSION"),
        "openfoam_package_version": subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", "openfoam10"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "simpleFoam_executable": shutil.which("simpleFoam"),
        "foamToVTK_executable": shutil.which("foamToVTK"),
    }
    if environment["WM_PROJECT"] != "OpenFOAM" or environment["WM_PROJECT_VERSION"] != "10":
        raise ValueError("runtime environment is not OpenFOAM Foundation v10")

    case_directory = args.case_directory
    result_directory = args.result_directory
    evidence_directory = args.evidence_directory
    for path in (case_directory, result_directory, evidence_directory):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"refusing to reuse evidence path: {path}")
    evidence_directory.mkdir(parents=True)
    shutil.copytree(source_case, case_directory, symlinks=False)
    system = case_directory / "system"
    if system.is_symlink() or not system.is_dir():
        raise ValueError("tutorial system directory is missing or unsafe")
    block_mesh_dict = system / "blockMeshDict"
    if block_mesh_dict.is_symlink() or not block_mesh_dict.is_file():
        raise ValueError("tutorial blockMeshDict is missing or unsafe")
    if _sha256(block_mesh_dict) != _sha256(source_mesh):
        raise ValueError("tutorial blockMeshDict does not match its pinned upstream resource")

    configuration_hash = hash_case_configuration(case_directory)
    mesh_stage = _run_logged(
        "blockMesh",
        ["blockMesh"],
        case_directory=case_directory,
        log_path=evidence_directory / "blockMesh.log",
        timeout_seconds=args.stage_timeout_seconds,
    )
    check_stage = None
    solver_stage = None
    sync_summary: dict[str, Any] | None = None
    mesh_ok = False
    solver_log_completed = False
    if mesh_stage["returncode"] == 0:
        check_stage = _run_logged(
            "checkMesh",
            ["checkMesh"],
            case_directory=case_directory,
            log_path=evidence_directory / "checkMesh.log",
            timeout_seconds=args.stage_timeout_seconds,
        )
        if check_stage["returncode"] == 0:
            mesh_ok = "Mesh OK" in (evidence_directory / "checkMesh.log").read_text(
                encoding="utf-8", errors="replace"
            )

    if mesh_ok:
        synchronizer = OpenFOAMResultSynchronizer(
            case_directory,
            result_directory,
            simulation_id="foundation-v10-pitzDaily-" + configuration_hash[:16],
            case_id="pitzDaily",
            configuration_hash=configuration_hash,
            required_fields=("U", "p"),
            optional_fields=(),
            include_surface_flux=False,
            poll_interval_seconds=0.5,
            settle_polls=2,
            timeout_seconds=args.stage_timeout_seconds,
        )
        solver_log = evidence_directory / "simpleFoam.log"
        solver_returncode = run_solver_with_sync(
            ["simpleFoam"],
            cwd=case_directory,
            log_path=solver_log,
            timeout_seconds=args.stage_timeout_seconds,
            synchronizer=synchronizer,
        )
        solver_log_text = solver_log.read_text(encoding="utf-8", errors="replace")
        solver_log_completed = any(line.strip() == "End" for line in solver_log_text.splitlines())
        solver_build = _build_identity(solver_log_text)
        sync_summary = synchronizer.finish(
            solver_returncode=solver_returncode,
            solver_log=solver_log,
        )
        solver_stage = {
            "name": "simpleFoam",
            "argv": ["simpleFoam"],
            "returncode": solver_returncode,
            "log": solver_log.name,
            "log_sha256": _sha256(solver_log) if solver_log.is_file() else None,
        }

    stages = {"blockMesh": mesh_stage}
    if check_stage is not None:
        stages["checkMesh"] = check_stage
    if solver_stage is not None:
        stages["simpleFoam"] = solver_stage

    sync = sync_summary or {}
    sync_manifest_path = Path(sync["manifest"]) if sync.get("manifest") else None
    sync_manifest_doc: dict[str, Any] = {}
    if sync_manifest_path is not None and sync_manifest_path.is_file():
        sync_manifest_doc = json.loads(sync_manifest_path.read_text(encoding="utf-8"))
    sync_errors = sync_manifest_doc.get("errors", [])
    if type(sync_errors) is not list:
        sync_errors = []
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "BLOCKED",
        "case_type": "upstream_foundation_tutorial",
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_commit": actual_commit,
        "source_case_path": UPSTREAM_CASE,
        "source_case_reference": (
            f"https://github.com/{UPSTREAM_REPOSITORY}/tree/{UPSTREAM_COMMIT}/{UPSTREAM_CASE}"
        ),
        "source_mesh_dictionary": UPSTREAM_MESH,
        "source_mesh_dictionary_sha256": _sha256(source_mesh),
        "solver_release": "OpenFOAM Foundation v10",
        "solver_build": solver_build if solver_stage is not None else None,
        "foamToVTK_build": None,
        "environment": environment,
        "case_configuration_sha256": configuration_hash,
        "stages": stages,
        "mesh_ok": mesh_ok,
        "solver_log_completed": solver_log_completed,
        "result_sync": {
            "status": sync.get("status"),
            "record_count": sync.get("record_count", 0),
            "times": sync.get("times", []),
            "manifest": sync.get("manifest"),
            "manifest_sha256": sync.get("manifest_sha256"),
            "error_count": sync.get("error_count", 0),
            "errors": [
                {
                    key: error.get(key)
                    for key in ("time_name", "attempt", "error_type", "message", "status")
                }
                for error in sync_errors[-10:]
                if type(error) is dict
            ],
            "failed_times": sync_manifest_doc.get("failed_times", []),
            "solver_returncode": sync_manifest_doc.get("solver_returncode"),
            "solver_log_status": sync_manifest_doc.get("solver_log_status"),
        },
        "scientific_validation": "BLOCKED",
        "limitations": [
            "The upstream tutorial is an integration fixture, not a cleanroom model.",
            "A successful process and result import do not establish convergence or physical validity.",
            "No independent cleanroom measurements or uncertainty analysis are included.",
        ],
    }
    if sync_manifest_doc:
        receipt["foamToVTK_build"] = sync_manifest_doc.get("solver_build")
        receipt["environment"]["foamToVTK_executable"] = sync_manifest_doc.get("foamToVTK_executable")
    try:
        if (
            mesh_stage["returncode"] == 0
            and check_stage is not None
            and check_stage["returncode"] == 0
            and solver_stage is not None
            and solver_stage["returncode"] == 0
            and sync.get("status") == "results_synced"
        ):
            receipt["status"] = "PASS"
            validate_receipt(receipt)
    except (TypeError, ValueError) as exc:
        receipt["status"] = "BLOCKED"
        receipt["validation_error"] = str(exc)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--case-directory", type=Path, required=True)
    parser.add_argument("--result-directory", type=Path, required=True)
    parser.add_argument("--evidence-directory", type=Path, required=True)
    parser.add_argument("--stage-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    receipt_path = args.evidence_directory / "tutorial-run-receipt.json"
    try:
        receipt = run(args)
    except Exception as exc:
        args.evidence_directory.mkdir(parents=True, exist_ok=True)
        receipt = {
            "schema": SCHEMA,
            "status": "BLOCKED",
            "error": f"{type(exc).__name__}: {exc}",
            "upstream_repository": UPSTREAM_REPOSITORY,
            "upstream_commit": UPSTREAM_COMMIT,
            "source_case_path": UPSTREAM_CASE,
            "scientific_validation": "BLOCKED",
        }
    _write_receipt(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))
    return 0 if receipt.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
