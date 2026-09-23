from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from math import prod

from .fan_speed import scale_fan_curve_for_speed
from .fan_variable_friction_uncertainty import (
    FanVariableFrictionLoopUncertaintyStudy,
    analyze_fan_variable_friction_loop_uncertainty,
)
from .uncertainty_models import UncertainValue


def _positive(value: float, field_name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be finite and > 0")
    return value


def _iter_uncertain_values(value):
    if isinstance(value, UncertainValue):
        yield value
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _iter_uncertain_values(nested)
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for nested in value:
            yield from _iter_uncertain_values(nested)


def _uncertainty_corner_count(
    study: FanVariableFrictionLoopUncertaintyStudy,
) -> int:
    values = []
    for field_info in fields(study):
        values.extend(
            _iter_uncertain_values(getattr(study, field_info.name))
        )
    return prod(
        len({item.lower, item.upper})
        for item in values
    ) if values else 1


@dataclass(frozen=True)
class FanVariableFrictionSpeedUncertaintyStudy:
    name: str
    base_uncertainty_study: FanVariableFrictionLoopUncertaintyStudy
    speed_ratios: tuple[float, ...]
    reference_speed_rpm: float | None = None
    max_total_cases: int = 1024

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "fan-speed/variable-friction uncertainty study name cannot be empty"
            )
        if not self.speed_ratios:
            raise ValueError(
                "fan-speed/variable-friction uncertainty study requires at least "
                "one speed ratio"
            )

        ratios = tuple(
            _positive(value, "speed ratio") for value in self.speed_ratios
        )
        if len(set(ratios)) != len(ratios):
            raise ValueError(
                "fan-speed/variable-friction uncertainty speed ratios must be unique"
            )
        object.__setattr__(self, "speed_ratios", ratios)

        if self.reference_speed_rpm is not None:
            object.__setattr__(
                self,
                "reference_speed_rpm",
                _positive(self.reference_speed_rpm, "reference_speed_rpm"),
            )

        if (
            isinstance(self.max_total_cases, bool)
            or not isinstance(self.max_total_cases, int)
            or self.max_total_cases <= 0
        ):
            raise ValueError("max_total_cases must be an integer > 0")


def analyze_fan_variable_friction_speed_uncertainty(
    study: FanVariableFrictionSpeedUncertaintyStudy,
) -> dict:
    corner_count = _uncertainty_corner_count(study.base_uncertainty_study)
    total_case_count = corner_count * len(study.speed_ratios)
    if total_case_count > study.max_total_cases:
        raise ValueError(
            "fan-speed/variable-friction uncertainty total case count "
            f"{total_case_count} is exceeding max_total_cases="
            f"{study.max_total_cases}"
        )

    cases: list[dict] = []
    counts: dict[str, int] = {}
    for ratio in study.speed_ratios:
        scaled_curve = scale_fan_curve_for_speed(
            study.base_uncertainty_study.fan_curve,
            ratio,
        )
        case_study = replace(
            study.base_uncertainty_study,
            name=f"{study.name} @ {ratio:.6g}x",
            fan_curve=scaled_curve,
        )
        analysis = analyze_fan_variable_friction_loop_uncertainty(
            case_study
        )
        if analysis["corner_count"] != corner_count:
            raise RuntimeError(
                "canonical nonlinear uncertainty corner count changed during "
                "fan-speed composition; update the generic corner counter"
            )

        status = analysis["status"]
        counts[status] = counts.get(status, 0) + 1
        cases.append(
            {
                "speed_ratio": round(ratio, 6),
                "speed_rpm": (
                    round(study.reference_speed_rpm * ratio, 3)
                    if study.reference_speed_rpm is not None
                    else None
                ),
                "affinity_scaling": {
                    "airflow_ratio": round(ratio, 6),
                    "pressure_ratio": round(ratio**2, 6),
                    "homologous_input_power_factor": round(ratio**3, 6),
                },
                "scaled_fan_curve": scaled_curve.name,
                "scaled_fan_curve_airflow_range_m3_h": [
                    round(scaled_curve.points[0].airflow_m3_h, 6),
                    round(scaled_curve.points[-1].airflow_m3_h, 6),
                ],
                "status": status,
                "nominal_status": analysis["nominal_status"],
                "corner_count": analysis["corner_count"],
                "solved_corner_count": analysis["solved_corner_count"],
                "unresolved_corner_count": analysis[
                    "unresolved_corner_count"
                ],
                "operating_point_envelope": analysis[
                    "operating_point_envelope"
                ],
                "edge_airflow_corner_ranges": analysis[
                    "edge_airflow_corner_ranges"
                ],
                "traceability": analysis["traceability"],
                "uncertainty_analysis": analysis,
            }
        )

    unresolved_speed_case_count = sum(
        count
        for status, count in counts.items()
        if status != "complete"
    )
    return {
        "study": study.name,
        "reference_fan_curve": (
            study.base_uncertainty_study.fan_curve.name
        ),
        "loop_network": study.base_uncertainty_study.loop_network.name,
        "fan_discharge_node": (
            study.base_uncertainty_study.fan_discharge_node
        ),
        "fan_suction_node": (
            study.base_uncertainty_study.fan_suction_node
        ),
        "reference_speed_rpm": study.reference_speed_rpm,
        "status": (
            "screening_complete"
            if unresolved_speed_case_count == 0
            else "attention_required"
        ),
        "counts": counts,
        "speed_case_count": len(cases),
        "uncertainty_corner_count_per_speed": corner_count,
        "total_speed_corner_case_count": total_case_count,
        "unresolved_speed_case_count": unresolved_speed_case_count,
        "speed_cases": cases,
        "scope_note": (
            "Each explicit speed ratio transforms only the supplied reference "
            "fan-curve points using the existing CleanroomX affinity-law "
            "implementation. The canonical nonlinear fan/variable-friction "
            "uncertainty study is then copied with that transformed fan curve "
            "and solved unchanged, so every uncertainty dimension supported by "
            "the canonical engine is preserved without duplicating its schema. "
            "Every corner continues to rebuild the affected geometry evidence "
            "and re-solve the complete Darcy-friction network at every bounded "
            "fan/system airflow. Complete envelopes are reported only when the "
            "nominal case and every corner solve for that speed. No transformed "
            "fan curve is extrapolated. Speed scenarios and uncertainty corners "
            "are deterministic engineering evidence, not statistical confidence "
            "bounds, inferred acceptable VFD limits, or manufacturer selection."
        ),
    }
