from __future__ import annotations

import copy

from .compliance_rulepack import (
    ComplianceCheck as RulePackComplianceCheck,
    analyze_compliance_check,
)
from .proofgraph_models import (
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

    status_map = {"pass": "pass", "fail": "fail", "not_checked": "unknown"}
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
        status = status_map[finding["status"]]
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
