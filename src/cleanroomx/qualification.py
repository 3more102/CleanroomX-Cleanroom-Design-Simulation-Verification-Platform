from __future__ import annotations

from dataclasses import asdict

from .qualification_models import (
    MeasurementCheck,
    PressureCascadeCheck,
    QualificationRequirement,
    QualificationUncertaintySpec,
)


def _decision(
    lower: float,
    upper: float,
    requirement: QualificationRequirement,
) -> tuple[str, str]:
    if requirement.kind == "minimum":
        if lower >= requirement.limit:
            return "pass", "The complete uncertainty interval meets the configured minimum."
        if upper < requirement.limit:
            return "fail", "The complete uncertainty interval is below the configured minimum."
        return "indeterminate", "The uncertainty interval overlaps the configured minimum."

    if upper <= requirement.limit:
        return "pass", "The complete uncertainty interval meets the configured maximum."
    if lower > requirement.limit:
        return "fail", "The complete uncertainty interval is above the configured maximum."
    return "indeterminate", "The uncertainty interval overlaps the configured maximum."


def analyze_measurement_check(check: MeasurementCheck) -> dict:
    status, message = _decision(check.observed.lower, check.observed.upper, check.requirement)
    return {
        "name": check.name,
        "kind": "measurement",
        "value": check.observed.value,
        "unit": check.observed.unit,
        "uncertainty_abs": check.observed.uncertainty_abs,
        "interval": {"lower": check.observed.lower, "upper": check.observed.upper},
        "requirement": asdict(check.requirement),
        "status": status,
        "message": message,
        "provenance": (
            asdict(check.observed.provenance)
            if check.observed.provenance is not None
            else None
        ),
    }


def analyze_pressure_cascade_check(check: PressureCascadeCheck) -> dict:
    nominal = check.higher_pressure.value - check.lower_pressure.value
    lower = check.higher_pressure.lower - check.lower_pressure.upper
    upper = check.higher_pressure.upper - check.lower_pressure.lower
    requirement = QualificationRequirement(
        kind="minimum",
        limit=check.min_delta_pa,
        unit="Pa",
        reference=check.requirement_reference,
    )
    status, message = _decision(lower, upper, requirement)
    return {
        "name": check.name,
        "kind": "pressure_cascade",
        "nominal_delta_pa": nominal,
        "interval_pa": {"lower": lower, "upper": upper},
        "requirement": asdict(requirement),
        "status": status,
        "message": message,
        "higher_pressure": {
            "value": check.higher_pressure.value,
            "uncertainty_abs": check.higher_pressure.uncertainty_abs,
            "provenance": (
                asdict(check.higher_pressure.provenance)
                if check.higher_pressure.provenance is not None
                else None
            ),
        },
        "lower_pressure": {
            "value": check.lower_pressure.value,
            "uncertainty_abs": check.lower_pressure.uncertainty_abs,
            "provenance": (
                asdict(check.lower_pressure.provenance)
                if check.lower_pressure.provenance is not None
                else None
            ),
        },
    }


def analyze_qualification_uncertainty(spec: QualificationUncertaintySpec) -> dict:
    measurement_results = [analyze_measurement_check(item) for item in spec.measurements]
    cascade_results = [analyze_pressure_cascade_check(item) for item in spec.pressure_cascades]
    results = measurement_results + cascade_results
    statuses = [item["status"] for item in results]

    overall_status = (
        "fail"
        if "fail" in statuses
        else "indeterminate"
        if "indeterminate" in statuses
        else "pass"
    )

    provenance_entries = []
    for item in spec.measurements:
        provenance_entries.append((item.name, item.observed.provenance))
    for item in spec.pressure_cascades:
        provenance_entries.extend(
            [
                (f"{item.name}: higher pressure", item.higher_pressure.provenance),
                (f"{item.name}: lower pressure", item.lower_pressure.provenance),
            ]
        )
    missing = [name for name, provenance in provenance_entries if provenance is None]

    return {
        "analysis": spec.name,
        "method": "conservative_interval",
        "overall_status": overall_status,
        "measurements": measurement_results,
        "pressure_cascades": cascade_results,
        "traceability": {
            "input_count": len(provenance_entries),
            "inputs_with_provenance": len(provenance_entries) - len(missing),
            "complete": not missing,
            "missing_provenance": missing,
        },
        "engineering_note": (
            "Decisions use deterministic worst-case intervals from user-supplied absolute "
            "uncertainty bounds. Missing provenance is reported separately and does not "
            "change the numerical decision. Project and regulatory decision rules take precedence."
        ),
    }
