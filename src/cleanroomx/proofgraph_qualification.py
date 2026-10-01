from __future__ import annotations

from dataclasses import asdict

from .proofgraph_models import (
    CalculationEvidence,
    CommissioningEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    Evidence,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
    _canonical_sha256,
)
from .qualification import analyze_qualification_uncertainty
from .qualification_models import QualificationUncertaintySpec
from .uncertainty_models import Provenance, UncertainValue


def _source_for_measurement(
    provenance: Provenance | None,
    *,
    fallback_source: EvidenceSource,
    sources: dict[str, EvidenceSource],
) -> EvidenceSource:
    if provenance is None:
        sources.setdefault(fallback_source.id, fallback_source)
        return sources[fallback_source.id]

    payload = asdict(provenance)
    digest = _canonical_sha256(payload)
    source_id = f"source:qualification-input:{digest[:16]}"
    reference = provenance.source_name
    if provenance.reference:
        reference = f"{reference} ({provenance.reference})"
    source = EvidenceSource(
        id=source_id,
        kind=provenance.source_type,
        reference=reference,
        revision=provenance.revision or digest,
    )
    sources.setdefault(source.id, source)
    return sources[source.id]


def _uncertain_payload(item: UncertainValue) -> dict[str, float]:
    return {
        "nominal": item.value,
        "lower": item.lower,
        "upper": item.upper,
        "uncertainty_abs": item.uncertainty_abs,
    }


def _commissioning_evidence(
    *,
    evidence_id: str,
    property_name: str,
    item: UncertainValue,
    origin: str,
    version: str,
    subject_ref: str,
    fallback_source: EvidenceSource,
    sources: dict[str, EvidenceSource],
) -> CommissioningEvidence:
    source = _source_for_measurement(
        item.provenance,
        fallback_source=fallback_source,
        sources=sources,
    )
    return CommissioningEvidence(
        id=evidence_id,
        property_name=property_name,
        value=_uncertain_payload(item),
        unit=item.unit,
        source_id=source.id,
        version=version,
        timestamp=item.provenance.date if item.provenance is not None else None,
        subject_ref=subject_ref,
        provenance=(
            ProvenanceRecord(
                id=f"provenance:{evidence_id}",
                source_id=source.id,
                origin=origin,
                method=(
                    "measured_value_with_absolute_uncertainty"
                    if item.provenance is not None
                    else "unattributed_measured_value_with_absolute_uncertainty"
                ),
            ),
        ),
    )


def _calculation_evidence(
    *,
    evidence_id: str,
    property_name: str,
    value: dict[str, float],
    unit: str,
    version: str,
    subject_ref: str,
    source: EvidenceSource,
    upstream_evidence_ids: tuple[str, ...],
    origin: str,
) -> CalculationEvidence:
    return CalculationEvidence(
        id=evidence_id,
        property_name=property_name,
        value=value,
        unit=unit,
        source_id=source.id,
        version=version,
        subject_ref=subject_ref,
        provenance=(
            ProvenanceRecord(
                id=f"provenance:{evidence_id}",
                source_id=source.id,
                origin=origin,
                upstream_evidence_ids=upstream_evidence_ids,
                originating_calculation="analyze_qualification_uncertainty",
                method="conservative_interval",
            ),
        ),
    )


def _proofgraph_status(
    canonical_status: str,
    canonical_message: str,
    *,
    missing_provenance: tuple[str, ...],
) -> tuple[str, str]:
    if canonical_status not in {"pass", "fail", "indeterminate"}:
        raise ValueError(
            f"unexpected canonical qualification status: {canonical_status!r}"
        )
    if not missing_provenance:
        return canonical_status, canonical_message

    missing = ", ".join(missing_provenance)
    return (
        "unknown",
        (
            f"Canonical qualification status is {canonical_status.upper()}, "
            f"but measurement provenance is incomplete for: {missing}. "
            "ProofGraph cannot issue a verified qualification verdict."
        ),
    )


