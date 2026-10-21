"""Offline recheck of a CFD export against a retained OpenFOAM case.

This verifies consistency with retained solver inputs, logs, receipt and fields.
It does not authenticate the producer, rerun a solver or certify a cleanroom.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ai_cfd_evidence import _recorded_report, bound_cfd_evidence
from .cfd_multizone_results import analyze_multizone_case
from .project import (
    ProjectDocument,
    capture_project_file_revision,
    project_file_revision_matches,
)


def _canonical_bytes(value: Any) -> bytes:
    """Use exact JSON value/type comparison, rather than coercing measurements."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def replay_recorded_cfd(
    export_directory: str | Path,
    case_directory: str | Path,
    *,
    project: ProjectDocument,
    project_path: str | Path,
) -> dict[str, Any]:
    """Recompute an exported summary from recorded p/U/C/phi and solver logs.

    The canonical analyzer checks the saved case manifest, execution receipt,
    stage-log digests, field digests, mesh and selected-iteration diagnostics.
    A matching JSON export proves consistency *with the retained case only*.
    """
    case_path = Path(case_directory).expanduser()
    if case_path.is_symlink() or not case_path.is_dir():
        raise ValueError("Recorded OpenFOAM case must be a real directory, not a symlink")

    project_source = Path(project_path).expanduser().resolve(strict=False)
    before = capture_project_file_revision(project_source)
    if not before.exists or not before.sha256:
        raise ValueError("Saved CleanroomX project is required for case replay")

    evidence = bound_cfd_evidence(
        export_directory, project=project, project_path=project_source,
    )
    report, report_identity = _recorded_report(export_directory)
    if report_identity["exported_report_sha256"] != evidence["report_sha256"]:
        raise ValueError("Exported CFD report changed between evidence checks")

    try:
        reference = report["pressure_reference"]["room_id"]
        density = report["density_kg_m3"]
        vertical_tolerance = report["vertical_tolerance_m_s"]
        iteration = report["time_name"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Export lacks recorded analyzer settings for case replay") from exc
    if type(reference) is not str or not reference:
        raise ValueError("Exported pressure reference must identify a room")
    if type(iteration) is not str or not iteration:
        raise ValueError("Exported selected iteration must be a nonempty string")

    recomputed = analyze_multizone_case(
        case_path,
        density_kg_m3=density,
        reference_room_id=reference,
        vertical_tolerance_m_s=vertical_tolerance,
        time_name=iteration,
    )
    # export_multizone_report deliberately excludes full cell and residual
    # arrays; recheck every other field, including provenance and numerics.
    replayed_summary = {
        key: value for key, value in recomputed.items()
        if key not in ("cells", "residual_history")
    }
    if _canonical_bytes(replayed_summary) != _canonical_bytes(report):
        raise ValueError(
            "Exported CFD report does not match recomputed recorded OpenFOAM fields"
        )

    # Recheck the export and saved project after the potentially long replay.
    final_report, final_identity = _recorded_report(export_directory)
    if (
        final_identity["exported_report_sha256"] != evidence["report_sha256"]
        or _canonical_bytes(final_report) != _canonical_bytes(report)
    ):
        raise ValueError("Exported CFD evidence changed during case replay")
    after = capture_project_file_revision(project_source)
    if not project_file_revision_matches(before, after):
        raise ValueError("Saved CleanroomX project changed during case replay")

    return {
        "schema": "cleanroomx.ai-cfd-case-replay",
        "schema_version": 1,
        "status": "recorded_case_consistent",
        "report_matches_recomputed_fields": True,
        "recorded_case_integrity_checked": True,
        "report_sha256": evidence["report_sha256"],
        "saved_project_source_sha256": before.sha256,
        "selected_iteration": evidence["source_iteration"],
        "solver_reported_convergence_at_selected_iteration": (
            evidence["solver_reported_convergence_at_selected_iteration"]
        ),
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "solver_producer_authenticated": False,
        "physical_validation_established": False,
        "note": (
            "Recorded source, logs and fields match the export under the "
            "canonical parser. This does not authenticate the producer, "
            "rerun OpenFOAM, prove mesh independence or establish compliance."
        ),
    }
