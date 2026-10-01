from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable

from .project_requirements import ProjectRequirement, ProjectRequirements
from .verification import aggregate_verification_status


REQUIREMENT_EVIDENCE_FRESHNESS = frozenset({"current", "stale", "unknown"})
REQUIREMENT_VERIFICATION_STATES = frozenset(
    {
        "pass",
        "fail",
        "not_checked",
        "stale",
        "incomplete",
        "invalid",
        "inactive",
        "not_applicable",
    }
)


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite number")
    return 0.0 if result == 0.0 else result


def _scalar(value: Any, field_name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return copy.deepcopy(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _finite(value, field_name)
    raise ValueError(
        f"{field_name} must be null, text, boolean, or a finite number"
    )


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an array of non-empty strings")
    normalized = tuple(
        _nonempty(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(normalized))


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return float(left) == float(right)
    return type(left) is type(right) and left == right


@dataclass(frozen=True, kw_only=True)
class RequirementEvidence:
    id: str
    requirement_id: str
    property_name: str
    value: Any
    source: str
    source_revision: str
    subject_ref: str | None = None
    unit: str | None = None
    calculation_source: str | None = None
    evidence_locator: str | None = None
    project_revision: str | None = None
    evidence_kinds: tuple[str, ...] = ()
    freshness: str = "unknown"

    def __post_init__(self) -> None:
        for name in ("id", "requirement_id", "property_name", "source", "source_revision"):
            object.__setattr__(
                self,
                name,
                _nonempty(getattr(self, name), f"requirement_evidence.{name}"),
            )
        for name in (
            "subject_ref",
            "unit",
            "calculation_source",
            "evidence_locator",
            "project_revision",
        ):
            object.__setattr__(
                self,
                name,
                _optional_text(
                    getattr(self, name),
                    f"requirement_evidence.{name}",
                ),
            )
        object.__setattr__(
            self,
            "value",
            _scalar(self.value, "requirement_evidence.value"),
        )
        object.__setattr__(
            self,
            "evidence_kinds",
            _string_tuple(
                self.evidence_kinds,
                "requirement_evidence.evidence_kinds",
            ),
        )
        if self.freshness not in REQUIREMENT_EVIDENCE_FRESHNESS:
            raise ValueError(
                "requirement_evidence.freshness must be one of: "
                + ", ".join(sorted(REQUIREMENT_EVIDENCE_FRESHNESS))
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "subject_ref": self.subject_ref,
            "property_name": self.property_name,
            "value": copy.deepcopy(self.value),
            "unit": self.unit,
            "source": self.source,
            "source_revision": self.source_revision,
            "calculation_source": self.calculation_source,
            "evidence_locator": self.evidence_locator,
            "project_revision": self.project_revision,
            "evidence_kinds": list(self.evidence_kinds),
            "freshness": self.freshness,
        }


@dataclass(frozen=True, kw_only=True)
class RequirementEvidenceAuthority:
    requirement_id: str
    evidence_id: str
    rationale: str
    subject_ref: str | None = None

    def __post_init__(self) -> None:
        for name in ("requirement_id", "evidence_id", "rationale"):
            object.__setattr__(
                self,
                name,
                _nonempty(
                    getattr(self, name),
                    f"requirement_evidence_authority.{name}",
                ),
            )
        object.__setattr__(
            self,
            "subject_ref",
            _optional_text(
                self.subject_ref,
                "requirement_evidence_authority.subject_ref",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "subject_ref": self.subject_ref,
            "evidence_id": self.evidence_id,
            "rationale": self.rationale,
        }


def _criterion(requirement: ProjectRequirement) -> dict[str, Any] | None:
    tolerance = requirement.tolerance if requirement.tolerance is not None else 0.0
    if requirement.target is not None:
        return {
            "operator": "equals",
            "expected": copy.deepcopy(requirement.target),
            "tolerance": tolerance,
        }
    if requirement.minimum is not None and requirement.maximum is not None:
        return {
            "operator": "range",
            "expected": {
                "minimum": requirement.minimum,
                "maximum": requirement.maximum,
            },
            "tolerance": tolerance,
        }
    if requirement.minimum is not None:
        return {
            "operator": "minimum",
            "expected": requirement.minimum,
            "tolerance": tolerance,
        }
    if requirement.maximum is not None:
        return {
            "operator": "maximum",
            "expected": requirement.maximum,
            "tolerance": tolerance,
        }
    return None


def _base_finding(
    requirement: ProjectRequirement,
    subject_ref: str | None,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement.id,
        "requirement_title": requirement.title,
        "requirement_status": requirement.status,
        "subject_ref": subject_ref,
        "discipline": requirement.discipline,
        "category": requirement.category,
        "source": requirement.source,
        "source_revision": requirement.source_revision,
        "reference": requirement.reference,
        "required_evidence": list(requirement.required_evidence),
        "criterion": _criterion(requirement),
        "unit": requirement.unit,
    }


def _unresolved(
    requirement: ProjectRequirement,
    subject_ref: str | None,
    *,
    state: str,
    explanation: str,
    evidence: RequirementEvidence | None = None,
    evidence_ids: list[str] | None = None,
    included: bool = True,
) -> dict[str, Any]:
    finding = _base_finding(requirement, subject_ref)
    finding.update(
        {
            "status": "not_checked",
            "state": state,
            "included": included,
            "actual": None if evidence is None else copy.deepcopy(evidence.value),
            "delta": None,
            "evidence_id": None if evidence is None else evidence.id,
            "evidence_ids": evidence_ids or ([] if evidence is None else [evidence.id]),
            "evidence_source": None if evidence is None else evidence.source,
            "evidence_revision": None if evidence is None else evidence.source_revision,
            "calculation_source": None if evidence is None else evidence.calculation_source,
            "project_revision": None if evidence is None else evidence.project_revision,
            "freshness": None if evidence is None else evidence.freshness,
            "evidence_kinds": [] if evidence is None else list(evidence.evidence_kinds),
            "explanation": explanation,
        }
    )
    return finding


def _evaluate(
    requirement: ProjectRequirement,
    subject_ref: str | None,
    evidence: RequirementEvidence,
) -> dict[str, Any]:
    criterion = _criterion(requirement)
    if criterion is None:
        return _unresolved(
            requirement,
            subject_ref,
            state="not_checked",
            explanation="Requirement has no explicit acceptance criterion.",
            evidence=evidence,
        )
    if evidence.freshness == "stale":
        return _unresolved(
            requirement,
            subject_ref,
            state="stale",
            explanation="Bound engineering evidence is stale and was not used for a verdict.",
            evidence=evidence,
        )
    if evidence.freshness != "current":
        return _unresolved(
            requirement,
            subject_ref,
            state="incomplete",
            explanation="Evidence freshness is not established as current.",
            evidence=evidence,
        )
    missing_kinds = sorted(
        set(requirement.required_evidence) - set(evidence.evidence_kinds)
    )
    if missing_kinds:
        return _unresolved(
            requirement,
            subject_ref,
            state="incomplete",
            explanation=(
                "Required evidence kind(s) are missing: " + ", ".join(missing_kinds)
            ),
            evidence=evidence,
        )
    if evidence.unit != requirement.unit:
        return _unresolved(
            requirement,
            subject_ref,
            state="invalid",
            explanation=(
                "Evidence unit does not exactly match the requirement unit; "
                "no implicit conversion was performed."
            ),
            evidence=evidence,
        )

    if evidence.value is None:
        return _unresolved(
            requirement,
            subject_ref,
            state="incomplete",
            explanation="Bound evidence does not contain an engineering value.",
            evidence=evidence,
        )

    operator = criterion["operator"]
    expected = criterion["expected"]
    tolerance = float(criterion["tolerance"])
    actual = evidence.value
    delta: float | None = None

    if operator == "equals" and isinstance(expected, (str, bool)):
        if tolerance != 0.0:
            return _unresolved(
                requirement,
                subject_ref,
                state="invalid",
                explanation="A non-numeric equality requirement cannot use numeric tolerance.",
                evidence=evidence,
            )
        passed = _json_equal(actual, expected)
    else:
        try:
            actual_number = _finite(actual, "requirement evidence actual")
        except ValueError:
            return _unresolved(
                requirement,
                subject_ref,
                state="invalid",
                explanation="Numeric requirement received non-numeric or non-finite evidence.",
                evidence=evidence,
            )
        if operator == "equals":
            expected_number = _finite(expected, "requirement expected")
            delta = actual_number - expected_number
            passed = abs(delta) <= tolerance
        elif operator == "minimum":
            expected_number = _finite(expected, "requirement minimum")
            delta = actual_number - expected_number
            passed = actual_number + tolerance >= expected_number
        elif operator == "maximum":
            expected_number = _finite(expected, "requirement maximum")
            delta = actual_number - expected_number
            passed = actual_number - tolerance <= expected_number
        elif operator == "range":
            minimum = _finite(expected["minimum"], "requirement minimum")
            maximum = _finite(expected["maximum"], "requirement maximum")
            passed = (
                actual_number >= minimum - tolerance
                and actual_number <= maximum + tolerance
            )
            if actual_number < minimum:
                delta = actual_number - minimum
            elif actual_number > maximum:
                delta = actual_number - maximum
            else:
                delta = 0.0
        else:
            raise AssertionError(f"unsupported requirement operator: {operator}")

    finding = _base_finding(requirement, subject_ref)
    finding.update(
        {
            "status": "pass" if passed else "fail",
            "state": "pass" if passed else "fail",
            "included": True,
            "actual": copy.deepcopy(actual),
            "delta": delta,
            "evidence_id": evidence.id,
            "evidence_ids": [evidence.id],
            "evidence_source": evidence.source,
            "evidence_revision": evidence.source_revision,
            "calculation_source": evidence.calculation_source,
            "project_revision": evidence.project_revision,
            "freshness": evidence.freshness,
            "evidence_kinds": list(evidence.evidence_kinds),
            "explanation": (
                "Current evidence satisfies the explicit requirement criterion."
                if passed
                else "Current evidence does not satisfy the explicit requirement criterion."
            ),
        }
    )
    return finding


def verify_project_requirements(
    requirements: ProjectRequirements,
    evidence: Iterable[RequirementEvidence],
    *,
    evidence_authority: Iterable[RequirementEvidenceAuthority] = (),
) -> dict[str, Any]:
    if not isinstance(requirements, ProjectRequirements):
        raise TypeError("requirements must be a ProjectRequirements value")

    requirement_list = [
        requirement
        for requirement_set in requirements.sets
        for requirement in requirement_set.requirements
    ]
    requirements_by_id = {item.id: item for item in requirement_list}

    evidence_list = tuple(evidence)
    if not all(isinstance(item, RequirementEvidence) for item in evidence_list):
        raise TypeError("evidence must contain RequirementEvidence values")
    evidence_ids = [item.id for item in evidence_list]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("requirement evidence contains duplicate ids")

    authority_list = tuple(evidence_authority)
    if not all(
        isinstance(item, RequirementEvidenceAuthority)
        for item in authority_list
    ):
        raise TypeError(
            "evidence_authority must contain RequirementEvidenceAuthority values"
        )
    authority_by_binding: dict[
        tuple[str, str | None], RequirementEvidenceAuthority
    ] = {}
    for item in authority_list:
        requirement = requirements_by_id.get(item.requirement_id)
        if requirement is None:
            raise ValueError(
                f"evidence authority references unknown requirement "
                f"{item.requirement_id!r}"
            )
        if requirement.scope:
            if item.subject_ref not in requirement.scope:
                raise ValueError(
                    f"evidence authority subject {item.subject_ref!r} is outside "
                    f"requirement {requirement.id!r} scope"
                )
        elif item.subject_ref is not None:
            raise ValueError(
                f"evidence authority supplies subject {item.subject_ref!r} for "
                f"project-scope requirement {requirement.id!r}"
            )
        key = (item.requirement_id, item.subject_ref)
        if key in authority_by_binding:
            raise ValueError(
                "multiple evidence authority records target the same "
                "requirement/entity binding"
            )
        authority_by_binding[key] = item

    evidence_by_binding: dict[
        tuple[str, str | None], list[RequirementEvidence]
    ] = {}
    for item in evidence_list:
        requirement = requirements_by_id.get(item.requirement_id)
        if requirement is None:
            raise ValueError(
                f"evidence {item.id!r} references unknown requirement "
                f"{item.requirement_id!r}"
            )
        if requirement.scope:
            if item.subject_ref not in requirement.scope:
                raise ValueError(
                    f"evidence {item.id!r} subject {item.subject_ref!r} is outside "
                    f"requirement {requirement.id!r} scope"
                )
        elif item.subject_ref is not None:
            raise ValueError(
                f"evidence {item.id!r} supplies subject {item.subject_ref!r} for "
                f"project-scope requirement {requirement.id!r}"
            )
        evidence_by_binding.setdefault(
            (item.requirement_id, item.subject_ref),
            [],
        ).append(item)

    for key, authority in authority_by_binding.items():
        bound = sorted(evidence_by_binding.get(key, []), key=lambda item: item.id)
        if len(bound) < 2:
            raise ValueError(
                "evidence authority must resolve a requirement/entity binding "
                "with multiple evidence records"
            )
        candidate_ids = {item.id for item in bound}
        if authority.evidence_id not in candidate_ids:
            raise ValueError(
                f"authoritative evidence {authority.evidence_id!r} is not bound "
                f"to requirement/entity {key!r}"
            )

    findings: list[dict[str, Any]] = []
    for requirement in sorted(requirement_list, key=lambda item: item.id):
        subjects: tuple[str | None, ...] = (
            tuple(requirement.scope) if requirement.scope else (None,)
        )
        for subject_ref in subjects:
            if requirement.status in {"superseded", "withdrawn"}:
                findings.append(
                    _unresolved(
                        requirement,
                        subject_ref,
                        state="inactive",
                        explanation=(
                            "Requirement lifecycle status is "
                            f"{requirement.status!r}; it is not an active criterion."
                        ),
                        included=False,
                    )
                )
                continue
            if requirement.status != "approved":
                findings.append(
                    _unresolved(
                        requirement,
                        subject_ref,
                        state="incomplete",
                        explanation=(
                            "Requirement lifecycle status is not approved; "
                            "no engineering verdict was issued."
                        ),
                    )
                )
                continue
            if requirement.applicability == "not_applicable":
                findings.append(
                    _unresolved(
                        requirement,
                        subject_ref,
                        state="not_applicable",
                        explanation="Requirement is explicitly marked not applicable.",
                        included=False,
                    )
                )
                continue
            if requirement.applicability != "applicable":
                findings.append(
                    _unresolved(
                        requirement,
                        subject_ref,
                        state="incomplete",
                        explanation=(
                            "Requirement applicability is not resolved as applicable."
                        ),
                    )
                )
                continue

            bound = sorted(
                evidence_by_binding.get((requirement.id, subject_ref), []),
                key=lambda item: item.id,
            )
            if not bound:
                findings.append(
                    _unresolved(
                        requirement,
                        subject_ref,
                        state="not_checked",
                        explanation="No engineering evidence is bound to this requirement.",
                    )
                )
                continue
            if len(bound) > 1:
                authority = authority_by_binding.get((requirement.id, subject_ref))
                if authority is None:
                    findings.append(
                        _unresolved(
                            requirement,
                            subject_ref,
                            state="invalid",
                            explanation=(
                                "Multiple evidence records are bound to the same "
                                "requirement/entity; the authoritative value is ambiguous."
                            ),
                            evidence_ids=[item.id for item in bound],
                        )
                    )
                    continue
                selected = next(
                    item for item in bound if item.id == authority.evidence_id
                )
                finding = _evaluate(requirement, subject_ref, selected)
                finding["evidence_ids"] = [item.id for item in bound]
                finding["evidence_authority"] = authority.to_dict()
                findings.append(finding)
                continue
            findings.append(_evaluate(requirement, subject_ref, bound[0]))

    included = [item for item in findings if item["included"]]
    statuses = [item["status"] for item in included]
    status = aggregate_verification_status(statuses)
    complete = bool(included) and all(item["status"] != "not_checked" for item in included)
    fail_count = sum(item["status"] == "fail" for item in included)
    pass_count = sum(item["status"] == "pass" for item in included)
    not_checked_count = sum(item["status"] == "not_checked" for item in included)
    no_failures_detected = fail_count == 0
    verified = complete and status == "pass"

    evidence_document = [
        item.to_dict()
        for item in sorted(
            evidence_list,
            key=lambda item: (
                item.requirement_id,
                "" if item.subject_ref is None else item.subject_ref,
                item.id,
            ),
        )
    ]
    authority_document = [
        item.to_dict()
        for item in sorted(
            authority_list,
            key=lambda item: (
                item.requirement_id,
                "" if item.subject_ref is None else item.subject_ref,
                item.evidence_id,
            ),
        )
    ]
    body = {
        "status": status,
        "complete": complete,
        "verified": verified,
        "no_failures_detected": no_failures_detected,
        "passed": no_failures_detected,
        "requirements_sha256": requirements.sha256,
        "evidence_sha256": _canonical_sha256(evidence_document),
        "summary": {
            "requirement_count": len(requirement_list),
            "finding_count": len(findings),
            "included_finding_count": len(included),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "not_checked_count": not_checked_count,
            "not_applicable_count": sum(
                item["state"] == "not_applicable" for item in findings
            ),
            "stale_count": sum(item["state"] == "stale" for item in findings),
            "incomplete_count": sum(
                item["state"] == "incomplete" for item in findings
            ),
            "invalid_count": sum(item["state"] == "invalid" for item in findings),
            "inactive_count": sum(item["state"] == "inactive" for item in findings),
        },
        "findings": findings,
    }
    if authority_document:
        body["evidence_authority"] = authority_document
        body["evidence_authority_sha256"] = _canonical_sha256(authority_document)
    return {**body, "verification_sha256": _canonical_sha256(body)}
