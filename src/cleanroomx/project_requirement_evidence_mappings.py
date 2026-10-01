from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Iterable

from .project_requirement_verification import RequirementEvidenceAuthority
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    ProjectRequirementsFormatError,
    project_requirements_from_dict,
)


PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY = "requirement_evidence_mappings"
PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA = (
    "cleanroomx.project-requirement-evidence-mappings"
)
PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION = 1
PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION = 2
SUPPORTED_PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSIONS = frozenset(
    {
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION,
        PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION,
    }
)
MAPPING_STATUSES = frozenset({"active", "disabled", "superseded"})


class ProjectRequirementEvidenceMappingsFormatError(ValueError):
    """Raised when persisted requirement-to-analysis mappings are invalid."""


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must be an array of non-empty strings"
        )
    normalized = tuple(
        _nonempty(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must not contain duplicates"
        )
    return tuple(sorted(normalized))


def _path_tuple(value: Any, field_name: str) -> tuple[str | int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must be an array of object keys/list indexes"
        )
    normalized: list[str | int] = []
    for index, token in enumerate(value):
        token_field = f"{field_name}[{index}]"
        if isinstance(token, bool):
            raise ProjectRequirementEvidenceMappingsFormatError(
                f"{token_field} must be an object key or non-negative list index"
            )
        if isinstance(token, int):
            if token < 0:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    f"{token_field} list index must be >= 0"
                )
            normalized.append(token)
            continue
        if isinstance(token, str):
            normalized.append(_nonempty(token, token_field))
            continue
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{token_field} must be an object key or non-negative list index"
        )
    if not normalized:
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must identify a value inside the analysis result"
        )
    return tuple(normalized)


def _reject_unknown(
    data: dict[str, Any],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} contains unsupported field(s): " + ", ".join(unknown)
        )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _check_sha256(value: Any, field_name: str) -> str:
    text = _nonempty(value, field_name)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must be a lowercase SHA-256 hex digest"
        )
    return text


@dataclass(frozen=True, kw_only=True)
class ProjectRequirementEvidenceMapping:
    id: str
    requirement_id: str
    analysis_id: str
    expected_analysis_kind: str
    property_name: str
    result_path: tuple[str | int, ...]
    subject_ref: str | None = None
    unit: str | None = None
    evidence_kinds: tuple[str, ...] = ()
    status: str = "active"
    notes: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "id",
            "requirement_id",
            "analysis_id",
            "expected_analysis_kind",
            "property_name",
        ):
            object.__setattr__(
                self,
                name,
                _nonempty(getattr(self, name), f"requirement_evidence_mapping.{name}"),
            )
        object.__setattr__(
            self,
            "subject_ref",
            _optional_text(
                self.subject_ref,
                "requirement_evidence_mapping.subject_ref",
            ),
        )
        object.__setattr__(
            self,
            "unit",
            _optional_text(self.unit, "requirement_evidence_mapping.unit"),
        )
        object.__setattr__(
            self,
            "notes",
            _optional_text(self.notes, "requirement_evidence_mapping.notes"),
        )
        object.__setattr__(
            self,
            "result_path",
            _path_tuple(
                self.result_path,
                "requirement_evidence_mapping.result_path",
            ),
        )
        object.__setattr__(
            self,
            "evidence_kinds",
            _string_tuple(
                self.evidence_kinds,
                "requirement_evidence_mapping.evidence_kinds",
            ),
        )
        if self.status not in MAPPING_STATUSES:
            raise ProjectRequirementEvidenceMappingsFormatError(
                "requirement_evidence_mapping.status must be one of: "
                + ", ".join(sorted(MAPPING_STATUSES))
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "analysis_id": self.analysis_id,
            "expected_analysis_kind": self.expected_analysis_kind,
            "subject_ref": self.subject_ref,
            "property_name": self.property_name,
            "result_path": list(self.result_path),
            "unit": self.unit,
            "evidence_kinds": list(self.evidence_kinds),
            "status": self.status,
            "notes": self.notes,
        }


