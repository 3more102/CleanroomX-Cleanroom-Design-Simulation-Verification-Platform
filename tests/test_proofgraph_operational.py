from __future__ import annotations

import copy

import pytest

from cleanroomx.proofgraph import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    DesignEvidence,
    EvidenceSource,
    ProofGraph,
    Requirement,
    RequirementSet,
    VerificationRun,
    operational_evidence_bundle,
    proofgraph_from_dict,
    proofgraph_with_operational_evidence,
)


def _observation(
    *,
    source_record_id: str = "BMS-0001",
    property_name: str = "room_pressure_pa",
    value: float = 15.2,
    timestamp: str = "2026-10-02T11:59:30+03:00",
) -> dict:
    return {
        "source_record_id": source_record_id,
        "property_name": property_name,
        "value": value,
        "unit": "Pa",
        "timestamp": timestamp,
        "subject_ref": "Room-A",
        "uncertainty_abs": 0.2,
        "cleanroomx_entity_id": "room-a",
    }


def _bundle(observations=None):
    return operational_evidence_bundle(
        observations or [_observation()],
        source_kind="bacnet_export",
        source_reference="BMS-AHU-01",
        source_revision="export-seq-0042",
        assessment_timestamp="2026-10-02T12:00:00+03:00",
        max_age_seconds=120.0,
        project_id="project-a",
    )


def _graph() -> ProofGraph:
    requirement = Requirement(
        id="REQ-1",
        title="Maintain positive room pressure",
        source="Project URS",
        criteria={"operator": "minimum", "value": 10.0, "unit": "Pa"},
    )
    source = EvidenceSource(
        id="source:baseline",
        kind="design",
        reference="design-basis",
        revision="1",
    )
    evidence = DesignEvidence(
        id="design:baseline",
        property_name="room_pressure_pa",
        value=15.0,
        unit="Pa",
        source_id=source.id,
        subject_ref="Room-A",
    )
    check = ComplianceCheck(
        id="check-1",
        requirement_id=requirement.id,
        evidence_ids=(evidence.id,),
        required_evidence_kinds=("design",),
    )
    finding = ComplianceFinding(
        id="finding-1",
        check_id=check.id,
        requirement_id=requirement.id,
        status="pass",
        reason="Baseline design evidence meets the project requirement.",
        evidence_ids=(evidence.id,),
        evidence_present=True,
        expected=10.0,
        actual=15.0,
        unit="Pa",
        delta=5.0,
    )
    verdict = ComplianceVerdict(
        id="verdict-1",
        requirement_id=requirement.id,
        status="pass",
        finding_ids=(finding.id,),
        reason=finding.reason,
    )
    run = VerificationRun(
        id="run-1",
        requirement_set_id="urs",
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
        input_sha256="a" * 64,
    )
    return ProofGraph(
        id="graph-1",
        requirement_set=RequirementSet(
            id="urs",
            version="1.0",
            title="Project URS",
            source="Project URS",
            requirements=(requirement,),
        ),
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    )


def test_operational_bundle_records_source_uncertainty_and_freshness() -> None:
    sources, evidence = _bundle()

    assert len(sources) == 2
    operational_source = next(
        item for item in sources if item.kind == "bacnet_export"
    )
    assert operational_source.reference == "BMS-AHU-01"
    assert operational_source.revision == "export-seq-0042"

    measurement = next(item for item in evidence if item.kind == "operational")
    freshness = next(
        item
        for item in evidence
        if item.property_name == "operational_freshness"
    )

    assert measurement.value == pytest.approx(15.2)
    assert measurement.unit == "Pa"
    assert measurement.timestamp == "2026-10-02T08:59:30Z"
    assert measurement.project_id == "project-a"
    assert measurement.subject_ref == "Room-A"
    assert measurement.confidence is not None
    assert measurement.confidence.uncertainty == pytest.approx(0.2)
    assert measurement.provenance[0].origin == "BMS-0001"
    assert measurement.provenance[0].cleanroomx_entity_id == "room-a"

    assert freshness.kind == "calculation"
    assert freshness.subject_ref == measurement.id
    assert freshness.timestamp == "2026-10-02T09:00:00Z"
    assert freshness.value["status"] == "current"
    assert freshness.value["age_seconds"] == pytest.approx(30.0)
    assert freshness.value["max_age_seconds"] == pytest.approx(120.0)
    assert freshness.provenance[0].upstream_evidence_ids == (measurement.id,)
    assert (
        freshness.provenance[0].originating_calculation
        == "operational_evidence_bundle"
    )


