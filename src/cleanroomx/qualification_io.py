from __future__ import annotations

import json
from pathlib import Path

from .qualification_models import (
    MeasurementCheck,
    PressureCascadeCheck,
    QualificationRequirement,
    QualificationUncertaintySpec,
)
from .uncertainty_models import Provenance, UncertainValue


def _provenance_from_dict(data: dict | None) -> Provenance | None:
    return Provenance(**data) if data is not None else None


def _uncertain_value_from_dict(data: dict) -> UncertainValue:
    return UncertainValue(
        value=data["value"],
        unit=data["unit"],
        uncertainty_abs=data.get("uncertainty_abs", 0.0),
        provenance=_provenance_from_dict(data.get("provenance")),
    )


def qualification_uncertainty_from_dict(data: dict) -> QualificationUncertaintySpec:
    measurements = tuple(
        MeasurementCheck(
            name=item["name"],
            observed=_uncertain_value_from_dict(item["observed"]),
            requirement=QualificationRequirement(
                kind=item["requirement"]["kind"],
                limit=item["requirement"]["limit"],
                unit=item["requirement"]["unit"],
                reference=item["requirement"].get("reference"),
            ),
        )
        for item in data.get("measurements", [])
    )
    pressure_cascades = tuple(
        PressureCascadeCheck(
            name=item["name"],
            higher_pressure=_uncertain_value_from_dict(item["higher_pressure"]),
            lower_pressure=_uncertain_value_from_dict(item["lower_pressure"]),
            min_delta_pa=item["min_delta_pa"],
            requirement_reference=item.get("requirement_reference"),
        )
        for item in data.get("pressure_cascades", [])
    )
    return QualificationUncertaintySpec(
        name=data["name"],
        measurements=measurements,
        pressure_cascades=pressure_cascades,
    )


def load_qualification_uncertainty(path: str | Path) -> QualificationUncertaintySpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return qualification_uncertainty_from_dict(data)
