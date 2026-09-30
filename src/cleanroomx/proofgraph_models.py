from __future__ import annotations

from dataclasses import dataclass, field
import copy
import hashlib
import json
import math
from typing import Any


PROOFGRAPH_SCHEMA = "cleanroomx.proofgraph"
PROOFGRAPH_SCHEMA_VERSION = 1

EVIDENCE_KINDS = frozenset(
    {
        "declared",
        "design",
        "calculation",
        "simulation",
        "commissioning",
        "operational",
    }
)
VERDICT_STATUSES = frozenset(
    {"pass", "warning", "fail", "unknown", "indeterminate", "not_checked"}
)


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite number")
    return result


def _json_value(value: Any, field_name: str) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return copy.deepcopy(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _finite_number(value, field_name)
        return copy.deepcopy(value)
    if isinstance(value, list):
        return [
            _json_value(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} object keys must be strings")
            normalized[key] = _json_value(item, f"{field_name}.{key}")
        return normalized
    raise ValueError(f"{field_name} must contain only JSON-compatible values")


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise ValueError(f"{field_name} must be an array of strings")
    normalized = tuple(
        _nonempty(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _check_sha256(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    text = _nonempty(value, field_name)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return text


def _reject_unknown(data: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{context} contains unsupported field(s): {', '.join(unknown)}")


@dataclass(frozen=True, kw_only=True)
class EvidenceSource:
    id: str
    kind: str
    reference: str
    revision: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.id, "evidence_source.id")
        _nonempty(self.kind, "evidence_source.kind")
        _nonempty(self.reference, "evidence_source.reference")
        _optional_text(self.revision, "evidence_source.revision")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "reference": self.reference,
            "revision": self.revision,
        }


@dataclass(frozen=True, kw_only=True)
class ProvenanceRecord:
    id: str
    source_id: str
    origin: str
    upstream_evidence_ids: tuple[str, ...] = ()
    ifc_global_id: str | None = None
    cleanroomx_entity_id: str | None = None
    originating_file: str | None = None
    originating_calculation: str | None = None
    method: str | None = None

    def __post_init__(self) -> None:
        _nonempty(self.id, "provenance.id")
        _nonempty(self.source_id, "provenance.source_id")
        _nonempty(self.origin, "provenance.origin")
        object.__setattr__(
            self,
            "upstream_evidence_ids",
            _string_tuple(self.upstream_evidence_ids, "provenance.upstream_evidence_ids"),
        )
        for name in (
            "ifc_global_id",
            "cleanroomx_entity_id",
            "originating_file",
            "originating_calculation",
            "method",
        ):
            _optional_text(getattr(self, name), f"provenance.{name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "origin": self.origin,
            "upstream_evidence_ids": list(self.upstream_evidence_ids),
            "ifc_global_id": self.ifc_global_id,
            "cleanroomx_entity_id": self.cleanroomx_entity_id,
            "originating_file": self.originating_file,
            "originating_calculation": self.originating_calculation,
            "method": self.method,
        }


@dataclass(frozen=True, kw_only=True)
class ConfidenceRecord:
    confidence: float | None = None
    uncertainty: float | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.confidence is not None:
            confidence = _finite_number(self.confidence, "confidence.confidence")
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence.confidence must be between 0 and 1")
            object.__setattr__(self, "confidence", confidence)
        if self.uncertainty is not None:
            uncertainty = _finite_number(self.uncertainty, "confidence.uncertainty")
            if uncertainty < 0:
                raise ValueError("confidence.uncertainty must be >= 0")
            object.__setattr__(self, "uncertainty", uncertainty)
        object.__setattr__(self, "notes", _string_tuple(self.notes, "confidence.notes"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, kw_only=True)
class Evidence:
    id: str
    property_name: str
    value: Any
    source_id: str
    kind: str = "declared"
    unit: str | None = None
    version: str | None = None
    timestamp: str | None = None
    project_id: str | None = None
    subject_ref: str | None = None
    provenance: tuple[ProvenanceRecord, ...] = ()
    confidence: ConfidenceRecord | None = None

    def __post_init__(self) -> None:
        _nonempty(self.id, "evidence.id")
        _nonempty(self.property_name, "evidence.property_name")
        _nonempty(self.source_id, "evidence.source_id")
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(
                "evidence.kind must be one of: " + ", ".join(sorted(EVIDENCE_KINDS))
            )
        object.__setattr__(self, "value", _json_value(self.value, "evidence.value"))
        for name in ("unit", "version", "timestamp", "project_id", "subject_ref"):
            _optional_text(getattr(self, name), f"evidence.{name}")
        if not isinstance(self.provenance, tuple):
            object.__setattr__(self, "provenance", tuple(self.provenance))
        if not all(isinstance(item, ProvenanceRecord) for item in self.provenance):
            raise ValueError("evidence.provenance must contain ProvenanceRecord values")
        if self.confidence is not None and not isinstance(
            self.confidence, ConfidenceRecord
        ):
            raise ValueError("evidence.confidence must be a ConfidenceRecord")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "property_name": self.property_name,
            "value": copy.deepcopy(self.value),
            "unit": self.unit,
            "source_id": self.source_id,
            "version": self.version,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "subject_ref": self.subject_ref,
            "provenance": [item.to_dict() for item in self.provenance],
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }


@dataclass(frozen=True, kw_only=True)
class DesignEvidence(Evidence):
    kind: str = field(default="design", init=False)


@dataclass(frozen=True, kw_only=True)
class CalculationEvidence(Evidence):
    kind: str = field(default="calculation", init=False)


@dataclass(frozen=True, kw_only=True)
class SimulationEvidence(Evidence):
    kind: str = field(default="simulation", init=False)


@dataclass(frozen=True, kw_only=True)
class CommissioningEvidence(Evidence):
    kind: str = field(default="commissioning", init=False)


@dataclass(frozen=True, kw_only=True)
class OperationalEvidence(Evidence):
    kind: str = field(default="operational", init=False)


@dataclass(frozen=True, kw_only=True)
class Requirement:
    id: str
    title: str
    source: str
    reference: str | None = None
    scope: tuple[str, ...] = ()
    criteria: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty(self.id, "requirement.id")
        _nonempty(self.title, "requirement.title")
        _nonempty(self.source, "requirement.source")
        _optional_text(self.reference, "requirement.reference")
        object.__setattr__(self, "scope", _string_tuple(self.scope, "requirement.scope"))
        object.__setattr__(
            self, "criteria", _json_value(self.criteria, "requirement.criteria")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "reference": self.reference,
            "scope": list(self.scope),
            "criteria": copy.deepcopy(self.criteria),
        }


@dataclass(frozen=True, kw_only=True)
class RequirementSet:
    id: str
    version: str
    title: str
    source: str
    requirements: tuple[Requirement, ...]

    def __post_init__(self) -> None:
        for name in ("id", "version", "title", "source"):
            _nonempty(getattr(self, name), f"requirement_set.{name}")
        if not isinstance(self.requirements, tuple):
            object.__setattr__(self, "requirements", tuple(self.requirements))
        if not self.requirements:
            raise ValueError("requirement_set.requirements must be non-empty")
        if not all(isinstance(item, Requirement) for item in self.requirements):
            raise ValueError("requirement_set.requirements must contain Requirement values")
        ids = [item.id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement_set.requirements contains duplicate ids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "title": self.title,
            "source": self.source,
            "requirements": [item.to_dict() for item in self.requirements],
        }


@dataclass(frozen=True, kw_only=True)
class ComplianceCheck:
    id: str
    requirement_id: str
    evidence_ids: tuple[str, ...] = ()
    required_evidence_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.id, "compliance_check.id")
        _nonempty(self.requirement_id, "compliance_check.requirement_id")
        object.__setattr__(
            self, "evidence_ids", _string_tuple(self.evidence_ids, "compliance_check.evidence_ids")
        )
        kinds = _string_tuple(
            self.required_evidence_kinds, "compliance_check.required_evidence_kinds"
        )
        unknown = sorted(set(kinds) - EVIDENCE_KINDS)
        if unknown:
            raise ValueError(
                "compliance_check.required_evidence_kinds contains unsupported kind(s): "
                + ", ".join(unknown)
            )
        object.__setattr__(self, "required_evidence_kinds", kinds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "evidence_ids": list(self.evidence_ids),
            "required_evidence_kinds": list(self.required_evidence_kinds),
        }


@dataclass(frozen=True, kw_only=True)
class ComplianceFinding:
    id: str
    check_id: str
    requirement_id: str
    status: str
    reason: str
    evidence_ids: tuple[str, ...] = ()
    evidence_present: bool = False
    expected: Any = None
    actual: Any = None
    unit: str | None = None
    delta: float | None = None

    def __post_init__(self) -> None:
        for name in ("id", "check_id", "requirement_id", "reason"):
            _nonempty(getattr(self, name), f"compliance_finding.{name}")
        if self.status not in VERDICT_STATUSES:
            raise ValueError(
                "compliance_finding.status must be one of: "
                + ", ".join(sorted(VERDICT_STATUSES))
            )
        object.__setattr__(
            self, "evidence_ids", _string_tuple(self.evidence_ids, "compliance_finding.evidence_ids")
        )
        if not isinstance(self.evidence_present, bool):
            raise ValueError("compliance_finding.evidence_present must be boolean")
        if self.status == "pass":
            if not self.evidence_present:
                raise ValueError(
                    "pass compliance finding requires evidence_present=true"
                )
            if not self.evidence_ids:
                raise ValueError(
                    "pass compliance finding requires at least one evidence id"
                )
        object.__setattr__(
            self, "expected", _json_value(self.expected, "compliance_finding.expected")
        )
        object.__setattr__(
            self, "actual", _json_value(self.actual, "compliance_finding.actual")
        )
        _optional_text(self.unit, "compliance_finding.unit")
        if self.delta is not None:
            object.__setattr__(
                self, "delta", _finite_number(self.delta, "compliance_finding.delta")
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "check_id": self.check_id,
            "requirement_id": self.requirement_id,
            "status": self.status,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
            "evidence_present": self.evidence_present,
            "expected": copy.deepcopy(self.expected),
            "actual": copy.deepcopy(self.actual),
            "unit": self.unit,
            "delta": self.delta,
        }


@dataclass(frozen=True, kw_only=True)
class ComplianceVerdict:
    id: str
    requirement_id: str
    status: str
    finding_ids: tuple[str, ...]
    reason: str
    confidence: ConfidenceRecord | None = None

    def __post_init__(self) -> None:
        _nonempty(self.id, "compliance_verdict.id")
        _nonempty(self.requirement_id, "compliance_verdict.requirement_id")
        _nonempty(self.reason, "compliance_verdict.reason")
        if self.status not in VERDICT_STATUSES:
            raise ValueError(
                "compliance_verdict.status must be one of: "
                + ", ".join(sorted(VERDICT_STATUSES))
            )
        object.__setattr__(
            self, "finding_ids", _string_tuple(self.finding_ids, "compliance_verdict.finding_ids")
        )
        if not self.finding_ids:
            raise ValueError("compliance_verdict.finding_ids must be non-empty")
        if self.confidence is not None and not isinstance(
            self.confidence, ConfidenceRecord
        ):
            raise ValueError("compliance_verdict.confidence must be a ConfidenceRecord")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "status": self.status,
            "finding_ids": list(self.finding_ids),
            "reason": self.reason,
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }


@dataclass(frozen=True, kw_only=True)
class CorrectiveAction:
    id: str
    requirement_id: str
    title: str
    description: str
    predicted_status: str | None = None
    assumptions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    requires_approval: bool = True

    def __post_init__(self) -> None:
        for name in ("id", "requirement_id", "title", "description"):
            _nonempty(getattr(self, name), f"corrective_action.{name}")
        if self.predicted_status is not None and self.predicted_status not in VERDICT_STATUSES:
            raise ValueError(
                "corrective_action.predicted_status must be one of: "
                + ", ".join(sorted(VERDICT_STATUSES))
            )
        object.__setattr__(
            self, "assumptions", _string_tuple(self.assumptions, "corrective_action.assumptions")
        )
        object.__setattr__(
            self, "evidence_ids", _string_tuple(self.evidence_ids, "corrective_action.evidence_ids")
        )
        if self.requires_approval is not True:
            raise ValueError("corrective_action.requires_approval must remain true")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "title": self.title,
            "description": self.description,
            "predicted_status": self.predicted_status,
            "assumptions": list(self.assumptions),
            "evidence_ids": list(self.evidence_ids),
            "requires_approval": True,
        }


@dataclass(frozen=True, kw_only=True)
class VerificationRun:
    id: str
    requirement_set_id: str
    check_ids: tuple[str, ...]
    verdict_ids: tuple[str, ...]
    timestamp: str | None = None
    input_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty(self.id, "verification_run.id")
        _nonempty(self.requirement_set_id, "verification_run.requirement_set_id")
        object.__setattr__(
            self, "check_ids", _string_tuple(self.check_ids, "verification_run.check_ids")
        )
        object.__setattr__(
            self, "verdict_ids", _string_tuple(self.verdict_ids, "verification_run.verdict_ids")
        )
        if not self.check_ids:
            raise ValueError("verification_run.check_ids must be non-empty")
        if not self.verdict_ids:
            raise ValueError("verification_run.verdict_ids must be non-empty")
        _optional_text(self.timestamp, "verification_run.timestamp")
        object.__setattr__(
            self, "input_sha256", _check_sha256(self.input_sha256, "verification_run.input_sha256")
        )
        object.__setattr__(
            self, "metadata", _json_value(self.metadata, "verification_run.metadata")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "requirement_set_id": self.requirement_set_id,
            "check_ids": list(self.check_ids),
            "verdict_ids": list(self.verdict_ids),
            "timestamp": self.timestamp,
            "input_sha256": self.input_sha256,
            "metadata": copy.deepcopy(self.metadata),
        }


def _unique_ids(items: tuple[Any, ...], context: str) -> set[str]:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{context} contains duplicate ids")
    return set(ids)


def _reject_evidence_dependency_cycles(evidence: tuple[Evidence, ...]) -> None:
    dependencies = {
        item.id: tuple(
            sorted(
                {
                    upstream_id
                    for provenance in item.provenance
                    for upstream_id in provenance.upstream_evidence_ids
                }
            )
        )
        for item in evidence
    }
    states: dict[str, int] = {}

    for evidence_id in sorted(dependencies):
        if states.get(evidence_id, 0) == 2:
            continue

        stack: list[tuple[str, int]] = [(evidence_id, 0)]
        path: list[str] = []
        path_index: dict[str, int] = {}

        while stack:
            current_id, next_dependency_index = stack[-1]
            if states.get(current_id, 0) == 0:
                states[current_id] = 1
                path_index[current_id] = len(path)
                path.append(current_id)

            current_dependencies = dependencies[current_id]
            if next_dependency_index >= len(current_dependencies):
                stack.pop()
                states[current_id] = 2
                path_index.pop(current_id)
                path.pop()
                continue

            upstream_id = current_dependencies[next_dependency_index]
            stack[-1] = (current_id, next_dependency_index + 1)
            upstream_state = states.get(upstream_id, 0)
            if upstream_state == 2:
                continue
            if upstream_state == 1:
                start = path_index[upstream_id]
                cycle = path[start:] + [upstream_id]
                raise ValueError(
                    "proofgraph evidence provenance contains dependency cycle: "
                    + " -> ".join(cycle)
                )
            stack.append((upstream_id, 0))


@dataclass(frozen=True, kw_only=True)
class ProofGraph:
    id: str
    requirement_set: RequirementSet
    evidence_sources: tuple[EvidenceSource, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    checks: tuple[ComplianceCheck, ...] = ()
    findings: tuple[ComplianceFinding, ...] = ()
    verdicts: tuple[ComplianceVerdict, ...] = ()
    corrective_actions: tuple[CorrectiveAction, ...] = ()
    verification_runs: tuple[VerificationRun, ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.id, "proofgraph.id")
        if not isinstance(self.requirement_set, RequirementSet):
            raise ValueError("proofgraph.requirement_set must be a RequirementSet")
        tuple_fields = (
            ("evidence_sources", EvidenceSource),
            ("evidence", Evidence),
            ("checks", ComplianceCheck),
            ("findings", ComplianceFinding),
            ("verdicts", ComplianceVerdict),
            ("corrective_actions", CorrectiveAction),
            ("verification_runs", VerificationRun),
        )
        for name, expected_type in tuple_fields:
            values = getattr(self, name)
            if not isinstance(values, tuple):
                values = tuple(values)
                object.__setattr__(self, name, values)
            if not all(isinstance(item, expected_type) for item in values):
                raise ValueError(f"proofgraph.{name} contains invalid values")

        requirement_ids = {item.id for item in self.requirement_set.requirements}
        source_ids = _unique_ids(self.evidence_sources, "proofgraph.evidence_sources")
        evidence_ids = _unique_ids(self.evidence, "proofgraph.evidence")
        check_ids = _unique_ids(self.checks, "proofgraph.checks")
        finding_ids = _unique_ids(self.findings, "proofgraph.findings")
        verdict_ids = _unique_ids(self.verdicts, "proofgraph.verdicts")
        checks_by_id = {item.id: item for item in self.checks}
        findings_by_id = {item.id: item for item in self.findings}
        verdicts_by_id = {item.id: item for item in self.verdicts}
        _unique_ids(self.corrective_actions, "proofgraph.corrective_actions")
        _unique_ids(self.verification_runs, "proofgraph.verification_runs")

        for item in self.evidence:
            if item.source_id not in source_ids:
                raise ValueError(
                    f"evidence {item.id!r} references unknown source {item.source_id!r}"
                )
            provenance_ids: set[str] = set()
            for provenance in item.provenance:
                if provenance.id in provenance_ids:
                    raise ValueError(
                        f"evidence {item.id!r} contains duplicate provenance id {provenance.id!r}"
                    )
                provenance_ids.add(provenance.id)
                if provenance.source_id not in source_ids:
                    raise ValueError(
                        f"provenance {provenance.id!r} references unknown source "
                        f"{provenance.source_id!r}"
                    )
                if item.id in provenance.upstream_evidence_ids:
                    raise ValueError(
                        f"provenance {provenance.id!r} cannot reference its own evidence"
                    )
                missing = set(provenance.upstream_evidence_ids) - evidence_ids
                if missing:
                    raise ValueError(
                        f"provenance {provenance.id!r} references unknown upstream evidence: "
                        + ", ".join(sorted(missing))
                    )

        _reject_evidence_dependency_cycles(self.evidence)

        explicit_project_ids = sorted(
            {
                item.project_id
                for item in self.evidence
                if item.project_id is not None
            }
        )
        if len(explicit_project_ids) > 1:
            raise ValueError(
                "proofgraph evidence contains multiple explicit project ids: "
                + ", ".join(explicit_project_ids)
            )

        for check in self.checks:
            if check.requirement_id not in requirement_ids:
                raise ValueError(
                    f"check {check.id!r} references unknown requirement "
                    f"{check.requirement_id!r}"
                )
            missing = set(check.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(
                    f"check {check.id!r} references unknown evidence: "
                    + ", ".join(sorted(missing))
                )

        for finding in self.findings:
            if finding.check_id not in check_ids:
                raise ValueError(
                    f"finding {finding.id!r} references unknown check {finding.check_id!r}"
                )
            if finding.requirement_id not in requirement_ids:
                raise ValueError(
                    f"finding {finding.id!r} references unknown requirement "
                    f"{finding.requirement_id!r}"
                )
            check = checks_by_id[finding.check_id]
            if finding.requirement_id != check.requirement_id:
                raise ValueError(
                    f"finding {finding.id!r} requirement {finding.requirement_id!r} "
                    f"does not match check {check.id!r} requirement "
                    f"{check.requirement_id!r}"
                )
            missing = set(finding.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(
                    f"finding {finding.id!r} references unknown evidence: "
                    + ", ".join(sorted(missing))
                )
            undeclared = set(finding.evidence_ids) - set(check.evidence_ids)
            if undeclared:
                raise ValueError(
                    f"finding {finding.id!r} references evidence not declared by "
                    f"check {check.id!r}: " + ", ".join(sorted(undeclared))
                )

        for verdict in self.verdicts:
            if verdict.requirement_id not in requirement_ids:
                raise ValueError(
                    f"verdict {verdict.id!r} references unknown requirement "
                    f"{verdict.requirement_id!r}"
                )
            missing = set(verdict.finding_ids) - finding_ids
            if missing:
                raise ValueError(
                    f"verdict {verdict.id!r} references unknown findings: "
                    + ", ".join(sorted(missing))
                )
            mismatched = sorted(
                finding_id
                for finding_id in verdict.finding_ids
                if findings_by_id[finding_id].requirement_id != verdict.requirement_id
            )
            if mismatched:
                raise ValueError(
                    f"verdict {verdict.id!r} references findings for another "
                    f"requirement: " + ", ".join(mismatched)
                )
            referenced_findings = tuple(
                findings_by_id[finding_id] for finding_id in verdict.finding_ids
            )
            if (
                len(referenced_findings) == 1
                and verdict.status != referenced_findings[0].status
            ):
                raise ValueError(
                    f"verdict {verdict.id!r} status {verdict.status!r} does not "
                    f"match its single finding status {referenced_findings[0].status!r}"
                )

        for action in self.corrective_actions:
            if action.requirement_id not in requirement_ids:
                raise ValueError(
                    f"corrective action {action.id!r} references unknown requirement "
                    f"{action.requirement_id!r}"
                )
            missing = set(action.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(
                    f"corrective action {action.id!r} references unknown evidence: "
                    + ", ".join(sorted(missing))
                )

        for run in self.verification_runs:
            if run.requirement_set_id != self.requirement_set.id:
                raise ValueError(
                    f"verification run {run.id!r} references another requirement set"
                )
            missing_checks = set(run.check_ids) - check_ids
            missing_verdicts = set(run.verdict_ids) - verdict_ids
            if missing_checks:
                raise ValueError(
                    f"verification run {run.id!r} references unknown checks: "
                    + ", ".join(sorted(missing_checks))
                )
            if missing_verdicts:
                raise ValueError(
                    f"verification run {run.id!r} references unknown verdicts: "
                    + ", ".join(sorted(missing_verdicts))
                )
            required_check_ids = {
                findings_by_id[finding_id].check_id
                for verdict_id in run.verdict_ids
                for finding_id in verdicts_by_id[verdict_id].finding_ids
            }
            missing_run_checks = required_check_ids - set(run.check_ids)
            if missing_run_checks:
                raise ValueError(
                    f"verification run {run.id!r} verdicts depend on checks not "
                    "included in the run: " + ", ".join(sorted(missing_run_checks))
                )
            checks_without_verdicts = set(run.check_ids) - required_check_ids
            if checks_without_verdicts:
                raise ValueError(
                    f"verification run {run.id!r} includes checks with no verdict "
                    "outcome: " + ", ".join(sorted(checks_without_verdicts))
                )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema": PROOFGRAPH_SCHEMA,
            "schema_version": PROOFGRAPH_SCHEMA_VERSION,
            "id": self.id,
            "requirement_set": self.requirement_set.to_dict(),
            "evidence_sources": [item.to_dict() for item in self.evidence_sources],
            "evidence": [item.to_dict() for item in self.evidence],
            "checks": [item.to_dict() for item in self.checks],
            "findings": [item.to_dict() for item in self.findings],
            "verdicts": [item.to_dict() for item in self.verdicts],
            "corrective_actions": [
                item.to_dict() for item in self.corrective_actions
            ],
            "verification_runs": [
                item.to_dict() for item in self.verification_runs
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        body = self.body_dict()
        return {**body, "graph_sha256": _canonical_sha256(body)}
