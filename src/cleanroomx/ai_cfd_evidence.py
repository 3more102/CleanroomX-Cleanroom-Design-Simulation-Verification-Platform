"""Bounded, read-only assistant lens over exported multiroom CFD evidence.

Recomputes the canonical engineering review; does not run OpenFOAM, grant
numerical acceptance, or authenticate the producer of JSON evidence.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from .ai_assistant import project_snapshot_sha256
from .cfd_multizone_review import SCHEMA as REVIEW_SCHEMA, review_recorded_multizone
from .project import (
    ProjectDocument,
    capture_project_file_revision,
    load_project_document_with_revision,
    project_file_revision_matches,
)
from .strict_json import load_strict_json_snapshot

MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_REVIEW_BYTES = 512 * 1024
MAX_ROOMS = 20
MAX_DOORS = 24
CFD_ASSISTANT_SCHEMA = "cleanroomx.ai-cfd-evidence"
CFD_ASSISTANT_VERSION = 1


def _sha256(value: bytes) -> str:
    return sha256(value).hexdigest()


def _optional_finite(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(field + " must be finite numeric CFD evidence or null")
    return float(value)


def _fraction(value: Any, field: str) -> float | None:
    numeric = _optional_finite(value, field)
    if numeric is not None and not 0.0 <= numeric <= 1.0:
        raise ValueError(field + " must lie between zero and one")
    return numeric


def _identity(value: Any, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(name + " must be a lowercase SHA-256 digest")
    return value


def _recorded_report(directory: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one stable report and validate its optional companion review.

    For fail-closed evidence ingestion, a present but inconsistent companion
    review is an error, rather than permission to silently regenerate it.
    """
    root = Path(directory).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("CFD export must be a regular, accessible directory")
    report_path = root / "report.json"
    if report_path.is_symlink() or not report_path.is_file():
        raise ValueError("Expected a regular exported CFD report.json")
    source = load_strict_json_snapshot(report_path, max_bytes=MAX_REPORT_BYTES)
    report = source.value
    if type(report) is not dict:
        raise ValueError("CFD report must be a JSON object")
    review = review_recorded_multizone(report)
    if review["schema"] != REVIEW_SCHEMA or review["engineering_release"] != "HOLD":
        raise ValueError("Unsupported engineering review outcome")

    companion = root / "engineering-review.json"
    companion_hash = None
    if companion.is_symlink():
        raise ValueError("Symlinked CFD engineering-review.json is not supported")
    if companion.exists():
        if not companion.is_file():
            raise ValueError("CFD engineering review is not a regular file")
        supplied = load_strict_json_snapshot(
            companion, max_bytes=MAX_REVIEW_BYTES
        )
        if supplied.value != review:
            raise ValueError(
                "Recorded engineering-review.json does not match the "
                "canonical review regenerated from report.json"
            )
        companion_hash = _sha256(supplied.raw_bytes)

    # Recheck the report after review processing so a concurrent replacement
    # is rejected even if its initial descriptor was internally stable.
    current = load_strict_json_snapshot(report_path, max_bytes=MAX_REPORT_BYTES)
    if _sha256(source.raw_bytes) != _sha256(current.raw_bytes):
        raise ValueError("CFD report changed during assistant evidence import")
    if companion_hash is not None:
        current_companion = load_strict_json_snapshot(
            companion, max_bytes=MAX_REVIEW_BYTES
        )
        if _sha256(current_companion.raw_bytes) != companion_hash:
            raise ValueError("CFD engineering review changed during import")
    return report, {
        "exported_report_sha256": _sha256(source.raw_bytes),
        "companion_review_sha256": companion_hash,
        "canonical_engineering_review": review,
    }


