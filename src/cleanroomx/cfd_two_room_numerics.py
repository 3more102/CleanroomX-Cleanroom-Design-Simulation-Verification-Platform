"""Receipt-bound, explicitly thresholded two-room CFD numerical screening.

This is a diagnostic review of solver log values. Even passing user-supplied
residual and reported-continuity limits is NOT solver convergence, mesh
independence, conservation verification, or physical cleanroom qualification.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .cfd_audit import MAX_LOG_BYTES, audit_openfoam_log
from .cfd_proofgraph import (
    _hash_regular_file,
    _read_json,
    proofgraph_from_two_room_receipt,
)

SCHEMA = "cleanroomx.cfd-two-room-numerical-criteria.v1"
RESULT_SCHEMA = "cleanroomx.cfd-two-room-numerical-screen.v1"
REQUIRED_FIELDS = ("Ux", "Uy", "Uz", "p")


def _positive(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite, strictly positive number")
    return float(value)


def validate_two_room_numerical_criteria(value: Any) -> dict[str, Any]:
    """Require an explicit four-field and continuity policy; no default pass gate."""
    required = {
        "schema_version", "fields", "max_initial_residual",
        "max_final_residual", "max_global_continuity", "window",
    }
    if type(value) is not dict or set(value) != required or value.get("schema_version") != SCHEMA:
        raise ValueError("Two-room numerical criteria require the exact versioned schema")
    if type(value["fields"]) is not list or value["fields"] != list(REQUIRED_FIELDS):
        raise ValueError("Two-room numerical screening requires all Ux, Uy, Uz, p fields in order")
    window = value["window"]
    if type(window) is not int or not 2 <= window <= 100:
        raise ValueError("Two-room numerical window must be an integer between 2 and 100")
    return {
        "schema_version": SCHEMA,
        "fields": list(REQUIRED_FIELDS),
        "max_initial_residual": _positive(value["max_initial_residual"], "max_initial_residual"),
        "max_final_residual": _positive(value["max_final_residual"], "max_final_residual"),
        "max_global_continuity": _positive(value["max_global_continuity"], "max_global_continuity"),
        "window": window,
    }


def screen_two_room_numerics(
    case_directory: str | Path,
    receipt_path: str | Path,
    criteria: dict[str, Any],
) -> dict[str, Any]:
    """Screen only the exact receipt-bound simpleFoam log with explicit policy.

    A valid v2 receipt and all underlying case/VTK/phi/probe evidence must
    first pass the existing ProofGraph integrity gate. The log is independently
    checked against its receipt hash both before and after ingestion.
    """
    normalized = validate_two_room_numerical_criteria(criteria)
    proofgraph_from_two_room_receipt(case_directory, receipt_path)
    case = Path(case_directory).resolve(strict=True)
    receipt, _ = _read_json(Path(receipt_path), max_bytes=2 * 1024 * 1024)
    stages = receipt.get("stages")
    if type(stages) is not list:
        raise ValueError("Two-room receipt lacks stage metadata")
    solvers = [
        step for step in stages
        if type(step) is dict and step.get("command") == "simpleFoam"
    ]
    if len(solvers) != 1 or solvers[0].get("log_path") != "simpleFoam.log":
        raise ValueError("Two-room receipt must bind exactly one simpleFoam.log")
    expected_hash = solvers[0].get("log_sha256")
    if type(expected_hash) is not str or len(expected_hash) != 64:
        raise ValueError("Two-room receipt has invalid solver log digest")
    log = case / "simpleFoam.log"
    digest, _ = _hash_regular_file(log, max_bytes=MAX_LOG_BYTES)
    if digest != expected_hash:
        raise ValueError("Verified solver log has changed since its receipt")
    screened = audit_openfoam_log(
        log,
        fields=tuple(normalized["fields"]),
        max_initial_residual=normalized["max_initial_residual"],
        max_final_residual=normalized["max_final_residual"],
        window=normalized["window"],
        max_global_continuity=normalized["max_global_continuity"],
    )
    digest_after, _ = _hash_regular_file(log, max_bytes=MAX_LOG_BYTES)
    if screened["log_sha256"] != digest or digest_after != digest:
        raise ValueError("Solver log changed during receipt-bound numerical screening")
    policy_bytes = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    met = screened["status"] == "numerically_screened"
    return {
        "schema_version": RESULT_SCHEMA,
        "status": "PROJECT_NUMERICAL_SCREEN_MET" if met else "PROJECT_NUMERICAL_SCREEN_NOT_MET",
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
        "mesh_independence": "NOT_ASSESSED",
        "source_receipt_sha256": receipt["receipt_sha256"],
        "source_case_manifest_sha256": receipt["manifest_sha256"],
        "source_solver_log_sha256": digest,
        "unsigned_policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "criteria": normalized,
        "log_screen": screened,
        "interpretation": (
            "User-supplied per-field linear residual and OpenFOAM-reported continuity "
            "screen only; no independent mass-balance integration, steady-state proof, "
            "mesh independence, model correlation, ISO acceptance, or certification."
        ),
    }
