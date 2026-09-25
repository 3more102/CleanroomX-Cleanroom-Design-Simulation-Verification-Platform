from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import ProjectSpec
from .verification import (
    AggregateVerificationStatus,
    Status,
    VerificationReport,
    aggregate_verification_status,
    verify_room,
)


@dataclass(frozen=True)
class PressureCascadeFinding:
    code: str
    status: Status
    message: str
    higher_pressure_room: str
    lower_pressure_room: str
    actual_delta_pa: float | None = None
    limit_pa: float | None = None


@dataclass(frozen=True)
class ProjectVerificationReport:
    project: str
    room_reports: tuple[VerificationReport, ...]
    pressure_cascade_findings: tuple[PressureCascadeFinding, ...]

    @property
    def status(self) -> AggregateVerificationStatus:
        statuses = [
            finding.status
            for report in self.room_reports
            for finding in report.findings
        ]
        statuses.extend(
            finding.status for finding in self.pressure_cascade_findings
        )
        return aggregate_verification_status(statuses)

    @property
    def complete(self) -> bool:
        return all(report.complete for report in self.room_reports) and all(
            finding.status != "not_checked"
            for finding in self.pressure_cascade_findings
        )

    @property
    def passed(self) -> bool:
        """Compatibility boolean: true when no configured check failed."""
        return all(report.passed for report in self.room_reports) and all(
            finding.status != "fail" for finding in self.pressure_cascade_findings
        )

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "status": self.status,
            "complete": self.complete,
            "passed": self.passed,
            "rooms": [report.to_dict() for report in self.room_reports],
            "pressure_cascade": [asdict(finding) for finding in self.pressure_cascade_findings],
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
        ok = actual_delta >= requirement.min_delta_pa
        findings.append(
            PressureCascadeFinding(
                code="PRESSURE_CASCADE",
                status="pass" if ok else "fail",
                message=(
                    "Observed room-to-room pressure cascade meets the configured project requirement."
                    if ok
                    else "Observed room-to-room pressure cascade is below the configured project requirement."
                ),
                higher_pressure_room=higher.name,
                lower_pressure_room=lower.name,
                actual_delta_pa=actual_delta,
                limit_pa=requirement.min_delta_pa,
            )
        )

    return ProjectVerificationReport(
        project=project.name,
        room_reports=room_reports,
        pressure_cascade_findings=tuple(findings),
    )
