from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import product

from .hvac_models import AirState, ThermalDesign, ThermalLoads
from .thermal import analyze_thermal_design
from .uncertainty_models import UncertainValue


def _require_unit(item: UncertainValue, expected: str, field_name: str) -> None:
    if item.unit != expected:
        raise ValueError(
            f"{field_name} unit must be {expected!r}, got {item.unit!r}"
        )


def _validate_air_state_interval(
    *,
    dry_bulb: UncertainValue,
    relative_humidity: UncertainValue,
    pressure: UncertainValue,
    prefix: str,
) -> None:
    _require_unit(dry_bulb, "degC", f"{prefix}_dry_bulb_c")
    _require_unit(relative_humidity, "%RH", f"{prefix}_relative_humidity_percent")
    _require_unit(pressure, "kPa", f"{prefix}_pressure_kpa")

    if dry_bulb.lower < -45.0 or dry_bulb.upper > 60.0:
        raise ValueError(
            f"{prefix} dry-bulb uncertainty interval must stay within -45 to 60 C"
        )
    if relative_humidity.lower <= 0.0 or relative_humidity.upper > 100.0:
        raise ValueError(
            f"{prefix} relative-humidity uncertainty interval must stay within "
            "> 0 and <= 100 %RH"
        )
    if pressure.lower <= 0.0:
        raise ValueError(f"{prefix} pressure lower uncertainty bound must remain > 0")


@dataclass(frozen=True)
class ThermalUncertaintyCase:
    name: str
    cleanroom_airflow_m3_h: UncertainValue
    room_dry_bulb_c: UncertainValue
    room_relative_humidity_percent: UncertainValue
    room_pressure_kpa: UncertainValue
    makeup_air_m3_h: UncertainValue = field(
        default_factory=lambda: UncertainValue(0.0, "m3/h")
    )
    outdoor_dry_bulb_c: UncertainValue | None = None
    outdoor_relative_humidity_percent: UncertainValue | None = None
    outdoor_pressure_kpa: UncertainValue | None = None
    supply_air_temp_c: UncertainValue | None = None
    loads: ThermalLoads = field(default_factory=ThermalLoads)
    capacity_margin_percent: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name cannot be empty")

        _require_unit(
            self.cleanroom_airflow_m3_h,
            "m3/h",
            "cleanroom_airflow_m3_h",
        )
        if self.cleanroom_airflow_m3_h.lower <= 0.0:
            raise ValueError(
                "cleanroom_airflow_m3_h lower uncertainty bound must remain > 0"
            )

        _validate_air_state_interval(
            dry_bulb=self.room_dry_bulb_c,
            relative_humidity=self.room_relative_humidity_percent,
            pressure=self.room_pressure_kpa,
            prefix="room",
        )

        _require_unit(self.makeup_air_m3_h, "m3/h", "makeup_air_m3_h")
        if self.makeup_air_m3_h.lower < 0.0:
            raise ValueError(
                "makeup_air_m3_h lower uncertainty bound must remain >= 0"
            )

        outdoor_items = (
            self.outdoor_dry_bulb_c,
            self.outdoor_relative_humidity_percent,
            self.outdoor_pressure_kpa,
        )
        supplied_outdoor = [item is not None for item in outdoor_items]
        if any(supplied_outdoor) and not all(supplied_outdoor):
            raise ValueError(
                "outdoor dry-bulb, relative humidity, and pressure must be "
                "provided together"
            )
        if self.makeup_air_m3_h.upper > 0.0 and not all(supplied_outdoor):
            raise ValueError(
                "outdoor air state is required when makeup airflow can be > 0"
            )
        if all(supplied_outdoor):
            _validate_air_state_interval(
                dry_bulb=self.outdoor_dry_bulb_c,
                relative_humidity=self.outdoor_relative_humidity_percent,
                pressure=self.outdoor_pressure_kpa,
                prefix="outdoor",
            )

        if self.supply_air_temp_c is not None:
            _require_unit(
                self.supply_air_temp_c,
                "degC",
                "supply_air_temp_c",
            )

        margin = float(self.capacity_margin_percent)
        if margin < 0.0:
            raise ValueError("capacity_margin_percent must be >= 0")
        object.__setattr__(self, "capacity_margin_percent", margin)


