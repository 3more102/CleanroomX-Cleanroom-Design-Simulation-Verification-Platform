from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import ProjectSpec
from .verification import Status, VerificationReport, verify_room


@dataclass(frozen=True)
class PressureCascadeFinding:
    code: str
    status: Status
    message: str
    higher_pressure_room: str
    lower_pressure_room: str
    actual_delta_pa: float | None = None
    limit_pa: float | None = None
    uncertainty_pa: float | None = None
    interval_low_pa: float | None = None
    interval_high_pa: float | None = None


@dataclass(frozen=True)
class ProjectVerificationReport:
    project: str
    room_reports: tuple[VerificationReport, ...]
    pressure_cascade_findings: tuple[PressureCascadeFinding, ...]

    @property
    def passed(self) -> bool:
        return all(report.passed for report in self.room_reports) and all(
            finding.status not in {"fail", "indeterminate"}
            for finding in self.pressure_cascade_findings
        )

    def to_dict(self) -> dict:
        return {
            "project": self.project,
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
        uncertainty = (
            higher.observed_pressure_uncertainty_pa
            + lower.observed_pressure_uncertainty_pa
        )
        low = actual_delta - uncertainty
        high = actual_delta + uncertainty
        if low >= requirement.min_delta_pa:
            status: Status = "pass"
            message = (
                "The complete room-to-room pressure-difference interval meets the "
                "configured project requirement."
            )
        elif high < requirement.min_delta_pa:
            status = "fail"
            message = (
                "The complete room-to-room pressure-difference interval is below the "
                "configured project requirement."
            )
        else:
            status = "indeterminate"
            message = (
                "The configured pressure-cascade requirement lies inside the conservative "
                "pressure-difference uncertainty interval."
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
                uncertainty_pa=uncertainty,
                interval_low_pa=low,
                interval_high_pa=high,
            )
        )

    return ProjectVerificationReport(
        project=project.name,
        room_reports=room_reports,
        pressure_cascade_findings=tuple(findings),
    )
