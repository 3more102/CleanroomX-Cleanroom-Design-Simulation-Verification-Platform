from __future__ import annotations

import json
from pathlib import Path

from .measurement import (
    MeasurementProvenance,
    MeasurementRequirement,
    MeasurementSpec,
    UncertaintyComponent,
)


def measurement_from_dict(data: dict) -> MeasurementSpec:
    components = tuple(
        UncertaintyComponent(
            name=item["name"],
            standard_uncertainty=item["standard_uncertainty"],
            sensitivity_coefficient=item.get("sensitivity_coefficient", 1.0),
            evaluation_type=item.get("evaluation_type"),
            source=item.get("source"),
        )
        for item in data["components"]
    )

    requirement_data = data.get("requirement")
    requirement = (
        MeasurementRequirement(
            kind=requirement_data["kind"],
            lower_limit=requirement_data.get("lower_limit"),
            upper_limit=requirement_data.get("upper_limit"),
            reference=requirement_data.get("reference"),
        )
        if requirement_data is not None
        else None
    )

    provenance_data = data.get("provenance") or {}
    provenance = MeasurementProvenance(
        instrument_id=provenance_data.get("instrument_id"),
        calibration_reference=provenance_data.get("calibration_reference"),
        calibration_due_date=provenance_data.get("calibration_due_date"),
        procedure_reference=provenance_data.get("procedure_reference"),
        operator=provenance_data.get("operator"),
        sample_location=provenance_data.get("sample_location"),
        measured_at=provenance_data.get("measured_at"),
        source_document=provenance_data.get("source_document"),
    )

    return MeasurementSpec(
        measurand=data["measurand"],
        value=data["value"],
        unit=data["unit"],
        components=components,
        coverage_factor=data.get("coverage_factor", 2.0),
        requirement=requirement,
        provenance=provenance,
    )


def load_measurement(path: str | Path) -> MeasurementSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return measurement_from_dict(data)
