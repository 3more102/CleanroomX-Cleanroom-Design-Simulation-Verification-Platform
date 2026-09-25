from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from .airflow import analyze_air_balance
from .hvac_models import AirBalanceDesign, ThermalDesign
from .numeric import finite_float, nonnegative_float, positive_float
from .thermal import analyze_thermal_design


_ALLOWED_STRATEGIES = frozenset(
    {
        "ceiling_supply_low_return",
        "ffu_ceiling",
        "mixed_return",
        "wall_return",
        "positive_pressure_suite",
        "negative_pressure_containment",
        "unidirectional_concept",
        "turbulent_mixing_concept",
        "project_defined",
    }
)
_ALLOWED_EQUIPMENT_CATEGORIES = frozenset(
    {
        "supply_terminal",
        "ffu",
        "return_grille",
        "exhaust_terminal",
        "filter",
    }
)


def _nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_nonempty(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _range(
    value: tuple[float, float] | None,
    field_name: str,
    *,
    minimum_allowed: float | None = None,
    maximum_allowed: float | None = None,
) -> tuple[float, float] | None:
    if value is None:
        return None
    if len(value) != 2:
        raise ValueError(f"{field_name} must contain exactly two values")
    low = finite_float(value[0], f"{field_name}[0]")
    high = finite_float(value[1], f"{field_name}[1]")
    if high < low:
        raise ValueError(f"{field_name} upper value must be >= lower value")
    if minimum_allowed is not None and low < minimum_allowed:
        raise ValueError(f"{field_name} must be >= {minimum_allowed}")
    if maximum_allowed is not None and high > maximum_allowed:
        raise ValueError(f"{field_name} must be <= {maximum_allowed}")
    return (low, high)


@dataclass(frozen=True)
class RequirementProfile:
    id: str
    name: str
    source: dict[str, Any]
    minimum_ach: float | None = None
    minimum_supply_airflow_m3_h: float | None = None
    temperature_range_c: tuple[float, float] | None = None
    relative_humidity_range_percent: tuple[float, float] | None = None
    recovery_target_minutes: float | None = None
    filtration_requirement: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _nonempty(self.id, "profile id"))
        object.__setattr__(self, "name", _nonempty(self.name, "profile name"))
        if not isinstance(self.source, dict) or not self.source:
            raise ValueError("profile source must be a non-empty object")
        object.__setattr__(self, "source", copy.deepcopy(self.source))
        if self.minimum_ach is not None:
            object.__setattr__(
                self,
                "minimum_ach",
                positive_float(self.minimum_ach, "minimum_ach"),
            )
        if self.minimum_supply_airflow_m3_h is not None:
            object.__setattr__(
                self,
                "minimum_supply_airflow_m3_h",
                positive_float(
                    self.minimum_supply_airflow_m3_h,
                    "minimum_supply_airflow_m3_h",
                ),
            )
        object.__setattr__(
            self,
            "temperature_range_c",
            _range(self.temperature_range_c, "temperature_range_c"),
        )
        object.__setattr__(
            self,
            "relative_humidity_range_percent",
            _range(
                self.relative_humidity_range_percent,
                "relative_humidity_range_percent",
                minimum_allowed=0.0,
                maximum_allowed=100.0,
            ),
        )
        if self.recovery_target_minutes is not None:
            object.__setattr__(
                self,
                "recovery_target_minutes",
                positive_float(
                    self.recovery_target_minutes,
                    "recovery_target_minutes",
                ),
            )
        object.__setattr__(
            self,
            "filtration_requirement",
            _optional_nonempty(
                self.filtration_requirement,
                "filtration_requirement",
            ),
        )


