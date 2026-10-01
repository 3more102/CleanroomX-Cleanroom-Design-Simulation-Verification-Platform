from __future__ import annotations

import copy
from typing import Iterable

from .project_requirement_verification import (
    RequirementEvidence,
    verify_project_requirements,
)
from .project_requirements import ProjectRequirement, ProjectRequirements
from .proofgraph_models import (
    EVIDENCE_KINDS,
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


def _proofgraph_status(source_state: str, source_status: str) -> str:
    if source_status in {"pass", "fail"}:
        return source_status
    if source_state in {"not_checked", "inactive", "not_applicable"}:
        return "not_checked"
    return "unknown"


def _evidence_kind(binding: RequirementEvidence) -> str:
    if (
        len(binding.evidence_kinds) == 1
        and binding.evidence_kinds[0] in EVIDENCE_KINDS
    ):
        return binding.evidence_kinds[0]
    return "declared"


def _source_identity(binding: RequirementEvidence) -> tuple[str, EvidenceSource]:
    revision_identity = _canonical_sha256(
        {
            "source": binding.source,
            "source_revision": binding.source_revision,
        }
    )
    source_id = f"source:project-requirements:{revision_identity}"
    return (
        source_id,
        EvidenceSource(
            id=source_id,
            kind="project_requirement_evidence",
            reference=binding.source,
            revision=binding.source_revision,
        ),
    )


def _requirement_criteria(requirement: ProjectRequirement) -> dict:
    if requirement.target is not None:
        criterion = {
            "operator": "equals",
            "expected": copy.deepcopy(requirement.target),
            "tolerance": (
                requirement.tolerance if requirement.tolerance is not None else 0.0
            ),
        }
    elif requirement.minimum is not None and requirement.maximum is not None:
        criterion = {
            "operator": "range",
            "expected": {
                "minimum": requirement.minimum,
                "maximum": requirement.maximum,
            },
            "tolerance": (
                requirement.tolerance if requirement.tolerance is not None else 0.0
            ),
        }
    elif requirement.minimum is not None:
        criterion = {
            "operator": "minimum",
            "expected": requirement.minimum,
            "tolerance": (
                requirement.tolerance if requirement.tolerance is not None else 0.0
            ),
        }
    elif requirement.maximum is not None:
        criterion = {
            "operator": "maximum",
            "expected": requirement.maximum,
            "tolerance": (
                requirement.tolerance if requirement.tolerance is not None else 0.0
            ),
        }
    else:
        criterion = None

    return {
        "description": requirement.description,
        "discipline": requirement.discipline,
        "category": requirement.category,
        "source_revision": requirement.source_revision,
        "unit": requirement.unit,
        "criterion": criterion,
        "applicability": requirement.applicability,
        "lifecycle_status": requirement.status,
        "verification_method": requirement.verification_method,
        "required_evidence": list(requirement.required_evidence),
        "assumptions": list(requirement.assumptions),
        "notes": requirement.notes,
    }


def _binding_key(requirement_id: str, subject_ref: str | None) -> tuple[str, str]:
    return (requirement_id, "" if subject_ref is None else subject_ref)


def _check_required_kinds(
    requirement: ProjectRequirement,
    evidence_ids: tuple[str, ...],
    evidence_by_id: dict[str, Evidence],
) -> tuple[str, ...]:
    required = tuple(requirement.required_evidence)
    if not required or any(kind not in EVIDENCE_KINDS for kind in required):
        return ()
    represented = {
        evidence_by_id[evidence_id].kind
        for evidence_id in evidence_ids
        if evidence_id in evidence_by_id
    }
    if not set(required).issubset(represented):
        # Do not fabricate separate lifecycle-layer evidence from one aggregate
        # binding merely to satisfy the structural ProofGraph invariant.
        return ()
    return required


def proofgraphs_from_project_requirements_verification(
    requirements: ProjectRequirements,
    evidence: Iterable[RequirementEvidence],
) -> tuple[ProofGraph, ...]:
    """Map canonical project-requirement verification into deterministic ProofGraphs.

    The canonical verifier remains the only comparison authority. One ProofGraph
    is emitted per non-empty persisted requirement set because ProofGraph schema
    v1 intentionally owns exactly one RequirementSet per graph.
    """
    if not isinstance(requirements, ProjectRequirements):
        raise TypeError("requirements must be a ProjectRequirements value")

    evidence_list = tuple(evidence)
    result = verify_project_requirements(requirements, evidence_list)

    source_findings = {
        _binding_key(item["requirement_id"], item["subject_ref"]): item
        for item in result["findings"]
    }
    evidence_by_requirement: dict[str, list[RequirementEvidence]] = {}
    for item in evidence_list:
        evidence_by_requirement.setdefault(item.requirement_id, []).append(item)

    graphs: list[ProofGraph] = []
    for persisted_set in requirements.sets:
        if not persisted_set.requirements:
            continue

        requirement_ids = {item.id for item in persisted_set.requirements}
        set_bindings = sorted(
            (
                binding
                for requirement_id in requirement_ids
                for binding in evidence_by_requirement.get(requirement_id, [])
            ),
            key=lambda item: (
                item.requirement_id,
                "" if item.subject_ref is None else item.subject_ref,
                item.id,
            ),
        )

        source_by_id: dict[str, EvidenceSource] = {}
        graph_evidence: list[Evidence] = []
        for binding in set_bindings:
            source_id, source = _source_identity(binding)
            source_by_id[source_id] = source
            graph_evidence.append(
                Evidence(
                    id=binding.id,
                    kind=_evidence_kind(binding),
                    property_name=binding.property_name,
                    value=copy.deepcopy(binding.value),
                    unit=binding.unit,
                    source_id=source_id,
                    version=binding.project_revision or binding.source_revision,
                    subject_ref=binding.subject_ref,
                    provenance=(
                        ProvenanceRecord(
                            id=f"provenance:project-requirements:{binding.id}",
                            source_id=source_id,
                            origin=binding.evidence_locator or binding.property_name,
                            cleanroomx_entity_id=binding.subject_ref,
                            originating_calculation=binding.calculation_source,
                            method="project_requirement_verification_binding",
                        ),
                    ),
                )
            )

        graph_evidence.sort(key=lambda item: item.id)
        graph_evidence_by_id = {item.id: item for item in graph_evidence}

        graph_requirements = tuple(
            Requirement(
                id=requirement.id,
                title=requirement.title,
                source=requirement.source,
                reference=requirement.reference,
                scope=requirement.scope,
                criteria=_requirement_criteria(requirement),
            )
            for requirement in persisted_set.requirements
        )
        requirement_set = RequirementSet(
            id=persisted_set.id,
            version=persisted_set.source_revision,
            title=persisted_set.title,
            source=persisted_set.source,
            requirements=graph_requirements,
        )

        checks: list[ComplianceCheck] = []
        findings: list[ComplianceFinding] = []
        verdicts: list[ComplianceVerdict] = []
        source_finding_metadata: list[dict] = []

        for requirement in persisted_set.requirements:
            subjects: tuple[str | None, ...] = (
                tuple(requirement.scope) if requirement.scope else (None,)
            )
            for subject_ref in subjects:
                source_finding = source_findings[
                    _binding_key(requirement.id, subject_ref)
                ]
                binding_identity = _canonical_sha256(
                    {
                        "requirement_id": requirement.id,
                        "subject_ref": subject_ref,
                    }
                )
                check_id = f"check:project-requirement:{binding_identity}"
                finding_id = f"finding:project-requirement:{binding_identity}"
                verdict_id = f"verdict:project-requirement:{binding_identity}"
                evidence_ids = tuple(
                    evidence_id
                    for evidence_id in source_finding["evidence_ids"]
                    if evidence_id in graph_evidence_by_id
                )
                graph_status = _proofgraph_status(
                    source_finding["state"],
                    source_finding["status"],
                )
                required_kinds = _check_required_kinds(
                    requirement,
                    evidence_ids,
                    graph_evidence_by_id,
                )
                reason = (
                    f"Canonical project-requirement state "
                    f"{source_finding['state']!r}: "
                    f"{source_finding['explanation']}"
                )

                checks.append(
                    ComplianceCheck(
                        id=check_id,
                        requirement_id=requirement.id,
                        evidence_ids=evidence_ids,
                        required_evidence_kinds=required_kinds,
                    )
                )
                findings.append(
                    ComplianceFinding(
                        id=finding_id,
                        check_id=check_id,
                        requirement_id=requirement.id,
                        status=graph_status,
                        reason=reason,
                        evidence_ids=evidence_ids,
                        evidence_present=bool(evidence_ids),
                        expected=copy.deepcopy(source_finding["criterion"]),
                        actual=copy.deepcopy(source_finding["actual"]),
                        unit=source_finding["unit"],
                        delta=source_finding["delta"],
                    )
                )
                verdicts.append(
                    ComplianceVerdict(
                        id=verdict_id,
                        requirement_id=requirement.id,
                        status=graph_status,
                        finding_ids=(finding_id,),
                        reason=reason,
                    )
                )
                source_finding_metadata.append(
                    {
                        "requirement_id": requirement.id,
                        "subject_ref": subject_ref,
                        "state": source_finding["state"],
                        "status": source_finding["status"],
                        "included": source_finding["included"],
                        "evidence_ids": list(source_finding["evidence_ids"]),
                    }
                )

        input_sha256 = _canonical_sha256(
            {
                "requirements_sha256": result["requirements_sha256"],
                "evidence_sha256": result["evidence_sha256"],
                "verification_sha256": result["verification_sha256"],
                "requirement_set_id": persisted_set.id,
            }
        )
        run = VerificationRun(
            id=f"verification:project-requirements:{input_sha256}",
            requirement_set_id=requirement_set.id,
            check_ids=tuple(item.id for item in checks),
            verdict_ids=tuple(item.id for item in verdicts),
            input_sha256=input_sha256,
            metadata={
                "adapter": "project_requirements_verification",
                "project_verification_status": result["status"],
                "project_verification_complete": result["complete"],
                "project_verified": result["verified"],
                "project_no_failures_detected": result["no_failures_detected"],
                "requirements_sha256": result["requirements_sha256"],
                "evidence_sha256": result["evidence_sha256"],
                "verification_sha256": result["verification_sha256"],
                "source_findings": source_finding_metadata,
            },
        )
        graphs.append(
            ProofGraph(
                id=(
                    "proofgraph:project-requirements:"
                    f"{persisted_set.id}:{input_sha256}"
                ),
                requirement_set=requirement_set,
                evidence_sources=tuple(
                    source_by_id[source_id] for source_id in sorted(source_by_id)
                ),
                evidence=tuple(graph_evidence),
                checks=tuple(checks),
                findings=tuple(findings),
                verdicts=tuple(verdicts),
                verification_runs=(run,),
            )
        )

    return tuple(graphs)
