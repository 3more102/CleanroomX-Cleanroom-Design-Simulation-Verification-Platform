from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Literal

from .calculations import air_changes_per_hour, room_volume_m3
from .models import RoomSpec

Status = Literal["pass", "fail", "not_checked"]
AggregateVerificationStatus = Literal[
    "pass", "fail", "pass_with_unchecked", "not_checked"
]


def aggregate_verification_status(
    statuses: Iterable[Status],
) -> AggregateVerificationStatus:
    """Aggregate finding states without promoting unchecked evidence to pass."""
    values = tuple(statuses)
    unsupported = [
        status for status in values if status not in {"pass", "fail", "not_checked"}
    ]
    if unsupported:
        raise ValueError(f"unsupported verification status: {unsupported[0]!r}")
    if "fail" in values:
        return "fail"
    has_pass = "pass" in values
    has_unchecked = "not_checked" in values
    if has_pass and has_unchecked:
        return "pass_with_unchecked"
    if has_pass:
        return "pass"
    return "not_checked"


@dataclass(frozen=True)
class Finding:
    code: str
    status: Status
    message: str
    actual: float | None = None
    limit: float | None = None
    unit: str | None = None


@dataclass(frozen=True)
class VerificationReport:
    room: str
    volume_m3: float
    ach: float
    findings: tuple[Finding, ...]

    @property
    def status(self) -> AggregateVerificationStatus:
        return aggregate_verification_status(item.status for item in self.findings)

    @property
    def complete(self) -> bool:
        return bool(self.findings) and all(
            item.status != "not_checked" for item in self.findings
        )

    @property
    def passed(self) -> bool:
        """Compatibility boolean: true when no configured check failed."""
        return all(item.status != "fail" for item in self.findings)

    def to_dict(self) -> dict:
        return {
            "room": self.room,
            "volume_m3": self.volume_m3,
            "ach": self.ach,
            "status": self.status,
            "complete": self.complete,
            "passed": self.passed,
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
        findings.append(Finding("PRESSURE", "not_checked", "Pressure requirement or observed value is not configured.", unit="Pa"))
    else:
        ok = room.observed_pressure_pa >= room.min_pressure_pa
        findings.append(
            Finding(
                "PRESSURE",
                "pass" if ok else "fail",
                "Observed differential pressure meets the configured project requirement." if ok else "Observed differential pressure is below the configured project requirement.",
                actual=room.observed_pressure_pa,
                limit=room.min_pressure_pa,
                unit="Pa",
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
