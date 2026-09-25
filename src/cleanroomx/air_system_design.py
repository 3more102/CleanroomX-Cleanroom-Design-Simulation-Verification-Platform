from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


_ALLOWED_STRATEGIES = {
    "ceiling_supply_low_return",
    "ffu_ceiling",
    "mixed_return",
    "wall_return",
    "positive_pressure_suite",
    "negative_pressure_containment",
    "unidirectional_concept",
    "turbulent_mixing_concept",
}


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


@dataclass(frozen=True)
class AirProperties:
    density_kg_m3: float = 1.2
    specific_heat_j_kg_k: float = 1006.0
    source: str = "CleanroomX preliminary screening defaults; override for project conditions"

    def __post_init__(self) -> None:
        object.__setattr__(self, "density_kg_m3", _positive(self.density_kg_m3, "density_kg_m3"))
        object.__setattr__(self, "specific_heat_j_kg_k", _positive(self.specific_heat_j_kg_k, "specific_heat_j_kg_k"))
        if not self.source.strip():
            raise ValueError("air-properties source cannot be empty")


@dataclass(frozen=True)
class TerminalCapacity:
    name: str
    rated_airflow_m3_h: float
    design_utilization: float = 0.9

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("terminal capacity name cannot be empty")
        object.__setattr__(self, "rated_airflow_m3_h", _positive(self.rated_airflow_m3_h, "rated_airflow_m3_h"))
        utilization = _finite(self.design_utilization, "design_utilization")
        if not 0 < utilization <= 1:
            raise ValueError("design_utilization must be > 0 and <= 1")
        object.__setattr__(self, "design_utilization", utilization)

    @property
    def design_airflow_m3_h(self) -> float:
        return self.rated_airflow_m3_h * self.design_utilization


@dataclass(frozen=True)
class AirSystemRoom:
    name: str
    length_m: float
    width_m: float
    height_m: float
    strategy: str
    min_ach: float | None = None
    sensible_load_w: float = 0.0
    room_air_temp_c: float | None = None
    supply_air_temp_c: float | None = None
    minimum_outdoor_air_m3_h: float = 0.0
    exhaust_airflow_m3_h: float = 0.0
    transfer_in_airflow_m3_h: float = 0.0
    transfer_out_airflow_m3_h: float = 0.0
    minimum_surplus_m3_h: float = 0.0
    filter_unit: TerminalCapacity | None = None
    supply_terminal: TerminalCapacity | None = None
    return_terminal: TerminalCapacity | None = None
    exhaust_terminal: TerminalCapacity | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        for field_name in ("length_m", "width_m", "height_m"):
            object.__setattr__(self, field_name, _positive(getattr(self, field_name), field_name))
        if self.strategy not in _ALLOWED_STRATEGIES:
            raise ValueError(
                "strategy must be one of: " + ", ".join(sorted(_ALLOWED_STRATEGIES))
            )
        if self.min_ach is not None:
            object.__setattr__(self, "min_ach", _positive(self.min_ach, "min_ach"))
        for field_name in (
            "sensible_load_w",
            "minimum_outdoor_air_m3_h",
            "exhaust_airflow_m3_h",
            "transfer_in_airflow_m3_h",
            "transfer_out_airflow_m3_h",
            "minimum_surplus_m3_h",
        ):
            object.__setattr__(self, field_name, _nonnegative(getattr(self, field_name), field_name))
        if self.room_air_temp_c is not None:
            object.__setattr__(self, "room_air_temp_c", _finite(self.room_air_temp_c, "room_air_temp_c"))
        if self.supply_air_temp_c is not None:
            object.__setattr__(self, "supply_air_temp_c", _finite(self.supply_air_temp_c, "supply_air_temp_c"))
        if (self.room_air_temp_c is None) != (self.supply_air_temp_c is None):
            raise ValueError("room_air_temp_c and supply_air_temp_c must be configured together")
        if self.room_air_temp_c is not None and self.supply_air_temp_c >= self.room_air_temp_c and self.sensible_load_w > 0:
            raise ValueError("supply_air_temp_c must be below room_air_temp_c when sensible_load_w > 0")


@dataclass(frozen=True)
class AirSystemDesign:
    name: str
    rooms: tuple[AirSystemRoom, ...]
    air_properties: AirProperties = field(default_factory=AirProperties)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("air-system design name cannot be empty")
        if not self.rooms:
            raise ValueError("air-system design must contain at least one room")
        names = [room.name for room in self.rooms]
        if len(names) != len(set(names)):
            raise ValueError("air-system room names must be unique")