@dataclass(frozen=True, kw_only=True)
class ProjectRequirementEvidenceMappings:
    mappings: tuple[ProjectRequirementEvidenceMapping, ...] = field(
        default_factory=tuple
    )
    evidence_authority: tuple[RequirementEvidenceAuthority, ...] = field(
        default_factory=tuple
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mappings, tuple):
            object.__setattr__(self, "mappings", tuple(self.mappings))
        if not all(
            isinstance(item, ProjectRequirementEvidenceMapping)
            for item in self.mappings
        ):
            raise ProjectRequirementEvidenceMappingsFormatError(
                "requirement_evidence_mappings.mappings must contain "
                "ProjectRequirementEvidenceMapping values"
            )
        if not isinstance(self.evidence_authority, tuple):
            object.__setattr__(
                self,
                "evidence_authority",
                tuple(self.evidence_authority),
            )
        if not all(
            isinstance(item, RequirementEvidenceAuthority)
            for item in self.evidence_authority
        ):
            raise ProjectRequirementEvidenceMappingsFormatError(
                "requirement_evidence_mappings.evidence_authority must contain "
                "RequirementEvidenceAuthority values"
            )

        ids = [item.id for item in self.mappings]
        if len(ids) != len(set(ids)):
            raise ProjectRequirementEvidenceMappingsFormatError(
                "requirement evidence mapping ids must be unique across the project"
            )

        authority_by_binding: dict[
            tuple[str, str | None], RequirementEvidenceAuthority
        ] = {}
        for authority in self.evidence_authority:
            key = (authority.requirement_id, authority.subject_ref)
            if key in authority_by_binding:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    "multiple evidence authority records target the same "
                    "requirement/subject binding"
                )
            authority_by_binding[key] = authority

        active_by_binding: dict[
            tuple[str, str | None], list[ProjectRequirementEvidenceMapping]
        ] = {}
        for mapping in self.mappings:
            if mapping.status == "active":
                active_by_binding.setdefault(
                    (mapping.requirement_id, mapping.subject_ref),
                    [],
                ).append(mapping)

        for key, active in active_by_binding.items():
            authority = authority_by_binding.get(key)
            if len(active) < 2:
                if authority is not None:
                    raise ProjectRequirementEvidenceMappingsFormatError(
                        "evidence authority must resolve an ambiguous active "
                        "requirement/subject binding"
                    )
                continue
            analysis_ids = {item.analysis_id for item in active}
            if len(analysis_ids) != 1:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    "ambiguous requirement/subject active mappings must belong "
                    "to the same analysis"
                )
            if authority is None:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    "active requirement evidence mappings must not create an "
                    "ambiguous requirement/subject binding without explicit "
                    "evidence authority"
                )
            candidate_ids = {item.id for item in active}
            if authority.evidence_id not in candidate_ids:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    f"authoritative evidence {authority.evidence_id!r} is not an "
                    "active mapping for its requirement/subject binding"
                )

        for key in authority_by_binding:
            if len(active_by_binding.get(key, ())) < 2:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    "evidence authority must resolve an ambiguous active "
                    "requirement/subject binding"
                )

        object.__setattr__(
            self,
            "mappings",
            tuple(sorted(self.mappings, key=lambda item: item.id)),
        )
        object.__setattr__(
            self,
            "evidence_authority",
            tuple(
                sorted(
                    self.evidence_authority,
                    key=lambda item: (
                        item.requirement_id,
                        "" if item.subject_ref is None else item.subject_ref,
                        item.evidence_id,
                    ),
                )
            ),
        )

    def body_dict(self) -> dict[str, Any]:
        schema_version = (
            PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION
            if self.evidence_authority
            else PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION
        )
        body = {
            "schema": PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA,
            "schema_version": schema_version,
            "mappings": [item.to_dict() for item in self.mappings],
        }
        if self.evidence_authority:
            body["evidence_authority"] = [
                item.to_dict() for item in self.evidence_authority
            ]
        return body

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.body_dict(),
            "mappings_sha256": self.sha256,
        }

    def for_analysis(
        self,
        analysis_id: str,
        *,
        active_only: bool = True,
    ) -> tuple[ProjectRequirementEvidenceMapping, ...]:
        normalized = _nonempty(analysis_id, "analysis_id")
        return tuple(
            item
            for item in self.mappings
            if item.analysis_id == normalized
            and (not active_only or item.status == "active")
        )

    def authority_for_analysis(
        self,
        analysis_id: str,
    ) -> tuple[RequirementEvidenceAuthority, ...]:
        normalized = _nonempty(analysis_id, "analysis_id")
        bindings = {
            (item.requirement_id, item.subject_ref)
            for item in self.mappings
            if item.analysis_id == normalized and item.status == "active"
        }
        return tuple(
            item
            for item in self.evidence_authority
            if (item.requirement_id, item.subject_ref) in bindings
        )


