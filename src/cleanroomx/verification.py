from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .calculations import air_changes_per_hour, room_volume_m3
from .models import RoomSpec

Status = Literal["pass", "fail", "indeterminate", "not_checked"]


@dataclass(frozen=True)
class Finding:
    code: str
    status: Status
    message: str
    actual: float | None = None
    limit: float | None = None
    unit: str | None = None
    uncertainty: float | None = None
    interval_low: float | None = None
    interval_high: float | None = None


@dataclass(frozen=True)
class VerificationReport:
    room: str
    volume_m3: float
    ach: float
    findings: tuple[Finding, ...]

    @property
    def failed(self) -> bool:
        return any(item.status == "fail" for item in self.findings)

    @property
    def indeterminate(self) -> bool:
        return any(item.status == "indeterminate" for item in self.findings)

    @property
    def passed(self) -> bool:
        return not self.failed and not self.indeterminate

    def to_dict(self) -> dict:
        return {
            "room": self.room,
            "volume_m3": self.volume_m3,
            "ach": self.ach,
            "passed": self.passed,
            "failed": self.failed,
            "indeterminate": self.indeterminate,
            "findings": [asdict(item) for item in self.findings],
        }


def verify_room(room: RoomSpec) -> VerificationReport:
    volume = room_volume_m3(room)
    ach = air_changes_per_hour(room)
    findings: list[Finding] = []

    if room.min_ach is None:
        findings.append(Finding("ACH", "not_checked", "No project ACH requirement configured.", actual=ach, unit="1/h"))
    else:
        ok = ach >= room.min_ach
        findings.append(
            Finding(
                "ACH",
                "pass" if ok else "fail",
                "Nominal supply ACH meets the configured project requirement." if ok else "Nominal supply ACH is below the configured project requirement.",
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
                actual=room.observed_pressure_pa,
                limit=room.min_pressure_pa,
                unit="Pa",
                uncertainty=room.observed_pressure_uncertainty_pa,
            )
        )
    else:
        uncertainty = room.observed_pressure_uncertainty_pa
        low = room.observed_pressure_pa - uncertainty
        high = room.observed_pressure_pa + uncertainty
        if low >= room.min_pressure_pa:
            status: Status = "pass"
            message = (
                "The complete observed-pressure interval meets the configured project requirement."
            )
        elif high < room.min_pressure_pa:
            status = "fail"
            message = (
                "The complete observed-pressure interval is below the configured project requirement."
            )
        else:
            status = "indeterminate"
            message = (
                "The configured pressure requirement lies inside the observed-pressure "
                "uncertainty interval."
            )
        findings.append(
            Finding(
                "PRESSURE",
                status,
                message,
                actual=room.observed_pressure_pa,
                limit=room.min_pressure_pa,
                unit="Pa",
                uncertainty=uncertainty,
                interval_low=low,
                interval_high=high,
            )
        )

    if not room.particle_requirements:
        findings.append(Finding("PARTICLES", "not_checked", "No particle-concentration requirements configured."))
    else:
        for requirement in room.particle_requirements:
            ok = requirement.observed_concentration_per_m3 <= requirement.max_concentration_per_m3
            findings.append(
                Finding(
                    f"PARTICLES_{requirement.size_um:g}UM",
                    "pass" if ok else "fail",
                    "Observed particle concentration meets the configured limit." if ok else "Observed particle concentration exceeds the configured limit.",
                    actual=requirement.observed_concentration_per_m3,
                    limit=requirement.max_concentration_per_m3,
                    unit="particles/m^3",
                )
            )

    return VerificationReport(room=room.name, volume_m3=volume, ach=ach, findings=tuple(findings))
