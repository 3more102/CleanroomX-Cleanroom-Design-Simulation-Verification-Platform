from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


def _finite(value: Any, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def _positive(value: Any, field_name: str) -> float:
    value = _finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _nonnegative(value: Any, field_name: str) -> float:
    value = _finite(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _optional_range(value: Any, field_name: str, *, low: float | None = None, high: float | None = None) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"min", "max"}:
        raise ValueError(f"{field_name} must be an object with exactly min and max")
    minimum = _finite(value["min"], f"{field_name}.min")
    maximum = _finite(value["max"], f"{field_name}.max")
    if minimum > maximum:
        raise ValueError(f"{field_name}.min must be <= {field_name}.max")
    if low is not None and minimum < low:
        raise ValueError(f"{field_name}.min must be >= {low}")
    if high is not None and maximum > high:
        raise ValueError(f"{field_name}.max must be <= {high}")
    return minimum, maximum


@dataclass(frozen=True)
class ReferenceProfile:
    id: str
    title: str
    source: str
    values: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("reference profile id cannot be empty")
        if not self.title.strip():
            raise ValueError("reference profile title cannot be empty")
        if not self.source.strip():
            raise ValueError("reference profile source cannot be empty")
        if not isinstance(self.values, dict):
            raise ValueError("reference profile values must be an object")


@dataclass(frozen=True)
class RoomDesignRequirements:
    name: str
    length_m: float
    width_m: float
    height_m: float
    profile_id: str | None = None
    classification: str | None = None
    intended_process: str | None = None
    occupancy: int = 0
    occupant_sensible_w_per_person: float = 0.0
    equipment_sensible_load_w: float = 0.0
    process_sensible_load_w: float = 0.0
    temperature_c: tuple[float, float] | None = None
    relative_humidity_percent: tuple[float, float] | None = None
    min_ach: float | None = None
    pressure_target_pa: float | None = None
    recovery_target_minutes: float | None = None
    filtration_requirement: str | None = None
    contamination_assumptions: tuple[str, ...] = field(default_factory=tuple)
    supply_return_strategy: str | None = None
    operating_mode: str | None = None
    origins: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for field_name in ("length_m", "width_m", "height_m"):
            object.__setattr__(self, field_name, _positive(getattr(self, field_name), field_name))
        occupancy = int(self.occupancy)
        if occupancy != self.occupancy or occupancy < 0:
            raise ValueError("occupancy must be a non-negative integer")
        object.__setattr__(self, "occupancy", occupancy)
        for field_name in (
            "occupant_sensible_w_per_person",
            "equipment_sensible_load_w",
            "process_sensible_load_w",
        ):
            object.__setattr__(self, field_name, _nonnegative(getattr(self, field_name), field_name))
        if self.min_ach is not None:
            object.__setattr__(self, "min_ach", _positive(self.min_ach, "min_ach"))
        if self.pressure_target_pa is not None:
            object.__setattr__(self, "pressure_target_pa", _finite(self.pressure_target_pa, "pressure_target_pa"))
        if self.recovery_target_minutes is not None:
            object.__setattr__(self, "recovery_target_minutes", _positive(self.recovery_target_minutes, "recovery_target_minutes"))
        if self.temperature_c is not None:
            _optional_range({"min": self.temperature_c[0], "max": self.temperature_c[1]}, "temperature_c")
        if self.relative_humidity_percent is not None:
            _optional_range(
                {"min": self.relative_humidity_percent[0], "max": self.relative_humidity_percent[1]},
                "relative_humidity_percent",
                low=0.0,
                high=100.0,
            )


@dataclass(frozen=True)
class DesignRequirementsProject:
    name: str
    rooms: tuple[RoomDesignRequirements, ...]
    reference_profiles: tuple[ReferenceProfile, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name cannot be empty")
        if not self.rooms:
            raise ValueError("project must contain at least one room")
        names = [room.name for room in self.rooms]
        if len(names) != len(set(names)):
            raise ValueError("room names must be unique")
        profile_ids = [profile.id for profile in self.reference_profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("reference profile ids must be unique")


def _origin(source_kind: str, source_name: str, source_reference: str) -> dict[str, str]:
    return {
        "kind": source_kind,
        "name": source_name,
        "reference": source_reference,
    }


def _merge_room_input(room: dict, profiles: dict[str, ReferenceProfile]) -> tuple[dict, dict[str, dict[str, str]]]:
    profile_id = room.get("profile_id")
    merged: dict[str, Any] = {}
    origins: dict[str, dict[str, str]] = {}
    if profile_id is not None:
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")
        if profile_id not in profiles:
            raise ValueError(f"unknown reference profile: {profile_id!r}")
        profile = profiles[profile_id]
        for key, value in profile.values.items():
            merged[key] = value
            origins[key] = _origin("reference_profile", profile.title, profile.source)
    for key, value in room.items():
        if key == "profile_id":
            continue
        merged[key] = value
        origins[key] = _origin("room_input", room.get("name", "room"), "project input")
    merged["profile_id"] = profile_id
    return merged, origins


def design_requirements_from_dict(data: dict) -> DesignRequirementsProject:
    if not isinstance(data, dict):
        raise ValueError("design requirements input must be an object")
    profiles: list[ReferenceProfile] = []
    for item in data.get("reference_profiles", []):
        if not isinstance(item, dict):
            raise ValueError("reference_profiles entries must be objects")
        profiles.append(
            ReferenceProfile(
                id=item["id"],
                title=item["title"],
                source=item["source"],
                values=dict(item.get("values", {})),
            )
        )
    profile_map = {profile.id: profile for profile in profiles}
    rooms: list[RoomDesignRequirements] = []
    for item in data["rooms"]:
        if not isinstance(item, dict):
            raise ValueError("rooms entries must be objects")
        merged, origins = _merge_room_input(item, profile_map)
        dimensions = merged.get("dimensions_m")
        if not isinstance(dimensions, dict):
            raise ValueError(f"room {merged.get('name')!r} requires dimensions_m")
        temperature = _optional_range(merged.get("temperature_c"), "temperature_c")
        rh = _optional_range(
            merged.get("relative_humidity_percent"),
            "relative_humidity_percent",
            low=0.0,
            high=100.0,
        )
        assumptions = merged.get("contamination_assumptions", [])
        if not isinstance(assumptions, list) or not all(isinstance(value, str) and value.strip() for value in assumptions):
            raise ValueError("contamination_assumptions must be an array of non-empty strings")
        rooms.append(
            RoomDesignRequirements(
                name=merged["name"],
                length_m=dimensions["length"],
                width_m=dimensions["width"],
                height_m=dimensions["height"],
                profile_id=merged.get("profile_id"),
                classification=merged.get("classification"),
                intended_process=merged.get("intended_process"),
                occupancy=merged.get("occupancy", 0),
                occupant_sensible_w_per_person=merged.get("occupant_sensible_w_per_person", 0.0),
                equipment_sensible_load_w=merged.get("equipment_sensible_load_w", 0.0),
                process_sensible_load_w=merged.get("process_sensible_load_w", 0.0),
                temperature_c=temperature,
                relative_humidity_percent=rh,
                min_ach=merged.get("min_ach"),
                pressure_target_pa=merged.get("pressure_target_pa"),
                recovery_target_minutes=merged.get("recovery_target_minutes"),
                filtration_requirement=merged.get("filtration_requirement"),
                contamination_assumptions=tuple(assumptions),
                supply_return_strategy=merged.get("supply_return_strategy"),
                operating_mode=merged.get("operating_mode"),
                origins=origins,
            )
        )
    return DesignRequirementsProject(
        name=data["name"],
        rooms=tuple(rooms),
        reference_profiles=tuple(profiles),
    )


def _target(
    *,
    name: str,
    value: Any,
    unit: str | None,
    source: str,
    equation: str,
    assumptions: list[str] | None = None,
    status: str = "configured",
    warnings: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "source": source,
        "equation": equation,
        "assumptions": list(assumptions or []),
        "status": status,
        "warnings": list(warnings or []),
        "provenance": dict(provenance or {}),
    }


def _source_for(room: RoomDesignRequirements, key: str) -> tuple[str, dict[str, Any]]:
    origin = room.origins.get(key)
    if origin is None:
        return "not configured", {}
    label = origin["name"]
    if origin["kind"] == "reference_profile":
        label = f"reference profile: {label}"
    return label, dict(origin)


def analyze_design_requirements(project: DesignRequirementsProject) -> dict:
    room_results: list[dict] = []
    project_warnings: list[str] = []
    for room in project.rooms:
        area = room.length_m * room.width_m
        volume = area * room.height_m
        occupant_load = room.occupancy * room.occupant_sensible_w_per_person
        provided_sensible = occupant_load + room.equipment_sensible_load_w + room.process_sensible_load_w
        min_ach_source, min_ach_provenance = _source_for(room, "min_ach")
        if room.min_ach is None:
            ach_airflow = None
            ach_status = "unchecked"
            ach_warnings = ["No minimum ACH requirement was configured; no ACH-based airflow target was derived."]
            project_warnings.append(f"{room.name}: minimum ACH is not configured")
        else:
            ach_airflow = volume * room.min_ach
            ach_status = "derived"
            ach_warnings = []

        required_fields = {
            "temperature_c": room.temperature_c,
            "relative_humidity_percent": room.relative_humidity_percent,
            "pressure_target_pa": room.pressure_target_pa,
            "filtration_requirement": room.filtration_requirement,
            "supply_return_strategy": room.supply_return_strategy,
        }
        missing = [key for key, value in required_fields.items() if value is None]
        warnings = [f"{key} is not configured" for key in missing]
        project_warnings.extend(f"{room.name}: {warning}" for warning in warnings)

        targets = [
            _target(
                name="floor_area",
                value=area,
                unit="m^2",
                source="room geometry",
                equation="length_m × width_m",
                status="derived",
                provenance={"length_m": room.length_m, "width_m": room.width_m},
            ),
            _target(
                name="room_volume",
                value=volume,
                unit="m^3",
                source="room geometry",
                equation="length_m × width_m × height_m",
                status="derived",
                provenance={"length_m": room.length_m, "width_m": room.width_m, "height_m": room.height_m},
            ),
            _target(
                name="minimum_ach",
                value=room.min_ach,
                unit="1/h",
                source=min_ach_source,
                equation="configured requirement",
                status="configured" if room.min_ach is not None else "unchecked",
                warnings=[] if room.min_ach is not None else ["No minimum ACH requirement configured."],
                provenance=min_ach_provenance,
            ),
            _target(
                name="ach_based_supply_airflow",
                value=ach_airflow,
                unit="m^3/h",
                source=min_ach_source,
                equation="room_volume_m3 × minimum_ach_1_h",
                status=ach_status,
                warnings=ach_warnings,
                provenance=min_ach_provenance,
            ),
            _target(
                name="provided_sensible_load",
                value=provided_sensible,
                unit="W",
                source="room input",
                equation="occupancy × occupant_sensible_w_per_person + equipment_sensible_load_w + process_sensible_load_w",
                assumptions=["Only explicitly entered sensible-load components are included."],
                status="derived",
                provenance={
                    "occupancy": room.occupancy,
                    "occupant_sensible_w_per_person": room.occupant_sensible_w_per_person,
                    "equipment_sensible_load_w": room.equipment_sensible_load_w,
                    "process_sensible_load_w": room.process_sensible_load_w,
                },
            ),
        ]
        room_results.append(
            {
                "name": room.name,
                "profile_id": room.profile_id,
                "classification": room.classification,
                "intended_process": room.intended_process,
                "operating_mode": room.operating_mode,
                "dimensions_m": {"length": room.length_m, "width": room.width_m, "height": room.height_m},
                "occupancy": room.occupancy,
                "temperature_c": None if room.temperature_c is None else {"min": room.temperature_c[0], "max": room.temperature_c[1]},
                "relative_humidity_percent": None if room.relative_humidity_percent is None else {"min": room.relative_humidity_percent[0], "max": room.relative_humidity_percent[1]},
                "pressure_target_pa": room.pressure_target_pa,
                "recovery_target_minutes": room.recovery_target_minutes,
                "filtration_requirement": room.filtration_requirement,
                "contamination_assumptions": list(room.contamination_assumptions),
                "supply_return_strategy": room.supply_return_strategy,
                "targets": targets,
                "warnings": warnings,
            }
        )

    return {
        "project": project.name,
        "status": "warning" if project_warnings else "ready",
        "rooms": room_results,
        "warning_count": len(project_warnings),
        "warnings": project_warnings,
        "reference_profiles": [
            {"id": profile.id, "title": profile.title, "source": profile.source, "values": dict(profile.values)}
            for profile in project.reference_profiles
        ],
        "engineering_note": (
            "Targets are derived only from explicit room inputs and explicitly selected reference profiles. "
            "CleanroomX does not treat these design targets as certification or regulatory approval."
        ),
    }
