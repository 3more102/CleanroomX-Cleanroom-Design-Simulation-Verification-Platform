from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json

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


def test_graph_rejects_provenance_dependency_cycles() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    derived = copy.deepcopy(broken["evidence"][0])
    derived["id"] = "ev-pressure-derived"
    derived["property_name"] = "derived_pressure_margin_pa"
    derived["provenance"][0]["id"] = "prov-pressure-derived"
    derived["provenance"][0]["origin"] = "derived from ev-pressure"
    derived["provenance"][0]["upstream_evidence_ids"] = ["ev-pressure"]
    broken["evidence"][0]["provenance"][0]["upstream_evidence_ids"] = [
        derived["id"]
    ]
    broken["evidence"].append(derived)
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="provenance contains dependency cycle"):
        proofgraph_from_dict(broken)


def test_graph_rejects_provenance_ids_reused_across_evidence() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    duplicate = copy.deepcopy(broken["evidence"][0])
    duplicate["id"] = "ev-secondary-pressure"
    duplicate["property_name"] = "secondary_pressure_differential_pa"
    broken["evidence"].append(duplicate)
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="duplicate provenance id"):
        proofgraph_from_dict(broken)


def test_graph_allows_distinct_provenance_ids_across_evidence() -> None:
    expanded = copy.deepcopy(_graph().to_dict())
    secondary = copy.deepcopy(expanded["evidence"][0])
    secondary["id"] = "ev-secondary-pressure"
    secondary["property_name"] = "secondary_pressure_differential_pa"
    secondary["provenance"][0]["id"] = "prov-secondary-pressure"
    expanded["evidence"].append(secondary)
    expanded.pop("graph_sha256")

    restored = proofgraph_from_dict(expanded)

    assert [item.id for item in restored.evidence] == [
        "ev-pressure",
        "ev-secondary-pressure",
    ]


def test_graph_rejects_mixed_explicit_project_identity() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    cross_project = copy.deepcopy(broken["evidence"][0])
    cross_project["id"] = "ev-other-project"
    cross_project["property_name"] = "other_project_pressure_pa"
    cross_project["project_id"] = "PROJECT-2"
    cross_project["provenance"][0]["id"] = "prov-other-project"
    broken["evidence"].append(cross_project)
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="multiple explicit project ids"):
        proofgraph_from_dict(broken)


def test_graph_accepts_deep_acyclic_provenance_chain() -> None:
    document = copy.deepcopy(_graph().to_dict())
    template = copy.deepcopy(document["evidence"][0])
    previous_id = template["id"]

    for index in range(1200):
        derived = copy.deepcopy(template)
        derived["id"] = f"ev-chain-{index:04d}"
        derived["property_name"] = f"derived_chain_value_{index:04d}"
        derived["provenance"][0]["id"] = f"prov-chain-{index:04d}"
        derived["provenance"][0]["origin"] = f"derived chain node {index:04d}"
        derived["provenance"][0]["upstream_evidence_ids"] = [previous_id]
        document["evidence"].append(derived)
        previous_id = derived["id"]

    document.pop("graph_sha256")
    restored = proofgraph_from_dict(document)

    assert len(restored.evidence) == 1201


def _add_second_requirement(document: dict) -> None:
    other = copy.deepcopy(document["requirement_set"]["requirements"][0])
    other["id"] = "CRX-PRESS-OTHER"
    other["title"] = "Other pressure requirement"
    document["requirement_set"]["requirements"].append(other)


def test_graph_rejects_finding_requirement_that_disagrees_with_check() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    _add_second_requirement(broken)
    broken["findings"][0]["requirement_id"] = "CRX-PRESS-OTHER"
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="does not match check"):
        proofgraph_from_dict(broken)


def test_graph_rejects_finding_evidence_not_declared_by_check() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    broken["checks"][0]["evidence_ids"] = []
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="evidence not declared by check"):
        proofgraph_from_dict(broken)


