from __future__ import annotations

import copy

import pytest

from cleanroomx.compliance_rulepack import compliance_check_from_dict
from cleanroomx.proofgraph import (
    CalculationEvidence,
    CommissioningEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    ConfidenceRecord,
    CorrectiveAction,
    DesignEvidence,
    EvidenceSource,
    OperationalEvidence,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    SimulationEvidence,
    VerificationRun,
    proofgraph_from_compliance_check,
    proofgraph_from_dict,
)


def _graph() -> ProofGraph:
    source = EvidenceSource(
        id="src-design",
        kind="ifc",
        reference="facility.ifc",
        revision="a" * 64,
    )
    requirement = Requirement(
        id="CRX-PRESS-001",
        title="Positive pressure relationship",
        source="Project URS",
        reference="URS-7.2",
        scope=("ROOM-A", "CORRIDOR-B"),
        criteria={"operator": "min", "expected": 10.0, "unit": "Pa"},
    )
    evidence = DesignEvidence(
        id="ev-pressure",
        property_name="pressure_differential_pa",
        value=13.6,
        unit="Pa",
        source_id=source.id,
        project_id="PROJECT-1",
        subject_ref="ROOM-A->CORRIDOR-B",
        provenance=(
            ProvenanceRecord(
                id="prov-pressure",
                source_id=source.id,
                origin="/spaces/ROOM-A/pressure_target_pa",
                ifc_global_id="SPACE-GLOBAL-ID",
                cleanroomx_entity_id="ROOM-A",
                originating_file="facility.ifc",
                method="ifc_property",
            ),
        ),
        confidence=ConfidenceRecord(
            confidence=0.97,
            uncertainty=0.4,
            notes=("design evidence",),
        ),
    )
    check = ComplianceCheck(
        id="check-pressure",
        requirement_id=requirement.id,
        evidence_ids=(evidence.id,),
        required_evidence_kinds=("design",),
    )
    finding = ComplianceFinding(
        id="finding-pressure",
        check_id=check.id,
        requirement_id=requirement.id,
        status="pass",
        reason="Design pressure exceeds the declared project minimum.",
        evidence_ids=(evidence.id,),
        evidence_present=True,
        expected=10.0,
        actual=13.6,
        unit="Pa",
        delta=3.6,
    )
    verdict = ComplianceVerdict(
        id="verdict-pressure",
        requirement_id=requirement.id,
        status="pass",
        finding_ids=(finding.id,),
        reason=finding.reason,
        confidence=evidence.confidence,
    )
    run = VerificationRun(
        id="run-001",
        requirement_set_id="project-urs",
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
        input_sha256="b" * 64,
        metadata={"mode": "design"},
    )
    return ProofGraph(
        id="project-1-proofgraph",
        requirement_set=RequirementSet(
            id="project-urs",
            version="1.0",
            title="Project URS",
            source="Approved project requirement set",
            requirements=(requirement,),
        ),
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    )


def _compliance_payload() -> dict:
    return {
        "name": "Pressure evidence",
        "rule_pack": {
            "schema": "cleanroomx.compliance-rule-pack",
            "schema_version": 1,
            "id": "project-urs",
            "version": "1.0",
            "title": "Project URS",
            "source": "Approved project requirement set",
            "rules": [
                {
                    "id": "pressure",
                    "title": "Room differential pressure",
                    "evidence_path": "/room/pressure_pa",
                    "operator": "min",
                    "expected": 10.0,
                    "unit": "Pa",
                    "reference": "URS-7.2",
                }
            ],
        },
        "evidence": {"room": {"pressure_pa": 13.6}},
    }


def test_graph_round_trip_preserves_canonical_digest() -> None:
    graph = _graph()
    document = graph.to_dict()

    restored = proofgraph_from_dict(copy.deepcopy(document))

    assert restored.to_dict() == document
    assert len(document["graph_sha256"]) == 64


def test_typed_evidence_layers_have_explicit_kind() -> None:
    common = {
        "id": "e",
        "property_name": "x",
        "value": 1.0,
        "source_id": "source",
    }

    assert DesignEvidence(**common).kind == "design"
    assert CalculationEvidence(**common).kind == "calculation"
    assert SimulationEvidence(**common).kind == "simulation"
    assert CommissioningEvidence(**common).kind == "commissioning"
    assert OperationalEvidence(**common).kind == "operational"


def test_graph_fails_closed_on_dangling_evidence_source() -> None:
    graph = _graph()
    broken = copy.deepcopy(graph.to_dict())
    broken["evidence"][0]["source_id"] = "missing"
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="unknown source"):
        proofgraph_from_dict(broken)


def test_graph_digest_detects_tampering() -> None:
    document = _graph().to_dict()
    document["evidence"][0]["value"] = 7.0

    with pytest.raises(ValueError, match="graph_sha256 does not match"):
        proofgraph_from_dict(document)


def test_non_finite_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite number"):
        DesignEvidence(
            id="ev",
            property_name="pressure",
            value=float("nan"),
            source_id="src",
        )


def test_corrective_actions_cannot_bypass_user_approval() -> None:
    with pytest.raises(ValueError, match="requires_approval must remain true"):
        CorrectiveAction(
            id="action-1",
            requirement_id="req-1",
            title="Increase supply",
            description="Increase supply airflow.",
            requires_approval=False,
        )


def test_existing_compliance_rulepack_maps_into_proofgraph() -> None:
    graph = proofgraph_from_compliance_check(
        compliance_check_from_dict(_compliance_payload())
    )
    document = graph.to_dict()

    assert document["requirement_set"]["id"] == "project-urs"
    assert document["evidence"][0]["kind"] == "declared"
    assert document["evidence"][0]["property_name"] == "/room/pressure_pa"
    assert document["verdicts"][0]["status"] == "pass"
    assert document["findings"][0]["actual"] == pytest.approx(13.6)
    assert len(document["verification_runs"][0]["input_sha256"]) == 64
    assert len(document["graph_sha256"]) == 64


def test_missing_compliance_evidence_preserves_not_checked_without_fabrication() -> None:
    payload = _compliance_payload()
    payload["evidence"] = {"room": {}}

    graph = proofgraph_from_compliance_check(compliance_check_from_dict(payload))
    document = graph.to_dict()

    assert document["evidence"] == []
    assert document["checks"][0]["evidence_ids"] == []
    assert document["findings"][0]["status"] == "not_checked"
    assert document["findings"][0]["evidence_present"] is False
    assert document["verdicts"][0]["status"] == "not_checked"
    assert document["verification_runs"][0]["metadata"]["source_status"] == "not_checked"
    assert proofgraph_from_dict(copy.deepcopy(document)).to_dict() == document


def test_evidence_revision_changes_proofgraph_identity() -> None:
    baseline = proofgraph_from_compliance_check(
        compliance_check_from_dict(_compliance_payload())
    ).to_dict()

    revised_payload = _compliance_payload()
    revised_payload["evidence"]["room"]["pressure_pa"] = 14.0
    revised = proofgraph_from_compliance_check(
        compliance_check_from_dict(revised_payload)
    ).to_dict()

    assert baseline["verdicts"][0]["status"] == revised["verdicts"][0]["status"] == "pass"
    assert baseline["evidence_sources"][0]["revision"] != revised["evidence_sources"][0]["revision"]
    assert baseline["graph_sha256"] != revised["graph_sha256"]
