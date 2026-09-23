from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .calculations import air_changes_per_hour, room_volume_m3
from .models import PressureCascadeSpec, RoomSpec

Status = Literal["pass", "fail", "not_checked"]


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
    def passed(self) -> bool:
        return all(item.status != "fail" for item in self.findings)

    def to_dict(self) -> dict:
        return {
            "room": self.room,
            "volume_m3": self.volume_m3,
            "ach": self.ach,
            "passed": self.passed,
            "findings": [asdict(item) for item in self.findings],
        }


@dataclass(frozen=True)
class CascadeVerificationReport:
    cascade: str
    zone_pressures_pa: dict[str, float]
    findings: tuple[Finding, ...]

    @property
    def passed(self) -> bool:
        return all(item.status != "fail" for item in self.findings)

    def to_dict(self) -> dict:
        return {
            "cascade": self.cascade,
            "zone_pressures_pa": self.zone_pressures_pa,
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


def _find_pressure_cycle(cascade: PressureCascadeSpec) -> tuple[str, ...] | None:
    graph: dict[str, list[str]] = {zone.name: [] for zone in cascade.zones}
    for requirement in cascade.requirements:
        graph[requirement.high_zone].append(requirement.low_zone)

    state: dict[str, int] = {name: 0 for name in graph}
    stack: list[str] = []
    stack_index: dict[str, int] = {}

    def visit(node: str) -> tuple[str, ...] | None:
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for neighbour in graph[node]:
            if state[neighbour] == 0:
                cycle = visit(neighbour)
                if cycle is not None:
                    return cycle
            elif state[neighbour] == 1:
                start = stack_index[neighbour]
                return tuple(stack[start:] + [neighbour])
        stack.pop()
        stack_index.pop(node)
        state[node] = 2
        return None

    for node in graph:
        if state[node] == 0:
            cycle = visit(node)
            if cycle is not None:
                return cycle
    return None


def verify_pressure_cascade(cascade: PressureCascadeSpec) -> CascadeVerificationReport:
    """Verify user-configured pressure relationships across multiple zones.

    Each requirement means the configured high-pressure zone must exceed the
    configured low-pressure zone by at least min_delta_pa. The graph is also
    checked for directed cycles, which are contradictory when every required
    differential is strictly positive.
    """
    pressures = {zone.name: zone.observed_pressure_pa for zone in cascade.zones}
    findings: list[Finding] = []

    cycle = _find_pressure_cycle(cascade)
    if cycle is None:
        findings.append(
            Finding(
                "CASCADE_TOPOLOGY",
                "pass",
                "Pressure-direction requirements form an acyclic cascade.",
            )
        )
    else:
        findings.append(
            Finding(
                "CASCADE_TOPOLOGY",
                "fail",
                "Contradictory pressure-direction cycle detected: " + " -> ".join(cycle),
            )
        )

    for requirement in cascade.requirements:
        actual_delta = pressures[requirement.high_zone] - pressures[requirement.low_zone]
        ok = actual_delta >= requirement.min_delta_pa
        findings.append(
            Finding(
                f"PRESSURE_DELTA::{requirement.high_zone}->{requirement.low_zone}",
                "pass" if ok else "fail",
                (
                    f"Observed pressure differential from {requirement.high_zone} to {requirement.low_zone} "
                    f"meets the configured project requirement."
                    if ok
                    else f"Observed pressure differential from {requirement.high_zone} to {requirement.low_zone} "
                    f"is below the configured project requirement."
                ),
                actual=actual_delta,
                limit=requirement.min_delta_pa,
                unit="Pa",
            )
        )

    return CascadeVerificationReport(
        cascade=cascade.name,
        zone_pressures_pa=pressures,
        findings=tuple(findings),
    )