def test_graph_rejects_verdict_findings_for_another_requirement() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    _add_second_requirement(broken)
    broken["verdicts"][0]["requirement_id"] = "CRX-PRESS-OTHER"
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="findings for another requirement"):
        proofgraph_from_dict(broken)


def test_graph_rejects_single_finding_verdict_status_mismatch() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    broken["verdicts"][0]["status"] = "fail"
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="does not match its single finding status"):
        proofgraph_from_dict(broken)


@pytest.mark.parametrize("status", ["fail", "warning", "unknown", "indeterminate", "not_checked"])
@pytest.mark.parametrize("reverse", [False, True])
def test_graph_rejects_pass_verdict_with_nonpassing_support(status, reverse) -> None:
    broken = _graph().to_dict()
    secondary = copy.deepcopy(broken["findings"][0])
    secondary.update(id="finding-secondary", status=status)
    broken["findings"].append(secondary)
    supporting_ids = [item["id"] for item in broken["findings"]]
    broken["verdicts"][0]["finding_ids"] = supporting_ids[::-1] if reverse else supporting_ids
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="pass verdict.*non-pass findings"):
        proofgraph_from_dict(broken)


def test_graph_accepts_pass_verdict_with_multiple_passing_findings() -> None:
    document = _graph().to_dict()
    secondary = copy.deepcopy(document["findings"][0])
    secondary["id"] = "finding-secondary"
    document["findings"].append(secondary)
    document["verdicts"][0]["finding_ids"].append(secondary["id"])
    document.pop("graph_sha256")

    graph = proofgraph_from_dict(document)
    assert graph.verdicts[0].status == "pass"
    assert len(graph.verdicts[0].finding_ids) == 2
    assert proofgraph_from_dict(graph.to_dict()).to_dict() == graph.to_dict()


@pytest.mark.parametrize(
    "status", ["fail", "warning", "unknown", "indeterminate", "not_checked"]
)
def test_graph_rejects_pass_verdict_that_omits_nonpassing_finding_for_supported_check(
    status,
) -> None:
    broken = _graph().to_dict()
    hidden = copy.deepcopy(broken["findings"][0])
    hidden.update(id="finding-hidden-nonpass", status=status)
    broken["findings"].append(hidden)
    broken.pop("graph_sha256")

    with pytest.raises(
        ValueError,
        match="pass verdict.*omits non-pass findings from its supporting checks",
    ):
        proofgraph_from_dict(broken)


def test_pass_verdict_check_closure_is_local_to_its_supporting_checks() -> None:
    document = _graph().to_dict()
    secondary_check = copy.deepcopy(document["checks"][0])
    secondary_check["id"] = "check-secondary"
    document["checks"].append(secondary_check)

    secondary_finding = copy.deepcopy(document["findings"][0])
    secondary_finding.update(
        id="finding-secondary-fail",
        check_id=secondary_check["id"],
        status="fail",
    )
    document["findings"].append(secondary_finding)

    secondary_verdict = copy.deepcopy(document["verdicts"][0])
    secondary_verdict.update(
        id="verdict-secondary-fail",
        status="fail",
        finding_ids=[secondary_finding["id"]],
    )
    document["verdicts"].append(secondary_verdict)
    document["verification_runs"][0]["check_ids"].append(secondary_check["id"])
    document["verification_runs"][0]["verdict_ids"].append(secondary_verdict["id"])
    document.pop("graph_sha256")

    graph = proofgraph_from_dict(document)

    assert graph.verdicts[0].status == "pass"
    assert graph.verdicts[1].status == "fail"


def test_direct_graph_construction_rejects_pass_verdict_with_hidden_nonpass_sibling() -> None:
    graph = _graph()
    hidden = replace(
        graph.findings[0], id="finding-hidden-failed", status="fail"
    )
    with pytest.raises(
        ValueError,
        match="pass verdict.*omits non-pass findings from its supporting checks",
    ):
        replace(graph, findings=(*graph.findings, hidden))


