from __future__ import annotations

import copy
from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any


PROJECT_REQUIREMENTS_METADATA_KEY = "requirements"
PROJECT_REQUIREMENTS_SCHEMA = "cleanroomx.project-requirements"
PROJECT_REQUIREMENTS_SCHEMA_VERSION = 1

REQUIREMENT_APPLICABILITY = frozenset(
    {"applicable", "conditional", "not_applicable", "unknown"}
)
REQUIREMENT_STATUSES = frozenset(
    {"draft", "approved", "superseded", "withdrawn"}
)


class ProjectRequirementsFormatError(ValueError):
    """Raised when first-class persisted project requirements are invalid."""


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectRequirementsFormatError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectRequirementsFormatError(
            f"{field_name} must be a finite number"
        )
    result = float(value)
    if not math.isfinite(result):
        raise ProjectRequirementsFormatError(
            f"{field_name} must be a finite number"
        )
    # Canonicalize signed zero so equivalent engineering values hash identically.
    return 0.0 if result == 0.0 else result


def _criterion_target(value: Any, field_name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return copy.deepcopy(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _finite(value, field_name)
    raise ProjectRequirementsFormatError(
        f"{field_name} must be null, text, boolean, or a finite number"
    )


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ProjectRequirementsFormatError(
            f"{field_name} must be an array of non-empty strings"
        )
    normalized = tuple(
        _nonempty(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise ProjectRequirementsFormatError(
            f"{field_name} must not contain duplicates"
        )
    return normalized


def _reject_unknown(
    data: dict[str, Any],
    allowed: set[str],
    field_name: str,
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ProjectRequirementsFormatError(
            f"{field_name} contains unsupported field(s): "
            + ", ".join(unknown)
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
        raise ProjectRequirementsFormatError(
            f"{field_name} must be a lowercase SHA-256 hex digest"
        )
    return text


@dataclass(frozen=True, kw_only=True)
class ProjectRequirement:
    id: str
    title: str
    description: str
    discipline: str
    category: str
    source: str
    source_revision: str
    reference: str | None = None
    unit: str | None = None
    target: Any = None
    minimum: float | None = None
    maximum: float | None = None
    tolerance: float | None = None
    applicability: str = "unknown"
    scope: tuple[str, ...] = ()
    verification_method: str | None = None
    required_evidence: tuple[str, ...] = ()
    status: str = "draft"
    assumptions: tuple[str, ...] = ()
    notes: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "id",
            "title",
            "description",
            "discipline",
            "category",
            "source",
            "source_revision",
        ):
            object.__setattr__(
                self,
                name,
                _nonempty(getattr(self, name), f"requirement.{name}"),
            )
        object.__setattr__(
            self,
            "reference",
            _optional_text(self.reference, "requirement.reference"),
        )
        object.__setattr__(
            self,
            "unit",
            _optional_text(self.unit, "requirement.unit"),
        )
        object.__setattr__(
            self,
            "verification_method",
            _optional_text(
                self.verification_method,
                "requirement.verification_method",
            ),
        )
        object.__setattr__(
            self,
            "notes",
            _optional_text(self.notes, "requirement.notes"),
        )
        object.__setattr__(
            self,
            "target",
            _criterion_target(self.target, "requirement.target"),
        )
        if self.minimum is not None:
            object.__setattr__(
                self,
                "minimum",
                _finite(self.minimum, "requirement.minimum"),
            )
        if self.maximum is not None:
            object.__setattr__(
                self,
                "maximum",
                _finite(self.maximum, "requirement.maximum"),
            )
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ProjectRequirementsFormatError(
                "requirement.minimum must be <= requirement.maximum"
            )
        if self.target is not None and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ProjectRequirementsFormatError(
                "requirement.target cannot be combined with minimum or maximum"
            )
        if self.tolerance is not None:
            tolerance = _finite(self.tolerance, "requirement.tolerance")
            if tolerance < 0:
                raise ProjectRequirementsFormatError(
                    "requirement.tolerance must be >= 0"
                )
            object.__setattr__(self, "tolerance", tolerance)
        if self.applicability not in REQUIREMENT_APPLICABILITY:
            raise ProjectRequirementsFormatError(
                "requirement.applicability must be one of: "
                + ", ".join(sorted(REQUIREMENT_APPLICABILITY))
            )
        if self.status not in REQUIREMENT_STATUSES:
            raise ProjectRequirementsFormatError(
                "requirement.status must be one of: "
                + ", ".join(sorted(REQUIREMENT_STATUSES))
            )
        object.__setattr__(
            self,
            "scope",
            tuple(sorted(_string_tuple(self.scope, "requirement.scope"))),
        )
        object.__setattr__(
            self,
            "required_evidence",
            tuple(
                sorted(
                    _string_tuple(
                        self.required_evidence,
                        "requirement.required_evidence",
                    )
                )
            ),
        )
        object.__setattr__(
            self,
            "assumptions",
            _string_tuple(self.assumptions, "requirement.assumptions"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "discipline": self.discipline,
            "category": self.category,
            "source": self.source,
            "source_revision": self.source_revision,
            "reference": self.reference,
            "unit": self.unit,
            "target": copy.deepcopy(self.target),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "tolerance": self.tolerance,
            "applicability": self.applicability,
            "scope": list(self.scope),
            "verification_method": self.verification_method,
            "required_evidence": list(self.required_evidence),
            "status": self.status,
            "assumptions": list(self.assumptions),
            "notes": self.notes,
        }


@dataclass(frozen=True, kw_only=True)
class ProjectRequirementSet:
    id: str
    title: str
    source: str
    source_revision: str
    requirements: tuple[ProjectRequirement, ...]
    description: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "title", "source", "source_revision"):
            object.__setattr__(
                self,
                name,
                _nonempty(getattr(self, name), f"requirement_set.{name}"),
            )
        object.__setattr__(
            self,
            "description",
            _optional_text(
                self.description,
                "requirement_set.description",
            ),
        )
        if not isinstance(self.requirements, tuple):
            object.__setattr__(
                self,
                "requirements",
                tuple(self.requirements),
            )
        if not all(
            isinstance(item, ProjectRequirement)
            for item in self.requirements
        ):
            raise ProjectRequirementsFormatError(
                "requirement_set.requirements must contain ProjectRequirement values"
            )
        ids = [item.id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ProjectRequirementsFormatError(
                "requirement_set.requirements contains duplicate ids"
            )
        object.__setattr__(
            self,
            "requirements",
            tuple(sorted(self.requirements, key=lambda item: item.id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "source_revision": self.source_revision,
            "requirements": [
                item.to_dict() for item in self.requirements
            ],
        }


@dataclass(frozen=True, kw_only=True)
class ProjectRequirements:
    sets: tuple[ProjectRequirementSet, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.sets, tuple):
            object.__setattr__(self, "sets", tuple(self.sets))
        if not all(
            isinstance(item, ProjectRequirementSet)
            for item in self.sets
        ):
            raise ProjectRequirementsFormatError(
                "requirements.sets must contain ProjectRequirementSet values"
            )
        set_ids = [item.id for item in self.sets]
        if len(set_ids) != len(set(set_ids)):
            raise ProjectRequirementsFormatError(
                "requirements.sets contains duplicate ids"
            )
        requirement_ids = [
            requirement.id
            for requirement_set in self.sets
            for requirement in requirement_set.requirements
        ]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ProjectRequirementsFormatError(
                "requirement ids must be unique across the project"
            )
        object.__setattr__(
            self,
            "sets",
            tuple(sorted(self.sets, key=lambda item: item.id)),
        )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema": PROJECT_REQUIREMENTS_SCHEMA,
            "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
            "sets": [item.to_dict() for item in self.sets],
        }

    @property
    def sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        body = self.body_dict()
        return {
            **body,
            "requirements_sha256": self.sha256,
        }


def _requirement_from_dict(
    data: Any,
    field_name: str,
) -> ProjectRequirement:
    if not isinstance(data, dict):
        raise ProjectRequirementsFormatError(
            f"{field_name} must be an object"
        )
    _reject_unknown(
        data,
        {
            "id",
            "title",
            "description",
            "discipline",
            "category",
            "source",
            "source_revision",
            "reference",
            "unit",
            "target",
            "minimum",
            "maximum",
            "tolerance",
            "applicability",
            "scope",
            "verification_method",
            "required_evidence",
            "status",
            "assumptions",
            "notes",
        },
        field_name,
    )
    return ProjectRequirement(
        id=data.get("id"),
        title=data.get("title"),
        description=data.get("description"),
        discipline=data.get("discipline"),
        category=data.get("category"),
        source=data.get("source"),
        source_revision=data.get("source_revision"),
        reference=data.get("reference"),
        unit=data.get("unit"),
        target=data.get("target"),
        minimum=data.get("minimum"),
        maximum=data.get("maximum"),
        tolerance=data.get("tolerance"),
        applicability=data.get("applicability", "unknown"),
        scope=_string_tuple(
            data.get("scope", []),
            f"{field_name}.scope",
        ),
        verification_method=data.get("verification_method"),
        required_evidence=_string_tuple(
            data.get("required_evidence", []),
            f"{field_name}.required_evidence",
        ),
        status=data.get("status", "draft"),
        assumptions=_string_tuple(
            data.get("assumptions", []),
            f"{field_name}.assumptions",
        ),
        notes=data.get("notes"),
    )


def _set_from_dict(
    data: Any,
    field_name: str,
) -> ProjectRequirementSet:
    if not isinstance(data, dict):
        raise ProjectRequirementsFormatError(
            f"{field_name} must be an object"
        )
    _reject_unknown(
        data,
        {
            "id",
            "title",
            "description",
            "source",
            "source_revision",
            "requirements",
        },
        field_name,
    )
    raw_requirements = data.get("requirements", [])
    if not isinstance(raw_requirements, list):
        raise ProjectRequirementsFormatError(
            f"{field_name}.requirements must be an array"
        )
    return ProjectRequirementSet(
        id=data.get("id"),
        title=data.get("title"),
        description=data.get("description"),
        source=data.get("source"),
        source_revision=data.get("source_revision"),
        requirements=tuple(
            _requirement_from_dict(
                requirement,
                f"{field_name}.requirements[{index}]",
            )
            for index, requirement in enumerate(raw_requirements)
        ),
    )


def project_requirements_from_dict(data: Any) -> ProjectRequirements:
    if not isinstance(data, dict):
        raise ProjectRequirementsFormatError(
            "requirements metadata must be an object"
        )
    _reject_unknown(
        data,
        {
            "schema",
            "schema_version",
            "sets",
            "requirements_sha256",
        },
        "requirements",
    )
    if data.get("schema") != PROJECT_REQUIREMENTS_SCHEMA:
        raise ProjectRequirementsFormatError(
            f"requirements.schema must be {PROJECT_REQUIREMENTS_SCHEMA!r}"
        )
    version = data.get("schema_version")
    if type(version) is not int:
        raise ProjectRequirementsFormatError(
            "requirements.schema_version must be an integer"
        )
    if version != PROJECT_REQUIREMENTS_SCHEMA_VERSION:
        raise ProjectRequirementsFormatError(
            "unsupported project requirements schema version "
            f"{version}; expected {PROJECT_REQUIREMENTS_SCHEMA_VERSION}"
        )
    raw_sets = data.get("sets", [])
    if not isinstance(raw_sets, list):
        raise ProjectRequirementsFormatError(
            "requirements.sets must be an array"
        )
    registry = ProjectRequirements(
        sets=tuple(
            _set_from_dict(item, f"requirements.sets[{index}]")
            for index, item in enumerate(raw_sets)
        )
    )
    supplied_digest = data.get("requirements_sha256")
    if supplied_digest is not None:
        supplied_digest = _check_sha256(
            supplied_digest,
            "requirements.requirements_sha256",
        )
        if supplied_digest != registry.sha256:
            raise ProjectRequirementsFormatError(
                "requirements_sha256 does not match normalized requirements"
            )
    return registry


def normalize_project_requirements_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise ProjectRequirementsFormatError(
            "project metadata must be an object"
        )
    normalized = copy.deepcopy(metadata)
    if PROJECT_REQUIREMENTS_METADATA_KEY not in normalized:
        return normalized
    registry = project_requirements_from_dict(
        normalized[PROJECT_REQUIREMENTS_METADATA_KEY]
    )
    normalized[PROJECT_REQUIREMENTS_METADATA_KEY] = registry.to_dict()
    return normalized
