"""Audit multiple explicit OpenFOAM Foundation v10 foamToVTK time selections.

The audit proves only that the requested solver times were exported and that
their synthetic U, p, phi, and supported boundary-patch datasets reproduce the
corresponding native files. It does not assess CFD convergence or physical
validity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from .cfd_openfoam import _foundation_v10_banner
from .cfd_vtk import (
    audit_openfoam_vtk_boundary_patch,
    audit_openfoam_vtk_pressure,
    audit_openfoam_vtk_surface_flux,
    audit_openfoam_vtk_velocity,
    import_vtk_case,
)


SCHEMA = "cleanroomx.openfoam-vtk-time-selection-evidence.v2"
PATCH_NAMES = ("inlet", "outlet", "walls")
CASE_IDS = tuple(
    f"configuration_{configuration}/{level}"
    for configuration in (1, 2, 3)
    for level in ("coarse", "medium", "fine")
)
_TIME_LINE = re.compile(r"^Time:\s*(\S+)\s*$", re.MULTILINE)


def _validated_selected_times(value: str | tuple[str, ...] | list[str]) -> list[str]:
    """Parse a nonempty, strictly increasing comma-separated time selection."""
    if type(value) is str:
        requested = value.split(",")
    elif type(value) in (tuple, list):
        requested = list(value)
    else:
        raise ValueError("Selected times must be a comma-separated string or a list of names")
    if not requested:
        raise ValueError("At least one finite numeric OpenFOAM time name is required")

    selected: list[str] = []
    numeric: list[float] = []
    for item in requested:
        if type(item) is not str:
            raise ValueError("Every selected OpenFOAM time name must be text")
        name = item.strip()
        if re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", name) is None:
            raise ValueError("Selected times must be finite numeric OpenFOAM time names")
        number = float(name)
        if not math.isfinite(number):
            raise ValueError("Selected times must be finite numeric OpenFOAM time names")
        if numeric and number <= numeric[-1]:
            raise ValueError("Selected times must be unique and strictly increasing")
        if number in numeric:
            raise ValueError("Selected times must be unique and strictly increasing")
        selected.append(name)
        numeric.append(number)
    return selected


def parse_foam_to_vtk_time_log(
    log_text: str,
    expected_times: str | tuple[str, ...] | list[str],
) -> list[str]:
    """Require the exact ordered time set and one clean terminal ``End``."""
    if type(log_text) is not str:
        raise ValueError("foamToVTK log must be text")
    expected = _validated_selected_times(expected_times)

    selected = _TIME_LINE.findall(log_text)
    if selected != expected:
        raise ValueError(
            f"foamToVTK selected times {selected!r}; expected exactly {expected!r}"
        )
    terminal_lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    if terminal_lines.count("End") != 1 or not terminal_lines or terminal_lines[-1] != "End":
        raise ValueError("foamToVTK log must contain exactly one terminal End line")
    if re.search(r"FOAM FATAL ERROR|Fatal Error", log_text, re.IGNORECASE):
        raise ValueError("foamToVTK log contains a fatal error")
    return selected


def _verified_patch_face_count(patch_parity: dict) -> int:
    """Sum patch faces only when native and VTK coverage agree for all patches."""
    if type(patch_parity) is not dict or set(patch_parity) != set(PATCH_NAMES):
        raise ValueError("Patch parity must contain exactly inlet, outlet, and walls")
    total = 0
    for patch_name in PATCH_NAMES:
        parity = patch_parity[patch_name]
        if type(parity) is not dict or parity.get("status") != "PASS":
            raise ValueError(f"{patch_name} patch parity is incomplete")
        native_count = parity.get("native_face_count")
        vtk_count = parity.get("vtk_face_count")
        if (
            type(native_count) is not int
            or type(vtk_count) is not int
            or native_count <= 0
            or vtk_count != native_count
        ):
            raise ValueError(f"{patch_name} patch face coverage is incomplete or inconsistent")
        total += native_count
    return total


def _sha256_file(path: Path, root: Path) -> dict:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside the evidence family: {path}") from exc
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Refusing a symbolic path component: {current}")
        if index < len(relative.parts) - 1 and not current.is_dir():
            raise ValueError(f"Expected a regular directory: {current}")
    if not path.is_file():
        raise ValueError(f"Expected a regular non-symlink file: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError(f"File escaped the evidence family: {path}")
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after_fd = os.fstat(stream.fileno())
    after_path = path.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_fd = (after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns)
    identity_after = (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns)
    if identity_before != identity_fd or identity_fd != identity_after:
        raise ValueError(f"File changed while hashing: {path}")
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest.hexdigest(),
        "size_bytes": before.st_size,
    }


def _read_json_file(path: Path, root: Path) -> tuple[dict, str]:
    record = _sha256_file(path, root)
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"Expected a JSON object in {path.name}")
    if _sha256_file(path, root)["sha256"] != record["sha256"]:
        raise ValueError(f"JSON file changed while being parsed: {path.name}")
    return value, record["sha256"]


def _atomic_json(path: Path, document: dict) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def audit_openfoam_vtk_time_selection(
    family_root: str | Path,
    *,
    selected_times: str | tuple[str, ...] | list[str] = ("50", "100"),
) -> dict:
    """Run and verify one explicit multi-time export for the nine-case family."""
    candidate_root = Path(family_root)
    if candidate_root.is_symlink() or not candidate_root.is_dir():
        raise ValueError("Evidence family must be a regular, non-symlink directory")
    root = candidate_root.resolve(strict=True)
    selected_times = _validated_selected_times(selected_times)
    time_argument = ",".join(selected_times)
    log_suffix = "-".join(name.replace("+", "p") for name in selected_times)

    if os.environ.get("WM_PROJECT") != "OpenFOAM" or os.environ.get("WM_PROJECT_VERSION") != "10":
        raise RuntimeError("Expected an OpenFOAM Foundation v10 runtime environment")

    manifest, manifest_sha = _read_json_file(root / "manifest.json", root)
    receipt_path = root / "grid_execution_evidence.json"
    receipt, receipt_sha = _read_json_file(receipt_path, root)
    if manifest.get("schema_version") != "cleanroomx.cfd-grid-family.v1":
        raise ValueError("Unexpected grid-family manifest schema")
    if receipt.get("schema_version") != "cleanroomx.openfoam-grid-execution-evidence.v1":
        raise ValueError("Unexpected Foundation v10 execution receipt schema")
    if receipt.get("status") != "executed_requires_convergence_review":
        raise ValueError("The nine-case solver receipt is not complete")
    if receipt.get("family_spec_sha256") != manifest.get("family_spec_sha256"):
        raise ValueError("Execution receipt does not match the generated family")
    cases = receipt.get("cases")
    if type(cases) is not dict or set(cases) != set(CASE_IDS):
        raise ValueError("Execution receipt must contain exactly the nine expected cases")
    if receipt.get("scientific_validation", "BLOCKED") != "BLOCKED":
        raise ValueError("The time-selection audit must preserve scientific validation BLOCKED")

    executables = receipt.get("executables")
    executable = executables.get("foamToVTK") if isinstance(executables, dict) else None
    if not isinstance(executable, str) or not Path(executable).is_file():
        raise ValueError("Execution receipt does not bind a usable foamToVTK executable")
    discovered = shutil.which("foamToVTK")
    if discovered is None or Path(discovered).resolve(strict=True) != Path(executable).resolve(strict=True):
        raise ValueError("Current foamToVTK executable differs from the execution receipt")
    solver_build = receipt.get("solver_build")
    if not isinstance(solver_build, str) or not solver_build:
        raise ValueError("Execution receipt has no Foundation v10 build identity")

    report_path = root / "vtk_time_selection_evidence.json"
    if report_path.exists() or report_path.is_symlink():
        raise FileExistsError("Refusing to overwrite prior explicit-time evidence")
    report = {
        "schema_version": SCHEMA,
        "status": "running",
        "interpretation": "execution_and_serialization_diagnostics_only",
        "scientific_validation": "BLOCKED",
        "solver_release": "OpenFOAM Foundation v10",
        "solver_build": solver_build,
        "selected_times": selected_times,
        "selection_options": ["-time", time_argument, "-useTimeName"],
        "manifest_sha256": manifest_sha,
        "execution_receipt_sha256": receipt_sha,
        "cases": {},
    }
    _atomic_json(report_path, report)

    for case_id in CASE_IDS:
        try:
            case_dir = root / case_id
            if case_dir.is_symlink() or not case_dir.is_dir():
                raise ValueError("Case directory is missing, symbolic, or invalid")
            case_dir = case_dir.resolve(strict=True)
            if not case_dir.is_relative_to(root):
                raise ValueError("Case directory escaped the evidence family")
            base_record = cases[case_id]
            stages = base_record.get("stages") if isinstance(base_record, dict) else None
            if (
                not isinstance(stages, list)
                or [stage.get("command") for stage in stages if isinstance(stage, dict)]
                != ["blockMesh", "checkMesh", "simpleFoam", "foamToVTK"]
                or any(stage.get("returncode") != 0 for stage in stages)
            ):
                raise ValueError("Case does not have four successful baseline solver stages")

            case_inputs = manifest.get("case_inputs", {}).get(case_id)
            if not isinstance(case_inputs, dict):
                raise ValueError("Case is missing generated-input manifest metadata")
            expected_cells = case_inputs.get("mesh_cells")
            if type(expected_cells) is not int or expected_cells <= 0:
                raise ValueError("Manifest mesh-cell count is invalid")

            vtk_dir = case_dir / "VTK"
            if vtk_dir.is_symlink() or not vtk_dir.is_dir():
                raise ValueError("Baseline VTK output directory is missing or symbolic")
            native_paths_by_time: dict[str, dict[str, Path]] = {}
            native_before_by_time: dict[str, dict[str, dict]] = {}
            output_paths_by_time: dict[str, dict] = {}
            for selected_time in selected_times:
                time_dir = case_dir / selected_time
                if time_dir.is_symlink() or not time_dir.is_dir():
                    raise ValueError(f"Requested solver time directory {selected_time!r} is missing")
                native_paths = {field: time_dir / field for field in ("U", "p", "phi")}
                native_paths_by_time[selected_time] = native_paths
                native_before_by_time[selected_time] = {
                    field: _sha256_file(path, root) for field, path in native_paths.items()
                }
                internal_path = vtk_dir / f"{case_dir.name}_{selected_time}.vtk"
                patch_paths = {
                    patch: vtk_dir / patch / f"{patch}_{selected_time}.vtk"
                    for patch in PATCH_NAMES
                }
                surface_path = vtk_dir / "surfaceFields" / f"surfaceFields_{selected_time}.vtk"
                selected_outputs = [internal_path, *patch_paths.values(), surface_path]
                if any(path.exists() or path.is_symlink() for path in selected_outputs):
                    raise FileExistsError(
                        f"Explicit-time VTK outputs for {selected_time!r} already exist; refusing to overwrite"
                    )
                output_paths_by_time[selected_time] = {
                    "internal": internal_path,
                    "patches": patch_paths,
                    "surface_phi": surface_path,
                }

            log_path = case_dir / f"foamToVTK-times-{log_suffix}.log"
            if log_path.exists() or log_path.is_symlink():
                raise FileExistsError("Explicit-time foamToVTK log already exists")
            arguments = [
                "-time", time_argument,
                "-useTimeName",
                "-fields", "( U p phi )",
                "-surfaceFields",
                "-ascii",
                "-poly",
                "-noPointValues",
            ]
            try:
                result = subprocess.run(
                    [executable, *arguments],
                    cwd=case_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=600,
                    check=False,
                )
                log_bytes = result.stdout or b""
                returncode = result.returncode
            except subprocess.TimeoutExpired as exc:
                captured = exc.stdout or b""
                if isinstance(captured, str):
                    captured = captured.encode("utf-8", errors="replace")
                log_bytes = captured
                returncode = 124
            with log_path.open("xb") as output:
                output.write(log_bytes)
            log_text = log_bytes.decode("utf-8", errors="replace")
            log_record = _sha256_file(log_path, root)
            if returncode != 0:
                raise RuntimeError(f"foamToVTK returned {returncode} for {case_id}")
            banner = _foundation_v10_banner(log_text)
            if not banner.get("is_foundation_v10") or banner.get("build") != solver_build:
                raise ValueError("Explicit-time export did not report the bound Foundation v10 build")
            selected_log_times = parse_foam_to_vtk_time_log(log_text, selected_times)

            time_records: dict[str, dict] = {}
            for selected_time in selected_times:
                native_paths = native_paths_by_time[selected_time]
                native_before = native_before_by_time[selected_time]
                time_outputs = output_paths_by_time[selected_time]
                internal_path = time_outputs["internal"]
                patch_paths = time_outputs["patches"]
                surface_path = time_outputs["surface_phi"]
                output_records = {
                    "internal": _sha256_file(internal_path, root),
                    "surface_phi": _sha256_file(surface_path, root),
                    "patches": {
                        patch: _sha256_file(path, root)
                        for patch, path in patch_paths.items()
                    },
                }
                for field, path in native_paths.items():
                    if _sha256_file(path, root) != native_before[field]:
                        raise ValueError(
                            f"Native {field} field at time {selected_time!r} changed during VTK export"
                        )

                imported = import_vtk_case(internal_path)
                if imported.get("mesh_cells") != expected_cells:
                    raise ValueError(
                        f"Explicit-time VTK cell count differs from generated inputs at {selected_time!r}"
                    )
                velocity = audit_openfoam_vtk_velocity(native_paths["U"], internal_path)
                pressure = audit_openfoam_vtk_pressure(native_paths["p"], internal_path)
                if velocity.get("status") != "PASS" or pressure.get("status") != "PASS":
                    raise ValueError(f"Explicit-time internal U/p parity did not pass at {selected_time!r}")
                if velocity.get("cell_count") != expected_cells or pressure.get("cell_count") != expected_cells:
                    raise ValueError(
                        f"Explicit-time internal U/p parity did not cover every cell at {selected_time!r}"
                    )

                patch_parity = {}
                for patch, path in patch_paths.items():
                    parity = audit_openfoam_vtk_boundary_patch(
                        native_paths["U"],
                        native_paths["p"],
                        case_dir / "constant" / "polyMesh",
                        path,
                        patch,
                    )
                    if parity.get("status") != "PASS":
                        raise ValueError(
                            f"Explicit-time {patch} patch parity did not pass at {selected_time!r}"
                        )
                    patch_parity[patch] = parity
                total_patch_faces = _verified_patch_face_count(patch_parity)

                surface_flux = audit_openfoam_vtk_surface_flux(
                    native_paths["phi"],
                    case_dir / "constant" / "polyMesh",
                    surface_path,
                )
                if surface_flux.get("status") != "PASS":
                    raise ValueError(f"Explicit-time surface phi parity did not pass at {selected_time!r}")

                time_records[selected_time] = {
                    "native_fields": native_before,
                    "datasets": output_records,
                    "internal_cell_count": expected_cells,
                    "velocity_components_compared": velocity.get("compared_velocity_components"),
                    "pressure_values_compared": pressure.get("compared_scalar_values"),
                    "patch_face_count": total_patch_faces,
                    "patch_parity": patch_parity,
                    "surface_flux_face_count": surface_flux.get("face_count"),
                    "surface_flux_components_compared": surface_flux.get("compared_flux_vector_components"),
                    "field_parity": {"U": velocity, "p": pressure},
                    "surface_flux_parity": surface_flux,
                }

            report["cases"][case_id] = {
                "selected_log_times": selected_log_times,
                "returncode": returncode,
                "command": ["foamToVTK", *arguments],
                "openfoam": banner,
                "log": log_record,
                "times": time_records,
                "status": "DIAGNOSTIC_ONLY",
            }
            _atomic_json(report_path, report)
        except Exception as exc:
            report["status"] = "failed"
            report["failure"] = {
                "case": case_id,
                "type": type(exc).__name__,
                "message": str(exc),
            }
            _atomic_json(report_path, report)
            raise

    if set(report["cases"]) != set(CASE_IDS):
        report["status"] = "failed"
        report["failure"] = {"type": "ValueError", "message": "Missing explicit-time case records"}
        _atomic_json(report_path, report)
        raise ValueError("Missing explicit-time case records")
    if _sha256_file(root / "manifest.json", root)["sha256"] != manifest_sha:
        raise ValueError("Generated input manifest changed during time-selection audit")
    if _sha256_file(receipt_path, root)["sha256"] != receipt_sha:
        raise ValueError("Baseline execution receipt changed during time-selection audit")

    report["status"] = "selection_and_serialization_diagnostics_passed"
    all_time_records = [
        time_record
        for case in report["cases"].values()
        for time_record in case["times"].values()
    ]
    report["summary"] = {
        "cases": len(report["cases"]),
        "selected_times_per_case": selected_times,
        "selected_time_count_per_case": len(selected_times),
        "internal_cell_datasets": len(all_time_records),
        "patch_datasets": sum(len(row["datasets"]["patches"]) for case in report["cases"].values() for row in case["times"].values()),
        "surface_phi_datasets": len(all_time_records),
        "internal_cells_compared": sum(row["internal_cell_count"] for row in all_time_records),
        "velocity_components_compared": sum(row["velocity_components_compared"] for row in all_time_records),
        "pressure_values_compared": sum(row["pressure_values_compared"] for row in all_time_records),
        "patch_faces_compared": sum(row["patch_face_count"] for row in all_time_records),
        "surface_flux_faces_compared": sum(row["surface_flux_face_count"] for row in all_time_records),
        "surface_flux_components_compared": sum(row["surface_flux_components_compared"] for row in all_time_records),
    }
    _atomic_json(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export and verify exact-time OpenFOAM v10 foamToVTK selections."
    )
    parser.add_argument("family_root", type=Path)
    parser.add_argument(
        "--times",
        "--time",
        dest="selected_times",
        default="50,100",
        help="Comma-separated, strictly increasing OpenFOAM time names",
    )
    args = parser.parse_args(argv)
    try:
        report = audit_openfoam_vtk_time_selection(
            args.family_root,
            selected_times=args.selected_times,
        )
    except Exception as exc:
        print(f"OpenFOAM VTK time-selection audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        f"OpenFOAM v10 explicit-time export passed: times={','.join(report['selected_times'])}; "
        f"cases={summary['cases']}; U_components={summary['velocity_components_compared']}; "
        f"p_values={summary['pressure_values_compared']}; "
        f"patch_faces={summary['patch_faces_compared']}; "
        f"surface_phi_faces={summary['surface_flux_faces_compared']}; "
        "scientific_validation=BLOCKED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
