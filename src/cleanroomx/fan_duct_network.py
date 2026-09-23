from __future__ import annotations

import math
from dataclasses import dataclass

from .duct import DuctNetwork, DuctSection
from .fan_curve import (
    FanCurve,
    FanOperatingPointStudy,
    SystemCurve,
    solve_fan_operating_point,
)


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _nonnegative(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and >= 0")
    return value


@dataclass(frozen=True)
class FanDuctNetworkStudy:
    name: str
    fan_curve: FanCurve
    duct_network: DuctNetwork
    reference_system_airflow_m3_h: float
    fixed_pressure_pa: float = 0.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fan/duct-network study name cannot be empty")
        reference = _positive(
            self.reference_system_airflow_m3_h,
            "reference_system_airflow_m3_h",
        )
        fixed = _nonnegative(self.fixed_pressure_pa, "fixed_pressure_pa")
        object.__setattr__(self, "reference_system_airflow_m3_h", reference)
        object.__setattr__(self, "fixed_pressure_pa", fixed)

        for path in self.duct_network.paths:
            for section in path.sections:
                if section.airflow_m3_h > reference + 1e-9:
                    raise ValueError(
                        f"duct section {section.name!r} reference airflow exceeds "
                        "reference_system_airflow_m3_h"
                    )


def _section_base_resistance(section: DuctSection) -> float:
    loss_multiplier = (
        section.friction_factor
        * section.length_m
        / section.hydraulic_diameter_m
        + section.local_loss_coefficient
    )
    return (
        0.5
        * section.air_density_kg_m3
        * loss_multiplier
        / (section.area_m2**2)
    )


def _section_scaled_resistance(
    section: DuctSection,
    reference_system_airflow_m3_h: float,
) -> float:
    flow_ratio = section.airflow_m3_h / reference_system_airflow_m3_h
    return _section_base_resistance(section) * flow_ratio**2


def analyze_fan_duct_network(study: FanDuctNetworkStudy) -> dict:
    reference_system_airflow_m3_s = (
        study.reference_system_airflow_m3_h / 3600.0
    )
    paths: list[dict] = []
    raw_path_resistance: dict[str, float] = {}

    for path in study.duct_network.paths:
        section_rows: list[dict] = []
        path_resistance = 0.0

        for section in path.sections:
            flow_ratio = (
                section.airflow_m3_h
                / study.reference_system_airflow_m3_h
            )
            scaled_resistance = _section_scaled_resistance(
                section,
                study.reference_system_airflow_m3_h,
            )
            reference_drop = (
                scaled_resistance
                * reference_system_airflow_m3_s**2
            )
            path_resistance += scaled_resistance
            section_rows.append(
                {
                    "name": section.name,
                    "reference_airflow_m3_h": round(
                        section.airflow_m3_h, 3
                    ),
                    "flow_ratio_to_system": round(flow_ratio, 9),
                    "quadratic_resistance_pa_per_m3_s_squared": round(
                        scaled_resistance, 9
                    ),
                    "reference_pressure_drop_pa": round(
                        reference_drop, 4
                    ),
                }
            )

        if path_resistance <= 0:
            raise ValueError(
                f"duct path {path.name!r} has zero derived "
                "quadratic resistance"
            )

        raw_path_resistance[path.name] = path_resistance
        paths.append(
            {
                "name": path.name,
                "quadratic_resistance_pa_per_m3_s_squared": round(
                    path_resistance, 9
                ),
                "reference_pressure_drop_pa": round(
                    path_resistance
                    * reference_system_airflow_m3_s**2,
                    4,
                ),
                "sections": section_rows,
            }
        )

    critical = max(
        paths,
        key=lambda item: raw_path_resistance[item["name"]],
    )
    critical_resistance = raw_path_resistance[critical["name"]]

    system_curve = SystemCurve(
        name=f"{critical['name']} derived system curve",
        fixed_pressure_pa=study.fixed_pressure_pa,
        resistance_pa_per_m3_s_squared=critical_resistance,
    )
    fan_result = solve_fan_operating_point(
        FanOperatingPointStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            system_curve=system_curve,
        )
    )

    operating_point = fan_result["operating_point"]
    if operating_point is not None:
        operating_q_m3_s = operating_point["airflow_m3_s"]
        for path in paths:
            path_resistance = raw_path_resistance[path["name"]]
            path["operating_pressure_drop_pa"] = round(
                path_resistance * operating_q_m3_s**2,
                4,
            )
            for section in path["sections"]:
                section["operating_airflow_m3_h"] = round(
                    operating_point["airflow_m3_h"]
                    * section["flow_ratio_to_system"],
                    3,
                )
                section["operating_pressure_drop_pa"] = round(
                    section[
                        "quadratic_resistance_pa_per_m3_s_squared"
                    ]
                    * operating_q_m3_s**2,
                    4,
                )

    return {
        "study": study.name,
        "status": fan_result["status"],
        "fan_curve": study.fan_curve.name,
        "reference_system_airflow_m3_h": round(
            study.reference_system_airflow_m3_h, 3
        ),
        "fixed_pressure_pa": round(study.fixed_pressure_pa, 4),
        "critical_path": critical["name"],
        "critical_path_quadratic_resistance_pa_per_m3_s_squared": round(
            critical_resistance, 9
        ),
        "critical_path_reference_pressure_drop_pa": critical[
            "reference_pressure_drop_pa"
        ],
        "paths": paths,
        "operating_point": operating_point,
        "fan_solver": fan_result,
        "scope_note": (
            "Duct pressure is converted to a quadratic system curve by "
            "holding each section's air density, Darcy friction factor, "
            "local-loss coefficient, and reference airflow fraction "
            "constant as total system airflow changes. The highest-"
            "resistance supplied path governs. Fan pressure is interpolated "
            "only inside the supplied fan curve. This is a bounded screening "
            "model, not a general nonlinear network, variable-friction, "
            "balancing, leakage, system-effect, stall/surge, or controls "
            "calculation."
        ),
    }
