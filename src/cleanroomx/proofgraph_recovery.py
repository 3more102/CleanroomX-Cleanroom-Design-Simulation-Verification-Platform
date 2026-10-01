from __future__ import annotations

from dataclasses import asdict

from .proofgraph_models import (
    CommissioningEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
    _canonical_sha256,
)
from .recovery_models import RecoveryTestSpec
from .recovery_test import analyze_recovery_test


def _proofgraph_status(
    canonical_status: str,
    *,
    traceability_complete: bool,
) -> str:
    if canonical_status == "not_checked":
        return "not_checked"
    if canonical_status == "incomplete":
        return "unknown"
    if canonical_status not in {"pass", "fail", "indeterminate"}:
        raise ValueError(f"unsupported recovery criterion status: {canonical_status!r}")
    if not traceability_complete:
        return "unknown"
    return canonical_status


def proofgraph_from_recovery_test(
    spec: RecoveryTestSpec,
    *,
    graph_id: str | None = None,
) -> ProofGraph:
    """Project the canonical measured particle-recovery workflow into ProofGraph.

    The recovery solver remains the sole acceptance authority. Commissioning
    evidence is traceable to the supplied test record and is not promoted to a
    verified PASS/FAIL/INDETERMINATE verdict unless the test identifies the
    instrument, sample location, and method/protocol reference.
    """
    if not isinstance(spec, RecoveryTestSpec):
        raise ValueError("spec must be a recovery_models.RecoveryTestSpec")

    result = analyze_recovery_test(spec)
    input_revision = _canonical_sha256(asdict(spec))
    source_id = f"source:recovery-test:{input_revision[:16]}"
    source_reference = (
        spec.instrument_id
        if spec.instrument_id is not None
        else f"recovery_test:{spec.name}"
    )
    source = EvidenceSource(
        id=source_id,
        kind="particle_recovery_measurement",
        reference=source_reference,
        revision=input_revision,
    )

    subject = spec.sample_location or spec.name
    requirement_id = f"recovery-criterion:{input_revision[:16]}"
    requirement = Requirement(
        id=requirement_id,
        title=f"Particle recovery criterion for {spec.name}",
        source="recovery_test_spec",
        reference=spec.method_reference,
        scope=(f"recovery-test:{spec.name}", f"location:{subject}"),
        criteria={
            "property": "particle_recovery",
            "particle_size_um": result["particle_size_um"],
            "target_concentration_per_m3": result["target_concentration_per_m3"],
            "max_recovery_time_minutes": result["max_recovery_time_minutes"],
            "decision_service": "analyze_recovery_test",
            "decision_rule": result["uncertainty_assessment"]["decision_rule"],
        },
    )
    requirement_set = RequirementSet(
        id=f"recovery-requirements:{input_revision[:16]}",
        version=input_revision,
        title=f"{spec.name} recovery requirement",
        source="recovery_test_spec",
        requirements=(requirement,),
    )

    evidence: list[CommissioningEvidence] = []
    for index, sample in enumerate(result["samples"]):
        evidence_id = f"recovery-sample:{input_revision[:16]}:{index:04d}"
        evidence.append(
            CommissioningEvidence(
                id=evidence_id,
                property_name="particle_concentration_interval_per_m3",
                value={
                    "time_minutes": sample["time_minutes"],
                    "nominal": sample["concentration_per_m3"],
                    "uncertainty_abs": sample["concentration_uncertainty_abs"],
                    "lower": sample["concentration_interval_per_m3"]["lower"],
                    "upper": sample["concentration_interval_per_m3"]["upper"],
                    "target_relation": sample["target_relation"],
                },
                unit="particles/m^3",
                source_id=source_id,
                version=input_revision,
                subject_ref=subject,
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:{evidence_id}",
                        source_id=source_id,
                        origin=f"recovery_test.samples[{index}]",
                        method=spec.method_reference,
                    ),
                ),
            )
        )

    traceability_missing = tuple(
        name
        for name, value in (
            ("instrument_id", spec.instrument_id),
            ("sample_location", spec.sample_location),
            ("method_reference", spec.method_reference),
        )
        if value is None or not value.strip()
    )
    traceability_complete = not traceability_missing
    canonical_status = result["criterion_status"]
    status = _proofgraph_status(
        canonical_status,
        traceability_complete=traceability_complete,
    )
    reason = result["criterion_message"]
    if canonical_status == "incomplete":
        reason = (
            "The canonical recovery workflow is incomplete, so ProofGraph cannot "
            "issue a verified recovery verdict."
        )
    elif canonical_status in {"pass", "fail", "indeterminate"} and not traceability_complete:
        reason = (
            "The canonical recovery workflow returned "
            f"{canonical_status!r}, but commissioning traceability is incomplete: "
            + ", ".join(traceability_missing)
            + ". ProofGraph therefore fails closed to UNKNOWN."
        )

    check_id = f"check:recovery:{input_revision[:16]}"
    finding_id = f"finding:recovery:{input_revision[:16]}"
    verdict_id = f"verdict:recovery:{input_revision[:16]}"
    evidence_ids = tuple(item.id for item in evidence)
    check = ComplianceCheck(
        id=check_id,
        requirement_id=requirement_id,
        evidence_ids=evidence_ids,
        required_evidence_kinds=("commissioning",),
    )
    finding = ComplianceFinding(
        id=finding_id,
        check_id=check_id,
        requirement_id=requirement_id,
        status=status,
        reason=reason,
        evidence_ids=evidence_ids,
        evidence_present=bool(evidence_ids),
        expected={
            "target_concentration_per_m3": result["target_concentration_per_m3"],
            "max_recovery_time_minutes": result["max_recovery_time_minutes"],
        },
        actual={
            "first_confirmed_recovery_sample_time_minutes": result[
                "uncertainty_assessment"
            ]["first_confirmed_recovery_sample_time_minutes"],
            "final_concentration_per_m3": result["final_concentration_per_m3"],
            "test_duration_minutes": result["test_duration_minutes"],
        },
    )
    verdict = ComplianceVerdict(
        id=verdict_id,
        requirement_id=requirement_id,
        status=status,
        finding_ids=(finding_id,),
        reason=reason,
    )
    run = VerificationRun(
        id=f"verification:recovery:{input_revision[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=(check_id,),
        verdict_ids=(verdict_id,),
        input_sha256=input_revision,
        metadata={
            "adapter": "recovery_test",
            "decision_service": "analyze_recovery_test",
            "canonical_criterion_status": canonical_status,
            "canonical_criterion_message": result["criterion_message"],
            "traceability_complete": traceability_complete,
            "traceability_missing_fields": list(traceability_missing),
            "instrument_id": spec.instrument_id,
            "sample_location": spec.sample_location,
            "occupancy_state": spec.occupancy_state,
            "method_reference": spec.method_reference,
            "uncertainty_present": result["uncertainty_assessment"][
                "uncertainty_present"
            ],
            "log_linear_fit_used_for_acceptance": False,
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:recovery:{input_revision[:16]}",
        requirement_set=requirement_set,
        evidence_sources=(source,),
        evidence=tuple(evidence),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    )
