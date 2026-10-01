from __future__ import annotations

import copy
from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
from pathlib import Path
from typing import Any

from . import __version__
from .application import (
    analysis_external_dependency_references,
    verify_analysis_run_bundle,
)
from .project import (
    ProjectFileRevision,
    load_project_document_with_revision_info,
    save_project_document_guarded,
)
from .project_requirement_evidence_mappings import (
    PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY,
    project_requirement_evidence_mappings_from_dict,
)
from .project_requirement_verification import (
    RequirementEvidence,
    verify_project_requirements,
)
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    project_requirements_from_dict,
)
from .project_requirements_workflow import (
    ProjectRequirementsWorkflowRun,
    verify_project_requirements_workflow_run,
)
from .proofgraph_project_requirements import (
    proofgraphs_from_project_requirements_verification,
)
from .verification_run_history import (
    append_project_verification_run_record,
    verification_run_identity_sha256,
)


class ProjectVerificationPersistenceError(RuntimeError):
    """Raised when a project verification run cannot be persisted safely."""


_EVIDENCE_FIELDS = frozenset(
    {
        "id",
        "requirement_id",
        "subject_ref",
        "property_name",
        "value",
        "unit",
        "source",
        "source_revision",
        "calculation_source",
        "evidence_locator",
        "project_revision",
        "evidence_kinds",
        "freshness",
    }
)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectVerificationPersistenceError(
            "verification persistence requires strict JSON values"
        ) from exc


def _same_json(left: Any, right: Any) -> bool:
    return _canonical_bytes(left) == _canonical_bytes(right)


def _evidence_from_dict(data: Any, index: int) -> RequirementEvidence:
    if not isinstance(data, dict):
        raise ProjectVerificationPersistenceError(
            f"workflow evidence[{index}] must be an object"
        )
    if set(data) != _EVIDENCE_FIELDS:
        raise ProjectVerificationPersistenceError(
            f"workflow evidence[{index}] does not have the canonical evidence fields"
        )
    try:
        return RequirementEvidence(
            id=data["id"],
            requirement_id=data["requirement_id"],
            subject_ref=data["subject_ref"],
            property_name=data["property_name"],
            value=copy.deepcopy(data["value"]),
            unit=data["unit"],
            source=data["source"],
            source_revision=data["source_revision"],
            calculation_source=data["calculation_source"],
            evidence_locator=data["evidence_locator"],
            project_revision=data["project_revision"],
            evidence_kinds=tuple(data["evidence_kinds"]),
            freshness=data["freshness"],
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ProjectVerificationPersistenceError(
            f"workflow evidence[{index}] is invalid: {exc}"
        ) from exc


def _external_dependency_fingerprints(
    provenance: dict[str, Any],
    *,
    analysis_kind: str,
    analysis_input: dict[str, Any],
) -> list[dict[str, Any]]:
    references = analysis_external_dependency_references(
        analysis_kind,
        analysis_input,
    )
    raw = provenance.get("external_dependencies")
    if not isinstance(raw, list) or len(raw) != len(references):
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance external dependencies are incomplete"
        )
    if provenance.get("external_dependency_count") != len(references):
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance dependency count is inconsistent"
        )
    if references and provenance.get("external_dependencies_stable") is not True:
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance reports unstable external dependencies"
        )

    normalized: list[dict[str, Any]] = []
    for index, ((field, declared_path), item) in enumerate(zip(references, raw)):
        if not isinstance(item, dict):
            raise ProjectVerificationPersistenceError(
                f"workflow external dependency[{index}] is invalid"
            )
        if item.get("field") != field or item.get("declared_path") != declared_path:
            raise ProjectVerificationPersistenceError(
                "workflow external dependency identity does not match analysis input"
            )
        if item.get("stable_during_run") is not True:
            raise ProjectVerificationPersistenceError(
                f"workflow external dependency {field!r} was unstable during execution"
            )

        digest = item.get("execution_snapshot_sha256")
        size_bytes = item.get("execution_snapshot_size_bytes")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ProjectVerificationPersistenceError(
                f"workflow external dependency {field!r} lacks a valid content digest"
            )
        if type(size_bytes) is not int or size_bytes < 0:
            raise ProjectVerificationPersistenceError(
                f"workflow external dependency {field!r} lacks a valid byte size"
            )
        if (
            item.get("sha256_before") != digest
            or item.get("sha256_after") != digest
            or item.get("size_bytes_before") != size_bytes
            or item.get("size_bytes_after") != size_bytes
        ):
            raise ProjectVerificationPersistenceError(
                f"workflow external dependency {field!r} content identity is inconsistent"
            )
        normalized.append(
            {
                "field": field,
                "declared_path": declared_path,
                "sha256": digest,
                "size_bytes": size_bytes,
            }
        )
    return sorted(
        normalized,
        key=lambda item: (item["field"], item["declared_path"]),
    )


