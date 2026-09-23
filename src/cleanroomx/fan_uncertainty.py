from __future__ import annotations

from dataclasses import asdict
from itertools import product

from .fan_curve import FanOperatingPointStudy, SystemCurve, solve_fan_operating_point
from .fan_uncertainty_models import FanSystemUncertaintyStudy
from .uncertainty_models import UncertainValue


def _input_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": (
            asdict(item.provenance) if item.provenance is not None else None
        ),
    }


def _solve(
    study: FanSystemUncertaintyStudy,
    fixed_pressure_pa: float,
    resistance_pa_per_m3_s_squared: float,
) -> dict:
    return solve_fan_operating_point(
        FanOperatingPointStudy(
            name=study.name,
            fan_curve=study.fan_curve,
            system_curve=SystemCurve(
                name=study.system_curve_name,
                fixed_pressure_pa=fixed_pressure_pa,
                resistance_pa_per_m3_s_squared=resistance_pa_per_m3_s_squared,
            ),
        )
    )


def _metric_envelope(points: list[dict], key: str, unit: str) -> dict:
    values = [point[key] for point in points]
    return {
        "lower": round(min(values), 6),
        "upper": round(max(values), 6),
        "unit": unit,
    }


def analyze_fan_system_uncertainty(
    study: FanSystemUncertaintyStudy,
) -> dict:
    nominal = _solve(
        study,
        study.fixed_pressure_pa.value,
        study.resistance_pa_per_m3_s_squared.value,
    )

    fixed_values = sorted(
        {study.fixed_pressure_pa.lower, study.fixed_pressure_pa.upper}
    )
    resistance_values = sorted(
        {
            study.resistance_pa_per_m3_s_squared.lower,
            study.resistance_pa_per_m3_s_squared.upper,
        }
    )

    corners = []
    solved_points = []
    for fixed_pressure, resistance in product(fixed_values, resistance_values):
        result = _solve(study, fixed_pressure, resistance)
        corner = {
            "fixed_pressure_pa": round(fixed_pressure, 6),
            "resistance_pa_per_m3_s_squared": round(resistance, 6),
            "status": result["status"],
            "operating_point": result["operating_point"],
        }
        corners.append(corner)
        if result["operating_point"] is not None:
            solved_points.append(result["operating_point"])

    unresolved_corner_count = sum(
        item["status"] != "solved" for item in corners
    )
    all_corners_solved = (
        unresolved_corner_count == 0 and nominal["status"] == "solved"
    )

    envelope = None
    if all_corners_solved:
        envelope = {
            "airflow_m3_h": _metric_envelope(
                solved_points, "airflow_m3_h", "m3/h"
            ),
            "system_pressure_pa": _metric_envelope(
                solved_points, "system_pressure_pa", "Pa"
            ),
        }

    inputs = [
        _input_record("fixed_pressure_pa", study.fixed_pressure_pa),
        _input_record(
            "resistance_pa_per_m3_s_squared",
            study.resistance_pa_per_m3_s_squared,
        ),
    ]
    missing = [
        item["name"] for item in inputs if item["provenance"] is None
    ]
    if study.fan_curve_provenance is None:
        missing.insert(0, "fan_curve")

    traceability = {
        "complete": not missing,
        "missing_provenance": missing,
        "fan_curve_provenance": (
            asdict(study.fan_curve_provenance)
            if study.fan_curve_provenance is not None
            else None
        ),
        "inputs": inputs,
    }

    nominal_point = nominal["operating_point"]
    return {
        "analysis": study.name,
        "status": "complete" if all_corners_solved else "indeterminate",
        "fan_curve": study.fan_curve.name,
        "system_curve": study.system_curve_name,
        "input_intervals": {
            "fixed_pressure_pa": {
                "nominal": study.fixed_pressure_pa.value,
                "lower": study.fixed_pressure_pa.lower,
                "upper": study.fixed_pressure_pa.upper,
                "unit": "Pa",
            },
            "resistance_pa_per_m3_s_squared": {
                "nominal": study.resistance_pa_per_m3_s_squared.value,
                "lower": study.resistance_pa_per_m3_s_squared.lower,
                "upper": study.resistance_pa_per_m3_s_squared.upper,
                "unit": "Pa/(m3/s)^2",
            },
        },
        "nominal_operating_point": nominal_point,
        "nominal_status": nominal["status"],
        "corner_count": len(corners),
        "solved_corner_count": len(solved_points),
        "unresolved_corner_count": unresolved_corner_count,
        "corners": corners,
        "operating_point_envelope": envelope,
        "traceability": traceability,
        "message": (
            "All bounded system-curve corners intersect the supplied fan curve; "
            "the reported airflow and pressure envelope is the min/max across solved "
            "corners."
            if all_corners_solved
            else "At least one bounded system-curve corner has no intersection "
            "inside the supplied fan-curve range; no complete operating-point "
            "envelope is reported."
        ),
        "engineering_note": (
            "This is deterministic corner analysis for user-supplied absolute "
            "bounds on fixed system pressure and quadratic resistance. The bounded "
            "envelope is limited to operating airflow and pressure; air-power extrema "
            "are not inferred from corner values because Q*pressure can have an "
            "interior extremum along a fan-curve segment. Fan pressure "
            "is piecewise-linearly interpolated only inside the supplied fan curve. "
            "No fan-curve extrapolation, probability distribution, covariance, "
            "fan-law scaling, variable resistance, controls, system-effect correction, "
            "stall/surge assessment, or manufacturer selection is inferred."
        ),
    }