def _capacity_from_dict(data: dict | None, label: str) -> TerminalCapacity | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    return TerminalCapacity(
        name=data["name"],
        rated_airflow_m3_h=data["rated_airflow_m3_h"],
        design_utilization=data.get("design_utilization", 0.9),
    )


def air_system_design_from_dict(data: dict) -> AirSystemDesign:
    if not isinstance(data, dict):
        raise ValueError("air-system design input must be an object")
    air_data = data.get("air_properties", {})
    if not isinstance(air_data, dict):
        raise ValueError("air_properties must be an object")
    properties = AirProperties(
        density_kg_m3=air_data.get("density_kg_m3", 1.2),
        specific_heat_j_kg_k=air_data.get("specific_heat_j_kg_k", 1006.0),
        source=air_data.get(
            "source",
            "CleanroomX preliminary screening defaults; override for project conditions",
        ),
    )
    rooms: list[AirSystemRoom] = []
    for item in data["rooms"]:
        if not isinstance(item, dict):
            raise ValueError("rooms entries must be objects")
        dimensions = item.get("dimensions_m")
        if not isinstance(dimensions, dict):
            raise ValueError(f"room {item.get('name')!r} requires dimensions_m")
        rooms.append(
            AirSystemRoom(
                name=item["name"],
                length_m=dimensions["length"],
                width_m=dimensions["width"],
                height_m=dimensions["height"],
                strategy=item["strategy"],
                min_ach=item.get("min_ach"),
                sensible_load_w=item.get("sensible_load_w", 0.0),
                room_air_temp_c=item.get("room_air_temp_c"),
                supply_air_temp_c=item.get("supply_air_temp_c"),
                minimum_outdoor_air_m3_h=item.get("minimum_outdoor_air_m3_h", 0.0),
                exhaust_airflow_m3_h=item.get("exhaust_airflow_m3_h", 0.0),
                transfer_in_airflow_m3_h=item.get("transfer_in_airflow_m3_h", 0.0),
                transfer_out_airflow_m3_h=item.get("transfer_out_airflow_m3_h", 0.0),
                minimum_surplus_m3_h=item.get("minimum_surplus_m3_h", 0.0),
                filter_unit=_capacity_from_dict(item.get("filter_unit"), "filter_unit"),
                supply_terminal=_capacity_from_dict(item.get("supply_terminal"), "supply_terminal"),
                return_terminal=_capacity_from_dict(item.get("return_terminal"), "return_terminal"),
                exhaust_terminal=_capacity_from_dict(item.get("exhaust_terminal"), "exhaust_terminal"),
            )
        )
    return AirSystemDesign(name=data["name"], rooms=tuple(rooms), air_properties=properties)


def _device_count(capacity: TerminalCapacity | None, airflow_m3_h: float) -> int | None:
    if capacity is None:
        return None
    if airflow_m3_h <= 0:
        return 0
    return math.ceil(airflow_m3_h / capacity.design_airflow_m3_h)