@dataclass(frozen=True)
class EquipmentSelectionInput:
    category: str
    name: str
    rated_airflow_m3_h: float
    design_utilization: float

    def __post_init__(self) -> None:
        if self.category not in _ALLOWED_EQUIPMENT_CATEGORIES:
            raise ValueError(
                "equipment category must be one of: "
                + ", ".join(sorted(_ALLOWED_EQUIPMENT_CATEGORIES))
            )
        object.__setattr__(self, "name", _nonempty(self.name, "equipment name"))
        object.__setattr__(
            self,
            "rated_airflow_m3_h",
            positive_float(self.rated_airflow_m3_h, "rated_airflow_m3_h"),
        )
        utilization = finite_float(self.design_utilization, "design_utilization")
        if not 0.0 < utilization <= 1.0:
            raise ValueError("design_utilization must be in (0, 1]")
        object.__setattr__(self, "design_utilization", utilization)


@dataclass(frozen=True)
class RoomDesignRequirements:
    name: str
    classification: str
    intended_process: str
    length_m: float
    width_m: float
    height_m: float
    occupancy: int
    supply_return_strategy: str
    operating_mode: str
    profile_id: str | None = None
    minimum_ach: float | None = None
    minimum_supply_airflow_m3_h: float | None = None
    temperature_range_c: tuple[float, float] | None = None
    relative_humidity_range_percent: tuple[float, float] | None = None
    recovery_target_minutes: float | None = None
    filtration_requirement: str | None = None
    contamination_assumptions: tuple[str, ...] = ()
    thermal_design: ThermalDesign | None = None
    air_balance: AirBalanceDesign | None = None
    equipment: tuple[EquipmentSelectionInput, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "room name"))
        object.__setattr__(
            self,
            "classification",
            _nonempty(self.classification, "classification"),
        )
        object.__setattr__(
            self,
            "intended_process",
            _nonempty(self.intended_process, "intended_process"),
        )
        for field_name in ("length_m", "width_m", "height_m"):
            object.__setattr__(
                self,
                field_name,
                positive_float(getattr(self, field_name), field_name),
            )
        if (
            isinstance(self.occupancy, bool)
            or not isinstance(self.occupancy, int)
            or self.occupancy < 0
        ):
            raise ValueError("occupancy must be a non-negative integer")
        if self.supply_return_strategy not in _ALLOWED_STRATEGIES:
            raise ValueError(
                "supply_return_strategy must be one of: "
                + ", ".join(sorted(_ALLOWED_STRATEGIES))
            )
        object.__setattr__(
            self,
            "operating_mode",
            _nonempty(self.operating_mode, "operating_mode"),
        )
        object.__setattr__(
            self,
            "profile_id",
            _optional_nonempty(self.profile_id, "profile_id"),
        )
        if self.minimum_ach is not None:
            object.__setattr__(
                self,
                "minimum_ach",
                positive_float(self.minimum_ach, "minimum_ach"),
            )
        if self.minimum_supply_airflow_m3_h is not None:
            object.__setattr__(
                self,
                "minimum_supply_airflow_m3_h",
                positive_float(
                    self.minimum_supply_airflow_m3_h,
                    "minimum_supply_airflow_m3_h",
                ),
            )
        object.__setattr__(
            self,
            "temperature_range_c",
            _range(self.temperature_range_c, "temperature_range_c"),
        )
        object.__setattr__(
            self,
            "relative_humidity_range_percent",
            _range(
                self.relative_humidity_range_percent,
                "relative_humidity_range_percent",
                minimum_allowed=0.0,
                maximum_allowed=100.0,
            ),
        )
        if self.recovery_target_minutes is not None:
            object.__setattr__(
                self,
                "recovery_target_minutes",
                positive_float(
                    self.recovery_target_minutes,
                    "recovery_target_minutes",
                ),
            )
        object.__setattr__(
            self,
            "filtration_requirement",
            _optional_nonempty(
                self.filtration_requirement,
                "filtration_requirement",
            ),
        )
        assumptions: list[str] = []
        for index, item in enumerate(self.contamination_assumptions):
            assumptions.append(
                _nonempty(item, f"contamination_assumptions[{index}]")
            )
        object.__setattr__(
            self,
            "contamination_assumptions",
            tuple(assumptions),
        )


