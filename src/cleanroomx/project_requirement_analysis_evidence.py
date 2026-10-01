from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .application import (
    AnalysisRun,
    analysis_run_external_dependencies_current,
    analysis_run_matches_input,
    verify_analysis_run_bundle,
)
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


def _analysis_run_from_verified_bundle(
    run_bundle: dict[str, Any],
) -> AnalysisRun:
    return AnalysisRun(
        kind=run_bundle["kind"],
        title=run_bundle["title"],
        status=run_bundle["status"],
        result=run_bundle["result"],
        markdown=run_bundle["markdown"],
        diagnostics=run_bundle["diagnostics"],
        plot=run_bundle["plot"],
        input_snapshot=run_bundle["input_snapshot"],
    )


def _derived_freshness(
    run: AnalysisRun,
    *,
    current_analysis_input: dict[str, Any] | None,
    base_dir: str | Path | None,
) -> str:
    if current_analysis_input is None:
        return "unknown"
    if not isinstance(current_analysis_input, dict):
        raise AnalysisRequirementEvidenceError(
            "current_analysis_input must be a JSON object or null"
        )
    if not analysis_run_matches_input(
        run,
        run.kind,
        current_analysis_input,
    ):
        return "stale"
    if not analysis_run_external_dependencies_current(
        run,
        base_dir=base_dir,
    ):
        return "stale"
    return "current"


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
    current_analysis_input: dict[str, Any] | None,
    source_project_revision: str | None = None,
    base_dir: str | Path | None = None,
) -> tuple[RequirementEvidence, ...]:
    """Bind verified immutable analysis output to explicit project requirements.

    Freshness is derived from exact analysis input and external-dependency
    provenance. Project revision comes from the integrity-verified run when the
    execution boundary recorded it; legacy/unbound runs require an explicit
    trusted revision.
    """
    supplied_source_revision = (
        None
        if source_project_revision is None
        else _sha256(source_project_revision, "source_project_revision")
    )
    if not isinstance(run_bundle, dict):
        raise AnalysisRequirementEvidenceError(
            "run_bundle must be a CleanroomX analysis-run object"
        )
    verified = verify_analysis_run_bundle(copy.deepcopy(run_bundle))
    embedded_source_revision = verified.get("project_source_revision")
    if embedded_source_revision is not None:
        embedded_source_revision = _sha256(
            embedded_source_revision,
            "verified_analysis.project_source_revision",
        )
        if (
            supplied_source_revision is not None
            and supplied_source_revision != embedded_source_revision
        ):
            raise AnalysisRequirementEvidenceError(
                "source_project_revision disagrees with the project revision "
                "bound into the verified analysis run"
            )
        source_revision = embedded_source_revision
    elif supplied_source_revision is not None:
        source_revision = supplied_source_revision
    else:
        raise AnalysisRequirementEvidenceError(
            "analysis run is not bound to a project revision; provide "
            "source_project_revision from a trusted project execution boundary"
        )

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

    run = _analysis_run_from_verified_bundle(run_bundle)
    freshness = _derived_freshness(
        run,
        current_analysis_input=current_analysis_input,
        base_dir=base_dir,
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
    current_analysis_input: dict[str, Any] | None,
    source_project_revision: str | None = None,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Bind one verified analysis run and evaluate through the canonical verifier."""
    bindings = bind_analysis_run_requirement_evidence(
        run_bundle,
        mappings,
        source_project_revision=source_project_revision,
        current_analysis_input=current_analysis_input,
        base_dir=base_dir,
    )
    return verify_project_requirements(requirements, bindings)
