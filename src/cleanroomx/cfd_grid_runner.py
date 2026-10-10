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
from .persistence import _stable_file_identity, _stable_file_path_matches_opened
from .cfd_blockmesh_source import verify_generated_blockmesh_source
from .cfd_grid_family import LEVELS, SCHEMA as FAMILY_SCHEMA
from .cfd_study import CONFIGURATIONS

RUN_SCHEMA = "cleanroomx.cfd-grid-run.v2"
STAGES = ("blockMesh", "checkMesh", "simpleFoam")
INPUTS = (
    "system/blockMeshDict", "system/controlDict", "system/fvSchemes",
    "system/fvSolution", "constant/physicalProperties",
    "constant/momentumTransport", "0/U", "0/p",
)
VERSION_PATTERN = re.compile(r"(?:OpenFOAM(?: Foundation)?[- ]?[vV]?)?10(?:\.0+)?\Z")


def _hash(path: Path) -> str:
    """Hash a stable, single-linked file revision in bounded memory.

    Before and after the streamed read, bind the opened descriptor to the
    filesystem path and compare revision metadata. This detects replacement
    and ordinary concurrent writes; it is not a guarantee against hostile
    mutations that deliberately restore metadata between observations.
    """
    if path.is_symlink():
        raise ValueError(f"Refuse symlinked CFD evidence: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before_path = path.stat()
        before_handle = os.fstat(handle.fileno())
        if (before_path.st_nlink != 1 or before_handle.st_nlink != 1
                or not _stable_file_path_matches_opened(before_path, before_handle)):
            raise ValueError(f"CFD evidence file changed or hardlinked during hashing: {path}")
        total_bytes = 0
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total_bytes += len(chunk)
            digest.update(chunk)
        after_handle = os.fstat(handle.fileno())
        after_path = path.stat()
    if (path.is_symlink() or after_path.st_nlink != 1
            or after_handle.st_nlink != 1
            or _stable_file_identity(before_path) != _stable_file_identity(after_path)
            or _stable_file_identity(before_handle) != _stable_file_identity(after_handle)
            or not _stable_file_path_matches_opened(after_path, after_handle)
            or total_bytes != after_handle.st_size):
        raise ValueError(f"CFD evidence file changed during hashing: {path}")
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
    if manifest_path.stat().st_nlink != 1:
        raise ValueError("Grid family manifest must not be hardlinked")
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
    # The generator uses one common three-level grid family for all
    # ventilation configurations. Strictly increasing cell totals are a
    # necessary (not sufficient) refinement condition. Require the declared
    # totals to agree across configurations; neither condition independently
    # verifies the actual cell topology inside OpenFOAM.
    reference_counts = None
    for configuration in (1, 2, 3):
        counts = tuple(
            manifest["case_inputs"][f"configuration_{configuration}/{level}"]["mesh_cells"]
            for level in LEVELS
        )
        if any(coarse >= fine for coarse, fine in zip(counts, counts[1:])):
            raise ValueError("Nine-case manifest has non-refining mesh cell counts")
        if reference_counts is not None and counts != reference_counts:
            raise ValueError("Nine-case manifest has inconsistent configuration mesh cell counts")
        reference_counts = counts
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
        if path.stat().st_nlink != 1:
            raise ValueError("Generated solver input must not be hardlinked: " + relative)
        if _hash(path) != expected_sha:
            raise ValueError("Generated solver input changed: " + relative)
    # Read the canonical source dictionary rather than trusting a mutable,
    # self-described mesh-cell count in the family manifest. The source
    # parser is narrowly scoped to CleanroomX's generated ASCII format.
    source_axis_cells = {}
    source_axis_positions = {}
    source_room_bounds = {}
    for key in sorted(cases):
        mesh_source = root / key / "system/blockMeshDict"
        source_geometry = verify_generated_blockmesh_source(
            mesh_source, expected_cells=manifest["case_inputs"][key]["mesh_cells"],
            expected_configuration=manifest["case_inputs"][key]["configuration"],
        )
        if _hash(mesh_source) != manifest["files"][f"{key}/system/blockMeshDict"]:
            raise ValueError("Generated blockMesh source drifted during parsing: " + key)
        source_axis_cells[key] = source_geometry["axis_cell_counts"]
        source_axis_positions[key] = source_geometry["axis_positions_m"]
        source_room_bounds[key] = source_geometry["bounds_m"]

    # Manifest totals cannot distinguish, e.g., 7x8x9 from 7x9x8.
    # Use source-verified Cartesian axes to require the same grid for all
    # ventilation configurations and strictly increasing *each* axis
    # through coarse -> medium -> fine. This does not prove CFD convergence.
    # All nine cases are generated from the SAME room dimensions. A
    # self-rehashed manifest must not allow an isolated translated/scaled
    # model to masquerade as a refinement or ventilation comparison.
    # The CleanroomX generator anchors all three axes at zero metres.
    expected_bounds = source_room_bounds["configuration_1/coarse"]
    if any(low != 0.0 for low, _ in expected_bounds):
        raise ValueError("Nine-case generated room origin is not canonical")
    if any(bounds != expected_bounds for bounds in source_room_bounds.values()):
        raise ValueError("Nine-case generated room bounds differ across cases")
    reference_axis_levels = None
    for configuration in (1, 2, 3):
        axis_levels = tuple(
            source_axis_cells[f"configuration_{configuration}/{level}"]
            for level in LEVELS
        )
        if any(
            any(low[axis] >= high[axis] for axis in range(3))
            for low, high in zip(axis_levels, axis_levels[1:])
        ):
            raise ValueError("Nine-case generated mesh axes do not refine strictly")
        if reference_axis_levels is not None and axis_levels != reference_axis_levels:
            raise ValueError(
                "Nine-case generated mesh axes differ across configurations"
            )
        reference_axis_levels = axis_levels
    # Axis cardinalities and room bounds do not establish identical meshes:
    # the same interior x/y/z planes must be used by each ventilation layout.
    for level in LEVELS:
        reference_planes = source_axis_positions[f"configuration_1/{level}"]
        if any(
            source_axis_positions[f"configuration_{config}/{level}"] != reference_planes
            for config in (2, 3)
        ):
            raise ValueError(
                "Nine-case generated internal grid planes differ across configurations"
            )
    return hashlib.sha256(raw).hexdigest()


def _verify_runtime_source_tree(workdir: Path, key: str) -> None:
    """Reject unmanifested input files even after OpenFOAM creates polyMesh.

    Only `constant/polyMesh` may be generated by the planned blockMesh
    stage. Runtime time directories and postProcessing are outside the three
    immutable source directories; their numerical validity needs review.
    """
    for folder in ("system", "0", "constant"):
        directory = workdir / folder
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"Unsafe solver source directory: {key}/{folder}")
        allowed = {
            relative.split("/", 1)[1]
            for relative in INPUTS if relative.startswith(folder + "/")
        }
        if folder == "constant":
            mesh = directory / "polyMesh"
            if mesh.is_symlink() or (mesh.exists() and not mesh.is_dir()):
                raise ValueError(f"Unsafe generated mesh directory: {key}/constant/polyMesh")
            if mesh.is_dir():
                # The mesh is solver-generated, not one of the 72 signed
                # inputs. It must nevertheless contain only local, ordinary
                # files/directories: checkMesh/simpleFoam must not read an
                # externally writable alias through this output tree.
                def _mesh_walk_error(exc: OSError) -> None:
                    raise ValueError(
                        f"Unreadable generated mesh tree: {key}/constant/polyMesh"
                    ) from exc

                for parent, directories, files in os.walk(
                    mesh, topdown=True, followlinks=False,
                    onerror=_mesh_walk_error,
                ):
                    for name in directories:
                        entry = Path(parent) / name
                        if entry.is_symlink() or not entry.is_dir():
                            raise ValueError(
                                f"Unsafe generated mesh directory: {key}/{entry.relative_to(workdir)}"
                            )
                    for name in files:
                        entry = Path(parent) / name
                        if (entry.is_symlink() or not entry.is_file()
                                or entry.stat().st_nlink != 1):
                            raise ValueError(
                                f"Unsafe generated mesh file: {key}/{entry.relative_to(workdir)}"
                            )
                if mesh.is_symlink() or not mesh.is_dir():
                    raise ValueError(f"Generated mesh replaced during inspection: {key}")
                allowed.add("polyMesh")
        if {entry.name for entry in directory.iterdir()} != allowed:
            raise ValueError(f"Unexpected solver source directory entries: {key}/{folder}")


