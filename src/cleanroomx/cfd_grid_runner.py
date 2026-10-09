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
from .cfd_study import CONFIGURATIONS

RUN_SCHEMA = "cleanroomx.cfd-grid-run.v1"
STAGES = ("blockMesh", "checkMesh", "simpleFoam")
INPUTS = (
    "system/blockMeshDict", "system/controlDict", "system/fvSchemes",
    "system/fvSolution", "constant/physicalProperties",
    "constant/momentumTransport", "0/U", "0/p",
)
VERSION_PATTERN = re.compile(r"(?:OpenFOAM(?: Foundation)?[- ]?[vV]?)?10(?:\.0+)?\Z")


def _hash(path: Path) -> str:
    """Hash solver inputs and logs without loading potentially large files into RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cases() -> tuple[str, ...]:
    return tuple(f"configuration_{configuration}/{level}"
                 for configuration in (1, 2, 3) for level in LEVELS)


_FAMILY_FIELDS = {"schema_version", "family_spec_sha256", "status", "case_inputs", "files"}
_CASE_METADATA_FIELDS = {
    "configuration", "layout", "mesh_cells", "mesh", "inlet_normal_speed_m_s",
    "requested_inlet_flow_m3_s", "model", "target", "limitations",
}
_MESH_METADATA_FIELDS = {
    "inlet_face_count", "outlet_face_count", "inlet_area_m2",
    "outlet_area_m2", "nominal_cell_volume_m3",
}
_CASE_LIMITATIONS = [
    "no underfloor plenum", "no scalar or particle transport",
    "no turbulence or buoyancy", "no mesh convergence proof",
    "empty rectangular room",
]


def _verify_case_metadata(key: str, value: object) -> None:
    """Reject malformed or fabricated physical-qualification metadata."""
    config_number = int(key.split("/", 1)[0].removeprefix("configuration_"))
    if type(value) is not dict or set(value) != _CASE_METADATA_FIELDS:
        raise ValueError(f"Malformed case metadata: {key}")
    if (type(value["configuration"]) is not int
            or value["configuration"] != config_number
            or value["layout"] != CONFIGURATIONS[config_number]
            or type(value["mesh_cells"]) is not int
            or not 1 <= value["mesh_cells"] <= 20_000
            or value["model"] != "steady incompressible isothermal laminar air (SIMPLE)"
            or value["target"] != "OpenFOAM Foundation v10 / simpleFoam"
            or value["limitations"] != _CASE_LIMITATIONS):
        raise ValueError(f"Inconsistent case metadata: {key}")
    mesh = value["mesh"]
    if type(mesh) is not dict or set(mesh) != _MESH_METADATA_FIELDS:
        raise ValueError(f"Malformed mesh metadata: {key}")
    for field in ("inlet_face_count", "outlet_face_count"):
        if type(mesh[field]) is not int or mesh[field] <= 0:
            raise ValueError(f"Invalid mesh face count: {key}/{field}")
    for field in (
        "inlet_area_m2", "outlet_area_m2", "nominal_cell_volume_m3",
    ):
        measure = mesh[field]
        if type(measure) not in (int, float) or not 0 < measure < float("inf"):
            raise ValueError(f"Invalid mesh quantity: {key}/{field}")
    for field in ("inlet_normal_speed_m_s", "requested_inlet_flow_m3_s"):
        measure = value[field]
        if type(measure) not in (int, float) or not 0 < measure < float("inf"):
            raise ValueError(f"Invalid case quantity: {key}/{field}")


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
            or set(manifest) != _FAMILY_FIELDS
            or manifest.get("schema_version") != FAMILY_SCHEMA
            or manifest.get("status") != "generated_not_executed"
            or type(manifest.get("family_spec_sha256")) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["family_spec_sha256"])
            or type(manifest.get("case_inputs")) is not dict
            or set(manifest["case_inputs"]) != cases
            or type(manifest.get("files")) is not dict):
        raise ValueError("Invalid nine-case grid family manifest")
    for key, metadata in manifest["case_inputs"].items():
        _verify_case_metadata(key, metadata)
    expected = {f"{case}/{item}" for case in cases for item in INPUTS}
    if set(manifest["files"]) != expected:
        raise ValueError("Grid family input file list must cover exactly 72 files")
    for relative, expected_sha in manifest["files"].items():
        if type(expected_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError("Invalid generated input SHA-256")
        candidate = root / relative
        if candidate.is_symlink():
            raise ValueError("Generated solver input must not be a symlink: " + relative)
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Generated input resolves outside grid family: " + relative)
        if _hash(path) != expected_sha:
            raise ValueError("Generated solver input changed: " + relative)
    return hashlib.sha256(raw).hexdigest()


def _verify_stage_source_snapshot(
    root: Path, key: str, manifest_sha: str, expected_hashes: dict,
) -> None:
    """Recheck this case's immutable inputs before *each* external stage.

    A correct initial preflight is insufficient when source files can change
    during foamVersion or a prior solver stage. This bounds, but cannot remove,
    filesystem time-of-check/time-of-use races on untrusted storage.
    """
    manifest = root / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or _hash(manifest) != manifest_sha:
        raise ValueError("Grid family manifest changed during execution")
    configuration, _ = key.split("/", 1)
    workdir = root / key
    if (root / configuration).is_symlink() or workdir.is_symlink():
        raise ValueError(f"Case directory replaced during execution: {key}")
    if not workdir.is_dir():
        raise ValueError(f"Case directory missing during execution: {key}")
    for relative in INPUTS:
        folder, _ = relative.split("/", 1)
        source_dir = workdir / folder
        source = workdir / relative
        if (source_dir.is_symlink() or source.is_symlink()
                or not source.is_file()):
            raise ValueError(f"Case input missing or linked during execution: {key}/{relative}")
        resolved = source.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"Case input escaped family during execution: {key}/{relative}")
        if _hash(resolved) != expected_hashes[f"{key}/{relative}"]:
            raise ValueError(f"Case input changed during execution: {key}/{relative}")


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
    except OSError as exc:
        raise ValueError("foamVersion could not be launched; no CFD was executed") from exc
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
    # Bind later per-stage checks to the exact manifest bytes already
    # accepted by the complete nine-case preflight.
    manifest_snapshot = load_strict_json_snapshot(
        root / "manifest.json", max_bytes=2_000_000
    )
    if ((root / "manifest.json").is_symlink()
            or hashlib.sha256(manifest_snapshot.raw_bytes).hexdigest() != digest):
        raise ValueError("Grid family manifest changed during preflight")
    expected_hashes = manifest_snapshot.value["files"]
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
    # Validate tool availability before reserving a run: a missing or invalid
    # OpenFOAM installation must not leave an orphaned execution reservation.
    environment = _openfoam_version()
    # Reserve the evidence namespace before any external solver process starts.
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
            # Refuse changed inputs even if the initial preflight succeeded.
            # Preserve the incomplete receipt and reservation on failure;
            # never launch another solver against inconsistent sources.
            _verify_stage_source_snapshot(root, key, digest, expected_hashes)
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
            # Successful termination without any diagnostic output is not a
            # verifiable stage completion. Preserve the true exit code while
            # blocking dependent stages, rather than claiming solver success.
            if outcome == "completed" and log_path.stat().st_size == 0:
                outcome = "empty_output"
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