def bound_cfd_evidence(
    directory: str | Path,
    *,
    project: ProjectDocument,
    project_path: str | Path,
) -> dict[str, Any]:
    """Import exported CFD metrics only for the *exact* saved project revision.

    Project JSON must have no unsaved in-memory changes. Exported case source
    hash must equal that same stable saved project SHA-256. A matching hash
    binds data identity, not physical truth or authentic origin.
    """
    if not isinstance(project, ProjectDocument):
        raise TypeError("A CleanroomX ProjectDocument is required")
    source_path = Path(project_path).expanduser().resolve(strict=False)
    disk_project, before = load_project_document_with_revision(source_path)
    if not before.exists or not before.sha256:
        raise ValueError("CFD assistant requires an existing saved project")
    if project_snapshot_sha256(disk_project) != project_snapshot_sha256(project):
        raise ValueError(
            "The current project has unsaved changes; save it and re-export "
            "matching CFD evidence before binding it to the assistant"
        )

    report, evidence = _recorded_report(directory)
    provenance = report.get("provenance")
    if type(provenance) is not dict:
        raise ValueError("CFD report lacks source provenance")
    source_sha = _identity(provenance.get("project_source_sha256"), "CFD project source")
    if source_sha != before.sha256:
        raise ValueError(
            "Exported CFD evidence belongs to a different saved project revision"
        )

    after = capture_project_file_revision(source_path)
    if not project_file_revision_matches(before, after):
        raise ValueError("Saved CleanroomX project changed during CFD evidence review")

    review = evidence["canonical_engineering_review"]
    rooms = report["rooms"]
    doors = review["door_review_by_absolute_mismatch"]
    ordered_rooms = sorted(rooms.items(), key=lambda item: str(item[0]))
    numerics = report.get("numerics", {})
    if type(numerics) is not dict:
        raise ValueError("Missing selected iteration numerical diagnostics")
    mesh = report.get("mesh")
    if type(mesh) is not dict:
        raise ValueError("Missing recorded mesh summary")

    return {
        "schema": CFD_ASSISTANT_SCHEMA,
        "schema_version": CFD_ASSISTANT_VERSION,
        "evidence_type": "exported_recorded_open_door_cfd",
        "report_sha256": evidence["exported_report_sha256"],
        "companion_review_sha256": evidence["companion_review_sha256"],
        "saved_project_source_sha256": source_sha,
        "source_manifest_sha256": review["source_manifest_sha256"],
        "source_run_receipt_sha256": review["source_run_receipt_sha256"],
        "source_iteration": review["source_iteration"][:64],
        "scenario": review["scenario"],
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "solver_reported_convergence_at_selected_iteration": (
            review["numerical_convergence_at_selected_iteration"]
        ),
        "run_reported_convergence": (
            numerics.get("run_reported_convergence")
            if type(numerics.get("run_reported_convergence")) is bool else None
        ),
        "solver_convergence_iteration": numerics.get("solver_convergence_iteration"),
        "mesh": {
            "mesh_ok": mesh["mesh_ok"],
            "cells": mesh.get("cells"),
        },
        "flow_balance": {
            "global_relative_boundary_imbalance": (
                review["global_relative_boundary_imbalance"]
            ),
            "global_signed_net_outward_m3_s": (
                review["global_signed_net_outward_m3_s"]
            ),
        },
        "room_count": len(rooms),
        "rooms": [
            {
                "room_id": str(rid)[:80],
                "name": str(room["name"])[:160],
                "mean_pressure_pa_relative_to_reference": (
                    room["mean_pressure_pa_relative_to_reference"]
                ),
                "mean_speed_m_s": _optional_finite(
                    room.get("mean_speed_m_s"), "room mean speed"
                ),
                "max_speed_m_s": _optional_finite(
                    room.get("max_speed_m_s"), "room max speed"
                ),
                "mean_downward_velocity_m_s": _optional_finite(
                    room.get("mean_downward_velocity_m_s"), "room downward velocity"
                ),
                "upward_volume_fraction": _fraction(
                    room.get("upward_volume_fraction"), "room upward fraction"
                ),
                "downward_volume_fraction": _fraction(
                    room.get("downward_volume_fraction"), "room downward fraction"
                ),
                "supply_inflow_m3_s": _optional_finite(
                    room.get("supply_inflow_m3_s"), "room supply airflow"
                ),
                "return_outflow_m3_s": _optional_finite(
                    room.get("return_outflow_m3_s"), "room return airflow"
                ),
                "net_outward_imbalance_m3_s": room["net_outward_imbalance_m3_s"],
            }
            for rid, room in ordered_rooms[:MAX_ROOMS]
        ],
        "rooms_truncated": len(rooms) > MAX_ROOMS,
        "door_count": len(doors),
        "doors": [
            {
                "door": str(door["door"])[:120],
                "from_room": str(door["from_room"])[:80],
                "to_room": str(door["to_room"])[:80],
                "target_delta_pa": door["target_delta_pa"],
                "observed_delta_pa": door["observed_delta_pa"],
                "delta_minus_target_pa": door["delta_minus_target_pa"],
                "target_direction_reversed": door["target_direction_reversed"],
                "computed_net_transfer_m3_s": door["computed_net_transfer_m3_s"],
                "computed_forward_m3_s": door["computed_forward_m3_s"],
                "computed_reverse_m3_s": door["computed_reverse_m3_s"],
            }
            for door in doors[:MAX_DOORS]
        ],
        "doors_truncated": len(doors) > MAX_DOORS,
        "review_reasons": [
            {
                "code": str(reason["code"])[:120],
                "message": str(reason["message"])[:400],
            }
            for reason in review["reasons"][:20]
        ],
        "non_prescriptive_checks": [
            str(check)[:500] for check in review["non_prescriptive_checks"][:10]
        ],
        "limitations": [
            "Self-consistency and project-revision SHA-256 checks are not proof of genuine solver origin.",
            "The export does not re-read or independently authenticate OpenFOAM fields.",
            "All doors are OPEN: closed-door cascade and 5 Pa acceptance remain NOT DEMONSTRATED.",
            "Selected-iteration solver markers are not physical validation or certification.",
            "No mesh-independence, turbulence or commissioning acceptance is claimed.",
            "The engineering release is HOLD regardless of observed target difference.",
        ],
    }


