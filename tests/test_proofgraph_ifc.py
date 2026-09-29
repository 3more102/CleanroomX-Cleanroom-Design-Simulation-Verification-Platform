from __future__ import annotations

import copy

import pytest

from cleanroomx.bim_ifc import IfcImportError, normalize_ifc_semantic_records
from cleanroomx.proofgraph import (
    ProofGraph,
    Requirement,
    RequirementSet,
    ifc_design_evidence_bundle,
    proofgraph_from_dict,
    proofgraph_with_ifc_design_evidence,
)


def _records() -> list[dict]:
    return [
        {
            "global_id": "SPACE-001",
            "ifc_class": "IfcSpace",
            "name": "ISO 7 Process",
            "x_m": 1.0,
            "y_m": 2.0,
            "z_m": 0.0,
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
            "dimension_source": "ifcopenshell_geometry",
            "classification": "ISO 7",
            "analysis_room_name": "Process",
            "storey_global_id": "STOREY-01",
            "storey_name": "Level 1",
            "storey_elevation_m": 0.0,
        },
        {
            "global_id": "AT-001",
            "ifc_class": "IfcAirTerminal",
            "name": "Supply 01",
            "room_global_id": "SPACE-001",
            "predefined_type": "SUPPLYAIR",
            "x_m": 2.0,
            "y_m": 3.0,
            "z_m": 2.8,
            "orientation_deg": 90.0,
        },
    ]


def _semantics() -> dict:
    return normalize_ifc_semantic_records(_records())


def _graph() -> ProofGraph:
    requirement = Requirement(
        id="REQ-1",
        title="Project requirement",
        source="Project URS",
        criteria={"operator": "exists"},
    )
    return ProofGraph(
        id="graph-1",
        requirement_set=RequirementSet(
            id="urs",
            version="1.0",
            title="Project URS",
            source="Project URS",
            requirements=(requirement,),
        ),
    )


def _by_subject_and_property(document: dict, subject: str, property_name: str) -> dict:
    return next(
        item
        for item in document["evidence"]
        if item["subject_ref"] == subject and item["property_name"] == property_name
    )


def test_ifc_bundle_preserves_space_dimension_provenance() -> None:
    source, evidence = ifc_design_evidence_bundle(
        _semantics(),
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )

    document = [item.to_dict() for item in evidence]
    length = next(
        item
        for item in document
        if item["subject_ref"] == "SPACE-001"
        and item["property_name"] == "length_m"
    )

    assert source.kind == "ifc"
    assert source.reference == "facility.ifc"
    assert source.revision == "a" * 64
    assert length["kind"] == "design"
    assert length["value"] == pytest.approx(6.0)
    assert length["unit"] == "m"
    assert length["version"] == _semantics()["semantic_sha256"]
    assert length["provenance"][0]["ifc_global_id"] == "SPACE-001"
    assert length["provenance"][0]["method"] == "ifcopenshell_geometry"
    assert length["provenance"][0]["originating_file"] == "facility.ifc"


def test_ifc_bundle_preserves_storey_device_and_orientation_semantics() -> None:
    _, evidence = ifc_design_evidence_bundle(
        _semantics(),
        source_name="facility.ifc",
        source_sha256="b" * 64,
    )
    document = {"evidence": [item.to_dict() for item in evidence]}

    room_link = _by_subject_and_property(document, "AT-001", "room_global_id")
    orientation = _by_subject_and_property(document, "AT-001", "orientation_deg")
    storey = _by_subject_and_property(document, "SPACE-001", "storey_global_id")

    assert room_link["value"] == "SPACE-001"
    assert orientation["value"] == pytest.approx(90.0)
    assert orientation["unit"] == "deg"
    assert storey["value"] == "STOREY-01"


def test_ifc_evidence_attachment_preserves_existing_graph_results() -> None:
    baseline = _graph()
    baseline_digest = baseline.to_dict()["graph_sha256"]

    enriched = proofgraph_with_ifc_design_evidence(
        baseline,
        _semantics(),
        source_name="facility.ifc",
        source_sha256="c" * 64,
    )
    document = enriched.to_dict()

    assert enriched.requirement_set == baseline.requirement_set
    assert enriched.checks == baseline.checks
    assert enriched.verdicts == baseline.verdicts
    assert len(document["evidence_sources"]) == 1
    assert len(document["evidence"]) > 0
    assert document["graph_sha256"] != baseline_digest


def test_enriched_ifc_graph_round_trips_through_strict_parser() -> None:
    document = proofgraph_with_ifc_design_evidence(
        _graph(),
        _semantics(),
        source_name="facility.ifc",
        source_sha256="d" * 64,
    ).to_dict()

    restored = proofgraph_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document


def test_ifc_semantic_digest_tampering_is_rejected() -> None:
    semantics = _semantics()
    semantics["semantic_sha256"] = "0" * 64

    with pytest.raises(IfcImportError, match="semantic digest"):
        ifc_design_evidence_bundle(
            semantics,
            source_name="facility.ifc",
            source_sha256="e" * 64,
        )


def test_ifc_source_sha_must_be_explicit_valid_sha256() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ifc_design_evidence_bundle(
            _semantics(),
            source_name="facility.ifc",
            source_sha256="not-a-digest",
        )


def test_ifc_evidence_rejects_duplicate_attachment() -> None:
    enriched = proofgraph_with_ifc_design_evidence(
        _graph(),
        _semantics(),
        source_name="facility.ifc",
        source_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="already attached"):
        proofgraph_with_ifc_design_evidence(
            enriched,
            _semantics(),
            source_name="facility.ifc",
            source_sha256="f" * 64,
        )