@dataclass(frozen=True)
class DesignRequirementsStudy:
    name: str
    profiles: tuple[RequirementProfile, ...]
    rooms: tuple[RoomDesignRequirements, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "study name"))
        if not self.rooms:
            raise ValueError("design requirements study requires at least one room")
        room_names = [room.name for room in self.rooms]
        if len(room_names) != len(set(room_names)):
            raise ValueError("room names must be unique")
        profile_ids = [profile.id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("reference profile ids must be unique")
        available = set(profile_ids)
        for room in self.rooms:
            if room.profile_id is not None and room.profile_id not in available:
                raise ValueError(
                    f"room {room.name!r} references unknown profile "
                    f"{room.profile_id!r}"
                )


def _target(
    key: str,
    *,
    value: Any,
    unit: str | None,
    source_kind: str,
    source: Any,
    equation: str | None,
    assumptions: list[str] | tuple[str, ...],
    status: str,
    warning: str | None = None,
    provenance: dict | None = None,
) -> dict:
    return {
        "key": key,
        "value": copy.deepcopy(value),
        "unit": unit,
        "source_kind": source_kind,
        "source": copy.deepcopy(source),
        "equation": equation,
        "assumptions": list(assumptions),
        "status": status,
        "warning": warning,
        "provenance": copy.deepcopy(provenance) if provenance is not None else {},
    }


def _resolve(
    room: RoomDesignRequirements,
    profile: RequirementProfile | None,
    field_name: str,
    *,
    unit: str | None,
) -> dict:
    explicit = getattr(room, field_name)
    if explicit is not None:
        return _target(
            field_name,
            value=explicit,
            unit=unit,
            source_kind="explicit_room_input",
            source={"room": room.name, "field": field_name},
            equation=None,
            assumptions=[],
            status="resolved",
            provenance={
                "precedence": "explicit room input overrides reference profile",
            },
        )
    if profile is not None:
        profile_value = getattr(profile, field_name)
        if profile_value is not None:
            return _target(
                field_name,
                value=profile_value,
                unit=unit,
                source_kind="reference_profile",
                source={
                    "profile_id": profile.id,
                    "profile_name": profile.name,
                    "reference": profile.source,
                },
                equation=None,
                assumptions=[],
                status="resolved",
                provenance={
                    "precedence": "profile used because room field is absent",
                },
            )
    return _target(
        field_name,
        value=None,
        unit=unit,
        source_kind="missing",
        source=None,
        equation=None,
        assumptions=[],
        status="unchecked",
        warning=(
            f"{field_name} is not explicitly defined and no selected "
            "reference profile supplies it"
        ),
        provenance={},
    )


def _equipment_basis(
    equipment: EquipmentSelectionInput,
    *,
    supply_m3_h: float | None,
    air_balance: dict | None,
) -> tuple[float | None, str]:
    if equipment.category in {"supply_terminal", "ffu", "filter"}:
        return supply_m3_h, "governing_supply_airflow_m3_h"
    if air_balance is None:
        return None, (
            "explicit air_balance is required for return/exhaust equipment sizing"
        )
    if equipment.category == "return_grille":
        return air_balance["return_airflow_m3_h"], "explicit_return_airflow_m3_h"
    if equipment.category == "exhaust_terminal":
        return air_balance["exhaust_airflow_m3_h"], "explicit_exhaust_airflow_m3_h"
    raise AssertionError("unsupported equipment category")


def analyze_design_requirements(study: DesignRequirementsStudy) -> dict:
    profiles = {profile.id: profile for profile in study.profiles}
    room_results = []
    incomplete_rooms: list[str] = []

    for room in study.rooms:
        profile = profiles.get(room.profile_id) if room.profile_id is not None else None
        volume_m3 = room.length_m * room.width_m * room.height_m

        targets = [
            _target(
                "classification",
                value=room.classification,
                unit=None,
                source_kind="explicit_room_input",
                source={"room": room.name, "field": "classification"},
                equation=None,
                assumptions=[],
                status="declared",
                warning=(
                    "Classification is recorded as project context only; CleanroomX "
                    "does not infer ACH, velocity, filtration, or acceptance criteria "
                    "from the classification label."
                ),
                provenance={},
            ),
            _target(
                "room_volume_m3",
                value=volume_m3,
                unit="m3",
                source_kind="derived",
                source={
                    "length_m": room.length_m,
                    "width_m": room.width_m,
                    "height_m": room.height_m,
                },
                equation="length_m * width_m * height_m",
                assumptions=[],
                status="resolved",
                provenance={"geometry_source": "explicit_room_input"},
            ),
            _resolve(room, profile, "minimum_ach", unit="1/h"),
            _resolve(
                room,
                profile,
                "minimum_supply_airflow_m3_h",
                unit="m3/h",
            ),
            _resolve(room, profile, "temperature_range_c", unit="degC"),
            _resolve(
                room,
                profile,
                "relative_humidity_range_percent",
                unit="percent",
            ),
            _resolve(
                room,
                profile,
                "recovery_target_minutes",
                unit="min",
            ),
            _resolve(
                room,
                profile,
                "filtration_requirement",
                unit=None,
            ),
        ]
        by_key = {item["key"]: item for item in targets}

        ach = by_key["minimum_ach"]["value"]
        ach_airflow = None
        if ach is not None:
            ach_airflow = volume_m3 * ach
            targets.append(
                _target(
                    "ach_based_supply_airflow_m3_h",
                    value=ach_airflow,
                    unit="m3/h",
                    source_kind="derived",
                    source={
                        "room_volume_m3": volume_m3,
                        "minimum_ach": ach,
                    },
                    equation="room_volume_m3 * minimum_ach",
                    assumptions=[],
                    status="resolved",
                    provenance={
                        "minimum_ach_source": by_key["minimum_ach"]["source_kind"],
                    },
                )
            )
        else:
            targets.append(
                _target(
                    "ach_based_supply_airflow_m3_h",
                    value=None,
                    unit="m3/h",
                    source_kind="missing_dependency",
                    source=None,
                    equation="room_volume_m3 * minimum_ach",
                    assumptions=[],
                    status="unchecked",
                    warning=(
                        "No minimum ACH is defined; no classification-based ACH "
                        "value is invented."
                    ),
                    provenance={},
                )
            )

        explicit_supply = by_key["minimum_supply_airflow_m3_h"]["value"]
        cleanroom_candidates = []
        if ach_airflow is not None:
            cleanroom_candidates.append(("minimum_ach", ach_airflow))
        if explicit_supply is not None:
            cleanroom_candidates.append(
                ("minimum_supply_airflow_m3_h", explicit_supply)
            )

        base_cleanroom_airflow = None
        base_basis = None
        if cleanroom_candidates:
            base_basis, base_cleanroom_airflow = max(
                cleanroom_candidates,
                key=lambda item: item[1],
            )

        thermal = None
        governing_supply = base_cleanroom_airflow
        governing_basis = base_basis
        thermal_warning = None
        if room.thermal_design is not None:
            if base_cleanroom_airflow is None:
                thermal_warning = (
                    "Thermal design is configured, but no explicit cleanroom airflow "
                    "constraint is available; thermal/governing airflow is not evaluated."
                )
            else:
                thermal = analyze_thermal_design(
                    room.thermal_design,
                    base_cleanroom_airflow,
                )
                governing_supply = thermal["governing_supply_airflow_m3_h"]
                governing_basis = thermal["governing_airflow_basis"]

        targets.append(
            _target(
                "governing_supply_airflow_m3_h",
                value=governing_supply,
                unit="m3/h",
                source_kind=(
                    "derived" if governing_supply is not None else "missing_dependency"
                ),
                source={
                    "cleanroom_candidates": cleanroom_candidates,
                    "thermal_design_evaluated": thermal is not None,
                },
                equation=(
                    "max(cleanroom airflow constraints, makeup airflow, "
                    "internal sensible-load airflow when thermal design is evaluated)"
                ),
                assumptions=[],
                status="resolved" if governing_supply is not None else "unchecked",
                warning=(
                    thermal_warning
                    if thermal_warning is not None
                    else (
                        None
                        if governing_supply is not None
                        else (
                            "No explicit minimum ACH or minimum supply airflow is "
                            "available, so a supply proposal cannot be calculated."
                        )
                    )
                ),
                provenance={
                    "governing_basis": governing_basis,
                    "thermal_backend": (
                        "cleanroomx.thermal.analyze_thermal_design"
                        if thermal is not None
                        else None
                    ),
                },
            )
        )

        balance = None
        if room.air_balance is not None and governing_supply is not None:
            balance = analyze_air_balance(
                governing_supply,
                room.air_balance,
            )

        equipment_results = []
        for equipment in room.equipment:
            basis_airflow, basis = _equipment_basis(
                equipment,
                supply_m3_h=governing_supply,
                air_balance=balance,
            )
            design_airflow = (
                equipment.rated_airflow_m3_h * equipment.design_utilization
            )
            if basis_airflow is None:
                equipment_results.append(
                    {
                        "category": equipment.category,
                        "name": equipment.name,
                        "status": "unchecked",
                        "required_count": None,
                        "basis": basis,
                        "rated_airflow_m3_h": equipment.rated_airflow_m3_h,
                        "design_utilization": equipment.design_utilization,
                        "design_airflow_per_unit_m3_h": design_airflow,
                        "equation": (
                            "ceil(basis_airflow / "
                            "(rated_airflow_m3_h * design_utilization))"
                        ),
                        "warning": basis,
                    }
                )
                continue
            count = math.ceil(basis_airflow / design_airflow) if basis_airflow > 0 else 0
            equipment_results.append(
                {
                    "category": equipment.category,
                    "name": equipment.name,
                    "status": "proposal",
                    "required_count": count,
                    "basis": basis,
                    "basis_airflow_m3_h": basis_airflow,
                    "rated_airflow_m3_h": equipment.rated_airflow_m3_h,
                    "design_utilization": equipment.design_utilization,
                    "design_airflow_per_unit_m3_h": design_airflow,
                    "equation": (
                        "ceil(basis_airflow / "
                        "(rated_airflow_m3_h * design_utilization))"
                    ),
                    "warning": (
                        "Preliminary quantity only; layout, throw, coverage, pressure "
                        "drop, acoustics, manufacturer limits, and redundancy are not "
                        "selected automatically."
                    ),
                }
            )

        room_complete = governing_supply is not None
        if not room_complete:
            incomplete_rooms.append(room.name)

        room_results.append(
            {
                "name": room.name,
                "classification": room.classification,
                "intended_process": room.intended_process,
                "occupancy": room.occupancy,
                "operating_mode": room.operating_mode,
                "supply_return_strategy": room.supply_return_strategy,
                "profile_id": room.profile_id,
                "status": "complete" if room_complete else "incomplete",
                "requirements": targets,
                "contamination_assumptions": list(room.contamination_assumptions),
                "air_system_proposal": {
                    "base_cleanroom_airflow_m3_h": base_cleanroom_airflow,
                    "base_cleanroom_airflow_basis": base_basis,
                    "governing_supply_airflow_m3_h": governing_supply,
                    "governing_airflow_basis": governing_basis,
                    "thermal": thermal,
                    "air_balance": balance,
                    "equipment": equipment_results,
                },
            }
        )

    return {
        "study": study.name,
        "status": "complete" if not incomplete_rooms else "incomplete",
        "complete": not incomplete_rooms,
        "rooms": room_results,
        "incomplete_rooms": incomplete_rooms,
        "reference_profiles": [
            {
                "id": profile.id,
                "name": profile.name,
                "source": copy.deepcopy(profile.source),
            }
            for profile in study.profiles
        ],
        "scope_note": (
            "Design requirements and preliminary air-system sizing only. "
            "Classification labels do not automatically create ACH, velocity, "
            "filtration, recovery, temperature, humidity, or acceptance criteria. "
            "Reference-profile values are project inputs with explicit source metadata. "
            "Thermal airflow reuses the existing CleanroomX preliminary thermal backend. "
            "Equipment counts are proposals only when explicit unit rating and design "
            "utilization are supplied."
        ),
    }
