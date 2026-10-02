from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .proofgraph_models import (
    CalculationEvidence,
    ConfidenceRecord,
    Evidence,
    EvidenceSource,
    OperationalEvidence,
    ProofGraph,
    ProvenanceRecord,
    _canonical_sha256,
    _nonempty,
    _reject_unknown,
)


_OBSERVATION_FIELDS = {
    "source_record_id",
    "property_name",
    "value",
    "unit",
    "timestamp",
    "subject_ref",
    "uncertainty_abs",
    "cleanroomx_entity_id",
}


def _finite_measurement(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be a finite number")
    return normalized


def _finite_nonnegative(value: Any, field_name: str) -> float:
    normalized = _finite_measurement(value, field_name)
    if normalized < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return normalized


def _aware_timestamp(value: Any, field_name: str) -> tuple[datetime, str]:
    text = _nonempty(value, field_name)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit timezone offset")
    utc_value = parsed.astimezone(timezone.utc)
    canonical = utc_value.isoformat().replace("+00:00", "Z")
    return utc_value, canonical


def _normalized_observation(
    data: Any,
    *,
    index: int,
    assessment_time: datetime,
) -> dict[str, Any]:
    field_name = f"observations[{index}]"
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be an object")
    _reject_unknown(data, _OBSERVATION_FIELDS, field_name)

    cleanroomx_entity_id = data.get("cleanroomx_entity_id")
    if cleanroomx_entity_id is not None:
        cleanroomx_entity_id = _nonempty(
            cleanroomx_entity_id, f"{field_name}.cleanroomx_entity_id"
        )

    observed_time, observed_timestamp = _aware_timestamp(
        data.get("timestamp"), f"{field_name}.timestamp"
    )
    age_seconds = (assessment_time - observed_time).total_seconds()
    if age_seconds < 0:
        raise ValueError(
            f"{field_name}.timestamp must not be later than assessment_timestamp"
        )

    return {
        "source_record_id": _nonempty(
            data.get("source_record_id"), f"{field_name}.source_record_id"
        ),
        "property_name": _nonempty(
            data.get("property_name"), f"{field_name}.property_name"
        ),
        "value": _finite_measurement(data.get("value"), f"{field_name}.value"),
        "unit": _nonempty(data.get("unit"), f"{field_name}.unit"),
        "timestamp": observed_timestamp,
        "subject_ref": _nonempty(
            data.get("subject_ref"), f"{field_name}.subject_ref"
        ),
        "uncertainty_abs": _finite_nonnegative(
            data.get("uncertainty_abs"), f"{field_name}.uncertainty_abs"
        ),
        "cleanroomx_entity_id": cleanroomx_entity_id,
        "age_seconds": age_seconds,
    }


def operational_evidence_bundle(
    observations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    source_kind: str,
    source_reference: str,
    source_revision: str,
    assessment_timestamp: str,
    max_age_seconds: float,
    project_id: str | None = None,
) -> tuple[tuple[EvidenceSource, ...], tuple[Evidence, ...]]:
    """Build operational observations plus deterministic freshness evidence.

    Source identity/revision, observation timestamps, a caller-supplied freshness
    assessment time/window, and absolute measurement uncertainty are mandatory.
    The system clock is never consulted and no compliance verdict is issued here.
    """
    if isinstance(observations, (str, bytes)) or not isinstance(
        observations, (list, tuple)
    ):
        raise ValueError("observations must be an array of objects")
    if not observations:
        raise ValueError("observations must be non-empty")

    source_kind = _nonempty(source_kind, "source_kind")
    source_reference = _nonempty(source_reference, "source_reference")
    source_revision = _nonempty(source_revision, "source_revision")
    if project_id is not None:
        project_id = _nonempty(project_id, "project_id")

    assessment_time, canonical_assessment = _aware_timestamp(
        assessment_timestamp, "assessment_timestamp"
    )
    max_age = _finite_nonnegative(max_age_seconds, "max_age_seconds")

    normalized = [
        _normalized_observation(
            item,
            index=index,
            assessment_time=assessment_time,
        )
        for index, item in enumerate(observations)
    ]
    record_ids = [item["source_record_id"] for item in normalized]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("observations contains duplicate source_record_id values")
    normalized.sort(
        key=lambda item: (
            item["timestamp"],
            item["subject_ref"],
            item["property_name"],
            item["source_record_id"],
        )
    )

    source_identity = _canonical_sha256(
        {
            "kind": source_kind,
            "reference": source_reference,
            "revision": source_revision,
        }
    )
    source_id = f"source:operational:{source_identity[:24]}"
    operational_source = EvidenceSource(
        id=source_id,
        kind=source_kind,
        reference=source_reference,
        revision=source_revision,
    )

    freshness_revision = _canonical_sha256(
        {
            "assessment_timestamp": canonical_assessment,
            "max_age_seconds": max_age,
            "method": "explicit_age_threshold",
        }
    )
    freshness_source_id = f"source:operational-freshness:{freshness_revision[:24]}"
    freshness_source = EvidenceSource(
        id=freshness_source_id,
        kind="cleanroomx_operational_freshness_assessment",
        reference="operational_evidence_bundle",
        revision=freshness_revision,
    )

    evidence: list[Evidence] = []
    for item in normalized:
        observation_identity = _canonical_sha256(
            {
                "source_id": source_id,
                "source_record_id": item["source_record_id"],
            }
        )
        observation_id = f"operational:{observation_identity[:24]}"
        observation = OperationalEvidence(
            id=observation_id,
            property_name=item["property_name"],
            value=item["value"],
            unit=item["unit"],
            source_id=source_id,
            version=source_revision,
            timestamp=item["timestamp"],
            project_id=project_id,
            subject_ref=item["subject_ref"],
            provenance=(
                ProvenanceRecord(
                    id=f"provenance:{observation_id}",
                    source_id=source_id,
                    origin=item["source_record_id"],
                    cleanroomx_entity_id=item["cleanroomx_entity_id"],
                    method="operational_measurement_with_absolute_uncertainty",
                ),
            ),
            confidence=ConfidenceRecord(
                uncertainty=item["uncertainty_abs"],
            ),
        )
        evidence.append(observation)

        freshness_identity = _canonical_sha256(
            {
                "observation_id": observation_id,
                "freshness_revision": freshness_revision,
            }
        )
        freshness_id = f"calculation:operational-freshness:{freshness_identity[:24]}"
        evidence.append(
            CalculationEvidence(
                id=freshness_id,
                property_name="operational_freshness",
                value={
                    "status": (
                        "current"
                        if item["age_seconds"] <= max_age
                        else "stale"
                    ),
                    "age_seconds": item["age_seconds"],
                    "max_age_seconds": max_age,
                    "assessment_timestamp": canonical_assessment,
                    "observation_timestamp": item["timestamp"],
                    "source_record_id": item["source_record_id"],
                },
                source_id=freshness_source_id,
                version=freshness_revision,
                timestamp=canonical_assessment,
                project_id=project_id,
                subject_ref=observation_id,
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance:{freshness_id}",
                        source_id=freshness_source_id,
                        origin="operational_freshness_assessment",
                        upstream_evidence_ids=(observation_id,),
                        originating_calculation="operational_evidence_bundle",
                        method="explicit_age_threshold",
                    ),
                ),
            )
        )

    return (operational_source, freshness_source), tuple(evidence)


