from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from . import __version__
from .application import (
    AnalysisRun,
    analysis_run_external_dependencies_current,
    analysis_run_matches_input,
    validate_analysis_input,
)
from .markdown import markdown_text
from .project import ProjectDocument
from .run_history import run_history_records
from .spatial import engineering_sync_status, normalize_layout, validate_layout
from .spatial_integrity import SPATIAL_METADATA_KEY


PROJECT_DIAGNOSTICS_SCHEMA = "cleanroomx.project-diagnostics"
PROJECT_DIAGNOSTICS_SCHEMA_VERSION = 1

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

_SPATIAL_ACTIONS = {
    "duplicate_room_name": "Rename rooms so every synchronization-facing room name is unambiguous.",
    "room_overlap": "Move or resize the affected rooms so their footprints no longer overlap.",
    "device_unassigned": "Assign the device to its intended room, or remove it if it is intentionally unused.",
    "orphan_device_room": "Repair the device room reference or remove the orphaned device.",
    "device_outside_room": "Move the device inside its assigned room or correct the room assignment.",
    "device_elevation_outside_room": "Correct the device elevation or the assigned room height.",
    "opening_above_room": "Lower/resize the opening or correct the room height.",
    "opening_off_wall": "Place the opening on its declared wall or correct its wall-side assignment.",
}


def _strict_json_clone(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    )


