from __future__ import annotations

from dataclasses import dataclass, field

from .numeric import finite_float, nonnegative_float, positive_float


@dataclass(frozen=True)
class ParticleRequirement:
    size_um: float
    max_concentration_per_m3: float
    observed_concentration_per_m3: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "size_um", positive_float(self.size_um, "size_um"))
        object.__setattr__(
            self,
            "max_concentration_per_m3",
            nonnegative_float(
                self.max_concentration_per_m3, "max_concentration_per_m3"
            ),
        )
        object.__setattr__(
            self,
            "observed_concentration_per_m3",
            nonnegative_float(
                self.observed_concentration_per_m3, "observed_concentration_per_m3"
            ),
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

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for label in (
            "length_m",
            "width_m",
            "height_m",
            "supply_airflow_m3_h",
        ):
            object.__setattr__(
                self, label, positive_float(getattr(self, label), label)
            )
        if self.min_ach is not None:
            object.__setattr__(
                self, "min_ach", positive_float(self.min_ach, "min_ach")
            )
        if self.min_pressure_pa is not None:
            object.__setattr__(
                self,
                "min_pressure_pa",
                finite_float(self.min_pressure_pa, "min_pressure_pa"),
            )
        if self.observed_pressure_pa is not None:
            object.__setattr__(
                self,
                "observed_pressure_pa",
                finite_float(self.observed_pressure_pa, "observed_pressure_pa"),
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
        object.__setattr__(
            self,
            "min_delta_pa",
            positive_float(self.min_delta_pa, "min_delta_pa"),
        )


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