def _mesh_file_hashes(workdir: Path, key: str) -> dict[str, str]:
    """Bind the final local polyMesh file bytes, without assessing mesh quality.

    This captures solver-generated output that is intentionally absent from
    the immutable 72-input manifest. The caller must preserve these digests
    in the execution receipt and recheck them during offline verification.
    """
    mesh = workdir / "constant" / "polyMesh"
    if mesh.is_symlink() or (mesh.exists() and not mesh.is_dir()):
        raise ValueError(f"Unsafe generated mesh root: {key}/constant/polyMesh")
    if not mesh.exists():
        return {}
    files: dict[str, str] = {}
    total_bytes = 0

    def _walk_error(exc: OSError) -> None:
        raise ValueError(f"Unreadable mesh output: {key}/constant/polyMesh") from exc

    for parent, directories, filenames in os.walk(
        mesh, topdown=True, followlinks=False, onerror=_walk_error,
    ):
        for directory in directories:
            entry = Path(parent) / directory
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError(f"Unsafe mesh subdirectory: {key}/{entry.relative_to(workdir)}")
        for filename in filenames:
            entry = Path(parent) / filename
            if entry.is_symlink() or not entry.is_file() or entry.stat().st_nlink != 1:
                raise ValueError(f"Unsafe generated mesh file: {key}/{entry.relative_to(workdir)}")
            relative = entry.relative_to(mesh).as_posix()
            if len(files) >= 4096:
                raise ValueError(f"Too many generated mesh files: {key}")
            total_bytes += entry.stat().st_size
            if total_bytes > 1_073_741_824:
                raise ValueError(f"Mesh output exceeds 1 GiB evidence limit: {key}")
            files[relative] = _hash(entry)
    if mesh.is_symlink() or not mesh.is_dir():
        raise ValueError(f"Generated mesh root changed while hashing: {key}")
    return dict(sorted(files.items()))


