from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .application import run_analysis, verify_analysis_run_bundle
from .project import (
    ProjectFileRevision,
    capture_project_file_revision,
    load_project_document_with_revision_info,
    project_file_revision_matches,
)
from .project_requirement_analysis_evidence import (
    AnalysisRequirementEvidenceMapping,
    bind_analysis_run_requirement_evidence,
)
from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    ProjectRequirementEvidenceMapping,
    ProjectRequirementEvidenceMappings,
    project_requirement_evidence_mappings_from_dict,
)
from .project_requirement_verification import verify_project_requirements
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    ProjectRequirements,
    project_requirements_from_dict,
)
from .proofgraph_io import proofgraph_from_dict
from .proofgraph_models import EVIDENCE_KINDS
from .proofgraph_project_requirements import (
    proofgraphs_from_project_requirements_verification,
)


PROJECT_REQUIREMENTS_WORKFLOW_SCHEMA = "cleanroomx.project-requirements-workflow"
PROJECT_REQUIREMENTS_WORKFLOW_SCHEMA_VERSION = 1


class ProjectRequirementsWorkflowError(RuntimeError):
    """Raised when project-native requirements execution cannot be trusted."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_source_revision(
    revision: ProjectFileRevision,
) -> str:
    if not revision.exists or revision.sha256 is None:
        raise ProjectRequirementsWorkflowError(
            "project-native requirements workflow requires a saved project file"
        )
    return revision.sha256


def _assert_source_revision_unchanged(
    source: Path,
    expected: ProjectFileRevision,
    *,
    stage: str,
) -> None:
    try:
        current = capture_project_file_revision(source)
    except OSError as exc:
        raise ProjectRequirementsWorkflowError(
            f"project source could not be verified {stage}: {exc}"
        ) from exc
    if not project_file_revision_matches(expected, current):
        raise ProjectRequirementsWorkflowError(
            f"project source changed {stage}; requirements verification was not issued"
        )


def _project_requirements(metadata: dict[str, Any]) -> ProjectRequirements:
    raw = metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    if raw is None:
        raise ProjectRequirementsWorkflowError(
            "project has no persisted requirements registry"
        )
    try:
        return project_requirements_from_dict(raw)
    except ValueError as exc:
        raise ProjectRequirementsWorkflowError(
            f"project requirements registry is invalid: {exc}"
        ) from exc


def _project_mappings(
    metadata: dict[str, Any],
) -> ProjectRequirementEvidenceMappings:
    raw = metadata.get(PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY)
    if raw is None:
        raise ProjectRequirementsWorkflowError(
            "project has no persisted requirement evidence mappings registry"
        )
    try:
        return project_requirement_evidence_mappings_from_dict(raw)
    except ValueError as exc:
        raise ProjectRequirementsWorkflowError(
            f"project requirement evidence mappings registry is invalid: {exc}"
        ) from exc


def _runtime_mapping(
    persisted: ProjectRequirementEvidenceMapping,
    *,
    actual_analysis_kind: str,
) -> AnalysisRequirementEvidenceMapping:
    if persisted.status != "active":
        raise ProjectRequirementsWorkflowError(
            f"mapping {persisted.id!r} is not active"
        )
    if persisted.expected_analysis_kind != actual_analysis_kind:
        raise ProjectRequirementsWorkflowError(
            f"mapping {persisted.id!r} expected analysis kind "
            f"{persisted.expected_analysis_kind!r} but selected analysis is "
            f"{actual_analysis_kind!r}"
        )
    return AnalysisRequirementEvidenceMapping(
        id=persisted.id,
        requirement_id=persisted.requirement_id,
        subject_ref=persisted.subject_ref,
        property_name=persisted.property_name,
        result_path=persisted.result_path,
        unit=persisted.unit,
        evidence_kinds=persisted.evidence_kinds,
    )


@dataclass(frozen=True, kw_only=True)
class ProjectRequirementsWorkflowRun:
    project_name: str
    source_path: str
    source_revision: str
    analysis_id: str
    analysis_name: str
    analysis_kind: str
    requirements_sha256: str
    mappings_sha256: str
    mapping_ids: tuple[str, ...]
    run_bundle: dict[str, Any]
    evidence: tuple[dict[str, Any], ...]
    verification: dict[str, Any]
    proofgraphs: tuple[dict[str, Any], ...]
    workflow_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECT_REQUIREMENTS_WORKFLOW_SCHEMA,
            "schema_version": PROJECT_REQUIREMENTS_WORKFLOW_SCHEMA_VERSION,
            "project": {
                "name": self.project_name,
                "source_path": self.source_path,
                "source_revision": self.source_revision,
            },
            "analysis": {
                "id": self.analysis_id,
                "name": self.analysis_name,
                "kind": self.analysis_kind,
                "mapping_ids": list(self.mapping_ids),
            },
            "requirements_sha256": self.requirements_sha256,
            "mappings_sha256": self.mappings_sha256,
            "run": copy.deepcopy(self.run_bundle),
            "evidence": copy.deepcopy(list(self.evidence)),
            "verification": copy.deepcopy(self.verification),
            "proofgraphs": copy.deepcopy(list(self.proofgraphs)),
            "workflow_sha256": self.workflow_sha256,
        }


def run_project_requirements_workflow(
    path: str | Path,
    analysis_id: str,
) -> ProjectRequirementsWorkflowRun:
    """Execute one saved project analysis through canonical requirements verification.

    The saved project is the orchestration boundary. Requirements and explicit
    evidence mappings are loaded from project metadata, the analysis run is bound
    to the exact source-project SHA-256, and no verdict is issued if the project
    source changes during execution.
    """
    source = Path(path).expanduser().resolve(strict=False)
    project, revision, _migration = load_project_document_with_revision_info(source)
    source_revision = _require_source_revision(revision)

    try:
        analysis = project.analysis_by_id(analysis_id)
    except KeyError as exc:
        raise ProjectRequirementsWorkflowError(
            f"unknown project analysis id: {analysis_id!r}"
        ) from exc

    requirements = _project_requirements(project.metadata)
    mappings_registry = _project_mappings(project.metadata)
    persisted_mappings = mappings_registry.for_analysis(
        analysis.id,
        active_only=True,
    )
    if not persisted_mappings:
        raise ProjectRequirementsWorkflowError(
            f"analysis {analysis.id!r} has no active persisted requirement evidence mappings"
        )

    runtime_mappings = tuple(
        _runtime_mapping(item, actual_analysis_kind=analysis.kind)
        for item in persisted_mappings
    )

    _assert_source_revision_unchanged(
        source,
        revision,
        stage="before analysis execution",
    )

    run = run_analysis(
        analysis.kind,
        copy.deepcopy(analysis.input),
        base_dir=source.parent,
        project_source_revision=source_revision,
    )
    run_bundle = run.to_dict()

    _assert_source_revision_unchanged(
        source,
        revision,
        stage="during analysis execution",
    )

    verified_run = verify_analysis_run_bundle(copy.deepcopy(run_bundle))
    if verified_run.get("project_source_revision") != source_revision:
        raise ProjectRequirementsWorkflowError(
            "completed analysis run is not bound to the exact source project revision"
        )

    bindings = bind_analysis_run_requirement_evidence(
        run_bundle,
        runtime_mappings,
        current_analysis_input=copy.deepcopy(analysis.input),
        base_dir=source.parent,
    )
    evidence_documents = tuple(
        item.to_dict()
        for item in sorted(
            bindings,
            key=lambda item: (
                item.requirement_id,
                "" if item.subject_ref is None else item.subject_ref,
                item.id,
            ),
        )
    )
    verification = verify_project_requirements(requirements, bindings)
    if verification["evidence_sha256"] != _canonical_sha256(
        list(evidence_documents)
    ):
        raise ProjectRequirementsWorkflowError(
            "canonical verification evidence digest disagrees with bound evidence"
        )
    proofgraphs = proofgraphs_from_project_requirements_verification(
        requirements,
        bindings,
    )
    proofgraph_documents = tuple(graph.to_dict() for graph in proofgraphs)

    identity = {
        "source_revision": source_revision,
        "analysis_id": analysis.id,
        "analysis_kind": analysis.kind,
        "requirements_sha256": requirements.sha256,
        "mappings_sha256": mappings_registry.sha256,
        "mapping_ids": [item.id for item in persisted_mappings],
        "run_bundle_sha256": verified_run["bundle_sha256"],
        "verification_sha256": verification["verification_sha256"],
        "proofgraph_sha256": [
            document["graph_sha256"] for document in proofgraph_documents
        ],
    }
    workflow_sha256 = _canonical_sha256(identity)

    return ProjectRequirementsWorkflowRun(
        project_name=project.name,
        source_path=str(source),
        source_revision=source_revision,
        analysis_id=analysis.id,
        analysis_name=analysis.name,
        analysis_kind=analysis.kind,
        requirements_sha256=requirements.sha256,
        mappings_sha256=mappings_registry.sha256,
        mapping_ids=tuple(item.id for item in persisted_mappings),
        run_bundle=copy.deepcopy(run_bundle),
        evidence=copy.deepcopy(evidence_documents),
        verification=copy.deepcopy(verification),
        proofgraphs=copy.deepcopy(proofgraph_documents),
        workflow_sha256=workflow_sha256,
    )

def _source_finding_projection(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": finding.get("requirement_id"),
        "subject_ref": finding.get("subject_ref"),
        "state": finding.get("state"),
        "status": finding.get("status"),
        "included": finding.get("included"),
        "evidence_ids": copy.deepcopy(finding.get("evidence_ids", [])),
    }


def _source_finding_sort_key(finding: dict[str, Any]) -> tuple[str, str]:
    requirement_id = finding.get("requirement_id")
    subject_ref = finding.get("subject_ref")
    return (
        "" if requirement_id is None else str(requirement_id),
        "" if subject_ref is None else str(subject_ref),
    )


def _expected_proofgraph_evidence(
    evidence: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_identity = _canonical_sha256(
        {
            "source": evidence.get("source"),
            "source_revision": evidence.get("source_revision"),
        }
    )
    source_id = f"source:project-requirements:{source_identity}"
    kinds = evidence.get("evidence_kinds")
    expected_kind = "declared"
    if (
        isinstance(kinds, list)
        and len(kinds) == 1
        and kinds[0] in EVIDENCE_KINDS
    ):
        expected_kind = kinds[0]
    expected_source = {
        "id": source_id,
        "kind": "project_requirement_evidence",
        "reference": evidence.get("source"),
        "revision": evidence.get("source_revision"),
    }
    expected_evidence = {
        "id": evidence.get("id"),
        "kind": expected_kind,
        "property_name": evidence.get("property_name"),
        "value": copy.deepcopy(evidence.get("value")),
        "unit": evidence.get("unit"),
        "source_id": source_id,
        "version": evidence.get("project_revision")
        or evidence.get("source_revision"),
        "timestamp": None,
        "project_id": None,
        "subject_ref": evidence.get("subject_ref"),
        "provenance": [
            {
                "id": f"provenance:project-requirements:{evidence.get('id')}",
                "source_id": source_id,
                "origin": evidence.get("evidence_locator")
                or evidence.get("property_name"),
                "upstream_evidence_ids": [],
                "ifc_global_id": None,
                "cleanroomx_entity_id": evidence.get("subject_ref"),
                "originating_file": None,
                "originating_calculation": evidence.get("calculation_source"),
                "method": "project_requirement_verification_binding",
            }
        ],
        "confidence": None,
    }
    return expected_source, expected_evidence


def _proofgraph_status_from_canonical_finding(
    source_state: Any,
    source_status: Any,
) -> str:
    if source_status in {"pass", "fail"}:
        return source_status
    if source_state in {"not_checked", "inactive", "not_applicable"}:
        return "not_checked"
    return "unknown"


def _ordered_graph_source_findings(
    graph,
    canonical_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_binding: dict[tuple[str, str | None], dict[str, Any]] = {}
    graph_requirement_ids = {
        requirement.id for requirement in graph.requirement_set.requirements
    }
    for finding in canonical_findings:
        if not isinstance(finding, dict):
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification findings must contain objects"
            )
        requirement_id = finding.get("requirement_id")
        if requirement_id not in graph_requirement_ids:
            continue
        subject_ref = finding.get("subject_ref")
        if not isinstance(requirement_id, str) or not requirement_id:
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification finding has invalid requirement identity"
            )
        if subject_ref is not None and (
            not isinstance(subject_ref, str) or not subject_ref
        ):
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification finding has invalid subject identity"
            )
        key = (requirement_id, subject_ref)
        if key in by_binding:
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification contains duplicate requirement bindings"
            )
        by_binding[key] = finding

    ordered: list[dict[str, Any]] = []
    for requirement in graph.requirement_set.requirements:
        subjects: tuple[str | None, ...] = (
            tuple(requirement.scope) if requirement.scope else (None,)
        )
        for subject_ref in subjects:
            key = (requirement.id, subject_ref)
            finding = by_binding.get(key)
            if finding is None:
                raise ProjectRequirementsWorkflowError(
                    "workflow ProofGraph requirement scope disagrees with canonical verification"
                )
            ordered.append(finding)

    if len(ordered) != len(by_binding):
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph requirement scope omits canonical verification bindings"
        )
    return ordered


def _verify_graph_requirement_projection(
    graph,
    ordered_findings: list[dict[str, Any]],
) -> None:
    findings_by_requirement: dict[str, list[dict[str, Any]]] = {}
    for finding in ordered_findings:
        findings_by_requirement.setdefault(
            finding["requirement_id"],
            [],
        ).append(finding)

    for requirement in graph.requirement_set.requirements:
        source_findings = findings_by_requirement.get(requirement.id, [])
        if not source_findings:
            raise ProjectRequirementsWorkflowError(
                f"workflow ProofGraph requirement {requirement.id!r} has no canonical finding"
            )
        first = source_findings[0]
        expected_fields = {
            "title": first.get("requirement_title"),
            "source": first.get("source"),
            "reference": first.get("reference"),
        }
        for field_name, expected in expected_fields.items():
            if getattr(requirement, field_name) != expected:
                raise ProjectRequirementsWorkflowError(
                    f"workflow ProofGraph requirement {requirement.id!r} "
                    f"{field_name} disagrees with canonical verification"
                )

        expected_criteria = {
            "discipline": first.get("discipline"),
            "category": first.get("category"),
            "source_revision": first.get("source_revision"),
            "unit": first.get("unit"),
            "criterion": copy.deepcopy(first.get("criterion")),
            "lifecycle_status": first.get("requirement_status"),
            "required_evidence": copy.deepcopy(first.get("required_evidence")),
        }
        for field_name, expected in expected_criteria.items():
            if requirement.criteria.get(field_name) != expected:
                raise ProjectRequirementsWorkflowError(
                    f"workflow ProofGraph requirement {requirement.id!r} criteria "
                    f"{field_name!r} disagrees with canonical verification"
                )

        for finding in source_findings[1:]:
            comparison = {
                "requirement_title": requirement.title,
                "source": requirement.source,
                "reference": requirement.reference,
                "discipline": requirement.criteria.get("discipline"),
                "category": requirement.criteria.get("category"),
                "source_revision": requirement.criteria.get("source_revision"),
                "unit": requirement.criteria.get("unit"),
                "criterion": requirement.criteria.get("criterion"),
                "requirement_status": requirement.criteria.get("lifecycle_status"),
                "required_evidence": requirement.criteria.get("required_evidence"),
            }
            for field_name, actual in comparison.items():
                if finding.get(field_name) != actual:
                    raise ProjectRequirementsWorkflowError(
                        f"workflow canonical verification metadata for requirement "
                        f"{requirement.id!r} is inconsistent across subjects"
                    )


def _expected_required_evidence_kinds(
    finding: dict[str, Any],
    expected_evidence: dict[str, dict[str, Any]],
) -> list[str]:
    required = finding.get("required_evidence")
    if not isinstance(required, list) or any(
        not isinstance(kind, str) or not kind for kind in required
    ):
        raise ProjectRequirementsWorkflowError(
            "workflow canonical verification required_evidence is invalid"
        )
    if not required or any(kind not in EVIDENCE_KINDS for kind in required):
        return []

    raw_evidence_ids = finding.get("evidence_ids")
    if not isinstance(raw_evidence_ids, list) or any(
        not isinstance(evidence_id, str) or not evidence_id
        for evidence_id in raw_evidence_ids
    ):
        raise ProjectRequirementsWorkflowError(
            "workflow canonical verification evidence_ids are invalid"
        )
    represented = {
        expected_evidence[evidence_id]["kind"]
        for evidence_id in raw_evidence_ids
        if evidence_id in expected_evidence
    }
    if not set(required).issubset(represented):
        return []
    return copy.deepcopy(required)


def _verify_workflow_proofgraph_projection(
    graph,
    *,
    evidence_by_id: dict[str, dict[str, Any]],
    verification: dict[str, Any],
    requirements_sha256: str,
    evidence_sha256: str,
    verification_sha256: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if len(graph.verification_runs) != 1:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph must contain exactly one project-requirements verification run"
        )

    canonical_findings = verification.get("findings")
    if not isinstance(canonical_findings, list):
        raise ProjectRequirementsWorkflowError(
            "workflow canonical verification findings must be a list"
        )
    ordered_findings = _ordered_graph_source_findings(
        graph,
        canonical_findings,
    )
    _verify_graph_requirement_projection(graph, ordered_findings)

    graph_requirement_ids = {
        requirement.id for requirement in graph.requirement_set.requirements
    }
    expected_evidence_ids = sorted(
        evidence_id
        for evidence_id, evidence in evidence_by_id.items()
        if evidence.get("requirement_id") in graph_requirement_ids
    )
    actual_evidence_ids = [item.id for item in graph.evidence]
    if actual_evidence_ids != expected_evidence_ids:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph evidence identities disagree with bound workflow evidence"
        )

    expected_sources: dict[str, dict[str, Any]] = {}
    expected_evidence: dict[str, dict[str, Any]] = {}
    for evidence_id in expected_evidence_ids:
        source, projected = _expected_proofgraph_evidence(
            evidence_by_id[evidence_id]
        )
        expected_sources[source["id"]] = source
        expected_evidence[evidence_id] = projected

    actual_evidence = [item.to_dict() for item in graph.evidence]
    expected_evidence_documents = [
        expected_evidence[evidence_id] for evidence_id in expected_evidence_ids
    ]
    if actual_evidence != expected_evidence_documents:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph evidence projection disagrees with bound workflow evidence"
        )

    actual_sources = [source.to_dict() for source in graph.evidence_sources]
    expected_source_documents = [
        expected_sources[source_id] for source_id in sorted(expected_sources)
    ]
    if actual_sources != expected_source_documents:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph evidence sources disagree with bound workflow evidence"
        )

    expected_checks: list[dict[str, Any]] = []
    expected_findings: list[dict[str, Any]] = []
    expected_verdicts: list[dict[str, Any]] = []
    expected_check_ids: list[str] = []
    expected_verdict_ids: list[str] = []
    expected_source_findings: list[dict[str, Any]] = []

    for finding in ordered_findings:
        raw_evidence_ids = finding.get("evidence_ids")
        if not isinstance(raw_evidence_ids, list) or any(
            not isinstance(evidence_id, str) or not evidence_id
            for evidence_id in raw_evidence_ids
        ):
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification evidence_ids are invalid"
            )
        if len(raw_evidence_ids) != len(set(raw_evidence_ids)):
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification evidence_ids contain duplicates"
            )
        missing_evidence = sorted(
            set(raw_evidence_ids) - set(expected_evidence)
        )
        if missing_evidence:
            raise ProjectRequirementsWorkflowError(
                "workflow canonical verification finding references evidence outside "
                "its ProofGraph requirement set: " + ", ".join(missing_evidence)
            )

        binding_identity = _canonical_sha256(
            {
                "requirement_id": finding.get("requirement_id"),
                "subject_ref": finding.get("subject_ref"),
            }
        )
        check_id = f"check:project-requirement:{binding_identity}"
        finding_id = f"finding:project-requirement:{binding_identity}"
        verdict_id = f"verdict:project-requirement:{binding_identity}"
        graph_status = _proofgraph_status_from_canonical_finding(
            finding.get("state"),
            finding.get("status"),
        )
        reason = (
            "Canonical project-requirement state "
            f"{finding.get('state')!r}: {finding.get('explanation')}"
        )
        expected_checks.append(
            {
                "id": check_id,
                "requirement_id": finding.get("requirement_id"),
                "evidence_ids": copy.deepcopy(raw_evidence_ids),
                "required_evidence_kinds": _expected_required_evidence_kinds(
                    finding,
                    expected_evidence,
                ),
            }
        )
        expected_findings.append(
            {
                "id": finding_id,
                "check_id": check_id,
                "requirement_id": finding.get("requirement_id"),
                "status": graph_status,
                "reason": reason,
                "evidence_ids": copy.deepcopy(raw_evidence_ids),
                "evidence_present": bool(raw_evidence_ids),
                "expected": copy.deepcopy(finding.get("criterion")),
                "actual": copy.deepcopy(finding.get("actual")),
                "unit": finding.get("unit"),
                "delta": finding.get("delta"),
            }
        )
        expected_verdicts.append(
            {
                "id": verdict_id,
                "requirement_id": finding.get("requirement_id"),
                "status": graph_status,
                "finding_ids": [finding_id],
                "reason": reason,
                "confidence": None,
            }
        )
        expected_check_ids.append(check_id)
        expected_verdict_ids.append(verdict_id)
        expected_source_findings.append(_source_finding_projection(finding))

    if [item.to_dict() for item in graph.checks] != expected_checks:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph checks disagree with canonical verification"
        )
    if [item.to_dict() for item in graph.findings] != expected_findings:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph findings disagree with canonical verification"
        )
    if [item.to_dict() for item in graph.verdicts] != expected_verdicts:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph verdicts disagree with canonical verification"
        )
    if graph.corrective_actions:
        raise ProjectRequirementsWorkflowError(
            "project-requirements ProofGraph must not contain corrective actions"
        )

    input_sha256 = _canonical_sha256(
        {
            "requirements_sha256": requirements_sha256,
            "evidence_sha256": evidence_sha256,
            "verification_sha256": verification_sha256,
            "requirement_set_id": graph.requirement_set.id,
        }
    )
    expected_metadata = {
        "adapter": "project_requirements_verification",
        "project_verification_status": verification.get("status"),
        "project_verification_complete": verification.get("complete"),
        "project_verified": verification.get("verified"),
        "project_no_failures_detected": verification.get(
            "no_failures_detected"
        ),
        "requirements_sha256": requirements_sha256,
        "evidence_sha256": evidence_sha256,
        "verification_sha256": verification_sha256,
        "source_findings": expected_source_findings,
    }
    expected_run = {
        "id": f"verification:project-requirements:{input_sha256}",
        "requirement_set_id": graph.requirement_set.id,
        "check_ids": expected_check_ids,
        "verdict_ids": expected_verdict_ids,
        "timestamp": None,
        "input_sha256": input_sha256,
        "metadata": expected_metadata,
    }
    run = graph.verification_runs[0]
    if run.to_dict() != expected_run:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph verification run disagrees with canonical projection"
        )

    expected_graph_id = (
        "proofgraph:project-requirements:"
        f"{graph.requirement_set.id}:{input_sha256}"
    )
    if graph.id != expected_graph_id:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph identity disagrees with canonical projection"
        )

    return (
        tuple(requirement.id for requirement in graph.requirement_set.requirements),
        tuple(actual_evidence_ids),
    )


def verify_project_requirements_workflow_run(
    workflow: ProjectRequirementsWorkflowRun,
) -> dict[str, Any]:
    """Verify the integrity-linked components of one workflow result."""
    if not isinstance(workflow, ProjectRequirementsWorkflowRun):
        raise TypeError("workflow must be a ProjectRequirementsWorkflowRun")

    source_revision = _require_source_revision(
        ProjectFileRevision(
            path=workflow.source_path,
            exists=True,
            size=None,
            mtime_ns=None,
            sha256=workflow.source_revision,
        )
    )
    verified_run = verify_analysis_run_bundle(copy.deepcopy(workflow.run_bundle))
    bundle_sha256 = verified_run.get("bundle_sha256")
    if not isinstance(bundle_sha256, str):
        raise ProjectRequirementsWorkflowError(
            "workflow analysis bundle is missing verified integrity identity"
        )
    if verified_run.get("project_source_revision") != source_revision:
        raise ProjectRequirementsWorkflowError(
            "workflow analysis bundle project revision does not match workflow source"
        )

    evidence_documents = copy.deepcopy(list(workflow.evidence))
    try:
        evidence_sha256 = _canonical_sha256(evidence_documents)
    except (TypeError, ValueError) as exc:
        raise ProjectRequirementsWorkflowError(
            "workflow evidence is not strict canonical JSON"
        ) from exc
    verification = copy.deepcopy(workflow.verification)
    if not isinstance(verification, dict):
        raise ProjectRequirementsWorkflowError(
            "workflow verification must be an object"
        )
    if verification.get("requirements_sha256") != workflow.requirements_sha256:
        raise ProjectRequirementsWorkflowError(
            "workflow requirements digest disagrees with canonical verification"
        )
    if verification.get("evidence_sha256") != evidence_sha256:
        raise ProjectRequirementsWorkflowError(
            "workflow evidence digest disagrees with canonical verification"
        )
    verification_sha256 = verification.get("verification_sha256")
    unsigned_verification = {
        key: value
        for key, value in verification.items()
        if key != "verification_sha256"
    }
    if (
        not isinstance(verification_sha256, str)
        or verification_sha256 != _canonical_sha256(unsigned_verification)
    ):
        raise ProjectRequirementsWorkflowError(
            "workflow canonical verification digest is invalid"
        )

    mapping_ids = tuple(workflow.mapping_ids)
    if len(mapping_ids) != len(set(mapping_ids)):
        raise ProjectRequirementsWorkflowError(
            "workflow mapping ids contain duplicates"
        )
    evidence_ids: list[str] = []
    for index, evidence in enumerate(evidence_documents):
        if not isinstance(evidence, dict):
            raise ProjectRequirementsWorkflowError(
                f"workflow evidence[{index}] must be an object"
            )
        evidence_id = evidence.get("id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ProjectRequirementsWorkflowError(
                f"workflow evidence[{index}].id must be a non-empty string"
            )
        evidence_ids.append(evidence_id)
        if evidence.get("source_revision") != bundle_sha256:
            raise ProjectRequirementsWorkflowError(
                f"workflow evidence {evidence_id!r} is not bound to the verified analysis bundle"
            )
        if evidence.get("project_revision") != source_revision:
            raise ProjectRequirementsWorkflowError(
                f"workflow evidence {evidence_id!r} project revision does not match workflow source"
            )
        locator = evidence.get("evidence_locator")
        if not isinstance(locator, str) or not locator.startswith("/result/"):
            raise ProjectRequirementsWorkflowError(
                f"workflow evidence {evidence_id!r} lacks an exact result locator"
            )
    if sorted(evidence_ids) != sorted(mapping_ids):
        raise ProjectRequirementsWorkflowError(
            "workflow evidence identities do not match active persisted mapping identities"
        )
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ProjectRequirementsWorkflowError(
            "workflow evidence contains duplicate identities"
        )
    evidence_by_id = {
        evidence["id"]: evidence
        for evidence in evidence_documents
    }

    canonical_findings = verification.get("findings")
    if not isinstance(canonical_findings, list) or any(
        not isinstance(finding, dict) for finding in canonical_findings
    ):
        raise ProjectRequirementsWorkflowError(
            "workflow canonical verification findings must be an array of objects"
        )
    canonical_requirement_ids = {
        finding.get("requirement_id") for finding in canonical_findings
    }
    if None in canonical_requirement_ids or any(
        not isinstance(requirement_id, str) or not requirement_id
        for requirement_id in canonical_requirement_ids
    ):
        raise ProjectRequirementsWorkflowError(
            "workflow canonical verification contains invalid requirement identities"
        )

    proofgraph_sha256: list[str] = []
    projected_requirement_ids: list[str] = []
    projected_evidence_ids: list[str] = []
    for document in workflow.proofgraphs:
        if not isinstance(document, dict):
            raise ProjectRequirementsWorkflowError(
                "workflow ProofGraph documents must be objects"
            )
        try:
            graph = proofgraph_from_dict(copy.deepcopy(document))
        except ValueError as exc:
            raise ProjectRequirementsWorkflowError(
                f"workflow ProofGraph integrity validation failed: {exc}"
            ) from exc
        requirement_ids, graph_evidence_ids = _verify_workflow_proofgraph_projection(
            graph,
            evidence_by_id=evidence_by_id,
            verification=verification,
            requirements_sha256=workflow.requirements_sha256,
            evidence_sha256=evidence_sha256,
            verification_sha256=verification_sha256,
        )
        projected_requirement_ids.extend(requirement_ids)
        projected_evidence_ids.extend(graph_evidence_ids)
        proofgraph_sha256.append(graph.to_dict()["graph_sha256"])

    if len(projected_requirement_ids) != len(set(projected_requirement_ids)):
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraphs contain duplicate requirement identities across graphs"
        )
    if set(projected_requirement_ids) != canonical_requirement_ids:
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph requirement coverage disagrees with canonical verification"
        )
    if sorted(projected_evidence_ids) != sorted(evidence_ids):
        raise ProjectRequirementsWorkflowError(
            "workflow ProofGraph evidence coverage disagrees with bound workflow evidence"
        )

    identity = {
        "source_revision": source_revision,
        "analysis_id": workflow.analysis_id,
        "analysis_kind": workflow.analysis_kind,
        "requirements_sha256": workflow.requirements_sha256,
        "mappings_sha256": workflow.mappings_sha256,
        "mapping_ids": list(mapping_ids),
        "run_bundle_sha256": bundle_sha256,
        "verification_sha256": verification_sha256,
        "proofgraph_sha256": proofgraph_sha256,
    }
    expected_workflow_sha256 = _canonical_sha256(identity)
    if workflow.workflow_sha256 != expected_workflow_sha256:
        raise ProjectRequirementsWorkflowError(
            "workflow identity digest does not match its verified components"
        )
    return {
        "project_source_revision": source_revision,
        "analysis_bundle_sha256": bundle_sha256,
        "evidence_sha256": evidence_sha256,
        "verification_sha256": verification_sha256,
        "proofgraph_sha256": tuple(proofgraph_sha256),
        "workflow_sha256": expected_workflow_sha256,
    }

