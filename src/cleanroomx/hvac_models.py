from __future__ import annotations

from dataclasses import dataclass, field

from .branched_duct import BranchedDuctNetwork
from .duct import DuctNetwork


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return value


def _efficiency(value: float, field_name: str) -> float:
    value = float(value)
    if not 0.0 < value <= 1.0:
        raise ValueError(f"{field_name} must be > 0 and <= 1")
    return value


@dataclass(frozen=True)
class AirState:
    dry_bulb_c: float
    relative_humidity_percent: float
    pressure_kpa: float = 101.325

    def __post_init__(self) -> None:
        temperature = float(self.dry_bulb_c)
        rh = float(self.relative_humidity_percent)
        pressure = _positive(self.pressure_kpa, "pressure_kpa")
        if not -45.0 <= temperature <= 60.0:
            raise ValueError(
                "dry_bulb_c must be between -45 and 60 C for the implemented "
                "saturation-vapor-pressure approximation"
            )
        if not 0.0 < rh <= 100.0:
            raise ValueError("relative_humidity_percent must be > 0 and <= 100")
        object.__setattr__(self, "dry_bulb_c", temperature)
        object.__setattr__(self, "relative_humidity_percent", rh)
        object.__setattr__(self, "pressure_kpa", pressure)


@dataclass(frozen=True)
class ThermalLoads:
    occupants: int = 0
    sensible_w_per_person: float = 0.0
    latent_w_per_person: float = 0.0
    lighting_w: float = 0.0
    equipment_w: float = 0.0
    envelope_sensible_w: float = 0.0
    other_sensible_w: float = 0.0
    process_latent_w: float = 0.0
    other_latent_w: float = 0.0

    def __post_init__(self) -> None:
        occupants = int(self.occupants)
        if occupants < 0 or occupants != self.occupants:
            raise ValueError("occupants must be a non-negative integer")
        object.__setattr__(self, "occupants", occupants)
        for field_name in (
            "sensible_w_per_person",
            "latent_w_per_person",
            "lighting_w",
            "equipment_w",
            "envelope_sensible_w",
            "other_sensible_w",
            "process_latent_w",
            "other_latent_w",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative(getattr(self, field_name), field_name),
            )

    @property
    def sensible_w(self) -> float:
        return (
            self.occupants * self.sensible_w_per_person
            + self.lighting_w
            + self.equipment_w
            + self.envelope_sensible_w
            + self.other_sensible_w
        )

    @property
    def latent_w(self) -> float:
        return (
            self.occupants * self.latent_w_per_person
            + self.process_latent_w
            + self.other_latent_w
        )

    @property
    def total_w(self) -> float:
        return self.sensible_w + self.latent_w


@dataclass(frozen=True)
class ThermalDesign:
    room_air: AirState
    loads: ThermalLoads = field(default_factory=ThermalLoads)
    outdoor_air: AirState | None = None
    makeup_air_m3_h: float = 0.0
    supply_air_temp_c: float | None = None
    capacity_margin_percent: float = 0.0

    def __post_init__(self) -> None:
        makeup = _nonnegative(self.makeup_air_m3_h, "makeup_air_m3_h")
        margin = _nonnegative(self.capacity_margin_percent, "capacity_margin_percent")
        if makeup > 0 and self.outdoor_air is None:
            raise ValueError("outdoor_air is required when makeup_air_m3_h > 0")
        object.__setattr__(self, "makeup_air_m3_h", makeup)
        object.__setattr__(self, "capacity_margin_percent", margin)
        if self.supply_air_temp_c is not None:
            object.__setattr__(
                self, "supply_air_temp_c", float(self.supply_air_temp_c)
            )


@dataclass(frozen=True)
class AirBalanceDesign:
    return_airflow_m3_h: float = 0.0
    exhaust_airflow_m3_h: float = 0.0
    transfer_in_airflow_m3_h: float = 0.0
    transfer_out_airflow_m3_h: float = 0.0
    minimum_surplus_m3_h: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "return_airflow_m3_h",
            "exhaust_airflow_m3_h",
            "transfer_in_airflow_m3_h",
            "transfer_out_airflow_m3_h",
            "minimum_surplus_m3_h",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative(getattr(self, field_name), field_name),
            )


@dataclass(frozen=True)
class FilterUnit:
    name: str
    rated_airflow_m3_h: float
    design_utilization: float = 0.90
    pressure_drop_pa: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("filter-unit name cannot be empty")
        object.__setattr__(
            self,
            "rated_airflow_m3_h",
            _positive(self.rated_airflow_m3_h, "rated_airflow_m3_h"),
        )
        object.__setattr__(
            self,
            "design_utilization",
            _efficiency(self.design_utilization, "design_utilization"),
        )
        object.__setattr__(
            self,
            "pressure_drop_pa",
            _nonnegative(self.pressure_drop_pa, "pressure_drop_pa"),
        )

    @property
    def design_airflow_m3_h(self) -> float:
        return self.rated_airflow_m3_h * self.design_utilization


@dataclass(frozen=True)
class FanSystem:
    name: str
    duct_pressure_drop_pa: float = 0.0
    coil_pressure_drop_pa: float = 0.0
    other_pressure_drop_pa: float = 0.0
    fan_efficiency: float = 0.65
    motor_efficiency: float = 0.90

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan-system name cannot be empty")
        for field_name in (
            "duct_pressure_drop_pa",
            "coil_pressure_drop_pa",
            "other_pressure_drop_pa",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "fan_efficiency",
            _efficiency(self.fan_efficiency, "fan_efficiency"),
        )
        object.__setattr__(
            self,
            "motor_efficiency",
            _efficiency(self.motor_efficiency, "motor_efficiency"),
        )


@dataclass(frozen=True)
class HVACRoom:
    name: str
    cleanroom_airflow_m3_h: float
    thermal_design: ThermalDesign
    air_balance: AirBalanceDesign = field(default_factory=AirBalanceDesign)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("room name cannot be empty")
        object.__setattr__(
            self,
            "cleanroom_airflow_m3_h",
            _positive(self.cleanroom_airflow_m3_h, "cleanroom_airflow_m3_h"),
        )


@dataclass(frozen=True)
class HVACProject:
    name: str
    rooms: tuple[HVACRoom, ...]
    filter_unit: FilterUnit | None = None
    fan_system: FanSystem | None = None
    duct_network: DuctNetwork | None = None
    branched_duct_network: BranchedDuctNetwork | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name cannot be empty")
        if not self.rooms:
            raise ValueError("project must contain at least one HVAC room")
        names = [room.name for room in self.rooms]
        if len(names) != len(set(names)):
            raise ValueError("HVAC room names must be unique")
        if self.duct_network is not None and self.branched_duct_network is not None:
            raise ValueError(
                "provide either duct_network or branched_duct_network, not both"
            )