def test_recomputed_digest_cannot_hide_nonpass_sibling_from_pass_verdict() -> None:
    document = _graph().to_dict()
    hidden = copy.deepcopy(document["findings"][0])
    hidden.update(id="finding-hidden-failed", status="fail")
    document["findings"].append(hidden)
    document.pop("graph_sha256")
    document["graph_sha256"] = hashlib.sha256(
        json.dumps(
            document, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(
        ValueError,
        match="pass verdict.*omits non-pass findings from its supporting checks",
    ):
        proofgraph_from_dict(document)


def test_direct_graph_construction_rejects_contradictory_pass_verdict() -> None:
    graph = _graph()
    failed = replace(graph.findings[0], id="finding-failed", status="fail")
    verdict = replace(
        graph.verdicts[0], finding_ids=(graph.findings[0].id, failed.id)
    )
    with pytest.raises(ValueError, match="pass verdict.*non-pass findings: finding-failed"):
        replace(graph, findings=(*graph.findings, failed), verdicts=(verdict,))


def test_recomputed_digest_cannot_authorize_contradictory_pass_verdict() -> None:
    document = _graph().to_dict()
    failed = copy.deepcopy(document["findings"][0])
    failed.update(id="finding-failed", status="fail")
    document["findings"].append(failed)
    document["verdicts"][0]["finding_ids"].append(failed["id"])
    document.pop("graph_sha256")
    document["graph_sha256"] = hashlib.sha256(
        json.dumps(
            document, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="pass verdict.*non-pass findings"):
        proofgraph_from_dict(document)


def test_graph_rejects_run_verdicts_that_depend_on_unlisted_checks() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    secondary_check = copy.deepcopy(broken["checks"][0])
    secondary_check["id"] = "check-secondary"
    broken["checks"].append(secondary_check)
    broken["verification_runs"][0]["check_ids"] = [secondary_check["id"]]
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="checks not included in the run"):
        proofgraph_from_dict(broken)


def test_graph_rejects_run_checks_without_verdict_outcomes() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    secondary_check = copy.deepcopy(broken["checks"][0])
    secondary_check["id"] = "check-without-verdict"
    broken["checks"].append(secondary_check)
    broken["verification_runs"][0]["check_ids"].append(secondary_check["id"])
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="checks with no verdict outcome"):
        proofgraph_from_dict(broken)


def test_non_finite_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="finite number"):
        DesignEvidence(
            id="ev",
            property_name="pressure",
            value=float("nan"),
            source_id="src",
        )


@pytest.mark.parametrize(
    ("evidence_ids", "evidence_present", "error"),
    [
        (("ev-pressure",), False, "requires evidence_present=true"),
        ((), True, "requires at least one evidence id"),
    ],
)
def test_pass_finding_requires_explicit_evidence(
    evidence_ids: tuple[str, ...],
    evidence_present: bool,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        ComplianceFinding(
            id="finding-pass-without-evidence",
            check_id="check-pressure",
            requirement_id="CRX-PRESS-001",
            status="pass",
            reason="A pass must be evidence-backed.",
            evidence_ids=evidence_ids,
            evidence_present=evidence_present,
        )


def test_graph_rejects_pass_finding_missing_required_evidence_kind() -> None:
    broken = copy.deepcopy(_graph().to_dict())
    broken["checks"][0]["required_evidence_kinds"] = ["design", "calculation"]
    broken.pop("graph_sha256")

    with pytest.raises(ValueError, match="missing required evidence kinds"):
        proofgraph_from_dict(broken)


def test_non_pass_finding_may_preserve_missing_required_evidence_kind() -> None:
    incomplete = copy.deepcopy(_graph().to_dict())
    incomplete["checks"][0]["required_evidence_kinds"] = ["design", "calculation"]
    incomplete["findings"][0]["status"] = "fail"
    incomplete["verdicts"][0]["status"] = "fail"
    incomplete.pop("graph_sha256")

    parsed = proofgraph_from_dict(incomplete)

    assert parsed.findings[0].status == "fail"
    assert parsed.checks[0].required_evidence_kinds == ("design", "calculation")


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