def proofgraph_from_qualification_uncertainty(
    spec: QualificationUncertaintySpec,
    *,
    graph_id: str | None = None,
) -> ProofGraph:
    """Map canonical qualification uncertainty checks into ProofGraph.

    The adapter reuses analyze_qualification_uncertainty and preserves its
    conservative-interval decision semantics. Qualification measurements are
    commissioning evidence. Missing source provenance is retained as a
    traceability gap and prevents ProofGraph from promoting the canonical
    numerical outcome to a verified PASS/FAIL/INDETERMINATE verdict.
    """
    if not isinstance(spec, QualificationUncertaintySpec):
        raise ValueError(
            "spec must be a qualification_models.QualificationUncertaintySpec"
        )

    result = analyze_qualification_uncertainty(spec)
    input_revision = _canonical_sha256(asdict(spec))

    fallback_source = EvidenceSource(
        id=f"source:qualification-spec:{input_revision[:16]}",
        kind="qualification_uncertainty_spec",
        reference=spec.name,
        revision=input_revision,
    )
    calculation_source = EvidenceSource(
        id=f"source:qualification-calculation:{input_revision[:16]}",
        kind="qualification_uncertainty_calculation",
        reference=spec.name,
        revision=input_revision,
    )
    sources: dict[str, EvidenceSource] = {
        calculation_source.id: calculation_source,
    }

    requirements: list[Requirement] = []
    evidence: list[Evidence] = []
    checks: list[ComplianceCheck] = []
    findings: list[ComplianceFinding] = []
    verdicts: list[ComplianceVerdict] = []
    canonical_check_statuses: list[dict[str, str]] = []

    for index, (check, check_result) in enumerate(
        zip(spec.measurements, result["measurements"], strict=True)
    ):
        token = f"measurement:{index}:{input_revision[:12]}"
        subject_ref = check.name
        requirement_id = f"requirement:qualification:{token}"
        observed_id = f"commissioning:qualification:{token}:observed"
        interval_id = f"calculation:qualification:{token}:interval"
        check_id = f"check:qualification:{token}"
        finding_id = f"finding:qualification:{token}"
        verdict_id = f"verdict:qualification:{token}"

        requirements.append(
            Requirement(
                id=requirement_id,
                title=check.name,
                source="qualification_uncertainty_spec",
                reference=check.requirement.reference or spec.name,
                scope=(subject_ref,),
                criteria={
                    "property": "observed_value",
                    "operator": (
                        "complete_interval_meets_minimum"
                        if check.requirement.kind == "minimum"
                        else "complete_interval_meets_maximum"
                    ),
                    "limit": check.requirement.limit,
                    "unit": check.requirement.unit,
                    "uncertainty_method": result["method"],
                },
            )
        )

        observed = _commissioning_evidence(
            evidence_id=observed_id,
            property_name="observed_value",
            item=check.observed,
            origin=f"qualification_spec.measurements[{index}].observed",
            version=input_revision,
            subject_ref=subject_ref,
            fallback_source=fallback_source,
            sources=sources,
        )
        interval = _calculation_evidence(
            evidence_id=interval_id,
            property_name="qualification_interval",
            value={
                "lower": check_result["interval"]["lower"],
                "upper": check_result["interval"]["upper"],
            },
            unit=check.observed.unit,
            version=input_revision,
            subject_ref=subject_ref,
            source=calculation_source,
            upstream_evidence_ids=(observed.id,),
            origin=f"analyze_qualification_uncertainty.measurements[{index}].interval",
        )
        evidence.extend((observed, interval))

        missing_provenance = (
            (check.name,) if check.observed.provenance is None else ()
        )
        status, reason = _proofgraph_status(
            check_result["status"],
            check_result["message"],
            missing_provenance=missing_provenance,
        )
        evidence_ids = (observed.id, interval.id)
        checks.append(
            ComplianceCheck(
                id=check_id,
                requirement_id=requirement_id,
                evidence_ids=evidence_ids,
                required_evidence_kinds=("commissioning", "calculation"),
            )
        )
        margin = (
            check_result["interval"]["lower"] - check.requirement.limit
            if check.requirement.kind == "minimum"
            else check.requirement.limit - check_result["interval"]["upper"]
        )
        findings.append(
            ComplianceFinding(
                id=finding_id,
                check_id=check_id,
                requirement_id=requirement_id,
                status=status,
                reason=reason,
                evidence_ids=evidence_ids,
                evidence_present=True,
                expected=check.requirement.limit,
                actual={
                    "nominal": check.observed.value,
                    "lower": check_result["interval"]["lower"],
                    "upper": check_result["interval"]["upper"],
                },
                unit=check.requirement.unit,
                delta=margin,
            )
        )
        verdicts.append(
            ComplianceVerdict(
                id=verdict_id,
                requirement_id=requirement_id,
                status=status,
                finding_ids=(finding_id,),
                reason=reason,
            )
        )
        canonical_check_statuses.append(
            {
                "kind": "measurement",
                "name": check.name,
                "status": check_result["status"],
            }
        )

    for index, (check, check_result) in enumerate(
        zip(spec.pressure_cascades, result["pressure_cascades"], strict=True)
    ):
        token = f"pressure-cascade:{index}:{input_revision[:12]}"
        subject_ref = check.name
        requirement_id = f"requirement:qualification:{token}"
        higher_id = f"commissioning:qualification:{token}:higher-pressure"
        lower_id = f"commissioning:qualification:{token}:lower-pressure"
        delta_id = f"calculation:qualification:{token}:pressure-delta"
        check_id = f"check:qualification:{token}"
        finding_id = f"finding:qualification:{token}"
        verdict_id = f"verdict:qualification:{token}"

        requirements.append(
            Requirement(
                id=requirement_id,
                title=check.name,
                source="qualification_uncertainty_spec",
                reference=check.requirement_reference or spec.name,
                scope=(subject_ref,),
                criteria={
                    "property": "pressure_cascade_delta_pa",
                    "operator": "complete_interval_meets_minimum",
                    "limit": check.min_delta_pa,
                    "unit": "Pa",
                    "uncertainty_method": result["method"],
                },
            )
        )

        higher = _commissioning_evidence(
            evidence_id=higher_id,
            property_name="higher_pressure",
            item=check.higher_pressure,
            origin=f"qualification_spec.pressure_cascades[{index}].higher_pressure",
            version=input_revision,
            subject_ref=subject_ref,
            fallback_source=fallback_source,
            sources=sources,
        )
        lower = _commissioning_evidence(
            evidence_id=lower_id,
            property_name="lower_pressure",
            item=check.lower_pressure,
            origin=f"qualification_spec.pressure_cascades[{index}].lower_pressure",
            version=input_revision,
            subject_ref=subject_ref,
            fallback_source=fallback_source,
            sources=sources,
        )
        delta = _calculation_evidence(
            evidence_id=delta_id,
            property_name="pressure_cascade_delta_pa",
            value={
                "nominal": check_result["nominal_delta_pa"],
                "lower": check_result["interval_pa"]["lower"],
                "upper": check_result["interval_pa"]["upper"],
            },
            unit="Pa",
            version=input_revision,
            subject_ref=subject_ref,
            source=calculation_source,
            upstream_evidence_ids=(higher.id, lower.id),
            origin=(
                f"analyze_qualification_uncertainty.pressure_cascades[{index}]"
                ".interval_pa"
            ),
        )
        evidence.extend((higher, lower, delta))

        missing_items: list[str] = []
        if check.higher_pressure.provenance is None:
            missing_items.append(f"{check.name}: higher pressure")
        if check.lower_pressure.provenance is None:
            missing_items.append(f"{check.name}: lower pressure")
        status, reason = _proofgraph_status(
            check_result["status"],
            check_result["message"],
            missing_provenance=tuple(missing_items),
        )
        evidence_ids = (higher.id, lower.id, delta.id)
        checks.append(
            ComplianceCheck(
                id=check_id,
                requirement_id=requirement_id,
                evidence_ids=evidence_ids,
                required_evidence_kinds=("commissioning", "calculation"),
            )
        )
        findings.append(
            ComplianceFinding(
                id=finding_id,
                check_id=check_id,
                requirement_id=requirement_id,
                status=status,
                reason=reason,
                evidence_ids=evidence_ids,
                evidence_present=True,
                expected=check.min_delta_pa,
                actual={
                    "nominal": check_result["nominal_delta_pa"],
                    "lower": check_result["interval_pa"]["lower"],
                    "upper": check_result["interval_pa"]["upper"],
                },
                unit="Pa",
                delta=check_result["interval_pa"]["lower"] - check.min_delta_pa,
            )
        )
        verdicts.append(
            ComplianceVerdict(
                id=verdict_id,
                requirement_id=requirement_id,
                status=status,
                finding_ids=(finding_id,),
                reason=reason,
            )
        )
        canonical_check_statuses.append(
            {
                "kind": "pressure_cascade",
                "name": check.name,
                "status": check_result["status"],
            }
        )

    requirement_set = RequirementSet(
        id=f"qualification:{input_revision[:16]}",
        version=input_revision,
        title=f"{spec.name} qualification requirements",
        source="qualification_uncertainty_spec",
        requirements=tuple(requirements),
    )
    run = VerificationRun(
        id=f"verification:qualification:{input_revision[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(item.id for item in checks),
        verdict_ids=tuple(item.id for item in verdicts),
        input_sha256=input_revision,
        metadata={
            "adapter": "qualification_uncertainty",
            "calculation_service": "analyze_qualification_uncertainty",
            "method": result["method"],
            "canonical_overall_status": result["overall_status"],
            "canonical_check_statuses": canonical_check_statuses,
            "traceability": result["traceability"],
            "engineering_note": result["engineering_note"],
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:qualification:{input_revision[:16]}",
        requirement_set=requirement_set,
        evidence_sources=tuple(sources[source_id] for source_id in sorted(sources)),
        evidence=tuple(evidence),
        checks=tuple(checks),
        findings=tuple(findings),
        verdicts=tuple(verdicts),
        verification_runs=(run,),
    )
