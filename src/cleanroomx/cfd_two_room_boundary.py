"""Receipt-bound OpenFOAM phi boundary-face screening for a two-room fixture.

Reads the *solver's* final boundary fluxes. This is not an independently
measured conservation balance, field convergence, or cleanroom qualification.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any

from .cfd_convergence_triage import (
    _MAX_GRID_FLUX_BYTES,
    _grid_phi_patch_values,
    _grid_poly_mesh_patch_counts,
    _read_stable_grid_text,
)
from .cfd_proofgraph import _read_json, proofgraph_from_two_room_receipt

SCHEMA = "cleanroomx.cfd-two-room-boundary-policy.v1"
RESULT_SCHEMA = "cleanroomx.cfd-two-room-boundary-screen.v1"
LIMITS = (
    "max_total_boundary_imbalance_percent",
    "max_wall_gross_leakage_percent",
    "max_reverse_inlet_percent",
    "max_reverse_outlet_percent",
)


def _finite(value: Any, name: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and numeric, not a boolean")
    return float(value)


def validate_boundary_policy(policy: Any) -> dict[str, Any]:
    if type(policy) is not dict or set(policy) != {"schema_version", *LIMITS} or policy.get("schema_version") != SCHEMA:
        raise ValueError("Boundary-flow policy must use the exact versioned schema")
    validated: dict[str, Any] = {"schema_version": SCHEMA}
    for key in LIMITS:
        number = _finite(policy[key], key)
        if number < 0:
            raise ValueError(f"{key} must be nonnegative")
        validated[key] = number
    return validated


def _match_receipt(value: Any, expected: Any, label: str) -> None:
    recorded = _finite(value, "receipt." + label)
    actual = _finite(expected, label)
    # The existing runner serializes the phi summary to 12 significant digits.
    if not math.isclose(recorded, actual, rel_tol=1e-9, abs_tol=1e-11):
        raise ValueError(f"Recomputed phi values disagree with receipt: {label}")


def _phi_paths(case: Path, flow: dict[str, Any], probe: dict[str, Any]) -> tuple[Path, Path]:
    relative = flow.get("phi_path")
    if type(relative) is not str or "\\" in relative or ":" in relative:
        raise ValueError("Receipt does not contain a safe final-time phi path")
    parsed = PurePosixPath(relative)
    if len(parsed.parts) != 2 or parsed.parts[-1] != "phi" or parsed.is_absolute():
        raise ValueError("Receipt has an invalid final-time phi location")
    step = parsed.parts[0]
    if step in (".", "..") or not step or "/" in step:
        raise ValueError("Receipt final-time phi path is unsafe")
    try:
        time = float(step)
    except ValueError as error:
        raise ValueError("Final-time phi path is not a solver index") from error
    if not math.isfinite(time) or time < 0:
        raise ValueError("Final-time phi path has invalid solver index")
    recorded_time = flow.get("last_solver_time")
    if type(recorded_time) is str:
        # The existing OpenFOAM receipt records solver times as numeric strings.
        # Only this source field receives string conversion; engineering policy
        # numbers stay strictly typed and non-finite strings remain forbidden.
        try:
            recorded_time = float(recorded_time)
        except ValueError as error:
            raise ValueError("Receipt has invalid final solver-time text") from error
    _match_receipt(recorded_time, time, "last_solver_time")
    _match_receipt(probe.get("last_solver_time"), time, "probe.last_solver_time")
    return case.joinpath(*parsed.parts), case / "constant" / "polyMesh" / "boundary"


def screen_two_room_boundary_flow(
    case_directory: str | Path,
    receipt_path: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Reparse bounded, hash-verified boundary faces; apply explicit limits."""
    criteria = validate_boundary_policy(policy)
    proofgraph_from_two_room_receipt(case_directory, receipt_path)
    case = Path(case_directory).resolve(strict=True)
    receipt, _ = _read_json(Path(receipt_path), max_bytes=2 * 1024 * 1024)
    flow = receipt.get("solver_flux")
    probe = receipt.get("pressure_probe")
    if type(flow) is not dict or type(probe) is not dict:
        raise ValueError("Completed two-room receipt lacks flux or probe evidence")
    phi_path, boundary_path = _phi_paths(case, flow, probe)
    boundary_raw, boundary_text = _read_stable_grid_text(
        boundary_path, case.parent, limit=_MAX_GRID_FLUX_BYTES
    )
    phi_raw, phi_text = _read_stable_grid_text(
        phi_path, case.parent, limit=_MAX_GRID_FLUX_BYTES
    )
    phi_sha = hashlib.sha256(phi_raw).hexdigest()
    boundary_sha = hashlib.sha256(boundary_raw).hexdigest()
    if phi_sha != flow.get("phi_sha256") or boundary_sha != flow.get("poly_mesh_boundary_sha256"):
        raise ValueError("Receipt-bound phi or boundary source hash changed")
    counts = _grid_poly_mesh_patch_counts(boundary_text)
    if counts != flow.get("patch_face_counts") or set(counts) != {"inlet", "outlet", "walls", "partition"}:
        raise ValueError("Boundary patch counts disagree with the two-room receipt")
    face_values = _grid_phi_patch_values(phi_text, counts)
    inlet, outlet = face_values["inlet"], face_values["outlet"]
    walls = face_values["walls"]
    partition = face_values["partition"]
    gross_inlet = math.fsum(max(-value, 0.0) for value in inlet)
    if gross_inlet <= 0 or not math.isfinite(gross_inlet):
        raise ValueError("Nonpositive or invalid gross inlet flux")
    net_inlet = -math.fsum(inlet)
    net_outlet = math.fsum(outlet)
    net_wall = math.fsum(walls) + math.fsum(partition)
    net_boundary = math.fsum([*inlet, *outlet, *walls, *partition])
    total_absolute = abs(net_boundary)
    reverse_inlet = math.fsum(max(value, 0.0) for value in inlet)
    gross_outlet = math.fsum(max(value, 0.0) for value in outlet)
    reverse_outlet = math.fsum(max(-value, 0.0) for value in outlet)
    wall_gross = math.fsum(abs(value) for value in [*walls, *partition])
    # Tie every relevant source-derived signed summary to the verified receipt.
    summary = {
        "inlet.gross_inward_m3_s": gross_inlet,
        "inlet.reverse_outward_m3_s": reverse_inlet,
        "inlet.net_inward_m3_s": net_inlet,
        "outlet.gross_outward_m3_s": gross_outlet,
        "outlet.reverse_inward_m3_s": reverse_outlet,
        "outlet.net_outward_m3_s": net_outlet,
        "walls_net_outward_m3_s": net_wall,
        "partition_net_outward_m3_s": math.fsum(partition),
        "net_boundary_outward_m3_s": net_boundary,
        "absolute_flux_imbalance_m3_s": total_absolute,
    }
    for name, number in summary.items():
        if not math.isfinite(number):
            raise ValueError("Boundary-face arithmetic overflow")
        parent, _, child = name.partition(".")
        recorded = flow.get(parent, {}).get(child) if child else flow.get(name)
        _match_receipt(recorded, number, name)
    _match_receipt(flow.get("relative_flux_imbalance_percent"),
                   100.0 * total_absolute / gross_inlet, "relative_flux_imbalance_percent")
    percentages = {
        "total_boundary_imbalance_percent": 100.0 * total_absolute / gross_inlet,
        "wall_gross_leakage_percent": 100.0 * wall_gross / gross_inlet,
        "reverse_inlet_percent": 100.0 * reverse_inlet / gross_inlet,
        "reverse_outlet_percent": 100.0 * reverse_outlet / gross_inlet,
    }
    if not all(math.isfinite(x) for x in percentages.values()):
        raise ValueError("Boundary-flow normalized arithmetic overflow")
    violated = [
        name for name, maximum in (
            ("total_boundary_imbalance_percent", criteria["max_total_boundary_imbalance_percent"]),
            ("wall_gross_leakage_percent", criteria["max_wall_gross_leakage_percent"]),
            ("reverse_inlet_percent", criteria["max_reverse_inlet_percent"]),
            ("reverse_outlet_percent", criteria["max_reverse_outlet_percent"]),
        ) if percentages[name] > maximum
    ]
    # Rehash after parsing to reject a file change while preparing diagnostics.
    phi_after, _ = _read_stable_grid_text(phi_path, case.parent, limit=_MAX_GRID_FLUX_BYTES)
    boundary_after, _ = _read_stable_grid_text(boundary_path, case.parent, limit=_MAX_GRID_FLUX_BYTES)
    if hashlib.sha256(phi_after).hexdigest() != phi_sha or hashlib.sha256(boundary_after).hexdigest() != boundary_sha:
        raise ValueError("Phi or boundary source changed during numerical screening")
    policy_hash = hashlib.sha256(json.dumps(
        criteria, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "PROJECT_BOUNDARY_SCREEN_MET" if not violated else "PROJECT_BOUNDARY_SCREEN_NOT_MET",
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
        "mesh_independence": "NOT_ASSESSED",
        "source_receipt_sha256": receipt["receipt_sha256"],
        "source_case_manifest_sha256": receipt["manifest_sha256"],
        "source_phi_sha256": phi_sha,
        "source_poly_mesh_boundary_sha256": boundary_sha,
        "unsigned_policy_sha256": policy_hash,
        "patch_face_counts": counts,
        "fluxes_m3_s": {
            "gross_inlet": gross_inlet,
            "net_inlet": net_inlet,
            "net_outlet": net_outlet,
            "net_wall_and_partition": net_wall,
            "total_outward_boundary": net_boundary,
            "gross_wall_and_partition_leakage": wall_gross,
            "reverse_inlet": reverse_inlet,
            "reverse_outlet": reverse_outlet,
        },
        "percent_of_gross_inlet": percentages,
        "criteria": criteria,
        "violations": violated,
        "interpretation": (
            "Solver-phi boundary-face flux screen only; gross wall leakage uses absolute "
            "face fluxes without cancellation. Internal mesh-face continuity is not "
            "recomputed. No independent airflow measurement, convergence proof, "
            "mesh independence, or cleanroom acceptance is established."
        ),
    }
