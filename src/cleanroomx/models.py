from __future__ import annotations

import math
from dataclasses import dataclass, field


def _finite(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


@dataclass(frozen=True)
class ParticleRequirement:
    size_um: float
    max_concentration_per_m3: float
    observed_concentration_per_m3: float
    observed_uncertainty_abs_per_m3: float = 0.0

    def __post_init__(self) -> None:
        size = _finite(self.size_um, "size_um")
        limit = _finite(
            self.max_concentration_per_m3, "max_concentration_per_m3"
        )
        observed = _finite(
            self.observed_concentration_per_m3,
            "observed_concentration_per_m3",
        )
        uncertainty = _finite(
            self.observed_uncertainty_abs_per_m3,
            "observed_uncertainty_abs_per_m3",
        )
        if size <= 0:
            raise ValueError("particle size must be positive")
        if limit < 0:
            raise ValueError("particle concentration limit cannot be negative")
        if observed < 0:
            raise ValueError("observed particle concentration cannot be negative")
        if uncertainty < 0:
            raise ValueError("observed particle uncertainty cannot be negative")
        object.__setattr__(self, "size_um", size)
        object.__setattr__(self, "max_concentration_per_m3", limit)
        object.__setattr__(self, "observed_concentration_per_m3", observed)
        object.__setattr__(
            self, "observed_uncertainty_abs_per_m3", uncertainty
        )


@dataclass(frozen=True)
class RoomSpec:
    name: str
    length_m: float
    width_m: float
    height_m: float
    supply_airflow_m3_h: float
    min_ach: float | None = None
    min_pressure_pa: float | None = None
    observed_pressure_pa: float | None = None
    particle_requirements: tuple[ParticleRequirement, ...] = field(default_factory=tuple)
    observed_pressure_uncertainty_pa: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for label in (
            "length_m",
            "width_m",
            "height_m",
            "supply_airflow_m3_h",
        ):
            value = _finite(getattr(self, label), label)
            if value <= 0:
                raise ValueError(f"{label} must be positive")
            object.__setattr__(self, label, value)

        if self.min_ach is not None:
            min_ach = _finite(self.min_ach, "min_ach")
            if min_ach <= 0:
                raise ValueError("min_ach must be positive when provided")
            object.__setattr__(self, "min_ach", min_ach)

        if self.min_pressure_pa is not None:
            object.__setattr__(
                self,
                "min_pressure_pa",
                _finite(self.min_pressure_pa, "min_pressure_pa"),
            )
        if self.observed_pressure_pa is not None:
            object.__setattr__(
                self,
                "observed_pressure_pa",
                _finite(self.observed_pressure_pa, "observed_pressure_pa"),
            )

        pressure_uncertainty = _finite(
            self.observed_pressure_uncertainty_pa,
            "observed_pressure_uncertainty_pa",
        )
        if pressure_uncertainty < 0:
            raise ValueError("observed pressure uncertainty cannot be negative")
        if pressure_uncertainty > 0 and self.observed_pressure_pa is None:
            raise ValueError(
                "observed_pressure_pa is required when pressure uncertainty is supplied"
            )
        object.__setattr__(
            self, "observed_pressure_uncertainty_pa", pressure_uncertainty
        )


@dataclass(frozen=True)
class PressureCascadeRequirement:
    higher_pressure_room: str
    lower_pressure_room: str
    min_delta_pa: float

    def __post_init__(self) -> None:
        if not self.higher_pressure_room.strip() or not self.lower_pressure_room.strip():
            raise ValueError("pressure-cascade room names cannot be empty")
        if self.higher_pressure_room == self.lower_pressure_room:
            raise ValueError("pressure-cascade rooms must be different")
        minimum = _finite(self.min_delta_pa, "min_delta_pa")
        if minimum <= 0:
            raise ValueError("min_delta_pa must be positive")
        object.__setattr__(self, "min_delta_pa", minimum)


@dataclass(frozen=True)
class ProjectSpec:
    name: str
    rooms: tuple[RoomSpec, ...]
    pressure_cascade: tuple[PressureCascadeRequirement, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name cannot be empty")
        if not self.rooms:
            raise ValueError("project must contain at least one room")

        room_names = [room.name for room in self.rooms]
        if len(room_names) != len(set(room_names)):
            raise ValueError("project room names must be unique")

        known_rooms = set(room_names)
        seen_edges: set[tuple[str, str]] = set()
        adjacency = {name: [] for name in room_names}
        indegree = {name: 0 for name in room_names}

        for requirement in self.pressure_cascade:
            higher = requirement.higher_pressure_room
            lower = requirement.lower_pressure_room
            if higher not in known_rooms or lower not in known_rooms:
                raise ValueError(
                    f"pressure-cascade requirement references unknown room: {higher!r} -> {lower!r}"
                )
            edge = (higher, lower)
            if edge in seen_edges:
                raise ValueError(
                    f"duplicate pressure-cascade requirement: {higher!r} -> {lower!r}"
                )
            seen_edges.add(edge)
            adjacency[higher].append(lower)
            indegree[lower] += 1

        queue = [name for name, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            room_name = queue.pop()
            visited += 1
            for lower in adjacency[room_name]:
                indegree[lower] -= 1
                if indegree[lower] == 0:
                    queue.append(lower)

        if visited != len(room_names):
            raise ValueError("pressure-cascade requirements contain a directed cycle")