def _endpoints(item: UncertainValue | None) -> tuple[float | None, ...]:
    if item is None:
        return (None,)
    if item.uncertainty_abs == 0.0:
        return (item.value,)
    return (item.lower, item.upper)


def _input_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": asdict(item.provenance) if item.provenance is not None else None,
    }


def _build_design(
    case: ThermalUncertaintyCase,
    *,
    room_t: float,
    room_rh: float,
    room_pressure: float,
    outdoor_t: float | None,
    outdoor_rh: float | None,
    outdoor_pressure: float | None,
    makeup_airflow: float,
    supply_t: float | None,
) -> ThermalDesign:
    outdoor = None
    if outdoor_t is not None:
        outdoor = AirState(outdoor_t, outdoor_rh, outdoor_pressure)

    return ThermalDesign(
        room_air=AirState(room_t, room_rh, room_pressure),
        loads=case.loads,
        outdoor_air=outdoor,
        makeup_air_m3_h=makeup_airflow,
        supply_air_temp_c=supply_t,
        capacity_margin_percent=case.capacity_margin_percent,
    )


def _interval(nominal: float, values: list[float], digits: int) -> dict:
    return {
        "nominal": round(nominal, digits),
        "lower": round(min(values), digits),
        "upper": round(max(values), digits),
    }


