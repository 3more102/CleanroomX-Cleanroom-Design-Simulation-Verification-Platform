from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import ProjectSpec
from .verification import ReportStatus, Status, VerificationReport, verify_room


@dataclass(frozen=True)
class PressureCascadeFinding:
    code: str
    status: Status
    message: str
    higher_pressure_room: str
    lower_pressure_room: str
    actual_delta_pa: float | None = None
    limit_pa: float | None = None
    lower_bound_pa: float | None = None
    upper_bound_pa: float | None = None


@dataclass(frozen=True)
class ProjectVerificationReport:
    project: str
    room_reports: tuple[VerificationReport, ...]
    pressure_cascade_findings: tuple[PressureCascadeFinding, ...]

    @property
    def status(self) -> ReportStatus:
        statuses: list[Status | ReportStatus] = [
            report.status for report in self.room_reports
        ]
        statuses.extend(
            finding.status for finding in self.pressure_cascade_findings
        )
        if "fail" in statuses:
            return "fail"
        if "indeterminate" in statuses:
            return "indeterminate"
        return "pass"

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "status": self.status,
            "passed": self.passed,
            "rooms": [report.to_dict() for report in self.room_reports],
            "pressure_cascade": [
                asdict(finding) for finding in self.pressure_cascade_findings
            ],
        }


def verify_project(project: ProjectSpec) -> ProjectVerificationReport:
    room_reports = tuple(verify_room(room) for room in project.rooms)
    rooms_by_name = {room.name: room for room in project.rooms}
    findings: list[PressureCascadeFinding] = []

    for requirement in project.pressure_cascade:
        higher = rooms_by_name[requirement.higher_pressure_room]
        lower = rooms_by_name[requirement.lower_pressure_room]

        if higher.observed_pressure_pa is None or lower.observed_pressure_pa is None:
            findings.append(
                PressureCascadeFinding(
                    code="PRESSURE_CASCADE",
                    status="not_checked",
                    message="Observed pressure is missing for one or both rooms.",
                    higher_pressure_room=higher.name,
                    lower_pressure_room=lower.name,
                    limit_pa=requirement.min_delta_pa,
                )
            )
            continue

        actual_delta = higher.observed_pressure_pa - lower.observed_pressure_pa
        lower_delta = (
            higher.observed_pressure_pa
            - higher.observed_pressure_uncertainty_pa
            - (
                lower.observed_pressure_pa
                + lower.observed_pressure_uncertainty_pa
            )
        )
        upper_delta = (
            higher.observed_pressure_pa
            + higher.observed_pressure_uncertainty_pa
            - (
                lower.observed_pressure_pa
                - lower.observed_pressure_uncertainty_pa
            )
        )

        if lower_delta >= requirement.min_delta_pa:
            status: Status = "pass"
            message = (
                "The complete room-to-room pressure-difference interval meets "
                "the configured project minimum."
            )
        elif upper_delta < requirement.min_delta_pa:
            status = "fail"
            message = (
                "The complete room-to-room pressure-difference interval is below "
                "the configured project minimum."
            )
        else:
            status = "indeterminate"
            message = (
                "The room-to-room pressure-difference interval overlaps the "
                "configured project minimum."
            )

        findings.append(
            PressureCascadeFinding(
                code="PRESSURE_CASCADE",
                status=status,
                message=message,
                higher_pressure_room=higher.name,
                lower_pressure_room=lower.name,
                actual_delta_pa=actual_delta,
                limit_pa=requirement.min_delta_pa,
                lower_bound_pa=lower_delta,
                upper_bound_pa=upper_delta,
            )
        )

    return ProjectVerificationReport(
        project=project.name,
        room_reports=room_reports,
        pressure_cascade_findings=tuple(findings),
    )