def _verifier_implementation_identity() -> dict[str, str]:
    try:
        source = inspect.getsource(verify_project_requirements)
    except (OSError, TypeError) as exc:
        raise ProjectVerificationPersistenceError(
            "canonical verifier source identity could not be captured"
        ) from exc
    return {
        "module": verify_project_requirements.__module__,
        "qualname": verify_project_requirements.__qualname__,
        "source_canonicalization": "python-inspect-source-utf8-v1",
        "source_sha256": sha256(source.encode("utf-8")).hexdigest(),
    }


@dataclass(frozen=True, kw_only=True)
class PersistedProjectVerificationRun:
    record: dict[str, Any]
    committed_project_revision: ProjectFileRevision

    def to_dict(self) -> dict[str, Any]:
        return {
            "record": copy.deepcopy(self.record),
            "committed_project_revision": {
                "path": self.committed_project_revision.path,
                "exists": self.committed_project_revision.exists,
                "size": self.committed_project_revision.size,
                "mtime_ns": self.committed_project_revision.mtime_ns,
                "sha256": self.committed_project_revision.sha256,
            },
        }


def persist_project_requirements_workflow_run(
    path: str | Path,
    workflow: ProjectRequirementsWorkflowRun,
    *,
    completed_at_utc: str | None = None,
    history_limit: int = 50,
    history_max_bytes: int = 16 * 1024 * 1024,
) -> PersistedProjectVerificationRun:
    """Persist one already-completed canonical workflow into project history.

    The project must still be byte-for-byte the source revision used for the
    workflow. The guarded save appends historical evidence without mutating the
    historical verdict itself.
    """
    verified_workflow = verify_project_requirements_workflow_run(workflow)

    source = Path(path).expanduser().resolve(strict=False)
    project, revision, _migration = load_project_document_with_revision_info(source)
    if (
        not revision.exists
        or revision.sha256 is None
        or revision.sha256 != workflow.source_revision
    ):
        raise ProjectVerificationPersistenceError(
            "project changed after verification; refusing to attach the workflow "
            "to a different project revision"
        )
    if project.name != workflow.project_name:
        raise ProjectVerificationPersistenceError(
            "workflow project name does not match the saved source project"
        )

    try:
        analysis = project.analysis_by_id(workflow.analysis_id)
    except KeyError as exc:
        raise ProjectVerificationPersistenceError(
            "workflow analysis no longer exists in the source project"
        ) from exc
    if (
        analysis.name != workflow.analysis_name
        or analysis.kind != workflow.analysis_kind
    ):
        raise ProjectVerificationPersistenceError(
            "workflow analysis identity does not match the source project"
        )

    raw_requirements = project.metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    raw_mappings = project.metadata.get(
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY
    )
    if raw_requirements is None or raw_mappings is None:
        raise ProjectVerificationPersistenceError(
            "source project is missing persisted requirements or evidence mappings"
        )
    try:
        requirements = project_requirements_from_dict(raw_requirements)
        mappings = project_requirement_evidence_mappings_from_dict(raw_mappings)
    except ValueError as exc:
        raise ProjectVerificationPersistenceError(
            f"source project verification metadata is invalid: {exc}"
        ) from exc

    if requirements.sha256 != workflow.requirements_sha256:
        raise ProjectVerificationPersistenceError(
            "workflow requirements digest does not match the source project"
        )
    if mappings.sha256 != workflow.mappings_sha256:
        raise ProjectVerificationPersistenceError(
            "workflow mapping digest does not match the source project"
        )
    active_mapping_ids = tuple(
        item.id for item in mappings.for_analysis(analysis.id, active_only=True)
    )
    if active_mapping_ids != workflow.mapping_ids:
        raise ProjectVerificationPersistenceError(
            "workflow active mapping identities do not match the source project"
        )

    evidence_objects = tuple(
        _evidence_from_dict(item, index)
        for index, item in enumerate(workflow.evidence)
    )
    canonical_verification = verify_project_requirements(
        requirements,
        evidence_objects,
    )
    if not _same_json(canonical_verification, workflow.verification):
        raise ProjectVerificationPersistenceError(
            "workflow verification no longer matches the canonical verifier"
        )

    canonical_graphs = tuple(
        graph.to_dict()
        for graph in proofgraphs_from_project_requirements_verification(
            requirements,
            evidence_objects,
        )
    )
    if not _same_json(list(canonical_graphs), list(workflow.proofgraphs)):
        raise ProjectVerificationPersistenceError(
            "workflow ProofGraph projection does not match canonical verification"
        )

    verified_bundle = verify_analysis_run_bundle(copy.deepcopy(workflow.run_bundle))
    provenance = workflow.run_bundle.get("diagnostics", {}).get(
        "application_execution_provenance"
    )
    if not isinstance(provenance, dict):
        raise ProjectVerificationPersistenceError(
            "workflow analysis run is missing execution provenance"
        )
    if provenance.get("project_source_revision") != workflow.source_revision:
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance is not bound to the source project"
        )
    runtime_environment = provenance.get("runtime_environment")
    code_revision = provenance.get("code_revision")
    cleanroomx_version = provenance.get("cleanroomx_version")
    input_sha256 = provenance.get("input_sha256")
    if not isinstance(runtime_environment, dict) or not isinstance(code_revision, dict):
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance lacks runtime/code identity"
        )
    if not isinstance(cleanroomx_version, str) or not cleanroomx_version:
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance lacks CleanroomX version"
        )
    if cleanroomx_version != __version__:
        raise ProjectVerificationPersistenceError(
            "workflow was produced by a different CleanroomX version"
        )
    if not isinstance(input_sha256, str):
        raise ProjectVerificationPersistenceError(
            "workflow execution provenance lacks analysis input identity"
        )

    proofgraph_sha256 = sorted(
        document["graph_sha256"] for document in canonical_graphs
    )
    external_dependencies = _external_dependency_fingerprints(
        provenance,
        analysis_kind=analysis.kind,
        analysis_input=analysis.input,
    )
    body: dict[str, Any] = {
        "record_schema_version": 2,
        "external_dependencies": external_dependencies,
        "project_source_revision": workflow.source_revision,
        "analysis_id": workflow.analysis_id,
        "analysis_name": workflow.analysis_name,
        "analysis_kind": workflow.analysis_kind,
        "analysis_bundle_sha256": verified_bundle["bundle_sha256"],
        "analysis_input_sha256": input_sha256,
        "requirements_sha256": workflow.requirements_sha256,
        "mappings_sha256": workflow.mappings_sha256,
        "mapping_ids": sorted(workflow.mapping_ids),
        "evidence_sha256": canonical_verification["evidence_sha256"],
        "evidence": copy.deepcopy(list(workflow.evidence)),
        "verification_sha256": canonical_verification["verification_sha256"],
        "verification": copy.deepcopy(canonical_verification),
        "proofgraph_sha256": proofgraph_sha256,
        "workflow_sha256": verified_workflow["workflow_sha256"],
        "verifier_implementation": _verifier_implementation_identity(),
        "cleanroomx_version": cleanroomx_version,
        "runtime_environment": copy.deepcopy(runtime_environment),
        "code_revision": copy.deepcopy(code_revision),
    }
    body["verification_identity_sha256"] = verification_run_identity_sha256(body)

    record = append_project_verification_run_record(
        project.metadata,
        body,
        completed_at_utc=completed_at_utc,
        limit=history_limit,
        max_bytes=history_max_bytes,
    )
    _saved_path, committed_revision = save_project_document_guarded(
        source,
        project,
        expected_revision=revision,
    )
    if not committed_revision.exists or committed_revision.sha256 is None:
        raise ProjectVerificationPersistenceError(
            "persisted project revision could not be verified after guarded save"
        )
    return PersistedProjectVerificationRun(
        record=copy.deepcopy(record),
        committed_project_revision=committed_revision,
    )
