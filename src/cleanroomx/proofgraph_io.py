from __future__ import annotations

from typing import Any

from .proofgraph_models import (
    PROOFGRAPH_SCHEMA,
    PROOFGRAPH_SCHEMA_VERSION,
    CalculationEvidence,
    CommissioningEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    ConfidenceRecord,
    CorrectiveAction,
    DesignEvidence,
    Evidence,
    EvidenceSource,
    OperationalEvidence,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    SimulationEvidence,
    VerificationRun,
    _check_sha256,
    _reject_unknown,
    _string_tuple,
)


def _confidence_from_dict(data: Any, field_name: str) -> ConfidenceRecord | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be an object or null")
    _reject_unknown(data, {"confidence", "uncertainty", "notes"}, field_name)
    return ConfidenceRecord(
        confidence=data.get("confidence"),
        uncertainty=data.get("uncertainty"),
        notes=_string_tuple(data.get("notes", []), f"{field_name}.notes"),
    )


def _provenance_from_dict(data: Any, field_name: str) -> ProvenanceRecord:
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be an object")
    allowed = {
        "id",
        "source_id",
        "origin",
        "upstream_evidence_ids",
        "ifc_global_id",
        "cleanroomx_entity_id",
        "originating_file",
        "originating_calculation",
        "method",
    }
    _reject_unknown(data, allowed, field_name)
    return ProvenanceRecord(
        id=data.get("id"),
        source_id=data.get("source_id"),
        origin=data.get("origin"),
        upstream_evidence_ids=_string_tuple(
            data.get("upstream_evidence_ids", []),
            f"{field_name}.upstream_evidence_ids",
        ),
        ifc_global_id=data.get("ifc_global_id"),
        cleanroomx_entity_id=data.get("cleanroomx_entity_id"),
        originating_file=data.get("originating_file"),
        originating_calculation=data.get("originating_calculation"),
        method=data.get("method"),
    )


def _evidence_from_dict(data: Any, field_name: str) -> Evidence:
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be an object")
    allowed = {
        "id",
        "kind",
        "property_name",
        "value",
        "unit",
        "source_id",
        "version",
        "timestamp",
        "project_id",
        "subject_ref",
        "provenance",
        "confidence",
    }
    _reject_unknown(data, allowed, field_name)
    kind = data.get("kind")
    if not isinstance(kind, str):
        raise ValueError(f"{field_name}.kind must be a string")
    raw_provenance = data.get("provenance", [])
    if not isinstance(raw_provenance, list):
        raise ValueError(f"{field_name}.provenance must be an array")
    classes = {
        "design": DesignEvidence,
        "calculation": CalculationEvidence,
        "simulation": SimulationEvidence,
        "commissioning": CommissioningEvidence,
        "operational": OperationalEvidence,
    }
    cls = classes.get(kind, Evidence)
    kwargs = {
        "id": data.get("id"),
        "property_name": data.get("property_name"),
        "value": data.get("value"),
        "source_id": data.get("source_id"),
        "unit": data.get("unit"),
        "version": data.get("version"),
        "timestamp": data.get("timestamp"),
        "project_id": data.get("project_id"),
        "subject_ref": data.get("subject_ref"),
        "provenance": tuple(
            _provenance_from_dict(item, f"{field_name}.provenance[{index}]")
            for index, item in enumerate(raw_provenance)
        ),
        "confidence": _confidence_from_dict(
            data.get("confidence"), f"{field_name}.confidence"
        ),
    }
    if cls is Evidence:
        kwargs["kind"] = kind
    return cls(**kwargs)