def _mapping_from_dict(
    data: Any,
    field_name: str,
) -> ProjectRequirementEvidenceMapping:
    if not isinstance(data, dict):
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must be an object"
        )
    _reject_unknown(
        data,
        {
            "id",
            "requirement_id",
            "analysis_id",
            "expected_analysis_kind",
            "subject_ref",
            "property_name",
            "result_path",
            "unit",
            "evidence_kinds",
            "status",
            "notes",
        },
        field_name,
    )
    return ProjectRequirementEvidenceMapping(
        id=data.get("id"),
        requirement_id=data.get("requirement_id"),
        analysis_id=data.get("analysis_id"),
        expected_analysis_kind=data.get("expected_analysis_kind"),
        subject_ref=data.get("subject_ref"),
        property_name=data.get("property_name"),
        result_path=_path_tuple(
            data.get("result_path"),
            f"{field_name}.result_path",
        ),
        unit=data.get("unit"),
        evidence_kinds=_string_tuple(
            data.get("evidence_kinds", []),
            f"{field_name}.evidence_kinds",
        ),
        status=data.get("status", "active"),
        notes=data.get("notes"),
    )


def _authority_from_dict(
    data: Any,
    field_name: str,
) -> RequirementEvidenceAuthority:
    if not isinstance(data, dict):
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} must be an object"
        )
    _reject_unknown(
        data,
        {
            "requirement_id",
            "subject_ref",
            "evidence_id",
            "authority_source",
            "decision_reference",
            "decision_revision",
            "rationale",
        },
        field_name,
    )
    try:
        return RequirementEvidenceAuthority(
            requirement_id=data.get("requirement_id"),
            subject_ref=data.get("subject_ref"),
            evidence_id=data.get("evidence_id"),
            authority_source=data.get("authority_source"),
            decision_reference=data.get("decision_reference"),
            decision_revision=data.get("decision_revision"),
            rationale=data.get("rationale"),
        )
    except ValueError as exc:
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"{field_name} is invalid: {exc}"
        ) from exc


def project_requirement_evidence_mappings_from_dict(
    data: Any,
) -> ProjectRequirementEvidenceMappings:
    if not isinstance(data, dict):
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement evidence mappings metadata must be an object"
        )
    _reject_unknown(
        data,
        {
            "schema",
            "schema_version",
            "mappings",
            "evidence_authority",
            "mappings_sha256",
        },
        "requirement_evidence_mappings",
    )
    if data.get("schema") != PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA:
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement_evidence_mappings.schema must be "
            f"{PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA!r}"
        )
    version = data.get("schema_version")
    if type(version) is not int:
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement_evidence_mappings.schema_version must be an integer"
        )
    if version not in SUPPORTED_PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSIONS:
        supported = ", ".join(
            str(item)
            for item in sorted(
                SUPPORTED_PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSIONS
            )
        )
        raise ProjectRequirementEvidenceMappingsFormatError(
            "unsupported project requirement evidence mappings schema version "
            f"{version}; supported versions: {supported}"
        )
    raw_mappings = data.get("mappings", [])
    if not isinstance(raw_mappings, list):
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement_evidence_mappings.mappings must be an array"
        )
    raw_authority = data.get("evidence_authority", [])
    if not isinstance(raw_authority, list):
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement_evidence_mappings.evidence_authority must be an array"
        )
    if (
        version == PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_SCHEMA_VERSION
        and "evidence_authority" in data
    ):
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement_evidence_mappings.evidence_authority requires "
            f"schema_version {PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION}"
        )
    if (
        version == PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION
        and not raw_authority
    ):
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement evidence mappings schema version "
            f"{PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_AUTHORITY_SCHEMA_VERSION} "
            "requires non-empty evidence_authority"
        )
    registry = ProjectRequirementEvidenceMappings(
        mappings=tuple(
            _mapping_from_dict(
                item,
                f"requirement_evidence_mappings.mappings[{index}]",
            )
            for index, item in enumerate(raw_mappings)
        ),
        evidence_authority=tuple(
            _authority_from_dict(
                item,
                f"requirement_evidence_mappings.evidence_authority[{index}]",
            )
            for index, item in enumerate(raw_authority)
        ),
    )
    supplied_digest = data.get("mappings_sha256")
    if supplied_digest is not None:
        supplied_digest = _check_sha256(
            supplied_digest,
            "requirement_evidence_mappings.mappings_sha256",
        )
        if supplied_digest != registry.sha256:
            raise ProjectRequirementEvidenceMappingsFormatError(
                "mappings_sha256 does not match normalized requirement evidence "
                "mappings"
            )
    return registry


