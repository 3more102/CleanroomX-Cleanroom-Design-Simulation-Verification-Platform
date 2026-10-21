"""Auditable, fail-closed numerical log screening of generated room cases.

This does not infer or simulate coupling through doors or validate laminar flow.
Run logs must come from OpenFOAM; synthetic test logs are explicitly fixtures.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .cfd_audit import (
    audit_openfoam_log, has_terminal_end_marker, read_bounded_regular_log,
)
from .cfd_project_rooms import CASE_RE, PROJECT_CFD_SCHEMA
from .strict_json import load_strict_json_snapshot


def _bounded_log(path: Path) -> tuple[str, str]:
    """Read and hash precisely the same bounded solver-log bytes."""
    data = read_bounded_regular_log(path)
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Solver log must be UTF-8: {path.name}") from exc
    return content, hashlib.sha256(data).hexdigest()


def audit_project_room_cases(
    directory: str | Path, *,
    fields: tuple[str, ...] | list[str],
    max_initial_residual: float,
    max_final_residual: float,
    window: int = 3,
    max_global_continuity: float | None = None,
) -> dict:
    """Verify unchanged case inputs, then screen actual solver log files.

    No criteria are silently selected for the project. Numerical screening
    is not a mesh independence, contamination, certification or CFD result.
    """
    root = Path(directory).resolve(strict=True)
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Manifest must be a regular file")
    # Strict, bounded, single-snapshot JSON: duplicate keys and mid-read
    # replacements must not become ambiguous evidence.
    snapshot = load_strict_json_snapshot(manifest_path, max_bytes=4 * 1024 * 1024)
    if manifest_path.is_symlink():
        raise ValueError("Manifest must remain a regular file")
    manifest = snapshot.value
    if not isinstance(manifest, dict) or manifest.get("schema_version") != PROJECT_CFD_SCHEMA:
        raise ValueError("Unsupported project room case manifest")
    cases, files = manifest.get("cases"), manifest.get("files")
    if not isinstance(cases, dict) or not cases or not isinstance(files, dict):
        raise ValueError("Incomplete project room case manifest")
    if any(not isinstance(name, str) or not CASE_RE.fullmatch(name) for name in cases):
        raise ValueError("Unsafe room name in manifest")
    # The generator and runner both need these inputs for every named case.
    # A manifest cannot silently omit their receipts and still pass review.
    mandatory = (
        "system/blockMeshDict", "system/controlDict", "system/fvSchemes",
        "system/fvSolution", "0/U", "0/p",
        "constant/transportProperties", "constant/turbulenceProperties",
    )
    for room in cases:
        for relative in mandatory:
            expected = f"room_{room}/{relative}"
            if expected not in files:
                raise ValueError(f"Missing case input receipt: {expected}")
    for name, checksum in files.items():
        if not isinstance(name, str) or not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Invalid generated file receipt")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe manifest path")
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise ValueError("Generated solver input is missing or symlinked")
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError("Generated solver input escapes its case bundle")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Generated solver input changed: {name}")
    summaries: dict[str, dict] = {}
    overall_ok = True
    for room in sorted(cases):
        directory_path = root / f"room_{room}"
        if directory_path.is_symlink() or not directory_path.is_dir():
            raise ValueError(f"Case directory missing or symlinked: {room}")
        evidence = {}
        issues = []
        for program in ("blockMesh", "checkMesh"):
            try:
                content, sha = _bounded_log(directory_path / (program + ".log"))
                evidence[program] = {
                    "sha256": sha,
                    "has_end_marker": has_terminal_end_marker(content),
                }
                if not evidence[program]["has_end_marker"]:
                    issues.append(f"{program}: missing terminal End marker")
                if re.search(r"FOAM FATAL|floating point exception|segmentation fault", content, re.I):
                    issues.append(f"{program}: fatal error marker")
                if program == "checkMesh":
                    evidence[program]["mesh_ok_marker"] = bool(
                        re.search(r"(?m)^\s*Mesh OK\.?(?:\s*)$", content)
                    )
                    if not evidence[program]["mesh_ok_marker"]:
                        issues.append("checkMesh: no Mesh OK marker")
            except (OSError, ValueError) as exc:
                issues.append(f"{program}: {exc}")
        residuals = None
        try:
            residuals = audit_openfoam_log(
                directory_path / "simpleFoam.log", fields=fields,
                max_initial_residual=max_initial_residual,
                max_final_residual=max_final_residual, window=window,
                max_global_continuity=max_global_continuity,
            )
            if residuals["status"] != "numerically_screened":
                issues.extend(residuals["violations"])
        except (OSError, ValueError) as exc:
            issues.append(f"simpleFoam: {exc}")
        if issues:
            overall_ok = False
        summaries[room] = {
            "status": "numerically_screened" if not issues else "incomplete_or_failed",
            "violations": issues,
            "mesh_logs": evidence,
            "solver_residuals": residuals,
        }
    return {
        "schema": "cleanroomx.project-room-cfd-audit.v1",
        "status": ("numerically_screened_requires_engineering_review" if overall_ok
                   else "incomplete_or_failed"),
        "case_count": len(cases),
        "cases": summaries,
        "project_source_sha256": manifest.get("project_source_sha256"),
        "input_manifest_sha256": hashlib.sha256(snapshot.raw_bytes).hexdigest(),
        "limitations": [
            "No coupled multizone CFD or closed-door leakage prediction",
            "OpenFOAM numeric logs and a Mesh OK marker do not establish physical validation",
            "No independent mass-balance integration, mesh-independence study or ISO classification",
            "Thresholds are explicitly supplied by the user, not certification criteria",
        ],
    }
