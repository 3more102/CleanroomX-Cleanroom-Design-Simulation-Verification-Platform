from __future__ import annotations

from dataclasses import dataclass, field


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
    return_air_m3_h: float = 0.0
    exhaust_air_m3_h: float = 0.0
    transfer_in_m3_h: float = 0.0
    transfer_out_m3_h: float = 0.0
    leakage_in_m3_h: float = 0.0
    leakage_out_m3_h: float = 0.0
    balance_tolerance_m3_h: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "return_air_m3_h",
            "exhaust_air_m3_h",
            "transfer_in_m3_h",
            "transfer_out_m3_h",
            "leakage_in_m3_h",
            "leakage_out_m3_h",
            "balance_tolerance_m3_h",
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

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("filter-unit name cannot be empty")
        object.__setattr__(
            self,
            "rated_airflow_m3_h",
            _positive(self.rated_airflow_m3_h, "rated_airflow_m3_h"),
        )
        utilization = float(self.design_utilization)
        if not 0.0 < utilization <= 1.0:
            raise ValueError("design_utilization must be > 0 and <= 1")
        object.__setattr__(self, "design_utilization", utilization)

    @property
    def design_airflow_m3_h(self) -> float:
        return self.rated_airflow_m3_h * self.design_utilization


@dataclass(frozen=True)
class HVACRoom:
    name: str
    cleanroom_airflow_m3_h: float
    thermal_design: ThermalDesign
    air_balance: AirBalanceDesign | None = None

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

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name cannot be empty")
        if not self.rooms:
            raise ValueError("project must contain at least one HVAC room")
        names = [room.name for room in self.rooms]
        if len(names) != len(set(names)):
            raise ValueError("HVAC room names must be unique")
