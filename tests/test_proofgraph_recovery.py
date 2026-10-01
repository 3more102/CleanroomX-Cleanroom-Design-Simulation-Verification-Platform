from __future__ import annotations

import copy

from cleanroomx.proofgraph_io import proofgraph_from_dict
from cleanroomx.proofgraph_recovery import proofgraph_from_recovery_test
from cleanroomx.recovery_models import RecoverySample, RecoveryTestSpec


def _spec(
    *,
    max_time: float | None = 10.0,
    instrument_id: str | None = "PC-17",
    sample_location: str | None = "Room A",
    method_reference: str | None = "Project SOP REC-01",
) -> RecoveryTestSpec:
    return RecoveryTestSpec(
        name="Room A recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100.0,
        max_recovery_time_minutes=max_time,
        instrument_id=instrument_id,
        sample_location=sample_location,
        occupancy_state="at-rest",
        method_reference=method_reference,
        samples=(
            RecoverySample(
                time_minutes=0.0,
                concentration_per_m3=500.0,
                concentration_uncertainty_abs=20.0,
            ),
            RecoverySample(
                time_minutes=5.0,
                concentration_per_m3=180.0,
                concentration_uncertainty_abs=10.0,
            ),
            RecoverySample(
                time_minutes=10.0,
                concentration_per_m3=80.0,
                concentration_uncertainty_abs=5.0,
            ),
        ),
    )


def test_recovery_adapter_emits_commissioning_evidence_and_canonical_pass():
    graph = proofgraph_from_recovery_test(_spec())

    assert graph.findings[0].status == "pass"
    assert graph.verdicts[0].status == "pass"
    assert graph.checks[0].required_evidence_kinds == ("commissioning",)
    assert len(graph.evidence) == 3
    assert {item.kind for item in graph.evidence} == {"commissioning"}
    assert graph.evidence[2].value["target_relation"] == "confirmed_at_or_below"
    assert graph.verification_runs[0].metadata["canonical_criterion_status"] == "pass"
    assert graph.verification_runs[0].metadata["traceability_complete"] is True
    assert graph.verification_runs[0].metadata["log_linear_fit_used_for_acceptance"] is False


def test_recovery_adapter_fails_closed_when_commissioning_traceability_is_missing():
    graph = proofgraph_from_recovery_test(
        _spec(instrument_id=None, method_reference=None)
    )

    assert graph.findings[0].status == "unknown"
    assert graph.verdicts[0].status == "unknown"
    metadata = graph.verification_runs[0].metadata
    assert metadata["canonical_criterion_status"] == "pass"
    assert metadata["traceability_complete"] is False
    assert metadata["traceability_missing_fields"] == [
        "instrument_id",
        "method_reference",
    ]


def test_recovery_adapter_maps_incomplete_canonical_result_to_unknown():
    spec = RecoveryTestSpec(
        name="Short recovery",
        particle_size_um=0.5,
        target_concentration_per_m3=100.0,
        max_recovery_time_minutes=10.0,
        instrument_id="PC-17",
        sample_location="Room A",
        method_reference="Project SOP REC-01",
        samples=(
            RecoverySample(time_minutes=0.0, concentration_per_m3=500.0),
            RecoverySample(time_minutes=5.0, concentration_per_m3=150.0),
        ),
    )

    graph = proofgraph_from_recovery_test(spec)

    assert graph.findings[0].status == "unknown"
    assert graph.verification_runs[0].metadata["canonical_criterion_status"] == "incomplete"


def test_recovery_adapter_preserves_not_checked_without_inventing_acceptance():
    graph = proofgraph_from_recovery_test(_spec(max_time=None))

    assert graph.findings[0].status == "not_checked"
    assert graph.verdicts[0].status == "not_checked"
    assert graph.requirement_set.requirements[0].criteria[
        "max_recovery_time_minutes"
    ] is None


def test_recovery_adapter_round_trips_through_strict_proofgraph_parser():
    graph = proofgraph_from_recovery_test(_spec())
    document = graph.to_dict()

    restored = proofgraph_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document
    assert len(document["graph_sha256"]) == 64
