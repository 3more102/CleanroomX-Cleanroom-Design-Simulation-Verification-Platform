from __future__ import annotations

from typing import Any

from .bim_ifc import (
    IFC_SEMANTICS_SCHEMA,
    IFC_SEMANTICS_SCHEMA_VERSION,
    IfcImportError,
    normalize_ifc_semantic_records,
)
from .proofgraph_models import (
    DesignEvidence,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    _check_sha256,
    _nonempty,
)


def _verified_semantics(semantics: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(semantics, dict):
        raise IfcImportError("IFC semantics must be an object")
    if semantics.get("schema") != IFC_SEMANTICS_SCHEMA:
        raise IfcImportError("unsupported IFC semantic schema")
    if semantics.get("schema_version") != IFC_SEMANTICS_SCHEMA_VERSION:
        raise IfcImportError("unsupported IFC semantic schema version")
    records = semantics.get("records")
    if not isinstance(records, list):
        raise IfcImportError("IFC semantics records must be an array")

    checked = normalize_ifc_semantic_records(records)
    expected_digest = semantics.get("semantic_sha256")
    if expected_digest is not None and expected_digest != checked["semantic_sha256"]:
        raise IfcImportError("IFC semantic digest does not match its records")
    return checked


def _unit_for_field(field_name: str) -> str | None:
    if field_name.endswith("_m"):
        return "m"
    if field_name == "orientation_deg":
        return "deg"
    return None


def _method_for_field(record: dict[str, Any], field_name: str) -> str:
    if (
        record["ifc_class"] == "IfcSpace"
        and field_name in {"length_m", "width_m", "height_m"}
    ):
        return record.get("dimension_source") or "ifc_semantic_record"
    return "ifc_semantic_record"


def ifc_design_evidence_bundle(
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
) -> tuple[EvidenceSource, tuple[DesignEvidence, ...]]:
    """Convert verified normalized IFC semantics into traceable design evidence."""
    source_name = _nonempty(source_name, "source_name")
    source_sha256 = _check_sha256(source_sha256, "source_sha256")
    assert source_sha256 is not None

    checked = _verified_semantics(semantics)
    semantic_sha256 = checked["semantic_sha256"]
    source_id = f"source:ifc:{source_sha256[:16]}:{semantic_sha256[:16]}"
    source = EvidenceSource(
        id=source_id,
        kind="ifc",
        reference=source_name,
        revision=source_sha256,
    )

    evidence: list[DesignEvidence] = []
    for record in checked["records"]:
        global_id = record["global_id"]
        ifc_class = record["ifc_class"]
        for field_name in sorted(record):
            if field_name == "global_id":
                continue
            evidence_id = f"ifc:{global_id}:{field_name}"
            evidence.append(
                DesignEvidence(
                    id=evidence_id,
                    property_name=field_name,
                    value=record[field_name],
                    unit=_unit_for_field(field_name),
                    source_id=source_id,
                    version=semantic_sha256,
                    subject_ref=global_id,
                    provenance=(
                        ProvenanceRecord(
                            id=f"provenance:{evidence_id}",
                            source_id=source_id,
                            origin=f"{ifc_class}[{global_id}].{field_name}",
                            ifc_global_id=global_id,
                            originating_file=source_name,
                            method=_method_for_field(record, field_name),
                        ),
                    ),
                )
            )
    return source, tuple(evidence)


def proofgraph_with_ifc_design_evidence(
    graph: ProofGraph,
    semantics: dict[str, Any],
    *,
    source_name: str,
    source_sha256: str,
) -> ProofGraph:
    """Return a new graph with verified IFC design evidence attached."""
    if not isinstance(graph, ProofGraph):
        raise ValueError("graph must be a ProofGraph")

    source, evidence = ifc_design_evidence_bundle(
        semantics,
        source_name=source_name,
        source_sha256=source_sha256,
    )
    existing_source_ids = {item.id for item in graph.evidence_sources}
    if source.id in existing_source_ids:
        raise ValueError(f"IFC evidence source {source.id!r} is already attached")
    existing_evidence_ids = {item.id for item in graph.evidence}
    duplicates = sorted(existing_evidence_ids & {item.id for item in evidence})
    if duplicates:
        raise ValueError(
            "IFC evidence conflicts with existing evidence ids: "
            + ", ".join(duplicates)
        )

    return ProofGraph(
        id=graph.id,
        requirement_set=graph.requirement_set,
        evidence_sources=graph.evidence_sources + (source,),
        evidence=graph.evidence + evidence,
        checks=graph.checks,
        findings=graph.findings,
        verdicts=graph.verdicts,
        corrective_actions=graph.corrective_actions,
        verification_runs=graph.verification_runs,
    )