def proofgraph_with_operational_evidence(
    graph: ProofGraph,
    observations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    source_kind: str,
    source_reference: str,
    source_revision: str,
    assessment_timestamp: str,
    max_age_seconds: float,
    project_id: str | None = None,
) -> ProofGraph:
    """Return a new graph with operational and freshness evidence attached.

    Existing requirements, checks, findings, verdicts, corrective actions, and
    verification runs are preserved exactly. Freshness evidence is read-only and
    cannot rewrite canonical verification.
    """
    if not isinstance(graph, ProofGraph):
        raise ValueError("graph must be a ProofGraph")

    sources, evidence = operational_evidence_bundle(
        observations,
        source_kind=source_kind,
        source_reference=source_reference,
        source_revision=source_revision,
        assessment_timestamp=assessment_timestamp,
        max_age_seconds=max_age_seconds,
        project_id=project_id,
    )

    existing_sources = {item.id: item for item in graph.evidence_sources}
    added_sources: list[EvidenceSource] = []
    for source in sources:
        existing = existing_sources.get(source.id)
        if existing is not None and existing != source:
            raise ValueError(
                f"operational evidence source {source.id!r} conflicts with existing source"
            )
        if existing is None:
            added_sources.append(source)

    existing_evidence_ids = {item.id for item in graph.evidence}
    duplicates = sorted(existing_evidence_ids & {item.id for item in evidence})
    if duplicates:
        raise ValueError(
            "operational evidence conflicts with existing evidence ids: "
            + ", ".join(duplicates)
        )

    return ProofGraph(
        id=graph.id,
        requirement_set=graph.requirement_set,
        evidence_sources=graph.evidence_sources + tuple(added_sources),
        evidence=graph.evidence + evidence,
        checks=graph.checks,
        findings=graph.findings,
        verdicts=graph.verdicts,
        corrective_actions=graph.corrective_actions,
        verification_runs=graph.verification_runs,
    )
