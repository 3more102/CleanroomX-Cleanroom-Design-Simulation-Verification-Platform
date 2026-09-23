from __future__ import annotations

from .hvac_models import DuctNetwork, DuctPath, DuctSegment


def analyze_duct_segment(segment: DuctSegment) -> dict:
    """Calculate straight and local pressure losses for one duct segment.

    The straight loss uses the Darcy-Weisbach form:
        delta_p = f_D * (L / D_h) * (rho * v^2 / 2)

    Local losses use:
        delta_p = K * (rho * v^2 / 2)

    The Darcy friction factor and local K are explicit project inputs.
    """
    airflow_m3_s = segment.airflow_m3_h / 3600.0
    area_m2 = segment.area_m2
    hydraulic_diameter_m = segment.hydraulic_diameter_m
    velocity_m_s = airflow_m3_s / area_m2
    velocity_pressure_pa = 0.5 * segment.air_density_kg_m3 * velocity_m_s**2

    straight_loss_pa = (
        segment.darcy_friction_factor
        * (segment.length_m / hydraulic_diameter_m)
        * velocity_pressure_pa
    )
    local_loss_pa = segment.local_loss_coefficient * velocity_pressure_pa
    total_loss_pa = straight_loss_pa + local_loss_pa

    return {
        "name": segment.name,
        "shape": segment.shape,
        "airflow_m3_h": round(segment.airflow_m3_h, 3),
        "airflow_m3_s": round(airflow_m3_s, 6),
        "area_m2": round(area_m2, 6),
        "hydraulic_diameter_m": round(hydraulic_diameter_m, 6),
        "velocity_m_s": round(velocity_m_s, 6),
        "air_density_kg_m3": round(segment.air_density_kg_m3, 6),
        "velocity_pressure_pa": round(velocity_pressure_pa, 6),
        "length_m": round(segment.length_m, 6),
        "darcy_friction_factor": segment.darcy_friction_factor,
        "local_loss_coefficient": segment.local_loss_coefficient,
        "straight_pressure_drop_pa": round(straight_loss_pa, 6),
        "local_pressure_drop_pa": round(local_loss_pa, 6),
        "total_pressure_drop_pa": round(total_loss_pa, 6),
        "geometry": {
            "diameter_m": segment.diameter_m,
            "width_m": segment.width_m,
            "height_m": segment.height_m,
        },
    }


def analyze_duct_path(path: DuctPath) -> dict:
    """Sum pressure losses along one explicit series path."""
    segments = [analyze_duct_segment(segment) for segment in path.segments]
    total_pressure_drop_pa = sum(item["total_pressure_drop_pa"] for item in segments)
    return {
        "name": path.name,
        "segment_count": len(segments),
        "segments": segments,
        "total_pressure_drop_pa": round(total_pressure_drop_pa, 6),
    }


def analyze_duct_network(network: DuctNetwork) -> dict:
    """Analyze explicit fan-to-terminal paths and identify the critical path.

    This is a pressure-loss model, not a nonlinear network-balancing solver.
    Segment airflows are supplied explicitly by the project.
    """
    paths = [analyze_duct_path(path) for path in network.paths]
    critical = max(paths, key=lambda item: item["total_pressure_drop_pa"])
    return {
        "name": network.name,
        "path_count": len(paths),
        "paths": paths,
        "critical_path_name": critical["name"],
        "critical_path_pressure_drop_pa": critical["total_pressure_drop_pa"],
        "scope_note": (
            "Each path is treated as an explicit series route. The critical path is the "
            "route with the largest calculated pressure loss. Shared branches may be "
            "repeated in multiple paths. Segment airflows, Darcy friction factors, local "
            "loss coefficients, and air density are project inputs; CleanroomX does not "
            "solve flow distribution or infer fitting coefficients."
        ),
    }
