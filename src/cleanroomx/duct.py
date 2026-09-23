from __future__ import annotations

from .duct_models import DuctNetwork, DuctPath, DuctSection


def analyze_duct_section(section: DuctSection) -> dict:
    """Calculate preliminary Darcy-Weisbach and minor pressure losses."""
    airflow_m3_s = section.airflow_m3_h / 3600.0
    velocity_m_s = airflow_m3_s / section.cross_section_area_m2
    velocity_pressure_pa = 0.5 * section.air_density_kg_m3 * velocity_m_s**2

    friction_pressure_drop_pa = (
        section.darcy_friction_factor
        * section.length_m
        / section.hydraulic_diameter_m
        * velocity_pressure_pa
    )
    minor_pressure_drop_pa = (
        section.minor_loss_coefficient * velocity_pressure_pa
    )
    total_pressure_drop_pa = (
        friction_pressure_drop_pa
        + minor_pressure_drop_pa
        + section.additional_pressure_drop_pa
    )

    return {
        "name": section.name,
        "airflow_m3_h": round(section.airflow_m3_h, 3),
        "airflow_m3_s": round(airflow_m3_s, 6),
        "velocity_m_s": round(velocity_m_s, 6),
        "velocity_pressure_pa": round(velocity_pressure_pa, 3),
        "darcy_friction_factor": section.darcy_friction_factor,
        "friction_pressure_drop_pa": round(friction_pressure_drop_pa, 3),
        "minor_loss_coefficient": section.minor_loss_coefficient,
        "minor_pressure_drop_pa": round(minor_pressure_drop_pa, 3),
        "additional_pressure_drop_pa": round(
            section.additional_pressure_drop_pa, 3
        ),
        "total_pressure_drop_pa": round(total_pressure_drop_pa, 3),
    }


def analyze_duct_path(path: DuctPath) -> dict:
    sections = [analyze_duct_section(section) for section in path.sections]
    total_pressure_drop_pa = sum(
        section["total_pressure_drop_pa"] for section in sections
    )
    max_velocity_m_s = max(section["velocity_m_s"] for section in sections)
    return {
        "name": path.name,
        "section_count": len(sections),
        "total_pressure_drop_pa": round(total_pressure_drop_pa, 3),
        "max_velocity_m_s": round(max_velocity_m_s, 6),
        "sections": sections,
    }


def analyze_duct_network(network: DuctNetwork) -> dict:
    paths = [analyze_duct_path(path) for path in network.paths]
    critical = max(paths, key=lambda path: path["total_pressure_drop_pa"])
    return {
        "name": network.name,
        "path_count": len(paths),
        "critical_path": critical["name"],
        "critical_path_pressure_drop_pa": critical["total_pressure_drop_pa"],
        "paths": paths,
        "method_note": (
            "Pressure loss uses Darcy-Weisbach friction plus entered minor-loss "
            "coefficients and fixed component drops for each explicit path. The "
            "highest calculated path loss is used as the network critical path."
        ),
        "scope_note": (
            "This is a preliminary steady-state pressure-loss model. Air density, "
            "Darcy friction factors, K values, geometry, flows, and fixed losses are "
            "project inputs. It does not infer roughness, Reynolds-dependent friction "
            "factors, duct leakage, acoustic criteria, system effect, balancing-device "
            "authority, or a final fan operating point."
        ),
    }
