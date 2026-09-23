from __future__ import annotations

from dataclasses import asdict

from .uncertainty_models import UncertainRoom, UncertainValue


def _value_record(name: str, item: UncertainValue) -> dict:
    return {
        "name": name,
        "value": item.value,
        "unit": item.unit,
        "uncertainty_abs": item.uncertainty_abs,
        "lower": item.lower,
        "upper": item.upper,
        "provenance": asdict(item.provenance) if item.provenance is not None else None,
    }


def _requirement_status(
    lower: float, upper: float, minimum: float | None
) -> tuple[str, str]:
    if minimum is None:
        return "not_checked", "No project minimum ACH requirement configured."
    if lower >= minimum:
        return (
            "pass",
            "The complete conservative ACH interval meets the configured minimum.",
        )
    if upper < minimum:
        return (
            "fail",
            "The complete conservative ACH interval is below the configured minimum.",
        )
    return (
        "indeterminate",
        "The configured minimum lies inside the conservative ACH interval; the supplied "
        "input uncertainty prevents a robust pass/fail decision.",
    )


def analyze_room_uncertainty(room: UncertainRoom) -> dict:
    volume_nominal = room.length_m.value * room.width_m.value * room.height_m.value
    volume_lower = room.length_m.lower * room.width_m.lower * room.height_m.lower
    volume_upper = room.length_m.upper * room.width_m.upper * room.height_m.upper

    ach_nominal = room.supply_airflow_m3_h.value / volume_nominal
    ach_lower = room.supply_airflow_m3_h.lower / volume_upper
    ach_upper = room.supply_airflow_m3_h.upper / volume_lower

    status, message = _requirement_status(ach_lower, ach_upper, room.min_ach)

    inputs = [
        _value_record("length_m", room.length_m),
        _value_record("width_m", room.width_m),
        _value_record("height_m", room.height_m),
        _value_record("supply_airflow_m3_h", room.supply_airflow_m3_h),
    ]
    missing = [item["name"] for item in inputs if item["provenance"] is None]

    return {
        "room": room.name,
        "method": "conservative_interval",
        "volume_m3": {
            "nominal": round(volume_nominal, 6),
            "lower": round(volume_lower, 6),
            "upper": round(volume_upper, 6),
        },
        "ach_1_h": {
            "nominal": round(ach_nominal, 6),
            "lower": round(ach_lower, 6),
            "upper": round(ach_upper, 6),
        },
        "requirement": {
            "min_ach": room.min_ach,
            "status": status,
            "message": message,
        },
        "traceability": {
            "input_count": len(inputs),
            "inputs_with_provenance": len(inputs) - len(missing),
            "complete": not missing,
            "missing_provenance": missing,
            "inputs": inputs,
        },
        "engineering_note": (
            "Bounds are propagated with deterministic worst-case interval arithmetic "
            "from the supplied absolute input bounds. This is a screening and "
            "traceability calculation, not a statistical uncertainty budget and not "
            "a substitute for the project measurement/qualification procedure."
        ),
    }
