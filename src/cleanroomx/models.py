from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParticleRequirement:
    size_um: float
    max_concentration_per_m3: float
    observed_concentration_per_m3: float

    def __post_init__(self) -> None:
        if self.size_um <= 0:
            raise ValueError("particle size must be positive")
        if self.max_concentration_per_m3 < 0:
            raise ValueError("particle concentration limit cannot be negative")
        if self.observed_concentration_per_m3 < 0:
            raise ValueError("observed particle concentration cannot be negative")


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
    observed_pressure_uncertainty_pa: float = 0.0
    particle_requirements: tuple[ParticleRequirement, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for label, value in (
            ("length_m", self.length_m),
            ("width_m", self.width_m),
            ("height_m", self.height_m),
            ("supply_airflow_m3_h", self.supply_airflow_m3_h),
        ):
            if value <= 0:
                raise ValueError(f"{label} must be positive")
        if self.min_ach is not None and self.min_ach <= 0:
            raise ValueError("min_ach must be positive when provided")
        uncertainty = float(self.observed_pressure_uncertainty_pa)
        if uncertainty < 0:
            raise ValueError("observed_pressure_uncertainty_pa cannot be negative")
        if self.observed_pressure_pa is None and uncertainty != 0:
            raise ValueError(
                "observed_pressure_uncertainty_pa requires observed_pressure_pa"
            )
        object.__setattr__(self, "observed_pressure_uncertainty_pa", uncertainty)


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
        if self.min_delta_pa <= 0:
            raise ValueError("min_delta_pa must be positive")


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
                raise ValueError(f"duplicate pressure-cascade requirement: {higher!r} -> {lower!r}")
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
