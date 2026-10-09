"""Evidence-preserving opt-in execution of a generated nine-case OpenFOAM family.

This runner does not establish convergence, physical validity, or certification.
Only generated inputs and real external process outputs are recorded.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from .strict_json import load_strict_json_snapshot
from .cfd_grid_family import LEVELS, SCHEMA as FAMILY_SCHEMA

RUN_SCHEMA = "cleanroomx.cfd-grid-run.v1"
STAGES = ("blockMesh", "checkMesh", "simpleFoam")
INPUTS = (
    "system/blockMeshDict", "system/controlDict", "system/fvSchemes",
    "system/fvSolution", "constant/physicalProperties",
    "constant/momentumTransport", "0/U", "0/p",
)
VERSION_PATTERN = re.compile(r"(?:OpenFOAM(?: Foundation)?[- ]?[vV]?)?10(?:\.0+)?\Z")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cases() -> tuple[str, ...]:
    return tuple(f"configuration_{configuration}/{level}"
                 for configuration in (1, 2, 3) for level in LEVELS)


def _verify_generated_inputs(root: Path) -> str:
    """Reject incomplete bundles, unexpected paths, and changed solver inputs."""
    if (root / "manifest.json").is_symlink():
        raise ValueError("Grid family manifest must be a real file, not a symlink")
    manifest_path = (root / "manifest.json").resolve(strict=True)
    if not manifest_path.is_relative_to(root) or not manifest_path.is_file():
        raise ValueError("Grid family manifest must be a file inside the family")
    snapshot = load_strict_json_snapshot(manifest_path, max_bytes=2_000_000)
    raw = snapshot.raw_bytes
    manifest = snapshot.value
    cases = set(_cases())
    if (type(manifest) is not dict
            or manifest.get("schema_version") != FAMILY_SCHEMA
            or type(manifest.get("case_inputs")) is not dict
            or set(manifest["case_inputs"]) != cases
            or type(manifest.get("files")) is not dict):
        raise ValueError("Invalid nine-case grid family manifest")
    expected = {f"{case}/{item}" for case in cases for item in INPUTS}
    if set(manifest["files"]) != expected:
        raise ValueError("Grid family input file list must cover exactly 72 files")
    for relative, expected_sha in manifest["files"].items():
        if type(expected_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError("Invalid generated input SHA-256")
        path = (root / relative).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Generated input resolves outside grid family: " + relative)
        if _hash(path) != expected_sha:
            raise ValueError("Generated solver input changed: " + relative)
    return hashlib.sha256(raw).hexdigest()


def _verify_pristine_case(workdir: Path, key: str) -> None:
    """Reject pre-existing solver output, which can contaminate a fresh run.

    Generated cases contain only their eight manifest-bound source files.
    No earlier polyMesh, time directories, VTK files, postProcessing results,
    or unexplained symlinks may be silently carried into new evidence.
    """
    expected: dict[str, set[str]] = {}
    for relative in INPUTS:
        folder, filename = relative.split("/", 1)
        expected.setdefault(folder, set()).add(filename)
    if {entry.name for entry in workdir.iterdir()} != set(expected):
        raise ValueError(f"Case has unexpected pre-existing solver artifacts: {key}")
    for folder_name, filenames in expected.items():
        folder = workdir / folder_name
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f"Case source directory must be a real directory: {key}/{folder_name}")
        entries = list(folder.iterdir())
        if {entry.name for entry in entries} != filenames:
            raise ValueError(f"Case has unexpected pre-existing solver artifacts: {key}/{folder_name}")
        if any(entry.is_symlink() or not entry.is_file() for entry in entries):
            raise ValueError(f"Case has linked or non-file solver inputs: {key}/{folder_name}")


def _openfoam_version() -> dict:
    executables = {}
    for tool in ("foamVersion", *STAGES):
        found = shutil.which(tool)
        if not found:
            raise ValueError(f"{tool} is not available in PATH; no CFD was executed")
        executables[tool] = found
    try:
        version = subprocess.run(
            [executables["foamVersion"]], capture_output=True, text=True,
            timeout=15, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("foamVersion timed out; no CFD was executed") from exc
    output = ((version.stdout or "") + "\n" + (version.stderr or "")).strip()
    final_line = output.splitlines()[-1].strip() if output else ""
    if version.returncode != 0 or not VERSION_PATTERN.fullmatch(final_line):
        raise ValueError(
            "Expected OpenFOAM Foundation v10 via foamVersion; "
            "version could not be verified; no CFD was executed"
        )
    return {"foam_version": final_line, "executables": executables}


def _write_receipt(root: Path, report: dict) -> None:
    """Persist stage-by-stage receipts with an atomic replacement."""
    target = root / "grid_run_evidence.json"
    staging = root / ".grid_run_evidence.json.tmp"
    with staging.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staging, target)


def run_grid_family(directory: str | Path, *, timeout_seconds: int = 3600) -> dict:
    """Run all nine cases after a strict read-only preflight.

    External commands are opt-in; exit code zero is NOT evidence of CFD
    convergence. Existing solver logs and receipts are never reused.
    """
    if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be an integer in [60,86400]")
    supplied_root = Path(directory)
    if supplied_root.is_symlink():
        raise ValueError("Grid family root must not be a symlink")
    root = supplied_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Grid family root must be a directory")
    digest = _verify_generated_inputs(root)
    receipt = root / "grid_run_evidence.json"
    staging = root / ".grid_run_evidence.json.tmp"
    if receipt.exists() or receipt.is_symlink() or staging.exists() or staging.is_symlink():
        raise FileExistsError("Existing grid execution receipt; refuse rerun/overwrite")
    cases = _cases()
    for config in (1, 2, 3):
        config_dir = root / f"configuration_{config}"
        if config_dir.is_symlink() or not config_dir.is_dir():
            raise ValueError(f"Configuration root must be a real directory: {config_dir.name}")
    for key in cases:
        raw_workdir = root / key
        if raw_workdir.is_symlink():
            raise ValueError(f"Case root must be a real directory: {key}")
        workdir = raw_workdir.resolve(strict=True)
        if not workdir.is_relative_to(root) or not workdir.is_dir():
            raise ValueError("Case directory resolves outside grid family: " + key)
        for stage in STAGES:
            log = workdir / (stage + ".log")
            if log.exists() or log.is_symlink():
                raise FileExistsError("Existing OpenFOAM stage log; refuse overwrite: " + key)
        _verify_pristine_case(workdir, key)
    # Reserve the evidence namespace before any external process starts.
    # An interrupted run leaves this marker for explicit operator review;
    # silently reclaiming it could combine evidence from different attempts.
    reservation = root / ".grid_run_reserved"
    try:
        reservation.mkdir()
    except FileExistsError as exc:
        raise FileExistsError("Existing CFD execution reservation; refuse concurrent or implicit restart") from exc
    # Recheck after reservation: a competing or interrupted invocation must
    # never cause an existing receipt or stage log to be overwritten.
    if receipt.exists() or receipt.is_symlink() or staging.exists() or staging.is_symlink():
        raise FileExistsError("Existing CFD execution evidence after reservation; refuse overwrite")
    environment = _openfoam_version()
    report = {
        "schema_version": RUN_SCHEMA,
        "source_manifest_sha256": digest,
        **environment,
        "status": "incomplete",
        "engineering_review": "BLOCKED",
        "physical_validation": "not_performed",
        "cases": {case: {"status": "not_run", "stages": []} for case in cases},
        "warning": "Solver execution is not residual convergence, mesh independence, physical validation or certification",
    }
    _write_receipt(root, report)
    for key in cases:
        case = report["cases"][key]
        workdir = root / key
        case["status"] = "running"
        _write_receipt(root, report)
        for stage in STAGES:
            log_path = workdir / (stage + ".log")
            returncode = None
            outcome = "failed"
            with log_path.open("x", encoding="utf-8") as output:
                try:
                    completed = subprocess.run(
                        [environment["executables"][stage]], cwd=workdir,
                        stdout=output, stderr=subprocess.STDOUT,
                        timeout=timeout_seconds, check=False,
                    )
                    returncode = completed.returncode
                    outcome = "completed" if returncode == 0 else "failed"
                except subprocess.TimeoutExpired:
                    outcome = "timed_out"
                except OSError:
                    outcome = "launch_failed"
            case["stages"].append({
                "command": stage, "returncode": returncode,
                "status": outcome, "log": f"{key}/{stage}.log",
                "log_sha256": _hash(log_path),
            })
            _write_receipt(root, report)
            if outcome != "completed":
                break
        case["status"] = (
            "executed_requires_convergence_review"
            if len(case["stages"]) == len(STAGES)
            and all(item["status"] == "completed" for item in case["stages"])
            else "execution_failed"
        )
        _write_receipt(root, report)
    if all(case["status"] == "executed_requires_convergence_review"
           for case in report["cases"].values()):
        report["status"] = "executed_requires_convergence_review"
    _write_receipt(root, report)
    return report