def proofgraph_from_dict(data: dict[str, Any]) -> ProofGraph:
    if not isinstance(data, dict):
        raise ValueError("proofgraph must be an object")
    allowed = {
        "schema",
        "schema_version",
        "id",
        "requirement_set",
        "evidence_sources",
        "evidence",
        "checks",
        "findings",
        "verdicts",
        "corrective_actions",
        "verification_runs",
        "graph_sha256",
    }
    _reject_unknown(data, allowed, "proofgraph")
    if data.get("schema") != PROOFGRAPH_SCHEMA:
        raise ValueError(f"proofgraph.schema must be {PROOFGRAPH_SCHEMA!r}")
    if data.get("schema_version") != PROOFGRAPH_SCHEMA_VERSION:
        raise ValueError(
            f"proofgraph.schema_version must be {PROOFGRAPH_SCHEMA_VERSION}"
        )

    requirement_set_data = data.get("requirement_set")
    if not isinstance(requirement_set_data, dict):
        raise ValueError("proofgraph.requirement_set must be an object")
    _reject_unknown(
        requirement_set_data,
        {"id", "version", "title", "source", "requirements"},
        "proofgraph.requirement_set",
    )
    raw_requirements = requirement_set_data.get("requirements")
    if not isinstance(raw_requirements, list):
        raise ValueError("proofgraph.requirement_set.requirements must be an array")
    requirements: list[Requirement] = []
    for index, raw in enumerate(raw_requirements):
        field_name = f"proofgraph.requirement_set.requirements[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            raw,
            {"id", "title", "source", "reference", "scope", "criteria"},
            field_name,
        )
        requirements.append(
            Requirement(
                id=raw.get("id"),
                title=raw.get("title"),
                source=raw.get("source"),
                reference=raw.get("reference"),
                scope=_string_tuple(raw.get("scope", []), f"{field_name}.scope"),
                criteria=raw.get("criteria", {}),
            )
        )
    requirement_set = RequirementSet(
        id=requirement_set_data.get("id"),
        version=requirement_set_data.get("version"),
        title=requirement_set_data.get("title"),
        source=requirement_set_data.get("source"),
        requirements=tuple(requirements),
    )

    raw_sources = data.get("evidence_sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("proofgraph.evidence_sources must be an array")
    sources: list[EvidenceSource] = []
    for index, raw in enumerate(raw_sources):
        field_name = f"proofgraph.evidence_sources[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(raw, {"id", "kind", "reference", "revision"}, field_name)
        sources.append(
            EvidenceSource(
                id=raw.get("id"),
                kind=raw.get("kind"),
                reference=raw.get("reference"),
                revision=raw.get("revision"),
            )
        )

    raw_evidence = data.get("evidence", [])
    if not isinstance(raw_evidence, list):
        raise ValueError("proofgraph.evidence must be an array")
    evidence = tuple(
        _evidence_from_dict(raw, f"proofgraph.evidence[{index}]")
        for index, raw in enumerate(raw_evidence)
    )

    raw_checks = data.get("checks", [])
    if not isinstance(raw_checks, list):
        raise ValueError("proofgraph.checks must be an array")
    checks: list[ComplianceCheck] = []
    for index, raw in enumerate(raw_checks):
        field_name = f"proofgraph.checks[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            raw,
            {"id", "requirement_id", "evidence_ids", "required_evidence_kinds"},
            field_name,
        )
        checks.append(
            ComplianceCheck(
                id=raw.get("id"),
                requirement_id=raw.get("requirement_id"),
                evidence_ids=_string_tuple(
                    raw.get("evidence_ids", []), f"{field_name}.evidence_ids"
                ),
                required_evidence_kinds=_string_tuple(
                    raw.get("required_evidence_kinds", []),
                    f"{field_name}.required_evidence_kinds",
                ),
            )
        )

    raw_findings = data.get("findings", [])
    if not isinstance(raw_findings, list):
        raise ValueError("proofgraph.findings must be an array")
    findings: list[ComplianceFinding] = []
    for index, raw in enumerate(raw_findings):
        field_name = f"proofgraph.findings[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            raw,
            {
                "id",
                "check_id",
                "requirement_id",
                "status",
                "reason",
                "evidence_ids",
                "evidence_present",
                "expected",
                "actual",
                "unit",
                "delta",
            },
            field_name,
        )
        findings.append(
            ComplianceFinding(
                id=raw.get("id"),
                check_id=raw.get("check_id"),
                requirement_id=raw.get("requirement_id"),
                status=raw.get("status"),
                reason=raw.get("reason"),
                evidence_ids=_string_tuple(
                    raw.get("evidence_ids", []), f"{field_name}.evidence_ids"
                ),
                evidence_present=raw.get("evidence_present"),
                expected=raw.get("expected"),
                actual=raw.get("actual"),
                unit=raw.get("unit"),
                delta=raw.get("delta"),
            )
        )

    raw_verdicts = data.get("verdicts", [])
    if not isinstance(raw_verdicts, list):
        raise ValueError("proofgraph.verdicts must be an array")
    verdicts: list[ComplianceVerdict] = []
    for index, raw in enumerate(raw_verdicts):
        field_name = f"proofgraph.verdicts[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            raw,
            {"id", "requirement_id", "status", "finding_ids", "reason", "confidence"},
            field_name,
        )
        verdicts.append(
            ComplianceVerdict(
                id=raw.get("id"),
                requirement_id=raw.get("requirement_id"),
                status=raw.get("status"),
                finding_ids=_string_tuple(
                    raw.get("finding_ids", []), f"{field_name}.finding_ids"
                ),
                reason=raw.get("reason"),
                confidence=_confidence_from_dict(
                    raw.get("confidence"), f"{field_name}.confidence"
                ),
            )
        )

    raw_actions = data.get("corrective_actions", [])
    if not isinstance(raw_actions, list):
        raise ValueError("proofgraph.corrective_actions must be an array")
    actions: list[CorrectiveAction] = []
    for index, raw in enumerate(raw_actions):
        field_name = f"proofgraph.corrective_actions[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            raw,
            {
                "id",
                "requirement_id",
                "title",
                "description",
                "predicted_status",
                "assumptions",
                "evidence_ids",
                "requires_approval",
            },
            field_name,
        )
        actions.append(
            CorrectiveAction(
                id=raw.get("id"),
                requirement_id=raw.get("requirement_id"),
                title=raw.get("title"),
                description=raw.get("description"),
                predicted_status=raw.get("predicted_status"),
                assumptions=_string_tuple(
                    raw.get("assumptions", []), f"{field_name}.assumptions"
                ),
                evidence_ids=_string_tuple(
                    raw.get("evidence_ids", []), f"{field_name}.evidence_ids"
                ),
                requires_approval=raw.get("requires_approval"),
            )
        )

    raw_runs = data.get("verification_runs", [])
    if not isinstance(raw_runs, list):
        raise ValueError("proofgraph.verification_runs must be an array")
    runs: list[VerificationRun] = []
    for index, raw in enumerate(raw_runs):
        field_name = f"proofgraph.verification_runs[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be an object")
        _reject_unknown(
            raw,
            {
                "id",
                "requirement_set_id",
                "check_ids",
                "verdict_ids",
                "timestamp",
                "input_sha256",
                "metadata",
            },
            field_name,
        )
        runs.append(
            VerificationRun(
                id=raw.get("id"),
                requirement_set_id=raw.get("requirement_set_id"),
                check_ids=_string_tuple(
                    raw.get("check_ids", []), f"{field_name}.check_ids"
                ),
                verdict_ids=_string_tuple(
                    raw.get("verdict_ids", []), f"{field_name}.verdict_ids"
                ),
                timestamp=raw.get("timestamp"),
                input_sha256=raw.get("input_sha256"),
                metadata=raw.get("metadata", {}),
            )
        )

    graph = ProofGraph(
        id=data.get("id"),
        requirement_set=requirement_set,
        evidence_sources=tuple(sources),
        evidence=evidence,
        checks=tuple(checks),
        findings=tuple(findings),
        verdicts=tuple(verdicts),
        corrective_actions=tuple(actions),
        verification_runs=tuple(runs),
    )
    recorded = data.get("graph_sha256")
    if recorded is not None:
        _check_sha256(recorded, "proofgraph.graph_sha256")
        actual = graph.to_dict()["graph_sha256"]
        if recorded != actual:
            raise ValueError("proofgraph.graph_sha256 does not match graph content")
    return graph
