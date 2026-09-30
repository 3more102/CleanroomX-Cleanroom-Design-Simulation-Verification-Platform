from __future__ import annotations

import copy
from dataclasses import asdict

from .compliance_rulepack import (
    ComplianceCheck as RulePackComplianceCheck,
    analyze_compliance_check,
)
from .pressure_design_consistency import (
    PressureDesignConsistencyStudy,
    analyze_pressure_design_consistency,
)
from .proofgraph_models import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    CalculationEvidence,
    DesignEvidence,
    Evidence,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
    _canonical_sha256,
)


def proofgraph_from_compliance_check(
    check: RulePackComplianceCheck,
    *,
    graph_id: str | None = None,
) -> ProofGraph:
    if not isinstance(check, RulePackComplianceCheck):
        raise ValueError("check must be a compliance_rulepack.ComplianceCheck")

    result = analyze_compliance_check(check)
    requirement_set = RequirementSet(
        id=check.rule_pack.id,
        version=check.rule_pack.version,
        title=check.rule_pack.title,
        source=check.rule_pack.source,
        requirements=tuple(
            Requirement(
                id=rule.id,
                title=rule.title,
                source=rule.source or check.rule_pack.source,
                reference=rule.reference,
                criteria={
                    "evidence_path": rule.evidence_path,
                    "operator": rule.operator,
                    "expected": copy.deepcopy(rule.expected),
                    "unit": rule.unit,
                    "tolerance": rule.tolerance,
                },
            )
            for rule in check.rule_pack.rules
        ),
    )

    source_id = f"source:{result['evidence_sha256'][:16]}"
    source = EvidenceSource(
        id=source_id,
        kind="declared_document",
        reference=check.name,
        revision=result["evidence_sha256"],
    )
    evidence: list[Evidence] = []
    checks: list[ComplianceCheck] = []
    findings: list[ComplianceFinding] = []
    verdicts: list[ComplianceVerdict] = []

    by_rule = {rule.id: rule for rule in check.rule_pack.rules}
    for finding in result["findings"]:
        rule = by_rule[finding["id"]]
        evidence_ids: tuple[str, ...] = ()
        if finding["evidence_present"]:
            evidence_id = f"evidence:{rule.id}"
            evidence_ids = (evidence_id,)
            evidence.append(
                Evidence(
                    id=evidence_id,
                    kind="declared",
                    property_name=rule.evidence_path,
                    value=finding["actual"],
                    unit=rule.unit,
                    source_id=source_id,
                    version=result["evidence_sha256"],
                    provenance=(
                        ProvenanceRecord(
                            id=f"provenance:{rule.id}",
                            source_id=source_id,
                            origin=rule.evidence_path,
                            method="compliance_rulepack_json_pointer",
                        ),
                    ),
                )
            )

        check_id = f"check:{rule.id}"
        finding_id = f"finding:{rule.id}"
        verdict_id = f"verdict:{rule.id}"
        status = finding["status"]
        reason = finding.get("note")
        if not reason:
            reason = (
                "Supplied evidence satisfies the declared criterion."
                if status == "pass"
                else "Supplied evidence does not satisfy the declared criterion."
            )

        checks.append(
            ComplianceCheck(
                id=check_id,
                requirement_id=rule.id,
                evidence_ids=evidence_ids,
            )
        )
        findings.append(
            ComplianceFinding(
                id=finding_id,
                check_id=check_id,
                requirement_id=rule.id,
                status=status,
                reason=reason,
                evidence_ids=evidence_ids,
                evidence_present=finding["evidence_present"],
                expected=copy.deepcopy(finding["expected"]),
                actual=copy.deepcopy(finding["actual"]),
                unit=finding["unit"],
                delta=finding["delta"],
            )
        )
        verdicts.append(
            ComplianceVerdict(
                id=verdict_id,
                requirement_id=rule.id,
                status=status,
                finding_ids=(finding_id,),
                reason=reason,
            )
        )

    input_sha256 = _canonical_sha256(
        {
            "rule_pack_sha256": result["rule_pack"]["sha256"],
            "evidence_sha256": result["evidence_sha256"],
        }
    )
    run = VerificationRun(
        id=f"verification:{input_sha256[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(item.id for item in checks),
        verdict_ids=tuple(item.id for item in verdicts),
        input_sha256=input_sha256,
        metadata={
            "adapter": "compliance_rulepack",
            "source_status": result["status"],
            "rule_pack_sha256": result["rule_pack"]["sha256"],
            "evidence_sha256": result["evidence_sha256"],
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:{requirement_set.id}:{input_sha256[:16]}",
        requirement_set=requirement_set,
        evidence_sources=(source,),
        evidence=tuple(evidence),
        checks=tuple(checks),
        findings=tuple(findings),
        verdicts=tuple(verdicts),
        verification_runs=(run,),
    )


def proofgraph_from_pressure_design_consistency(
    study: PressureDesignConsistencyStudy,
    *,
    graph_id: str | None = None,
) -> ProofGraph:
    """Map canonical pressure-target consistency evidence into ProofGraph."""
    if not isinstance(study, PressureDesignConsistencyStudy):
        raise ValueError(
            "study must be a pressure_design_consistency.PressureDesignConsistencyStudy"
        )

    result = analyze_pressure_design_consistency(study)
    configured_rooms = tuple(
        room for room in study.requirements.rooms if room.pressure_target_pa is not None
    )
    if not configured_rooms:
        raise ValueError(
            "pressure ProofGraph adaptation requires at least one configured "
            "pressure_target_pa; no requirement is invented for observation-only rooms"
        )

    requirements_revision = _canonical_sha256(asdict(study.requirements))
    network_revision = _canonical_sha256(asdict(study.pressure_network))
    mappings_revision = _canonical_sha256(
        {
            "mappings": [asdict(mapping) for mapping in study.mappings],
            "pressure_abs_tolerance_pa": study.pressure_abs_tolerance_pa,
            "require_all_configured_targets_mapped": (
                study.require_all_configured_targets_mapped
            ),
        }
    )
    input_sha256 = _canonical_sha256(
        {
            "requirements_sha256": requirements_revision,
            "pressure_network_sha256": network_revision,
            "mapping_policy_sha256": mappings_revision,
        }
    )

    design_source_id = f"source:design-requirements:{requirements_revision[:16]}"
    calculation_source_id = f"source:pressure-network:{network_revision[:16]}"
    evidence_sources = (
        EvidenceSource(
            id=design_source_id,
            kind="design_requirements",
            reference=study.requirements.name,
            revision=requirements_revision,
        ),
        EvidenceSource(
            id=calculation_source_id,
            kind="pressure_network_solver",
            reference=study.pressure_network.name,
            revision=network_revision,
        ),
    )

    findings_by_room = {item["room"]: item for item in result["findings"]}
    requirements: list[Requirement] = []
    evidence: list[Evidence] = []
    checks: list[ComplianceCheck] = []
    graph_findings: list[ComplianceFinding] = []
    verdicts: list[ComplianceVerdict] = []

    for room in configured_rooms:
        finding = findings_by_room[room.name]
        mapping = finding["mapping"]
        origin = room.origins.get("pressure_target_pa") or {}
        origin_kind = origin.get("kind") or "design_requirements"
        origin_name = origin.get("name") or study.requirements.name
        origin_reference = origin.get("reference") or study.requirements.name

        requirement_id = f"pressure-target:{room.name}"
        scope = [f"room:{room.name}"]
        if mapping is not None:
            scope.extend(
                [
                    f"node:{mapping['node']}",
                    f"reference_node:{mapping['reference_node']}",
                ]
            )
        requirements.append(
            Requirement(
                id=requirement_id,
                title=f"Pressure target for {room.name}",
                source=f"{origin_kind}:{origin_name}",
                reference=origin_reference,
                scope=tuple(scope),
                criteria={
                    "property": "pressure_target_pa",
                    "operator": "equals_with_absolute_tolerance",
                    "expected": room.pressure_target_pa,
                    "unit": "Pa",
                    "absolute_tolerance_pa": study.pressure_abs_tolerance_pa,
                    "mapping": copy.deepcopy(mapping),
                },
            )
        )

        design_evidence_id = f"design-pressure-target:{room.name}"
        evidence_ids = [design_evidence_id]
        evidence.append(
            DesignEvidence(
                id=design_evidence_id,
                property_name="pressure_target_pa",
                value=room.pressure_target_pa,
                unit="Pa",
                source_id=design_source_id,
                version=requirements_revision,
                subject_ref=room.name,
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:design-pressure-target:{room.name}",
                        source_id=design_source_id,
                        origin=f"design_requirements.rooms[{room.name}].pressure_target_pa",
                        method=origin_kind,
                    ),
                ),
            )
        )

        calculation_present = finding["actual"] is not None
        if calculation_present:
            calculation_evidence_id = f"calculated-pressure-difference:{room.name}"
            evidence_ids.append(calculation_evidence_id)
            calculation_origin = (
                f"pressure({mapping['node']})-pressure({mapping['reference_node']})"
                if mapping is not None
                else "pressure network result"
            )
            evidence.append(
                CalculationEvidence(
                    id=calculation_evidence_id,
                    property_name="pressure_difference_pa",
                    value=finding["actual"],
                    unit="Pa",
                    source_id=calculation_source_id,
                    version=network_revision,
                    subject_ref=room.name,
                    provenance=(
                        ProvenanceRecord(
                            id=f"provenance:calculated-pressure-difference:{room.name}",
                            source_id=calculation_source_id,
                            origin=calculation_origin,
                            originating_calculation=study.pressure_network.name,
                            method="pressure_network_solver",
                        ),
                    ),
                )
            )

        check_id = f"check:pressure-target:{room.name}"
        finding_id = f"finding:pressure-target:{room.name}"
        verdict_id = f"verdict:pressure-target:{room.name}"
        status = finding["status"]
        checks.append(
            ComplianceCheck(
                id=check_id,
                requirement_id=requirement_id,
                evidence_ids=tuple(evidence_ids),
                required_evidence_kinds=("design", "calculation"),
            )
        )
        graph_findings.append(
            ComplianceFinding(
                id=finding_id,
                check_id=check_id,
                requirement_id=requirement_id,
                status=status,
                reason=finding["message"],
                evidence_ids=tuple(evidence_ids),
                evidence_present=calculation_present,
                expected=finding["expected"],
                actual=finding["actual"],
                unit=finding["unit"],
                delta=finding["delta"],
            )
        )
        verdicts.append(
            ComplianceVerdict(
                id=verdict_id,
                requirement_id=requirement_id,
                status=status,
                finding_ids=(finding_id,),
                reason=finding["message"],
            )
        )

    requirement_set = RequirementSet(
        id=f"pressure-targets:{requirements_revision[:16]}",
        version=requirements_revision,
        title=f"{study.requirements.name} pressure targets",
        source=study.requirements.name,
        requirements=tuple(requirements),
    )
    skipped_unconfigured = tuple(
        room.name
        for room in study.requirements.rooms
        if room.pressure_target_pa is None
    )
    run = VerificationRun(
        id=f"verification:pressure-design:{input_sha256[:16]}",
        requirement_set_id=requirement_set.id,
        check_ids=tuple(item.id for item in checks),
        verdict_ids=tuple(item.id for item in verdicts),
        input_sha256=input_sha256,
        metadata={
            "adapter": "pressure_design_consistency",
            "source_status": result["status"],
            "requirements_sha256": requirements_revision,
            "pressure_network_sha256": network_revision,
            "mapping_policy_sha256": mappings_revision,
            "skipped_unconfigured_rooms": list(skipped_unconfigured),
        },
    )
    return ProofGraph(
        id=graph_id or f"proofgraph:pressure-design:{input_sha256[:16]}",
        requirement_set=requirement_set,
        evidence_sources=evidence_sources,
        evidence=tuple(evidence),
        checks=tuple(checks),
        findings=tuple(graph_findings),
        verdicts=tuple(verdicts),
        verification_runs=(run,),
    )