def format_cfd_evidence(context: dict[str, Any]) -> str:
    """Human-readable, fail-closed evidence summary with explicit HOLD."""
    if (
        type(context) is not dict
        or context.get("schema") != CFD_ASSISTANT_SCHEMA
        or context.get("schema_version") != CFD_ASSISTANT_VERSION
        or context.get("engineering_release") != "HOLD"
        or context.get("closed_door_5pa_demonstrated") is not False
    ):
        raise ValueError("Invalid or unsupported CleanroomX CFD assistant evidence")
    lines = [
        "RECORDED CFD EXPORT REVIEW — HOLD (NOT CERTIFIED)",
        "Selected SIMPLE iteration: " + str(context["source_iteration"]),
        "Scenario: " + str(context["scenario"]),
        "Solver convergence marker for selected iteration: " + str(
            context["solver_reported_convergence_at_selected_iteration"]
        ),
        "Full-run convergence marker: " + str(
            context.get("run_reported_convergence", "unknown")
        ),
        "Room count: " + str(context["room_count"]),
        "Door count: " + str(context["door_count"]),
        "Source project SHA-256: " + context["saved_project_source_sha256"][:12],
        "Exported report SHA-256: " + context["report_sha256"][:12],
        "",
    ]
    for room in context["rooms"]:
        lines.append(
            "Room " + str(room["name"]) + ": mean relative pressure "
            + str(room["mean_pressure_pa_relative_to_reference"]) + " Pa"
            + "; mean speed " + str(room.get("mean_speed_m_s")) + " m/s"
            + "; mean downward velocity "
            + str(room.get("mean_downward_velocity_m_s")) + " m/s"
            + "; upward cell volume fraction "
            + str(room.get("upward_volume_fraction"))
            + "; net outward imbalance "
            + str(room["net_outward_imbalance_m3_s"]) + " m³/s"
        )
    for door in context["doors"]:
        lines.append(
            "Door " + str(door["door"]) + ": observed Δp "
            + str(door["observed_delta_pa"]) + " Pa"
            + "; target Δp " + str(door["target_delta_pa"]) + " Pa"
            + "; net phi " + str(door["computed_net_transfer_m3_s"]) + " m³/s"
        )
    if context["rooms_truncated"] or context["doors_truncated"]:
        lines.append("Some room/door rows were omitted by assistant size limits.")
    lines.extend(
        ["", "Engineering HOLD reasons:"]
        + [
            " - " + reason["code"] + ": " + reason["message"]
            for reason in context["review_reasons"]
        ]
    )
    lines.append("Further checks (not executed):")
    lines.extend(
        " - " + str(check) for check in context.get("non_prescriptive_checks", [])
    )
    lines.append(
        "This is a self-consistent exported report, not independent solver "
        "authentication, physical validation, or closed-door certification."
    )
    return "\n".join(lines)
