from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .calculations import air_changes_per_hour, room_volume_m3
from .models import RoomSpec

Status = Literal["pass", "fail", "indeterminate", "not_checked"]
ReportStatus = Literal["pass", "fail", "indeterminate"]


@dataclass(frozen=True)
class Finding:
    code: str
    status: Status
    message: str
    actual: float | None = None
    limit: float | None = None
    unit: str | None = None
    uncertainty_abs: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None


@dataclass(frozen=True)
class VerificationReport:
    room: str
    volume_m3: float
    ach: float
    findings: tuple[Finding, ...]

    @property
    def status(self) -> ReportStatus:
        statuses = {item.status for item in self.findings}
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
            "room": self.room,
            "volume_m3": self.volume_m3,
            "ach": self.ach,
            "status": self.status,
            "passed": self.passed,
            "findings": [asdict(item) for item in self.findings],
        }


def _lower_limit_status(
    actual: float,
    uncertainty_abs: float,
    limit: float,
) -> tuple[Status, float, float]:
    lower = actual - uncertainty_abs
    upper = actual + uncertainty_abs
    if lower >= limit:
        return "pass", lower, upper
    if upper < limit:
        return "fail", lower, upper
    return "indeterminate", lower, upper


def _upper_limit_status(
    actual: float,
    uncertainty_abs: float,
    limit: float,
    *,
    floor: float | None = None,
) -> tuple[Status, float, float]:
    lower = actual - uncertainty_abs
    upper = actual + uncertainty_abs
    if floor is not None:
        lower = max(floor, lower)
    if upper <= limit:
        return "pass", lower, upper
    if lower > limit:
        return "fail", lower, upper
    return "indeterminate", lower, upper


def verify_room(room: RoomSpec) -> VerificationReport:
    volume = room_volume_m3(room)
    ach = air_changes_per_hour(room)
    findings: list[Finding] = []

    if room.min_ach is None:
        findings.append(
            Finding(
                "ACH",
                "not_checked",
                "No project ACH requirement configured.",
                actual=ach,
                unit="1/h",
            )
        )
    else:
        ok = ach >= room.min_ach
        findings.append(
            Finding(
                "ACH",
                "pass" if ok else "fail",
                (
                    "Nominal supply ACH meets the configured project requirement."
                    if ok
                    else "Nominal supply ACH is below the configured project requirement."
                ),
                actual=ach,
                limit=room.min_ach,
                unit="1/h",
            )
        )

    if room.min_pressure_pa is None or room.observed_pressure_pa is None:
        findings.append(
            Finding(
                "PRESSURE",
                "not_checked",
                "Pressure requirement or observed value is not configured.",
                unit="Pa",
            )
        )
    else:
        status, lower, upper = _lower_limit_status(
            room.observed_pressure_pa,
            room.observed_pressure_uncertainty_pa,
            room.min_pressure_pa,
        )
        messages = {
            "pass": (
                "The complete observed-pressure interval meets the configured "
                "project minimum."
            ),
            "fail": (
                "The complete observed-pressure interval is below the configured "
                "project minimum."
            ),
            "indeterminate": (
                "The observed-pressure interval overlaps the configured project "
                "minimum."
            ),
        }
        findings.append(
            Finding(
                "PRESSURE",
                status,
                messages[status],
                actual=room.observed_pressure_pa,
                limit=room.min_pressure_pa,
                unit="Pa",
                uncertainty_abs=room.observed_pressure_uncertainty_pa,
                lower_bound=lower,
                upper_bound=upper,
            )
        )

    if not room.particle_requirements:
        findings.append(
            Finding(
                "PARTICLES",
                "not_checked",
                "No particle-concentration requirements configured.",
            )
        )
    else:
        for requirement in room.particle_requirements:
            status, lower, upper = _upper_limit_status(
                requirement.observed_concentration_per_m3,
                requirement.observed_uncertainty_abs_per_m3,
                requirement.max_concentration_per_m3,
                floor=0.0,
            )
            messages = {
                "pass": (
                    "The complete observed particle-concentration interval meets "
                    "the configured upper limit."
                ),
                "fail": (
                    "The complete observed particle-concentration interval exceeds "
                    "the configured upper limit."
                ),
                "indeterminate": (
                    "The observed particle-concentration interval overlaps the "
                    "configured upper limit."
                ),
            }
            findings.append(
                Finding(
                    f"PARTICLES_{requirement.size_um:g}UM",
                    status,
                    messages[status],
                    actual=requirement.observed_concentration_per_m3,
                    limit=requirement.max_concentration_per_m3,
                    unit="particles/m^3",
                    uncertainty_abs=requirement.observed_uncertainty_abs_per_m3,
                    lower_bound=lower,
                    upper_bound=upper,
                )
            )

    return VerificationReport(
        room=room.name,
        volume_m3=volume,
        ach=ach,
        findings=tuple(findings),
    )