def _issue(
    *,
    rule: str,
    category: str,
    severity: str,
    message: str,
    suggested_action: str,
    element_type: str = "project",
    element_id: str | None = None,
    element_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if severity not in _SEVERITY_ORDER:
        raise ValueError(f"unsupported diagnostics severity: {severity!r}")
    issue = {
        "rule": rule,
        "category": category,
        "severity": severity,
        "element": {
            "type": element_type,
            "id": element_id,
            "name": element_name,
        },
        "message": message,
        "suggested_action": suggested_action,
    }
    if details:
        issue["details"] = _strict_json_clone(details)
    return issue


def _analysis_run_from_record(record: dict[str, Any]) -> AnalysisRun:
    """Build the minimal immutable AnalysisRun view needed by freshness helpers."""
    return AnalysisRun(
        kind=record["analysis_kind"],
        title=record.get("run_title") or record["analysis_name"],
        status=record["status"],
        result=record.get("result") if isinstance(record.get("result"), dict) else {},
        markdown=record.get("report_markdown") if isinstance(record.get("report_markdown"), str) else "",
        diagnostics={
            "application_execution_provenance": copy.deepcopy(
                record["execution_provenance"]
            )
        },
        plot=record.get("plot") if isinstance(record.get("plot"), dict) else None,
        input_snapshot=copy.deepcopy(record["input_snapshot"]),
    )


def _spatial_issues(project: ProjectDocument, layout: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for spatial_issue in validate_layout(layout):
        item_ids = [
            str(value)
            for value in spatial_issue.get("item_ids", [])
            if str(value).strip()
        ]
        details = {
            key: copy.deepcopy(value)
            for key, value in spatial_issue.items()
            if key not in {"code", "severity", "message"}
        }
        code = str(spatial_issue.get("code") or "spatial_validation")
        issues.append(
            _issue(
                rule=f"spatial.{code}",
                category="spatial",
                severity=str(spatial_issue.get("severity") or "warning"),
                element_type="spatial_element",
                element_id=item_ids[0] if item_ids else None,
                message=str(spatial_issue.get("message") or code),
                suggested_action=_SPATIAL_ACTIONS.get(
                    code,
                    "Review and correct the affected spatial model elements.",
                ),
                details=details,
            )
        )
    return issues


def _analysis_definition_issues(
    project: ProjectDocument,
    *,
    base_dir: Path | None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    first_name: dict[str, Any] = {}

    for analysis in project.analyses:
        key = analysis.name.strip().casefold()
        previous = first_name.get(key)
        if key and previous is not None:
            issues.append(
                _issue(
                    rule="analysis.duplicate_name",
                    category="analysis",
                    severity="warning",
                    element_type="analysis",
                    element_id=analysis.id,
                    element_name=analysis.name,
                    message=(
                        f"Analysis name {analysis.name!r} is also used by analysis "
                        f"{previous.id!r}; display-name ambiguity can make review harder."
                    ),
                    suggested_action="Rename one analysis while preserving its stable analysis id.",
                    details={"other_analysis_id": previous.id},
                )
            )
        else:
            first_name[key] = analysis

        try:
            validate_analysis_input(
                analysis.kind,
                analysis.input,
                base_dir=base_dir,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append(
                _issue(
                    rule="analysis.input_invalid",
                    category="analysis",
                    severity="error",
                    element_type="analysis",
                    element_id=analysis.id,
                    element_name=analysis.name,
                    message=f"Analysis input does not pass its backend validation: {exc}",
                    suggested_action=(
                        "Correct the analysis input or its referenced files, then validate it again "
                        "through the normal CleanroomX workflow."
                    ),
                    details={"analysis_kind": analysis.kind},
                )
            )
    return issues


def _sync_issues(project: ProjectDocument, layout: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    rooms = layout.get("rooms", [])
    if not rooms:
        return []

    sync_record = layout.get("engineering_sync")
    sync_analysis_id = (
        str(sync_record.get("analysis_id") or "").strip()
        if isinstance(sync_record, dict)
        else ""
    )
    verification_analyses = [
        item
        for item in project.analyses
        if item.kind in {"room_verification", "project_verification"}
    ]

    if not sync_analysis_id:
        if verification_analyses:
            return [
                _issue(
                    rule="engineering_sync.not_configured",
                    category="engineering_sync",
                    severity="info",
                    message=(
                        "Spatial rooms exist and verification analyses are available, but no "
                        "explicit engineering synchronization authority is persisted."
                    ),
                    suggested_action=(
                        "Use the spatial synchronization workflow when geometry is intended to be "
                        "linked to a room/project verification analysis."
                    ),
                    details={
                        "candidate_analysis_ids": [
                            item.id for item in verification_analyses
                        ]
                    },
                )
            ]
        return []

    analysis = next(
        (item for item in project.analyses if item.id == sync_analysis_id),
        None,
    )
    if analysis is None:
        return [
            _issue(
                rule="engineering_sync.missing_analysis",
                category="engineering_sync",
                severity="error",
                element_type="analysis",
                element_id=sync_analysis_id,
                message=(
                    f"Spatial synchronization references missing analysis id "
                    f"{sync_analysis_id!r}."
                ),
                suggested_action=(
                    "Restore the referenced verification analysis or explicitly rebind spatial "
                    "synchronization to an existing analysis."
                ),
            )
        ]
    if analysis.kind not in {"room_verification", "project_verification"}:
        return [
            _issue(
                rule="engineering_sync.unsupported_analysis",
                category="engineering_sync",
                severity="error",
                element_type="analysis",
                element_id=analysis.id,
                element_name=analysis.name,
                message=(
                    f"Spatial synchronization references analysis kind {analysis.kind!r}, which "
                    "has no room-geometry synchronization contract."
                ),
                suggested_action=(
                    "Rebind spatial synchronization to a room or project verification analysis."
                ),
            )
        ]

    status = engineering_sync_status(layout, analysis)
    actions = {
        "geometry_newer": (
            "Review the geometry change and explicitly push spatial dimensions to engineering "
            "input, or revert the spatial edit."
        ),
        "engineering_newer": (
            "Review the engineering change and explicitly pull dimensions into the spatial model, "
            "or revert the engineering edit."
        ),
        "conflicting": (
            "Resolve the room mapping/dimension conflict, then perform an explicit synchronization."
        ),
        "unmapped": (
            "Correct the room-to-analysis mapping and synchronize explicitly."
        ),
    }
    for room_status in status["rooms"]:
        state = room_status["state"]
        if state == "synchronized":
            continue
        room = next(
            (item for item in rooms if item["id"] == room_status["room_id"]),
            None,
        )
        room_name = room["name"] if room is not None else room_status["analysis_room_name"]
        message = str(room_status.get("message") or "").strip()
        if not message:
            message = {
                "geometry_newer": "Spatial room dimensions changed after the last synchronization.",
                "engineering_newer": "Engineering room dimensions changed after the last synchronization.",
                "conflicting": "Spatial and engineering room dimensions cannot be ordered safely.",
                "unmapped": "Spatial room is not mapped to an engineering room.",
            }.get(state, f"Engineering synchronization state is {state!r}.")
        issues.append(
            _issue(
                rule=f"engineering_sync.{state}",
                category="engineering_sync",
                severity="error" if state == "conflicting" else "warning",
                element_type="room",
                element_id=room_status["room_id"],
                element_name=room_name,
                message=message,
                suggested_action=actions.get(
                    state,
                    "Review the synchronization state before relying on coupled spatial/engineering data.",
                ),
                details={
                    "analysis_id": analysis.id,
                    "analysis_room_name": room_status["analysis_room_name"],
                    "differences": copy.deepcopy(room_status.get("differences", [])),
                },
            )
        )
    return issues


def _run_history_issues(
    project: ProjectDocument,
    *,
    base_dir: Path | None,
) -> list[dict[str, Any]]:
    records = run_history_records(project.metadata)
    issues: list[dict[str, Any]] = []
    analyses_by_id = {item.id: item for item in project.analyses}

    orphan_ids: list[str] = []
    for record in records:
        analysis_id = str(record.get("analysis_id") or "")
        if analysis_id and analysis_id not in analyses_by_id and analysis_id not in orphan_ids:
            orphan_ids.append(analysis_id)
    for analysis_id in orphan_ids:
        issues.append(
            _issue(
                rule="run_history.orphan_record",
                category="traceability",
                severity="warning",
                element_type="analysis",
                element_id=analysis_id,
                message=(
                    f"Retained run-history evidence references removed analysis id "
                    f"{analysis_id!r}."
                ),
                suggested_action=(
                    "Review whether the historical evidence should remain as an audit record; "
                    "do not treat it as evidence for a current analysis."
                ),
            )
        )

    for analysis in project.analyses:
        candidates = [
            record for record in records if record.get("analysis_id") == analysis.id
        ]
        if not candidates:
            issues.append(
                _issue(
                    rule="run_history.analysis_not_run",
                    category="traceability",
                    severity="info",
                    element_type="analysis",
                    element_id=analysis.id,
                    element_name=analysis.name,
                    message="No retained completed run evidence exists for this analysis.",
                    suggested_action=(
                        "Run the analysis when current engineering results or auditable run evidence "
                        "are required."
                    ),
                    details={"analysis_kind": analysis.kind},
                )
            )
            continue

        current_record = None
        stale_dependency_record = None
        for record in reversed(candidates):
            run = _analysis_run_from_record(record)
            if not analysis_run_matches_input(
                run,
                analysis.kind,
                analysis.input,
            ):
                continue
            if analysis_run_external_dependencies_current(
                run,
                base_dir=base_dir,
            ):
                current_record = record
                break
            if stale_dependency_record is None:
                stale_dependency_record = record

        if current_record is not None:
            continue

        if stale_dependency_record is None:
            latest = candidates[-1]
            issues.append(
                _issue(
                    rule="run_history.current_input_not_run",
                    category="traceability",
                    severity="warning",
                    element_type="analysis",
                    element_id=analysis.id,
                    element_name=analysis.name,
                    message=(
                        "Retained run evidence exists, but none matches the current analysis kind "
                        "and input snapshot."
                    ),
                    suggested_action="Re-run the analysis before relying on prior engineering results.",
                    details={
                        "analysis_kind": analysis.kind,
                        "latest_retained_sequence": latest["sequence"],
                    },
                )
            )
            continue

        provenance = stale_dependency_record["execution_provenance"]
        dependency_count = provenance.get("external_dependency_count", 0)
        issues.append(
            _issue(
                rule="run_history.external_dependency_stale",
                category="traceability",
                severity="warning",
                element_type="analysis",
                element_id=analysis.id,
                element_name=analysis.name,
                message=(
                    "Retained runs match the current analysis input, but their file-backed "
                    "engineering dependencies no longer match any recorded revision."
                ),
                suggested_action=(
                    "Review the changed/missing dependency and re-run the analysis against the "
                    "intended source revision."
                ),
                details={
                    "analysis_kind": analysis.kind,
                    "retained_sequence": stale_dependency_record["sequence"],
                    "external_dependency_count": dependency_count,
                },
            )
        )
    return issues


def analyze_project_diagnostics(
    project: ProjectDocument,
    *,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run deterministic cross-project design/model diagnostics without mutation.

    This composes existing CleanroomX validation, synchronization, and provenance
    authorities. It is software/design-data diagnostics, not a standards-compliance
    or certification engine.
    """
    if not isinstance(project, ProjectDocument):
        raise TypeError("project diagnostics require a ProjectDocument")
    base = Path(base_dir) if base_dir is not None else None
    layout_value = project.metadata.get(SPATIAL_METADATA_KEY)
    layout = normalize_layout(layout_value) if isinstance(layout_value, dict) else None

    issues: list[dict[str, Any]] = []
    if layout is not None:
        issues.extend(_spatial_issues(project, layout))
    issues.extend(_analysis_definition_issues(project, base_dir=base))
    if layout is not None:
        issues.extend(_sync_issues(project, layout))
    issues.extend(_run_history_issues(project, base_dir=base))

    for sequence, issue in enumerate(issues, start=1):
        issue["sequence"] = sequence

    error_count = sum(item["severity"] == "error" for item in issues)
    warning_count = sum(item["severity"] == "warning" for item in issues)
    info_count = sum(item["severity"] == "info" for item in issues)
    status = "error" if error_count else ("warning" if warning_count else "pass")

    result = {
        "schema": PROJECT_DIAGNOSTICS_SCHEMA,
        "schema_version": PROJECT_DIAGNOSTICS_SCHEMA_VERSION,
        "cleanroomx_version": __version__,
        "project": {
            "name": project.name,
            "analysis_count": len(project.analyses),
            "spatial_room_count": len(layout["rooms"]) if layout is not None else 0,
            "spatial_device_count": len(layout["devices"]) if layout is not None else 0,
        },
        "summary": {
            "status": status,
            "complete": True,
            "issue_count": len(issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
        },
        "issues": issues,
        "limitations": [
            "Diagnostics compose configured CleanroomX model, validation, synchronization, and provenance rules.",
            "A passing diagnostics report is not cleanroom certification, CFD validation, commissioning/TAB acceptance, or regulatory compliance.",
            "Project-specific standards and acceptance criteria remain explicit external/configured inputs.",
        ],
    }
    return _strict_json_clone(result)


def project_diagnostics_exit_code(result: dict[str, Any]) -> int:
    """Return 0 for a clean project, 1 for actionable diagnostics."""
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    if summary.get("error_count", 0) or summary.get("warning_count", 0):
        return 1
    return 0


def markdown_project_diagnostics_report(result: dict[str, Any]) -> str:
    if not isinstance(result, dict) or result.get("schema") != PROJECT_DIAGNOSTICS_SCHEMA:
        raise ValueError("invalid CleanroomX project diagnostics result")
    summary = result.get("summary", {})
    project = result.get("project", {})
    lines = [
        "# CleanroomX Project Diagnostics",
        "",
        f"- Project: **{markdown_text(project.get('name', ''))}**",
        f"- Status: **{markdown_text(summary.get('status', 'unknown'))}**",
        f"- Errors: **{summary.get('error_count', 0)}**",
        f"- Warnings: **{summary.get('warning_count', 0)}**",
        f"- Informational: **{summary.get('info_count', 0)}**",
        "",
    ]
    issues = result.get("issues", [])
    if not issues:
        lines.extend(
            [
                "No project diagnostic errors or warnings were found.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Findings",
                "",
                "| # | Severity | Category | Rule | Element | Finding | Corrective action |",
                "|---:|---|---|---|---|---|---|",
            ]
        )
        for issue in issues:
            element = issue.get("element", {})
            element_text = (
                element.get("name")
                or element.get("id")
                or element.get("type")
                or "project"
            )
            lines.append(
                "| {sequence} | {severity} | {category} | {rule} | {element} | "
                "{message} | {action} |".format(
                    sequence=issue.get("sequence", ""),
                    severity=markdown_text(issue.get("severity", "")),
                    category=markdown_text(issue.get("category", "")),
                    rule=markdown_text(issue.get("rule", "")),
                    element=markdown_text(element_text),
                    message=markdown_text(issue.get("message", "")),
                    action=markdown_text(issue.get("suggested_action", "")),
                )
            )
        lines.append("")

    lines.extend(
        [
            "## Engineering boundary",
            "",
            (
                "This report is a deterministic project/model health diagnostic. It does not by "
                "itself establish cleanroom certification, CFD validation, commissioning/TAB "
                "acceptance, manufacturer approval, or regulatory compliance."
            ),
            "",
        ]
    )
    return "\n".join(lines)
