from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .application import validate_analysis_input
from .project import ProjectDocument, ProjectFormatError, project_from_dict
from .spatial import (
    SPATIAL_METADATA_KEY,
    validate_layout,
    validate_layout_integrity,
)


@dataclass(frozen=True)
class ProjectValidationFinding:
    severity: str
    code: str
    scope: str
    message: str
    analysis_id: str | None = None
    analysis_name: str | None = None
    analysis_kind: str | None = None
    item_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["item_ids"] = list(self.item_ids)
        return data


@dataclass(frozen=True)
class ProjectValidationReport:
    project_name: str
    project_sha256: str | None
    analyses_checked: int
    valid_analyses: int
    invalid_analyses: int
    spatial_checked: bool
    findings: tuple[ProjectValidationFinding, ...]

    @property
    def error_count(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    @property
    def status(self) -> str:
        if self.error_count:
            return "fail"
        if self.warning_count:
            return "warning"
        return "pass"

    @property
    def passed(self) -> bool:
        return self.status != "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project_name,
            "status": self.status,
            "passed": self.passed,
            "project_sha256": self.project_sha256,
            "summary": {
                "analyses_checked": self.analyses_checked,
                "valid_analyses": self.valid_analyses,
                "invalid_analyses": self.invalid_analyses,
                "spatial_checked": self.spatial_checked,
                "errors": self.error_count,
                "warnings": self.warning_count,
            },
            "findings": [item.to_dict() for item in self.findings],
        }


def _canonical_project_sha256(project: ProjectDocument) -> str | None:
    try:
        payload = json.dumps(
            project.to_dict(),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return sha256(payload).hexdigest()


def _finding_from_spatial(issue: dict[str, Any]) -> ProjectValidationFinding:
    item_ids = issue.get("item_ids", [])
    return ProjectValidationFinding(
        severity=issue.get("severity", "warning"),
        code=f"spatial_{issue.get('code', 'finding')}",
        scope="spatial",
        message=str(issue.get("message", "Spatial validation finding.")),
        item_ids=tuple(str(value) for value in item_ids),
    )


def validate_project(
    project: ProjectDocument,
    *,
    base_dir: str | Path | None = None,
) -> ProjectValidationReport:
    """Validate complete project state without running engineering analyses.

    Existing analysis parsers remain the source of truth for analysis-input
    contracts. Spatial structural checks run before advisory geometry checks so
    malformed data is reported without normalization or random ID generation.
    """
    if not isinstance(project, ProjectDocument):
        raise TypeError("project must be a ProjectDocument")

    findings: list[ProjectValidationFinding] = []
    project_sha256 = _canonical_project_sha256(project)

    try:
        project_from_dict(project.to_dict())
    except (ProjectFormatError, TypeError, ValueError) as exc:
        findings.append(
            ProjectValidationFinding(
                severity="error",
                code="project_structure_invalid",
                scope="project",
                message=str(exc),
            )
        )

    if not project.analyses:
        findings.append(
            ProjectValidationFinding(
                severity="warning",
                code="project_has_no_analyses",
                scope="project",
                message="Project contains no analyses to validate.",
            )
        )

    base = Path(base_dir) if base_dir is not None else None
    valid_analyses = 0
    invalid_analyses = 0
    for analysis in project.analyses:
        try:
            validate_analysis_input(analysis.kind, analysis.input, base_dir=base)
        except Exception as exc:  # analysis-validator isolation boundary
            invalid_analyses += 1
            detail = str(exc).strip() or "validation failed"
            message = f"{exc.__class__.__name__}: {detail}"
            findings.append(
                ProjectValidationFinding(
                    severity="error",
                    code="analysis_input_invalid",
                    scope="analysis",
                    message=message,
                    analysis_id=analysis.id,
                    analysis_name=analysis.name,
                    analysis_kind=analysis.kind,
                )
            )
        else:
            valid_analyses += 1

    spatial_checked = False
    metadata = project.metadata
    if isinstance(metadata, dict) and SPATIAL_METADATA_KEY in metadata:
        spatial_checked = True
        layout = metadata[SPATIAL_METADATA_KEY]
        integrity_issues = validate_layout_integrity(layout)
        findings.extend(_finding_from_spatial(issue) for issue in integrity_issues)
        if not any(issue.get("severity") == "error" for issue in integrity_issues):
            findings.extend(
                _finding_from_spatial(issue) for issue in validate_layout(layout)
            )

    return ProjectValidationReport(
        project_name=project.name,
        project_sha256=project_sha256,
        analyses_checked=len(project.analyses),
        valid_analyses=valid_analyses,
        invalid_analyses=invalid_analyses,
        spatial_checked=spatial_checked,
        findings=tuple(findings),
    )


def markdown_project_validation_report(report: ProjectValidationReport) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "# CleanroomX project validation",
        "",
        f"- Project: {report.project_name}",
        f"- Status: {report.status.upper()}",
        f"- Project SHA-256: {report.project_sha256 or 'unavailable'}",
        f"- Analyses checked: {report.analyses_checked}",
        f"- Valid analyses: {report.valid_analyses}",
        f"- Invalid analyses: {report.invalid_analyses}",
        f"- Spatial metadata checked: {'yes' if report.spatial_checked else 'no'}",
        f"- Errors: {report.error_count}",
        f"- Warnings: {report.warning_count}",
        "",
    ]
    if not report.findings:
        lines.append("No validation findings.")
        return "\n".join(lines) + "\n"

    lines.extend([
        "| Severity | Scope | Code | Analysis | Message |",
        "| --- | --- | --- | --- | --- |",
    ])
    for finding in report.findings:
        analysis = finding.analysis_name or finding.analysis_id or ""
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    finding.severity.upper(),
                    finding.scope,
                    finding.code,
                    analysis,
                    finding.message,
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