def _verify_stage_source_snapshot(
    root: Path, key: str, manifest_sha: str, expected_hashes: dict,
) -> None:
    """Recheck this case's immutable inputs before *each* external stage.

    A correct initial preflight is insufficient when source files can change
    during foamVersion or a prior solver stage. This bounds, but cannot remove,
    filesystem time-of-check/time-of-use races on untrusted storage.
    """
    manifest = root / "manifest.json"
    if (manifest.is_symlink() or not manifest.is_file()
            or manifest.stat().st_nlink != 1 or _hash(manifest) != manifest_sha):
        raise ValueError("Grid family manifest changed during execution")
    configuration, _ = key.split("/", 1)
    workdir = root / key
    if (root / configuration).is_symlink() or workdir.is_symlink():
        raise ValueError(f"Case directory replaced during execution: {key}")
    if not workdir.is_dir():
        raise ValueError(f"Case directory missing during execution: {key}")
    _verify_runtime_source_tree(workdir, key)
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
        if resolved.stat().st_nlink != 1:
            raise ValueError(f"Case input hardlinked during execution: {key}/{relative}")
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
        "cases": {case: {"status": "not_run", "stages": [], "mesh_files": {}} for case in cases},
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
            # Once blockMesh has finished, the generated mesh becomes an
            # immutable baseline for checkMesh/simpleFoam in this workflow.
            # A concurrent edit between stage invocations is not accepted.
            if (stage != "blockMesh"
                    and _mesh_file_hashes(workdir, key) != case["mesh_files"]):
                raise ValueError(f"Generated mesh changed between solver stages: {key}")
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
            # An external process may alter the source bundle *during* its
            # last stage; a pre-stage check alone cannot catch that. Record
            # the stage and its real exit code, but never report completion
            # for an attempt whose originally accepted input bytes drifted.
            try:
                _verify_stage_source_snapshot(root, key, digest, expected_hashes)
                current_mesh = _mesh_file_hashes(workdir, key)
                if stage == "blockMesh":
                    # Record the immediate post-blockMesh revision rather than
                    # accepting whatever files remain after later solver stages.
                    case["mesh_files"] = current_mesh
                elif current_mesh != case["mesh_files"]:
                    outcome = "source_drift"
            except (OSError, ValueError):
                outcome = "source_drift"
            if stage == "checkMesh" and outcome == "completed":
                # An exit code of zero does not guarantee Mesh OK.
                # Post-run mesh topology and count audits remain separate.
                from .cfd_checkmesh_log import screen_checkmesh_verdict
                try:
                    screen_checkmesh_verdict(
                        log_path,
                        expected_cells=manifest_snapshot.value["case_inputs"][key]["mesh_cells"],
                    )
                except (OSError, ValueError):
                    outcome = "mesh_check_rejected"
            case["stages"].append({
                "command": stage, "returncode": returncode,
                "status": outcome, "log": f"{key}/{stage}.log",
                "log_sha256": _hash(log_path),
            })
            _write_receipt(root, report)
            if outcome != "completed":
                break
        # Recheck the final mesh against the immediately post-blockMesh
        # snapshot. Do not overwrite that baseline with changed later output.
        try:
            if _mesh_file_hashes(workdir, key) != case["mesh_files"]:
                if case["stages"]:
                    case["stages"][-1]["status"] = "source_drift"
        except (OSError, ValueError):
            if case["stages"]:
                case["stages"][-1]["status"] = "source_drift"
        case["status"] = (
            "executed_requires_convergence_review"
            if len(case["stages"]) == len(STAGES)
            and all(item["status"] == "completed" for item in case["stages"])
            else "execution_failed"
        )
        _write_receipt(root, report)
        if case["stages"] and case["stages"][-1]["status"] == "source_drift":
            # Source custody is compromised; do not launch a later case or
            # collapse evidence into a green execution-level status.
            return report
    if all(case["status"] == "executed_requires_convergence_review"
           for case in report["cases"].values()):
        report["status"] = "executed_requires_convergence_review"
    _write_receipt(root, report)
    return report
