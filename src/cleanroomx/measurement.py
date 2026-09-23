from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal


CriterionStatus = Literal["pass", "fail", "indeterminate", "not_checked"]
RequirementKind = Literal["upper", "lower", "range"]


@dataclass(frozen=True)
class UncertaintyComponent:
    name: str
    standard_uncertainty: float
    sensitivity_coefficient: float = 1.0
    evaluation_type: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("uncertainty component name cannot be empty")
        uncertainty = float(self.standard_uncertainty)
        sensitivity = float(self.sensitivity_coefficient)
        if not math.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError("standard_uncertainty must be finite and >= 0")
        if not math.isfinite(sensitivity):
            raise ValueError("sensitivity_coefficient must be finite")
        if self.evaluation_type not in (None, "A", "B"):
            raise ValueError("evaluation_type must be 'A', 'B', or omitted")
        object.__setattr__(self, "standard_uncertainty", uncertainty)
        object.__setattr__(self, "sensitivity_coefficient", sensitivity)


@dataclass(frozen=True)
class MeasurementProvenance:
    instrument_id: str | None = None
    calibration_reference: str | None = None
    calibration_due_date: str | None = None
    procedure_reference: str | None = None
    operator: str | None = None
    sample_location: str | None = None
    measured_at: str | None = None
    source_document: str | None = None


@dataclass(frozen=True)
class MeasurementRequirement:
    kind: RequirementKind
    lower_limit: float | None = None
    upper_limit: float | None = None
    reference: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("upper", "lower", "range"):
            raise ValueError("requirement kind must be upper, lower, or range")

        lower = None if self.lower_limit is None else float(self.lower_limit)
        upper = None if self.upper_limit is None else float(self.upper_limit)
        if lower is not None and not math.isfinite(lower):
            raise ValueError("lower_limit must be finite")
        if upper is not None and not math.isfinite(upper):
            raise ValueError("upper_limit must be finite")

        if self.kind == "upper":
            if upper is None or lower is not None:
                raise ValueError("upper requirement requires only upper_limit")
        elif self.kind == "lower":
            if lower is None or upper is not None:
                raise ValueError("lower requirement requires only lower_limit")
        elif lower is None or upper is None or lower >= upper:
            raise ValueError("range requirement needs lower_limit < upper_limit")

        object.__setattr__(self, "lower_limit", lower)
        object.__setattr__(self, "upper_limit", upper)


@dataclass(frozen=True)
class MeasurementSpec:
    measurand: str
    value: float
    unit: str
    components: tuple[UncertaintyComponent, ...]
    coverage_factor: float = 2.0
    requirement: MeasurementRequirement | None = None
    provenance: MeasurementProvenance = field(default_factory=MeasurementProvenance)

    def __post_init__(self) -> None:
        if not self.measurand.strip():
            raise ValueError("measurand cannot be empty")
        if not self.unit.strip():
            raise ValueError("unit cannot be empty")
        value = float(self.value)
        coverage_factor = float(self.coverage_factor)
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        if not self.components:
            raise ValueError("at least one uncertainty component is required")
        if not math.isfinite(coverage_factor) or coverage_factor <= 0:
            raise ValueError("coverage_factor must be finite and > 0")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "coverage_factor", coverage_factor)


def combined_standard_uncertainty(
    components: tuple[UncertaintyComponent, ...],
) -> float:
    if not components:
        raise ValueError("at least one uncertainty component is required")
    return math.sqrt(
        sum(
            (component.sensitivity_coefficient * component.standard_uncertainty) ** 2
            for component in components
        )
    )


def _evaluate_requirement(
    requirement: MeasurementRequirement | None,
    lower_bound: float,
    upper_bound: float,
) -> tuple[CriterionStatus, str]:
    if requirement is None:
        return "not_checked", "No measurement requirement configured."

    if requirement.kind == "upper":
        assert requirement.upper_limit is not None
        if upper_bound <= requirement.upper_limit:
            return "pass", "The full expanded-uncertainty interval is at or below the upper limit."
        if lower_bound > requirement.upper_limit:
            return "fail", "The full expanded-uncertainty interval is above the upper limit."
        return "indeterminate", "The expanded-uncertainty interval overlaps the upper limit."

    if requirement.kind == "lower":
        assert requirement.lower_limit is not None
        if lower_bound >= requirement.lower_limit:
            return "pass", "The full expanded-uncertainty interval is at or above the lower limit."
        if upper_bound < requirement.lower_limit:
            return "fail", "The full expanded-uncertainty interval is below the lower limit."
        return "indeterminate", "The expanded-uncertainty interval overlaps the lower limit."

    assert requirement.lower_limit is not None
    assert requirement.upper_limit is not None
    if lower_bound >= requirement.lower_limit and upper_bound <= requirement.upper_limit:
        return "pass", "The full expanded-uncertainty interval is inside the specified range."
    if upper_bound < requirement.lower_limit or lower_bound > requirement.upper_limit:
        return "fail", "The full expanded-uncertainty interval is outside the specified range."
    return "indeterminate", "The expanded-uncertainty interval overlaps a specified range limit."


def analyze_measurement(spec: MeasurementSpec) -> dict:
    combined = combined_standard_uncertainty(spec.components)
    expanded = combined * spec.coverage_factor
    lower_bound = spec.value - expanded
    upper_bound = spec.value + expanded
    status, message = _evaluate_requirement(spec.requirement, lower_bound, upper_bound)

    component_rows = []
    for component in spec.components:
        signed_contribution = (
            component.sensitivity_coefficient * component.standard_uncertainty
        )
        component_rows.append(
            {
                **asdict(component),
                "standard_contribution": signed_contribution,
                "variance_contribution": signed_contribution**2,
            }
        )

    requirement = asdict(spec.requirement) if spec.requirement is not None else None
    relative_expanded = (
        abs(expanded / spec.value) * 100.0 if spec.value != 0 else None
    )

    return {
        "measurand": spec.measurand,
        "value": spec.value,
        "unit": spec.unit,
        "combined_standard_uncertainty": combined,
        "coverage_factor": spec.coverage_factor,
        "expanded_uncertainty": expanded,
        "coverage_interval": {
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
        },
        "relative_expanded_uncertainty_percent": relative_expanded,
        "criterion_status": status,
        "criterion_message": message,
        "requirement": requirement,
        "provenance": asdict(spec.provenance),
        "components": component_rows,
        "engineering_note": (
            "The interval decision is a transparent screening rule based on the configured "
            "expanded-uncertainty interval. The coverage factor does not by itself guarantee "
            "a specific coverage probability. Project or regulatory decision rules take precedence."
        ),
    }
