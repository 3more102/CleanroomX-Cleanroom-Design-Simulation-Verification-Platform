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
    verification = verify_project_requirements(requirements, bindings)
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
        verification=copy.deepcopy(verification),
        proofgraphs=copy.deepcopy(proofgraph_documents),
        workflow_sha256=workflow_sha256,
    )
