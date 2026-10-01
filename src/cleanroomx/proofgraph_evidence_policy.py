from __future__ import annotations

from dataclasses import dataclass
import copy
import json
from typing import Any

from .proofgraph_models import EVIDENCE_KINDS, Evidence, ProofGraph


EVIDENCE_PRECEDENCE_SCHEMA = "cleanroomx.proofgraph-evidence-precedence"
EVIDENCE_PRECEDENCE_SCHEMA_VERSION = 1
EVIDENCE_PRECEDENCE_DECISION_SCOPE = "assessment_only"
EVIDENCE_RESOLUTION_STATUSES = frozenset(
    {"single", "selected", "equivalent", "conflict"}
)


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _ordered_unique_strings(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise ValueError(f"{field_name} must be an array of strings")
    normalized = tuple(
        _nonempty_text(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return normalized


@dataclass(frozen=True, kw_only=True)
class EvidencePrecedencePolicy:
    """Explicit strongest-first evidence precedence for one assessment."""

    id: str
    kind_precedence: tuple[str, ...] = ()
    source_precedence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _nonempty_text(self.id, "evidence_precedence_policy.id")
        kinds = _ordered_unique_strings(
            self.kind_precedence,
            "evidence_precedence_policy.kind_precedence",
        )
        unknown = sorted(set(kinds) - EVIDENCE_KINDS)
        if unknown:
            raise ValueError(
                "evidence_precedence_policy.kind_precedence contains unsupported "
                "kind(s): " + ", ".join(unknown)
            )
        sources = _ordered_unique_strings(
            self.source_precedence,
            "evidence_precedence_policy.source_precedence",
        )
        object.__setattr__(self, "kind_precedence", kinds)
        object.__setattr__(self, "source_precedence", sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind_precedence": list(self.kind_precedence),
            "source_precedence": list(self.source_precedence),
        }


@dataclass(frozen=True, kw_only=True)
class EvidenceResolution:
    subject_ref: str | None
    property_name: str
    candidates: tuple[Evidence, ...]
    preferred: tuple[Evidence, ...]
    status: str
    selected_evidence_id: str | None
    reason: str

    def __post_init__(self) -> None:
        _nonempty_text(self.property_name, "evidence_resolution.property_name")
        if self.status not in EVIDENCE_RESOLUTION_STATUSES:
            raise ValueError(
                "evidence_resolution.status must be one of: "
                + ", ".join(sorted(EVIDENCE_RESOLUTION_STATUSES))
            )
        if not self.candidates:
            raise ValueError("evidence_resolution.candidates must be non-empty")
        candidate_ids = {item.id for item in self.candidates}
        preferred_ids = {item.id for item in self.preferred}
        if not preferred_ids or not preferred_ids <= candidate_ids:
            raise ValueError(
                "evidence_resolution.preferred must be a non-empty subset of candidates"
            )
        if self.selected_evidence_id is not None:
            _nonempty_text(
                self.selected_evidence_id,
                "evidence_resolution.selected_evidence_id",
            )
            if self.selected_evidence_id not in preferred_ids:
                raise ValueError(
                    "evidence_resolution.selected_evidence_id must reference "
                    "preferred evidence"
                )
        _nonempty_text(self.reason, "evidence_resolution.reason")

    @staticmethod
    def _evidence_summary(item: Evidence) -> dict[str, Any]:
        return {
            "id": item.id,
            "kind": item.kind,
            "source_id": item.source_id,
            "value": copy.deepcopy(item.value),
            "unit": item.unit,
            "version": item.version,
            "timestamp": item.timestamp,
            "project_id": item.project_id,
            "subject_ref": item.subject_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        preferred_ids = {item.id for item in self.preferred}
        return {
            "subject_ref": self.subject_ref,
            "property_name": self.property_name,
            "status": self.status,
            "selected_evidence_id": self.selected_evidence_id,
            "preferred_evidence_ids": sorted(preferred_ids),
            "shadowed_evidence_ids": sorted(
                item.id for item in self.candidates if item.id not in preferred_ids
            ),
            "reason": self.reason,
            "candidates": [
                self._evidence_summary(item)
                for item in sorted(self.candidates, key=lambda candidate: candidate.id)
            ],
        }


@dataclass(frozen=True, kw_only=True)
class EvidencePrecedenceReport:
    policy: EvidencePrecedencePolicy
    resolutions: tuple[EvidenceResolution, ...]

    @property
    def has_conflicts(self) -> bool:
        return any(item.status == "conflict" for item in self.resolutions)

    def to_dict(self) -> dict[str, Any]:
        counts = {
            status: sum(item.status == status for item in self.resolutions)
            for status in sorted(EVIDENCE_RESOLUTION_STATUSES)
        }
        return {
            "schema": EVIDENCE_PRECEDENCE_SCHEMA,
            "schema_version": EVIDENCE_PRECEDENCE_SCHEMA_VERSION,
            "decision_scope": EVIDENCE_PRECEDENCE_DECISION_SCOPE,
            "changes_canonical_verification": False,
            "policy": self.policy.to_dict(),
            "has_conflicts": self.has_conflicts,
            "counts": counts,
            "resolutions": [item.to_dict() for item in self.resolutions],
        }


def _claim_signature(item: Evidence) -> str:
    return json.dumps(
        {"unit": item.unit, "value": item.value},
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _precedence_rank(
    item: Evidence,
    *,
    kind_rank: dict[str, int],
    source_rank: dict[str, int],
) -> tuple[int, int]:
    return (
        kind_rank.get(item.kind, len(kind_rank)),
        source_rank.get(item.source_id, len(source_rank)),
    )


def assess_evidence_precedence(
    graph: ProofGraph,
    policy: EvidencePrecedencePolicy,
) -> EvidencePrecedenceReport:
    """Assess competing evidence claims without mutating or deleting graph history.

    Evidence is grouped by subject reference and engineering property. The policy
    is strongest-first by evidence kind and then source id. Unlisted kinds/sources
    rank after explicitly listed entries. No unit conversion, timestamp inference,
    confidence weighting, or solver recomputation is performed.

    This report is assessment-only. A selected_evidence_id identifies the preferred
    claim inside this precedence assessment; it does not authorize that evidence
    for canonical project-requirements verification and cannot change an existing
    ProofGraph finding or verdict.
    """
    if not isinstance(graph, ProofGraph):
        raise ValueError("graph must be a ProofGraph")
    if not isinstance(policy, EvidencePrecedencePolicy):
        raise ValueError("policy must be an EvidencePrecedencePolicy")

    kind_rank = {
        kind: index for index, kind in enumerate(policy.kind_precedence)
    }
    source_rank = {
        source_id: index
        for index, source_id in enumerate(policy.source_precedence)
    }

    grouped: dict[tuple[str | None, str], list[Evidence]] = {}
    for item in graph.evidence:
        grouped.setdefault((item.subject_ref, item.property_name), []).append(item)

    resolutions: list[EvidenceResolution] = []
    for (subject_ref, property_name), candidates in sorted(
        grouped.items(),
        key=lambda entry: (
            entry[0][0] is not None,
            entry[0][0] or "",
            entry[0][1],
        ),
    ):
        ordered = tuple(sorted(candidates, key=lambda item: item.id))
        ranked = {
            item.id: _precedence_rank(
                item,
                kind_rank=kind_rank,
                source_rank=source_rank,
            )
            for item in ordered
        }
        best_rank = min(ranked.values())
        preferred = tuple(
            item for item in ordered if ranked[item.id] == best_rank
        )

        if len(ordered) == 1:
            status = "single"
            selected = ordered[0].id
            reason = "Only one evidence claim exists for this subject/property."
        elif len(preferred) == 1:
            status = "selected"
            selected = preferred[0].id
            reason = (
                "Explicit kind/source precedence selected one preferred claim; "
                "all lower-precedence evidence remains retained."
            )
        elif len({_claim_signature(item) for item in preferred}) == 1:
            status = "equivalent"
            selected = None
            reason = (
                "Multiple equally preferred claims carry the same value and unit; "
                "no single claim is promoted over its peers."
            )
        else:
            status = "conflict"
            selected = None
            reason = (
                "Multiple equally preferred claims disagree in value and/or unit; "
                "the conflict remains unresolved and no claim is promoted."
            )

        resolutions.append(
            EvidenceResolution(
                subject_ref=subject_ref,
                property_name=property_name,
                candidates=ordered,
                preferred=preferred,
                status=status,
                selected_evidence_id=selected,
                reason=reason,
            )
        )

    return EvidencePrecedenceReport(
        policy=policy,
        resolutions=tuple(resolutions),
    )