def normalize_project_requirement_evidence_mappings_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ProjectRequirementEvidenceMappingsFormatError(
            "project metadata must be an object"
        )
    normalized = copy.deepcopy(metadata)
    if PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY not in normalized:
        return normalized
    registry = project_requirement_evidence_mappings_from_dict(
        normalized[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY]
    )
    normalized[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY] = (
        registry.to_dict()
    )
    return normalized


def validate_project_requirement_evidence_mappings(
    metadata: dict[str, Any],
    analyses: Iterable[Any],
) -> None:
    if PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY not in metadata:
        return
    registry = project_requirement_evidence_mappings_from_dict(
        metadata[PROJECT_REQUIREMENT_EVIDENCE_MAPPINGS_METADATA_KEY]
    )
    if not registry.mappings:
        return

    requirements_data = metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    if requirements_data is None:
        raise ProjectRequirementEvidenceMappingsFormatError(
            "requirement evidence mappings require project.metadata.requirements"
        )
    try:
        requirements = project_requirements_from_dict(requirements_data)
    except ProjectRequirementsFormatError as exc:
        raise ProjectRequirementEvidenceMappingsFormatError(
            f"cannot validate mapping requirements: {exc}"
        ) from exc

    requirement_by_id = {
        requirement.id: requirement
        for requirement_set in requirements.sets
        for requirement in requirement_set.requirements
    }
    analysis_by_id: dict[str, Any] = {}
    for analysis in analyses:
        analysis_id = getattr(analysis, "id", None)
        analysis_kind = getattr(analysis, "kind", None)
        if not isinstance(analysis_id, str) or not isinstance(analysis_kind, str):
            raise ProjectRequirementEvidenceMappingsFormatError(
                "project analyses are not valid mapping targets"
            )
        analysis_by_id[analysis_id] = analysis

    for mapping in registry.mappings:
        if mapping.status != "active":
            continue
        requirement = requirement_by_id.get(mapping.requirement_id)
        if requirement is None:
            raise ProjectRequirementEvidenceMappingsFormatError(
                f"active mapping {mapping.id!r} references unknown requirement "
                f"{mapping.requirement_id!r}"
            )
        analysis = analysis_by_id.get(mapping.analysis_id)
        if analysis is None:
            raise ProjectRequirementEvidenceMappingsFormatError(
                f"active mapping {mapping.id!r} references unknown analysis "
                f"{mapping.analysis_id!r}"
            )
        actual_kind = getattr(analysis, "kind")
        if actual_kind != mapping.expected_analysis_kind:
            raise ProjectRequirementEvidenceMappingsFormatError(
                f"active mapping {mapping.id!r} expected analysis kind "
                f"{mapping.expected_analysis_kind!r} but analysis "
                f"{mapping.analysis_id!r} is {actual_kind!r}"
            )
        if requirement.scope:
            if mapping.subject_ref not in requirement.scope:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    f"active mapping {mapping.id!r} subject_ref must reference one "
                    "of the requirement scope entities"
                )
        elif mapping.subject_ref is not None:
            raise ProjectRequirementEvidenceMappingsFormatError(
                f"active mapping {mapping.id!r} must not assign subject_ref to a "
                "project-scoped requirement"
            )

    for authority in registry.evidence_authority:
        requirement = requirement_by_id.get(authority.requirement_id)
        if requirement is None:
            raise ProjectRequirementEvidenceMappingsFormatError(
                "evidence authority references unknown requirement "
                f"{authority.requirement_id!r}"
            )
        if (
            requirement.status != "approved"
            or requirement.applicability != "applicable"
        ):
            raise ProjectRequirementEvidenceMappingsFormatError(
                "evidence authority may target only approved, applicable requirements"
            )
        if requirement.scope:
            if authority.subject_ref not in requirement.scope:
                raise ProjectRequirementEvidenceMappingsFormatError(
                    f"evidence authority subject {authority.subject_ref!r} is outside "
                    f"requirement {requirement.id!r} scope"
                )
        elif authority.subject_ref is not None:
            raise ProjectRequirementEvidenceMappingsFormatError(
                f"evidence authority supplies subject {authority.subject_ref!r} for "
                f"project-scope requirement {requirement.id!r}"
            )
