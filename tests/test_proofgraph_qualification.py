from __future__ import annotations

import copy

from cleanroomx.proofgraph import (
    proofgraph_from_dict,
    proofgraph_from_qualification_uncertainty,
)
from cleanroomx.qualification_models import (
    MeasurementCheck,
    PressureCascadeCheck,
    QualificationRequirement,
    QualificationUncertaintySpec,
)
from cleanroomx.uncertainty_models import Provenance, UncertainValue


def uv(
    value: float,
    unit: str,
    uncertainty: float = 0.0,
    *,
    with_provenance: bool = True,
) -> UncertainValue:
    provenance = (
        Provenance(
            source_type="measurement",
            source_name="Qualification record",
            reference="Q-001",
            revision="R1",
            date="2026-09-30",
            uncertainty_basis="Instrument absolute uncertainty",
        )
        if with_provenance
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def test_qualification_measurement_maps_to_commissioning_and_calculation_evidence() -> None:
    spec = QualificationUncertaintySpec(
        "Suite qualification",
        measurements=(
            MeasurementCheck(
                "Room differential pressure",
                uv(14.0, "Pa", 1.0),
                QualificationRequirement("minimum", 10.0, "Pa", "URS-P-01"),
            ),
        ),
    )

    document = proofgraph_from_qualification_uncertainty(spec).to_dict()

    assert document["verdicts"][0]["status"] == "pass"
    assert document["findings"][0]["actual"] == {
        "nominal": 14.0,
        "lower": 13.0,
        "upper": 15.0,
    }
    assert document["findings"][0]["delta"] == 3.0
    assert document["requirement_set"]["requirements"][0]["criteria"]["property"] == (
        "qualification_interval"
    )
    interval = next(
        item
        for item in document["evidence"]
        if item["property_name"] == "qualification_interval"
    )
    assert interval["value"] == {"lower": 13.0, "upper": 15.0}
    assert set(document["checks"][0]["required_evidence_kinds"]) == {
        "commissioning",
        "calculation",
    }
    assert {item["kind"] for item in document["evidence"]} == {
        "commissioning",
        "calculation",
    }
    assert any(item["revision"] == "R1" for item in document["evidence_sources"])


def test_qualification_blank_optional_provenance_date_is_omitted() -> None:
    provenance = Provenance(
        source_type="measurement",
        source_name="Qualification record",
        reference="Q-001",
        revision="R1",
        date="",
    )
    spec = QualificationUncertaintySpec(
        "Blank provenance date",
        measurements=(
            MeasurementCheck(
                "Room differential pressure",
                UncertainValue(14.0, "Pa", 1.0, provenance),
                QualificationRequirement("minimum", 10.0, "Pa"),
            ),
        ),
    )

    document = proofgraph_from_qualification_uncertainty(spec).to_dict()

    commissioning = next(
        item for item in document["evidence"] if item["kind"] == "commissioning"
    )
    assert commissioning["timestamp"] is None
    assert document["verdicts"][0]["status"] == "pass"


def test_qualification_missing_measurement_provenance_fails_closed_to_unknown() -> None:
    spec = QualificationUncertaintySpec(
        "Traceability gap",
        measurements=(
            MeasurementCheck(
                "Room differential pressure",
                uv(14.0, "Pa", 1.0, with_provenance=False),
                QualificationRequirement("minimum", 10.0, "Pa"),
            ),
        ),
    )

    document = proofgraph_from_qualification_uncertainty(spec).to_dict()

    run = document["verification_runs"][0]
    assert run["metadata"]["canonical_overall_status"] == "pass"
    assert run["metadata"]["traceability"]["complete"] is False
    assert document["verdicts"][0]["status"] == "unknown"
    assert "cannot issue a verified qualification verdict" in document["verdicts"][0]["reason"]


def test_qualification_pressure_cascade_preserves_indeterminate_interval() -> None:
    spec = QualificationUncertaintySpec(
        "Cascade qualification",
        pressure_cascades=(
            PressureCascadeCheck(
                "Process to ante",
                higher_pressure=uv(20.0, "Pa", 2.0),
                lower_pressure=uv(10.0, "Pa", 1.0),
                min_delta_pa=9.0,
                requirement_reference="URS-CASCADE-01",
            ),
        ),
    )

    document = proofgraph_from_qualification_uncertainty(spec).to_dict()

    assert document["verdicts"][0]["status"] == "indeterminate"
    assert document["findings"][0]["actual"] == {
        "nominal": 10.0,
        "lower": 7.0,
        "upper": 13.0,
    }
    assert document["findings"][0]["delta"] == -2.0
    calculation = next(
        item
        for item in document["evidence"]
        if item["property_name"] == "pressure_cascade_delta_pa"
    )
    assert len(calculation["provenance"][0]["upstream_evidence_ids"]) == 2


def test_qualification_fail_is_preserved_when_traceability_is_complete() -> None:
    spec = QualificationUncertaintySpec(
        "Particle qualification",
        measurements=(
            MeasurementCheck(
                "Particle concentration",
                uv(450000.0, "particles/m3", 20000.0),
                QualificationRequirement(
                    "maximum",
                    400000.0,
                    "particles/m3",
                    "URS-PARTICLE-01",
                ),
            ),
        ),
    )

    document = proofgraph_from_qualification_uncertainty(spec).to_dict()

    assert document["verdicts"][0]["status"] == "fail"
    assert document["findings"][0]["delta"] == -70000.0


def test_qualification_graph_round_trips_and_is_deterministic() -> None:
    spec = QualificationUncertaintySpec(
        "Deterministic qualification",
        measurements=(
            MeasurementCheck(
                "Pressure",
                uv(14.0, "Pa", 1.0),
                QualificationRequirement("minimum", 10.0, "Pa"),
            ),
        ),
    )

    first = proofgraph_from_qualification_uncertainty(spec).to_dict()
    second = proofgraph_from_qualification_uncertainty(spec).to_dict()

    assert first == second
    assert proofgraph_from_dict(copy.deepcopy(first)).to_dict() == first