def test_operational_bundle_retains_stale_observation_without_promoting_it() -> None:
    _, evidence = _bundle(
        [_observation(timestamp="2026-10-02T11:55:00+03:00")]
    )

    measurement = next(item for item in evidence if item.kind == "operational")
    freshness = next(
        item
        for item in evidence
        if item.property_name == "operational_freshness"
    )

    assert measurement.value == pytest.approx(15.2)
    assert freshness.value["status"] == "stale"
    assert freshness.value["age_seconds"] == pytest.approx(300.0)


@pytest.mark.parametrize(
    ("timestamp", "message"),
    [
        ("2026-10-02T11:59:30", "timezone"),
        ("2026-10-02T12:00:01+03:00", "later than assessment_timestamp"),
    ],
)
def test_operational_bundle_fails_closed_on_invalid_time_contract(
    timestamp: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _bundle([_observation(timestamp=timestamp)])


def test_operational_bundle_rejects_negative_uncertainty() -> None:
    observation = _observation()
    observation["uncertainty_abs"] = -0.1

    with pytest.raises(ValueError, match=">= 0"):
        _bundle([observation])


def test_operational_bundle_rejects_duplicate_source_record_identity() -> None:
    first = _observation(source_record_id="same-record")
    second = _observation(
        source_record_id="same-record",
        property_name="temperature_c",
        value=22.0,
    )
    second["unit"] = "degC"

    with pytest.raises(ValueError, match="duplicate source_record_id"):
        _bundle([first, second])


def test_operational_bundle_rejects_unknown_observation_fields() -> None:
    observation = _observation()
    observation["quality"] = "good"

    with pytest.raises(ValueError, match="unsupported field"):
        _bundle([observation])


def test_operational_bundle_is_deterministic_across_input_order() -> None:
    first = _observation(
        source_record_id="BMS-0001",
        property_name="room_pressure_pa",
        value=15.2,
    )
    second = _observation(
        source_record_id="BMS-0002",
        property_name="temperature_c",
        value=22.5,
    )
    second["unit"] = "degC"

    sources_a, evidence_a = _bundle([first, second])
    sources_b, evidence_b = _bundle([second, first])

    assert [item.to_dict() for item in sources_a] == [
        item.to_dict() for item in sources_b
    ]
    assert [item.to_dict() for item in evidence_a] == [
        item.to_dict() for item in evidence_b
    ]


def test_operational_attachment_preserves_existing_verification_and_round_trips() -> None:
    baseline = _graph()
    enriched = proofgraph_with_operational_evidence(
        baseline,
        [_observation()],
        source_kind="bacnet_export",
        source_reference="BMS-AHU-01",
        source_revision="export-seq-0042",
        assessment_timestamp="2026-10-02T12:00:00+03:00",
        max_age_seconds=120.0,
        project_id="project-a",
    )

    assert enriched.requirement_set == baseline.requirement_set
    assert enriched.checks == baseline.checks
    assert enriched.findings == baseline.findings
    assert enriched.verdicts == baseline.verdicts
    assert enriched.verification_runs == baseline.verification_runs
    assert len(enriched.evidence) == len(baseline.evidence) + 2

    document = enriched.to_dict()
    restored = proofgraph_from_dict(copy.deepcopy(document))
    assert restored.to_dict() == document


def test_operational_attachment_rejects_duplicate_evidence() -> None:
    enriched = proofgraph_with_operational_evidence(
        _graph(),
        [_observation()],
        source_kind="bacnet_export",
        source_reference="BMS-AHU-01",
        source_revision="export-seq-0042",
        assessment_timestamp="2026-10-02T12:00:00+03:00",
        max_age_seconds=120.0,
    )

    with pytest.raises(ValueError, match="conflicts with existing evidence ids"):
        proofgraph_with_operational_evidence(
            enriched,
            [_observation()],
            source_kind="bacnet_export",
            source_reference="BMS-AHU-01",
            source_revision="export-seq-0042",
            assessment_timestamp="2026-10-02T12:00:00+03:00",
            max_age_seconds=120.0,
        )
