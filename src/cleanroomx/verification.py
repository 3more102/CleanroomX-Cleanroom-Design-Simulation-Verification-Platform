from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .calculations import air_changes_per_hour, room_volume_m3
from .models import Provenance, RoomSpec

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
    requirement_reference: str | None = None
    provenance: Provenance | None = None


@dataclass(frozen=True)
class VerificationReport:
    room: str
    volume_m3: float
    ach: float
    findings: tuple[Finding, ...]

    @property
    def passed(self) -> bool:
        return all(item.status not in {"fail", "indeterminate"} for item in self.findings)

    def to_dict(self) -> dict:
        return {
            "room": self.room,
            "volume_m3": self.volume_m3,
            "ach": self.ach,
            "passed": self.passed,
            "findings": [asdict(item) for item in self.findings],
        }


def _minimum_status(
    actual: float, limit: float, uncertainty: float | None
) -> tuple[Status, float | None, float | None]:
    if uncertainty is None or uncertainty == 0:
        return ("pass" if actual >= limit else "fail"), None, None

    low = max(0.0, actual - uncertainty)
    high = actual + uncertainty
    if low >= limit:
        status: Status = "pass"
    elif high < limit:
        status = "fail"
    else:
        status = "indeterminate"
    return status, low, high


def _maximum_status(
    actual: float, limit: float, uncertainty: float | None
) -> tuple[Status, float | None, float | None]:
    if uncertainty is None or uncertainty == 0:
        return ("pass" if actual <= limit else "fail"), None, None

    low = max(0.0, actual - uncertainty)
    high = actual + uncertainty
    if high <= limit:
        status: Status = "pass"
    elif low > limit:
        status = "fail"
    else:
        status = "indeterminate"
    return status, low, high


def verify_room(room: RoomSpec) -> VerificationReport:
    volume = room_volume_m3(room)
    ach = air_changes_per_hour(room)
    findings: list[Finding] = []

    ach_uncertainty = (
        room.supply_airflow_uncertainty_m3_h / volume
        if room.supply_airflow_uncertainty_m3_h is not None
        else None
    )

    if room.min_ach is None:
        findings.append(
            Finding(
                "ACH",
                "not_checked",
                "No project ACH requirement configured.",
                actual=ach,
                unit="1/h",
                uncertainty=ach_uncertainty,
                requirement_reference=room.ach_requirement_reference,
                provenance=room.airflow_provenance,
            )
        )
    else:
        status, low, high = _minimum_status(ach, room.min_ach, ach_uncertainty)
        messages = {
            "pass": "Nominal supply ACH, including configured uncertainty when provided, meets the project requirement.",
            "fail": "Nominal supply ACH, including configured uncertainty when provided, is below the project requirement.",
            "indeterminate": "The configured ACH uncertainty interval overlaps the project requirement.",
        }
        findings.append(
            Finding(
                "ACH",
                status,
                messages[status],
                actual=ach,
                limit=room.min_ach,
                unit="1/h",
                uncertainty=ach_uncertainty,
                interval_low=low,
                interval_high=high,
                requirement_reference=room.ach_requirement_reference,
                provenance=room.airflow_provenance,
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
                requirement_reference=room.pressure_requirement_reference,
                provenance=room.pressure_provenance,
            )
        )
    else:
        status, low, high = _minimum_status(
            room.observed_pressure_pa,
            room.min_pressure_pa,
            room.observed_pressure_uncertainty_pa,
        )
        messages = {
            "pass": "Observed differential pressure, including configured uncertainty when provided, meets the project requirement.",
            "fail": "Observed differential pressure, including configured uncertainty when provided, is below the project requirement.",
            "indeterminate": "The configured pressure uncertainty interval overlaps the project requirement.",
        }
        findings.append(
            Finding(
                "PRESSURE",
                status,
                messages[status],
                actual=room.observed_pressure_pa,
                limit=room.min_pressure_pa,
                unit="Pa",
                uncertainty=room.observed_pressure_uncertainty_pa,
                interval_low=low,
                interval_high=high,
                requirement_reference=room.pressure_requirement_reference,
                provenance=room.pressure_provenance,
            )
        )

    if not room.particle_requirements:
        findings.append(Finding("PARTICLES", "not_checked", "No particle-concentration requirements configured."))
    else:
        for requirement in room.particle_requirements:
            status, low, high = _maximum_status(
                requirement.observed_concentration_per_m3,
                requirement.max_concentration_per_m3,
                requirement.observed_uncertainty_per_m3,
            )
            messages = {
                "pass": "Observed particle concentration, including configured uncertainty when provided, meets the configured limit.",
                "fail": "Observed particle concentration, including configured uncertainty when provided, exceeds the configured limit.",
                "indeterminate": "The configured particle-count uncertainty interval overlaps the concentration limit.",
            }
            findings.append(
                Finding(
                    f"PARTICLES_{requirement.size_um:g}UM",
                    status,
                    messages[status],
                    actual=requirement.observed_concentration_per_m3,
                    limit=requirement.max_concentration_per_m3,
                    unit="particles/m^3",
                    uncertainty=requirement.observed_uncertainty_per_m3,
                    interval_low=low,
                    interval_high=high,
                    requirement_reference=requirement.requirement_reference,
                    provenance=requirement.provenance,
                )
            )

    return VerificationReport(room=room.name, volume_m3=volume, ach=ach, findings=tuple(findings))