def analyze_thermal_uncertainty(case: ThermalUncertaintyCase) -> dict:
    """Evaluate endpoint combinations for bounded thermal/HVAC input uncertainty."""
    variables = {
        "cleanroom_airflow_m3_h": case.cleanroom_airflow_m3_h,
        "room_dry_bulb_c": case.room_dry_bulb_c,
        "room_relative_humidity_percent": case.room_relative_humidity_percent,
        "room_pressure_kpa": case.room_pressure_kpa,
        "makeup_air_m3_h": case.makeup_air_m3_h,
    }
    if case.outdoor_dry_bulb_c is not None:
        variables.update(
            {
                "outdoor_dry_bulb_c": case.outdoor_dry_bulb_c,
                "outdoor_relative_humidity_percent": (
                    case.outdoor_relative_humidity_percent
                ),
                "outdoor_pressure_kpa": case.outdoor_pressure_kpa,
            }
        )
    if case.supply_air_temp_c is not None:
        variables["supply_air_temp_c"] = case.supply_air_temp_c

    uncertain_dimensions = [
        name for name, item in variables.items() if item.uncertainty_abs > 0.0
    ]

    room_t_values = _endpoints(case.room_dry_bulb_c)
    room_rh_values = _endpoints(case.room_relative_humidity_percent)
    room_pressure_values = _endpoints(case.room_pressure_kpa)
    outdoor_t_values = _endpoints(case.outdoor_dry_bulb_c)
    outdoor_rh_values = _endpoints(case.outdoor_relative_humidity_percent)
    outdoor_pressure_values = _endpoints(case.outdoor_pressure_kpa)
    makeup_values = _endpoints(case.makeup_air_m3_h)
    supply_t_values = _endpoints(case.supply_air_temp_c)
    cleanroom_values = _endpoints(case.cleanroom_airflow_m3_h)

    scenario_results: list[dict] = []
    for (
        cleanroom_airflow,
        room_t,
        room_rh,
        room_pressure,
        outdoor_t,
        outdoor_rh,
        outdoor_pressure,
        makeup_airflow,
        supply_t,
    ) in product(
        cleanroom_values,
        room_t_values,
        room_rh_values,
        room_pressure_values,
        outdoor_t_values,
        outdoor_rh_values,
        outdoor_pressure_values,
        makeup_values,
        supply_t_values,
    ):
        design = _build_design(
            case,
            room_t=room_t,
            room_rh=room_rh,
            room_pressure=room_pressure,
            outdoor_t=outdoor_t,
            outdoor_rh=outdoor_rh,
            outdoor_pressure=outdoor_pressure,
            makeup_airflow=makeup_airflow,
            supply_t=supply_t,
        )
        scenario_results.append(analyze_thermal_design(design, cleanroom_airflow))

    nominal_design = _build_design(
        case,
        room_t=case.room_dry_bulb_c.value,
        room_rh=case.room_relative_humidity_percent.value,
        room_pressure=case.room_pressure_kpa.value,
        outdoor_t=(
            case.outdoor_dry_bulb_c.value
            if case.outdoor_dry_bulb_c is not None
            else None
        ),
        outdoor_rh=(
            case.outdoor_relative_humidity_percent.value
            if case.outdoor_relative_humidity_percent is not None
            else None
        ),
        outdoor_pressure=(
            case.outdoor_pressure_kpa.value
            if case.outdoor_pressure_kpa is not None
            else None
        ),
        makeup_airflow=case.makeup_air_m3_h.value,
        supply_t=(
            case.supply_air_temp_c.value
            if case.supply_air_temp_c is not None
            else None
        ),
    )
    nominal = analyze_thermal_design(
        nominal_design,
        case.cleanroom_airflow_m3_h.value,
    )

    cooling_values = [
        item["preliminary_cooling_capacity_kw"] for item in scenario_results
    ]
    heating_values = [
        item["preliminary_heating_capacity_kw"] for item in scenario_results
    ]
    governing_values = [
        item["governing_supply_airflow_m3_h"] for item in scenario_results
    ]
    makeup_total_values = [
        item["loads"]["makeup_air_total_kw"] for item in scenario_results
    ]
    net_load_values = [
        item["loads"]["net_room_plus_makeup_kw"] for item in scenario_results
    ]

    thermal_airflow_values = [
        item["thermal_airflow_for_internal_sensible_m3_h"]
        for item in scenario_results
        if item["thermal_airflow_for_internal_sensible_m3_h"] is not None
    ]
    all_thermal_airflows_defined = (
        len(thermal_airflow_values) == len(scenario_results)
    )
    if not thermal_airflow_values:
        thermal_airflow = {
            "nominal": nominal["thermal_airflow_for_internal_sensible_m3_h"],
            "lower": None,
            "upper": None,
            "status": "not_defined",
        }
    else:
        thermal_airflow = {
            "nominal": nominal["thermal_airflow_for_internal_sensible_m3_h"],
            "lower": round(min(thermal_airflow_values), 3),
            "upper": round(max(thermal_airflow_values), 3),
            "status": (
                "defined_all_scenarios"
                if all_thermal_airflows_defined
                else "partially_defined"
            ),
        }

    input_records = [
        _input_record(name, item) for name, item in variables.items()
    ]
    missing_provenance = [
        item["name"] for item in input_records if item["provenance"] is None
    ]

    return {
        "case": case.name,
        "method": "endpoint_scenario_envelope",
        "scenario_count": len(scenario_results),
        "uncertain_dimensions": uncertain_dimensions,
        "preliminary_cooling_capacity_kw": _interval(
            nominal["preliminary_cooling_capacity_kw"],
            cooling_values,
            4,
        ),
        "preliminary_heating_capacity_kw": _interval(
            nominal["preliminary_heating_capacity_kw"],
            heating_values,
            4,
        ),
        "governing_supply_airflow_m3_h": _interval(
            nominal["governing_supply_airflow_m3_h"],
            governing_values,
            3,
        ),
        "makeup_air_total_kw": _interval(
            nominal["loads"]["makeup_air_total_kw"],
            makeup_total_values,
            4,
        ),
        "net_room_plus_makeup_kw": _interval(
            nominal["loads"]["net_room_plus_makeup_kw"],
            net_load_values,
            4,
        ),
        "thermal_airflow_for_internal_sensible_m3_h": thermal_airflow,
        "governing_airflow_bases": sorted(
            {item["governing_airflow_basis"] for item in scenario_results}
        ),
        "traceability": {
            "input_count": len(input_records),
            "inputs_with_provenance": len(input_records) - len(missing_provenance),
            "complete": not missing_provenance,
            "missing_provenance": missing_provenance,
            "inputs": input_records,
        },
        "engineering_note": (
            "This result is an endpoint-scenario envelope over the supplied absolute "
            "input bounds. It reuses the CleanroomX preliminary thermal model at every "
            "endpoint combination. Because the psychrometric model is nonlinear, this "
            "endpoint envelope is a bounded sensitivity screen and is not claimed to be "
            "a mathematically guaranteed global interval enclosure or a statistical "
            "measurement-uncertainty budget. Internal heat-load inputs and the capacity "
            "margin remain deterministic in this workflow."
        ),
    }
