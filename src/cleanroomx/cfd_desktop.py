"""Bridge a Studio room to reproducible, explicitly idealized solver studies."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .cfd_openfoam import SCHEMA, export_openfoam_cases, validate_openfoam_spec


def room_study_input(project: dict, room_id: str) -> dict:
    """Use canonical geometry and a uniquely declared verification supply flow."""
    layout = project.get("project", {}).get("metadata", {}).get("spatial_layout", {})
    room = next((r for r in layout.get("rooms", []) if r.get("id") == room_id), None)
    if room is None:
        raise ValueError("Select a room in Design Studio first")
    dimensions = [room.get(k) for k in ("length_m", "width_m", "height_m")]
    if any(type(v) not in (float, int) or not math.isfinite(v) or v <= 0 for v in dimensions):
        raise ValueError("The selected room needs finite, positive dimensions")
    name = room.get("analysis_room_name") or room["name"]
    # Verification inputs are keyed by engineering room names rather than
    # Studio IDs. Never auto-assign a shared name's airflow to multiple rooms.
    identity = name.strip().casefold()
    same_identity = [
        item for item in layout.get("rooms", [])
        if isinstance(item, dict)
        and isinstance(item.get("analysis_room_name") or item.get("name"), str)
        and (item.get("analysis_room_name") or item.get("name")).strip().casefold() == identity
    ]
    ambiguous_room_identity = len(same_identity) != 1
    candidates = []
    for analysis in project.get("analyses", []):
        payload = analysis.get("input", {})
        if analysis.get("kind") == "room_verification":
            rooms = [payload]
        elif analysis.get("kind") == "project_verification":
            rooms = payload.get("rooms", [])
        else:
            continue
        for entry in rooms:
            value = entry.get("supply_airflow_m3_h")
            if entry.get("name") == name and type(value) in (int, float) and math.isfinite(value) and value > 0:
                candidates.append({"analysis_id": analysis["id"], "value_m3_h": value})
    values = {item["value_m3_h"] for item in candidates}
    return {
        "room_id": room_id, "room_name": room["name"],
        "engineering_room_name": name, "room_m": dimensions,
        "volume_m3": math.prod(dimensions),
        "supply_airflow_m3_h": next(iter(values)) if len(values) == 1 and not ambiguous_room_identity else None,
        "supply_sources": candidates,
        "supply_status": "ambiguous_room_identity" if ambiguous_room_identity else
                         "declared" if len(values) == 1 else "conflicting" if values else "missing",
        "project_sha256": hashlib.sha256(json.dumps(project, sort_keys=True, separators=(",", ":"),
                                                   ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
    }


# Only simulation-relevant input changes require another review. Changes to
# unrelated project metadata must not continuously interrupt a CFD run.
_REVIEW_FIELDS = (
    "room_id", "room_name", "engineering_room_name", "room_m",
    "volume_m3", "supply_airflow_m3_h", "supply_sources", "supply_status",
)


def room_study_context_matches(reviewed: dict, current: dict) -> bool:
    """Check that a previously reviewed room context is still authoritative."""
    return (
        isinstance(reviewed, dict) and isinstance(current, dict)
        and all(field in reviewed and field in current and reviewed[field] == current[field]
                for field in _REVIEW_FIELDS)
    )


def prepare_room_study(project: dict, room_id: str, directory: str | Path, *,
                       supply_airflow_m3_h: float, mesh_cells: list[int], max_iterations: int) -> dict:
    """Write a new three-layout bundle and its exact project-input provenance."""
    source = room_study_input(project, room_id)
    if type(supply_airflow_m3_h) not in (int, float) or not math.isfinite(supply_airflow_m3_h) or supply_airflow_m3_h <= 0:
        raise ValueError("Supply airflow must be finite and positive (m³/h)")
    spec = {"schema_version": SCHEMA, "name": source["room_name"] + " — isolated room study",
            "room_m": source["room_m"], "mesh_cells": mesh_cells,
            "supply_flow_m3_s": supply_airflow_m3_h / 3600,
            "kinematic_viscosity_m2_s": 1.5e-5, "max_iterations": max_iterations,
            "output_interval": min(50, max_iterations)}
    validate_openfoam_spec(spec)
    root = Path(directory)
    if root.exists() or root.is_symlink():
        raise FileExistsError("Choose a new run directory; previous runs are retained")
    # The existing exporter also verifies all boundary inputs before publication.
    manifest = export_openfoam_cases(spec, root / "cases")
    provenance = {"schema_version": "cleanroomx.desktop-room-study.v1", **source,
                  "supply_airflow_m3_h_used": supply_airflow_m3_h,
                  "supply_origin": "declared_verification_input" if supply_airflow_m3_h == source["supply_airflow_m3_h"] else "user_override",
                  "input_supply_ach_per_h": supply_airflow_m3_h / source["volume_m3"],
                  "case_spec_sha256": manifest["spec_sha256"],
                  "model": "Three alternative idealized steady isothermal laminar rectangular-room layouts",
                  "assumptions": ["Uses selected-room dimensions and declared or edited supply airflow",
                                  "Device locations, obstructions, doors and inter-room connections are not meshed",
                                  "Pressure setpoints are not computed pressure results",
                                  "No turbulence, heat, contaminant or particle transport is solved"],
                  "scientific_validation": "BLOCKED"}
    (root / "specification.json").write_text(json.dumps(spec, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (root / "project-input.json").write_text(json.dumps(project, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (root / "room-study.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return {"directory": str(root), "cases": str(root / "cases"),
            "results": str(root / "results"), "specification": str(root / "specification.json"),
            "provenance": provenance}


_TIME = re.compile(r"^Time = (\S+)\s*$", re.M)
_RESIDUAL = re.compile(r"Solving for (\w+), Initial residual = ([^,\s]+), Final residual = ([^,\s]+)")
_FATAL = re.compile(r"FOAM FATAL|^\s*(?:Floating point exception|Segmentation fault)\b", re.I | re.M)


def read_solver_progress(directory: str | Path) -> dict:
    """Read all nine stage logs, retaining numerical problems in earlier cases.

    Log progress is diagnostic, not a substitute for exit codes or receipt audits.
    """
    root = Path(directory)
    completed = 0
    latest = None
    issues = []
    for cfg in (1, 2, 3):
        for program in ("blockMesh", "checkMesh", "simpleFoam"):
            path = root / f"configuration_{cfg}" / f"{program}.log"
            if path.is_symlink() or not path.is_file():
                continue
            try:
                with path.open("rb") as stream:
                    stream.seek(max(0, path.stat().st_size - 32768))
                    log_text = stream.read(32768).decode("utf-8", errors="replace")
            except OSError:
                continue
            lines = [line.strip() for line in log_text.splitlines() if line.strip()]
            # Do not classify a line the solver has not finished writing.
            complete_text = log_text if log_text.endswith("\n") else log_text.rsplit("\n", 1)[0] if "\n" in log_text else ""
            times = _TIME.findall(complete_text)
            residuals = _RESIDUAL.findall(complete_text)
            fatal = bool(_FATAL.search(log_text))
            invalid_residual = None
            for field, initial, final in residuals:
                for stage, raw in (("initial", initial), ("final", final)):
                    try:
                        valid = math.isfinite(float(raw))
                    except ValueError:
                        valid = False
                    if not valid:
                        invalid_residual = f"{field} {stage} residual {raw}"
                        break
                if invalid_residual:
                    break
            has_error = fatal or invalid_residual is not None
            ended = bool(lines and lines[-1] == "End" and not has_error)
            completed += int(ended)
            tail = "\n".join(lines[-12:])
            if has_error:
                issues.append({
                    "case": cfg, "program": program,
                    "reason": "OpenFOAM fatal error" if fatal else f"Invalid/non-finite {invalid_residual}",
                    "log": str(path), "tail": tail,
                })
            latest = {
                "case": cfg, "program": program, "iteration": times[-1] if times else None,
                "residual": residuals[-1] if residuals else None, "ended": ended,
                "fatal_error": has_error, "log": str(path), "tail": tail,
            }
    return {"completed_stages": completed, "total_stages": 9, "latest": latest, "issues": issues}