def analyze_air_system_design(design: AirSystemDesign) -> dict:
    rooms: list[dict] = []
    overall_warnings: list[str] = []
    total_supply = 0.0
    total_return = 0.0
    total_exhaust = 0.0
    total_outdoor = 0.0

    for room in design.rooms:
        volume = room.length_m * room.width_m * room.height_m
        ach_airflow = None if room.min_ach is None else volume * room.min_ach
        sensible_airflow = None
        sensible_equation = None
        room_warnings: list[str] = []
        if room.sensible_load_w > 0:
            if room.room_air_temp_c is None or room.supply_air_temp_c is None:
                room_warnings.append(
                    "Sensible load is configured but room/supply air temperatures are missing; sensible-load airflow was not evaluated."
                )
            else:
                delta_t = room.room_air_temp_c - room.supply_air_temp_c
                sensible_airflow = (
                    room.sensible_load_w
                    / (design.air_properties.density_kg_m3 * design.air_properties.specific_heat_j_kg_k * delta_t)
                    * 3600.0
                )
                sensible_equation = "Q_sensible / (rho × cp × (T_room - T_supply)) × 3600"

        drivers: list[tuple[str, float]] = []
        if ach_airflow is not None:
            drivers.append(("minimum_ach", ach_airflow))
        if sensible_airflow is not None:
            drivers.append(("sensible_load", sensible_airflow))
        if room.minimum_outdoor_air_m3_h > 0:
            drivers.append(("minimum_outdoor_air", room.minimum_outdoor_air_m3_h))
        if not drivers:
            raise ValueError(
                f"room {room.name!r} has no airflow driver; configure min_ach, sensible-load temperatures, or minimum_outdoor_air_m3_h"
            )
        governing_basis, governing_airflow = max(drivers, key=lambda item: (item[1], item[0]))

        proposed_return = (
            governing_airflow
            + room.transfer_in_airflow_m3_h
            - room.exhaust_airflow_m3_h
            - room.transfer_out_airflow_m3_h
            - room.minimum_surplus_m3_h
        )
        if proposed_return < 0:
            room_warnings.append(
                "Requested exhaust/transfer/surplus exceeds supply plus transfer-in; proposed return was clamped to 0 m^3/h."
            )
            proposed_return = 0.0
        achieved_surplus = (
            governing_airflow
            + room.transfer_in_airflow_m3_h
            - proposed_return
            - room.exhaust_airflow_m3_h
            - room.transfer_out_airflow_m3_h
        )
        makeup_airflow = max(
            room.minimum_outdoor_air_m3_h,
            room.exhaust_airflow_m3_h + room.transfer_out_airflow_m3_h - room.transfer_in_airflow_m3_h,
        )

        counts = {
            "filter_units": _device_count(room.filter_unit, governing_airflow),
            "supply_terminals": _device_count(room.supply_terminal, governing_airflow),
            "return_grilles": _device_count(room.return_terminal, proposed_return),
            "exhaust_terminals": _device_count(room.exhaust_terminal, room.exhaust_airflow_m3_h),
        }
        if room.strategy == "ffu_ceiling" and room.filter_unit is None:
            room_warnings.append("FFU ceiling strategy selected but no filter_unit capacity is configured.")

        overall_warnings.extend(f"{room.name}: {warning}" for warning in room_warnings)
        total_supply += governing_airflow
        total_return += proposed_return
        total_exhaust += room.exhaust_airflow_m3_h
        total_outdoor += makeup_airflow
        rooms.append(
            {
                "name": room.name,
                "strategy": room.strategy,
                "volume_m3": volume,
                "airflow_drivers": {
                    "minimum_ach": {
                        "airflow_m3_h": ach_airflow,
                        "equation": "room_volume_m3 × minimum_ach_1_h",
                        "status": "evaluated" if ach_airflow is not None else "unchecked",
                    },
                    "sensible_load": {
                        "airflow_m3_h": sensible_airflow,
                        "equation": sensible_equation,
                        "status": "evaluated" if sensible_airflow is not None else "unchecked",
                    },
                    "minimum_outdoor_air": {
                        "airflow_m3_h": room.minimum_outdoor_air_m3_h,
                        "equation": "configured requirement",
                        "status": "evaluated" if room.minimum_outdoor_air_m3_h > 0 else "unchecked",
                    },
                },
                "governing_airflow_m3_h": governing_airflow,
                "governing_basis": governing_basis,
                "proposed_return_airflow_m3_h": proposed_return,
                "exhaust_airflow_m3_h": room.exhaust_airflow_m3_h,
                "transfer_in_airflow_m3_h": room.transfer_in_airflow_m3_h,
                "transfer_out_airflow_m3_h": room.transfer_out_airflow_m3_h,
                "minimum_surplus_m3_h": room.minimum_surplus_m3_h,
                "achieved_surplus_m3_h": achieved_surplus,
                "preliminary_makeup_airflow_m3_h": makeup_airflow,
                "equipment_counts": counts,
                "warnings": room_warnings,
            }
        )

    return {
        "design": design.name,
        "status": "warning" if overall_warnings else "ready",
        "air_properties": {
            "density_kg_m3": design.air_properties.density_kg_m3,
            "specific_heat_j_kg_k": design.air_properties.specific_heat_j_kg_k,
            "source": design.air_properties.source,
        },
        "rooms": rooms,
        "totals": {
            "supply_airflow_m3_h": total_supply,
            "proposed_return_airflow_m3_h": total_return,
            "exhaust_airflow_m3_h": total_exhaust,
            "preliminary_makeup_airflow_m3_h": total_outdoor,
        },
        "warning_count": len(overall_warnings),
        "warnings": overall_warnings,
        "engineering_note": (
            "This workflow produces preliminary design proposals from explicit requirements and disclosed screening assumptions. "
            "Equipment quantities are capacity-based preliminary counts, not manufacturer selection or certification."
        ),
    }
