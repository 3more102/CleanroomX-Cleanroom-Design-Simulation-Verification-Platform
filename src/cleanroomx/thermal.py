from __future__ import annotations

from .hvac_models import ThermalDesign
from .psychrometrics import (
    air_state_result,
    dry_air_mass_flow_kg_s,
    moist_air_cp_kj_kg_da_k,
    moist_air_enthalpy_kj_kg_da,
    moist_air_specific_volume_m3_kg_da,
)


def analyze_thermal_design(
    design: ThermalDesign,
    cleanroom_airflow_m3_h: float,
) -> dict:
    """Return a transparent preliminary thermal/HVAC analysis for one room."""
    if cleanroom_airflow_m3_h <= 0:
        raise ValueError("cleanroom_airflow_m3_h must be > 0")

    loads = design.loads
    internal_sensible_kw = loads.sensible_w / 1000.0
    internal_latent_kw = loads.latent_w / 1000.0
    internal_total_kw = loads.total_w / 1000.0

    makeup_total_kw = 0.0
    makeup_sensible_kw = 0.0
    makeup_latent_kw = 0.0
    outdoor_result = None

    if design.makeup_air_m3_h > 0 and design.outdoor_air is not None:
        room_h = moist_air_enthalpy_kj_kg_da(design.room_air)
        outdoor_h = moist_air_enthalpy_kj_kg_da(design.outdoor_air)
        m_da = dry_air_mass_flow_kg_s(
            design.makeup_air_m3_h, design.outdoor_air
        )
        makeup_total_kw = m_da * (outdoor_h - room_h)

        average_cp = (
            moist_air_cp_kj_kg_da_k(design.room_air)
            + moist_air_cp_kj_kg_da_k(design.outdoor_air)
        ) / 2.0
        makeup_sensible_kw = (
            m_da
            * average_cp
            * (design.outdoor_air.dry_bulb_c - design.room_air.dry_bulb_c)
        )
        makeup_latent_kw = makeup_total_kw - makeup_sensible_kw
        outdoor_result = air_state_result(design.outdoor_air)

    net_load_kw = internal_total_kw + makeup_total_kw
    sizing_multiplier = 1.0 + design.capacity_margin_percent / 100.0
    cooling_kw = max(net_load_kw, 0.0) * sizing_multiplier
    heating_kw = max(-net_load_kw, 0.0) * sizing_multiplier

    thermal_airflow_m3_h = None
    thermal_airflow_note = None
    if design.supply_air_temp_c is not None:
        delta_t = design.room_air.dry_bulb_c - design.supply_air_temp_c
        if internal_sensible_kw == 0:
            thermal_airflow_m3_h = 0.0
        elif delta_t <= 0:
            thermal_airflow_note = (
                "Supply-air temperature is not below the room setpoint, so a cooling "
                "airflow for positive internal sensible load cannot be calculated."
            )
        else:
            cp = moist_air_cp_kj_kg_da_k(design.room_air)
            required_m_da_kg_s = internal_sensible_kw / (cp * delta_t)
            thermal_airflow_m3_h = (
                required_m_da_kg_s
                * moist_air_specific_volume_m3_kg_da(design.room_air)
                * 3600.0
            )

    candidates = [
        ("cleanroom_airflow", cleanroom_airflow_m3_h),
        ("makeup_air", design.makeup_air_m3_h),
    ]
    if thermal_airflow_m3_h is not None:
        candidates.append(("internal_sensible_load", thermal_airflow_m3_h))
    governing_basis, governing_airflow = max(candidates, key=lambda item: item[1])

    return {
        "room_air": air_state_result(design.room_air),
        "outdoor_air": outdoor_result,
        "loads": {
            "internal_sensible_kw": round(internal_sensible_kw, 4),
            "internal_latent_kw": round(internal_latent_kw, 4),
            "internal_total_kw": round(internal_total_kw, 4),
            "makeup_air_sensible_kw": round(makeup_sensible_kw, 4),
            "makeup_air_latent_kw": round(makeup_latent_kw, 4),
            "makeup_air_total_kw": round(makeup_total_kw, 4),
            "net_room_plus_makeup_kw": round(net_load_kw, 4),
        },
        "makeup_air_m3_h": design.makeup_air_m3_h,
        "supply_air_temp_c": design.supply_air_temp_c,
        "thermal_airflow_for_internal_sensible_m3_h": (
            round(thermal_airflow_m3_h, 3)
            if thermal_airflow_m3_h is not None
            else None
        ),
        "thermal_airflow_note": thermal_airflow_note,
        "governing_supply_airflow_m3_h": round(governing_airflow, 3),
        "governing_airflow_basis": governing_basis,
        "capacity_margin_percent": design.capacity_margin_percent,
        "preliminary_cooling_capacity_kw": round(cooling_kw, 4),
        "preliminary_heating_capacity_kw": round(heating_kw, 4),
        "scope_note": (
            "Preliminary load estimate only. Envelope, people, lighting, equipment "
            "and latent gains are explicit user inputs; fan heat, duct heat, diversity, "
            "solar detail, coil bypass/ADP, humidification and equipment selection are "
            "not modeled."
        ),
    }
