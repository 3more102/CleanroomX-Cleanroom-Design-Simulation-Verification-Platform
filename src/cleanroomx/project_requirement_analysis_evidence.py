from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable

from .application import verify_analysis_run_bundle
from .project_requirement_verification import (
    RequirementEvidence,
    verify_project_requirements,
)
from .project_requirements import ProjectRequirements


class AnalysisRequirementEvidenceError(ValueError):
    """Raised when immutable analysis evidence cannot be bound safely."""


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnalysisRequirementEvidenceError(
            f"{field_name} must be a non-empty string"
        )
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _sha256(value: Any, field_name: str) -> str:
    text = _nonempty(value, field_name)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise AnalysisRequirementEvidenceError(
            f"{field_name} must be a lowercase SHA-256 hex digest"
        )
    return text


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise AnalysisRequirementEvidenceError(
            f"{field_name} must be an array of non-empty strings"
        )
    normalized = tuple(
        _nonempty(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise AnalysisRequirementEvidenceError(
            f"{field_name} must not contain duplicates"
        )
    return tuple(sorted(normalized))


def _path_tuple(value: Any, field_name: str) -> tuple[str | int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise AnalysisRequirementEvidenceError(
            f"{field_name} must be an array of object keys/list indexes"
        )
    normalized: list[str | int] = []
    for index, token in enumerate(value):
        token_field = f"{field_name}[{index}]"
        if isinstance(token, bool):
            raise AnalysisRequirementEvidenceError(
                f"{token_field} must be an object key or non-negative list index"
            )
        if isinstance(token, int):
            if token < 0:
                raise AnalysisRequirementEvidenceError(
                    f"{token_field} list index must be >= 0"
                )
            normalized.append(token)
            continue
        if isinstance(token, str):
            normalized.append(_nonempty(token, token_field))
            continue
        raise AnalysisRequirementEvidenceError(
            f"{token_field} must be an object key or non-negative list index"
        )
    if not normalized:
        raise AnalysisRequirementEvidenceError(
            f"{field_name} must identify a value inside the analysis result"
        )
    return tuple(normalized)


def _result_locator(path: tuple[str | int, ...]) -> str:
    encoded = []
    for token in path:
        if isinstance(token, int):
            encoded.append(str(token))
        else:
            encoded.append(token.replace("~", "~0").replace("/", "~1"))
    return "/result/" + "/".join(encoded)


def _extract_result_value(
    result: dict[str, Any],
    path: tuple[str | int, ...],
) -> Any:
    current: Any = result
    for token in path:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return None
            current = current[token]
            continue
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return copy.deepcopy(current)


def _derived_freshness(
    *,
    source_project_revision: str,
    current_project_revision: str | None,
    external_dependencies_stable: Any,
) -> str:
    if current_project_revision is None:
        return "unknown"
    if current_project_revision != source_project_revision:
        return "stale"
    if external_dependencies_stable is True:
        return "current"
    if external_dependencies_stable is False:
        return "stale"
    return "unknown"


@dataclass(frozen=True, kw_only=True)
class AnalysisRequirementEvidenceMapping:
    id: str
    requirement_id: str
    property_name: str
    result_path: tuple[str | int, ...]
    subject_ref: str | None = None
    unit: str | None = None
    evidence_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "requirement_id", "property_name"):
            object.__setattr__(
                self,
                name,
                _nonempty(
                    getattr(self, name),
                    f"analysis_requirement_evidence_mapping.{name}",
                ),
            )
        for name in ("subject_ref", "unit"):
            object.__setattr__(
                self,
                name,
                _optional_text(
                    getattr(self, name),
                    f"analysis_requirement_evidence_mapping.{name}",
                ),
            )
        object.__setattr__(
            self,
            "result_path",
            _path_tuple(
                self.result_path,
                "analysis_requirement_evidence_mapping.result_path",
            ),
        )
        object.__setattr__(
            self,
            "evidence_kinds",
            _string_tuple(
                self.evidence_kinds,
                "analysis_requirement_evidence_mapping.evidence_kinds",
            ),
        )


def bind_analysis_run_requirement_evidence(
    run_bundle: dict[str, Any],
    mappings: Iterable[AnalysisRequirementEvidenceMapping],
    *,
    source_project_revision: str,
    current_project_revision: str | None,
) -> tuple[RequirementEvidence, ...]:
    """Bind verified immutable analysis output to explicit project requirements.

    Freshness is derived from project content identity and run external-dependency
    provenance. It is never accepted as a free-form caller assertion.
    """
    source_revision = _sha256(
        source_project_revision,
        "source_project_revision",
    )
    current_revision = (
        None
        if current_project_revision is None
        else _sha256(current_project_revision, "current_project_revision")
    )
    if not isinstance(run_bundle, dict):
        raise AnalysisRequirementEvidenceError(
            "run_bundle must be a CleanroomX analysis-run object"
        )
    verified = verify_analysis_run_bundle(copy.deepcopy(run_bundle))
    result = run_bundle.get("result")
    if not isinstance(result, dict):
        raise AnalysisRequirementEvidenceError(
            "verified run bundle result must be an object"
        )

    mapping_list = tuple(mappings)
    if not all(
        isinstance(item, AnalysisRequirementEvidenceMapping)
        for item in mapping_list
    ):
        raise TypeError(
            "mappings must contain AnalysisRequirementEvidenceMapping values"
        )
    mapping_ids = [item.id for item in mapping_list]
    if len(mapping_ids) != len(set(mapping_ids)):
        raise AnalysisRequirementEvidenceError(
            "analysis requirement evidence mappings contain duplicate ids"
        )

    freshness = _derived_freshness(
        source_project_revision=source_revision,
        current_project_revision=current_revision,
        external_dependencies_stable=verified.get(
            "external_dependencies_stable"
        ),
    )
    analysis_kind = _nonempty(
        verified.get("analysis_kind"),
        "verified_analysis.analysis_kind",
    )
    title = _nonempty(run_bundle.get("title"), "run_bundle.title")
    bundle_sha256 = _sha256(
        verified.get("bundle_sha256"),
        "verified_analysis.bundle_sha256",
    )

    bindings: list[RequirementEvidence] = []
    for mapping in sorted(mapping_list, key=lambda item: item.id):
        locator = _result_locator(mapping.result_path)
        value = _extract_result_value(result, mapping.result_path)
        try:
            bindings.append(
                RequirementEvidence(
                    id=mapping.id,
                    requirement_id=mapping.requirement_id,
                    subject_ref=mapping.subject_ref,
                    property_name=mapping.property_name,
                    value=value,
                    unit=mapping.unit,
                    source=f"CleanroomX analysis run: {title}",
                    source_revision=bundle_sha256,
                    calculation_source=f"{analysis_kind}:{locator}",
                    evidence_locator=locator,
                    project_revision=source_revision,
                    evidence_kinds=mapping.evidence_kinds,
                    freshness=freshness,
                )
            )
        except ValueError as exc:
            raise AnalysisRequirementEvidenceError(
                f"mapping {mapping.id!r} could not bind {locator}: {exc}"
            ) from exc
    return tuple(bindings)


def verify_project_requirements_from_analysis_run(
    requirements: ProjectRequirements,
    run_bundle: dict[str, Any],
    mappings: Iterable[AnalysisRequirementEvidenceMapping],
    *,
    source_project_revision: str,
    current_project_revision: str | None,
) -> dict[str, Any]:
    """Bind one verified analysis run and evaluate through the canonical verifier."""
    bindings = bind_analysis_run_requirement_evidence(
        run_bundle,
        mappings,
        source_project_revision=source_project_revision,
        current_project_revision=current_project_revision,
    )
    return verify_project_requirements(requirements, bindings)
