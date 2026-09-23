from __future__ import annotations

import math

from .hvac_models import DuctNetwork, DuctPath, DuctSection


def _geometry(section: DuctSection) -> tuple[str, float, float]:
    if section.diameter_m is not None:
        diameter = section.diameter_m
        area = math.pi * diameter**2 / 4.0
        return "round", area, diameter

    width = section.width_m
    height = section.height_m
    assert width is not None and height is not None
    area = width * height
    hydraulic_diameter = 2.0 * width * height / (width + height)
    return "rectangular", area, hydraulic_diameter


def darcy_friction_factor(
    reynolds_number: float,
    relative_roughness: float,
) -> float:
    """Return Darcy friction factor using laminar 64/Re or iterative Colebrook."""
    re = float(reynolds_number)
    rr = float(relative_roughness)
    if re <= 0:
        raise ValueError("reynolds_number must be > 0")
    if rr < 0:
        raise ValueError("relative_roughness must be >= 0")
    if re < 2300.0:
        return 64.0 / re

    friction = 0.02
    for _ in range(100):
        inverse_sqrt = -2.0 * math.log10(
            rr / 3.7 + 2.51 / (re * math.sqrt(friction))
        )
        updated = 1.0 / inverse_sqrt**2
        if abs(updated - friction) < 1e-12:
            return updated
        friction = updated
    return friction


def analyze_duct_section(
    section: DuctSection,
    *,
    air_density_kg_m3: float,
    dynamic_viscosity_pa_s: float,
) -> dict:
    density = float(air_density_kg_m3)
    viscosity = float(dynamic_viscosity_pa_s)
    if density <= 0:
        raise ValueError("air_density_kg_m3 must be > 0")
    if viscosity <= 0:
        raise ValueError("dynamic_viscosity_pa_s must be > 0")

    shape, area_m2, hydraulic_diameter_m = _geometry(section)
    airflow_m3_s = section.airflow_m3_h / 3600.0
    velocity_m_s = airflow_m3_s / area_m2
    reynolds_number = (
        density * velocity_m_s * hydraulic_diameter_m / viscosity
    )
    relative_roughness = section.roughness_m / hydraulic_diameter_m
    friction_factor = darcy_friction_factor(
        reynolds_number, relative_roughness
    )
    velocity_pressure_pa = 0.5 * density * velocity_m_s**2
    friction_pressure_loss_pa = (
        friction_factor
        * section.length_m
        / hydraulic_diameter_m
        * velocity_pressure_pa
    )
    local_pressure_loss_pa = (
        section.local_loss_coefficient * velocity_pressure_pa
    )
    total_pressure_loss_pa = friction_pressure_loss_pa + local_pressure_loss_pa

    return {
        "name": section.name,
        "shape": shape,
        "length_m": round(section.length_m, 6),
        "airflow_m3_h": round(section.airflow_m3_h, 3),
        "area_m2": round(area_m2, 6),
        "hydraulic_diameter_m": round(hydraulic_diameter_m, 6),
        "roughness_m": round(section.roughness_m, 9),
        "relative_roughness": round(relative_roughness, 8),
        "velocity_m_s": round(velocity_m_s, 5),
        "reynolds_number": round(reynolds_number, 1),
        "darcy_friction_factor": round(friction_factor, 7),
        "velocity_pressure_pa": round(velocity_pressure_pa, 4),
        "friction_pressure_loss_pa": round(friction_pressure_loss_pa, 4),
        "local_loss_coefficient": round(section.local_loss_coefficient, 6),
        "local_pressure_loss_pa": round(local_pressure_loss_pa, 4),
        "total_pressure_loss_pa": round(total_pressure_loss_pa, 4),
        "friction_rate_pa_per_m": round(
            friction_pressure_loss_pa / section.length_m, 5
        ),
        "flow_regime": (
            "laminar"
            if reynolds_number < 2300.0
            else "transitional"
            if reynolds_number < 4000.0
            else "turbulent"
        ),
        "friction_factor_method": (
            "64/Re" if reynolds_number < 2300.0 else "iterative Colebrook"
        ),
    }


def analyze_duct_path(
    path: DuctPath,
    *,
    air_density_kg_m3: float,
    dynamic_viscosity_pa_s: float,
) -> dict:
    sections = [
        analyze_duct_section(
            section,
            air_density_kg_m3=air_density_kg_m3,
            dynamic_viscosity_pa_s=dynamic_viscosity_pa_s,
        )
        for section in path.sections
    ]
    total = sum(item["total_pressure_loss_pa"] for item in sections)
    return {
        "name": path.name,
        "sections": sections,
        "total_pressure_loss_pa": round(total, 4),
    }


def analyze_duct_network(network: DuctNetwork) -> dict:
    paths = [
        analyze_duct_path(
            path,
            air_density_kg_m3=network.air_density_kg_m3,
            dynamic_viscosity_pa_s=network.dynamic_viscosity_pa_s,
        )
        for path in network.paths
    ]
    critical = max(paths, key=lambda item: item["total_pressure_loss_pa"])
    return {
        "air_density_kg_m3": network.air_density_kg_m3,
        "dynamic_viscosity_pa_s": network.dynamic_viscosity_pa_s,
        "paths": paths,
        "critical_path": critical["name"],
        "critical_path_pressure_loss_pa": critical["total_pressure_loss_pa"],
        "engineering_note": (
            "Steady-state pressure-loss screening using Darcy-Weisbach friction "
            "and explicit local loss coefficients. Air properties, roughness, geometry, "
            "section airflow, and fitting-loss coefficients are project inputs. "
            "Leakage, thermal-gravity effects, fan system effect, acoustics, balancing, "
            "and automatic network flow distribution are not solved."
        ),
    }
