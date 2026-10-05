from __future__ import annotations

from dataclasses import replace

import pytest

from cleanroomx.proofgraph import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    DesignEvidence,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
    compare_proofgraphs,
)


def _graph() -> ProofGraph:
    source = EvidenceSource(
        id="source",
        kind="ifc",
        reference="facility.ifc",
        revision="a" * 64,
    )
    requirement = Requirement(
        id="REQ-1",
        title="Pressure relationship",
        source="Project URS",
        criteria={"operator": "min", "expected": 10.0, "unit": "Pa"},
    )
    evidence = DesignEvidence(
        id="EV-1",
        property_name="pressure_differential_pa",
        value=13.0,
        unit="Pa",
        source_id=source.id,
        provenance=(
            ProvenanceRecord(
                id="PROV-1",
                source_id=source.id,
                origin="facility.ifc",
            ),
        ),
    )
    check = ComplianceCheck(
        id="CHECK-1",
        requirement_id=requirement.id,
        evidence_ids=(evidence.id,),
        required_evidence_kinds=("design",),
    )
    finding = ComplianceFinding(
        id="FINDING-1",
        check_id=check.id,
        requirement_id=requirement.id,
        status="pass",
        reason="Pressure margin passes.",
        evidence_ids=(evidence.id,),
        evidence_present=True,
        expected=10.0,
        actual=13.0,
        unit="Pa",
        delta=3.0,
    )
    verdict = ComplianceVerdict(
        id="VERDICT-1",
        requirement_id=requirement.id,
        status="pass",
        finding_ids=(finding.id,),
        reason=finding.reason,
    )
    run = VerificationRun(
        id="RUN-1",
        requirement_set_id="URS",
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
        input_sha256="b" * 64,
    )
    return ProofGraph(
        id="GRAPH-1",
        requirement_set=RequirementSet(
            id="URS",
            version="1",
            title="URS",
            source="Project URS",
            requirements=(requirement,),
        ),
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    )


def test_identical_graphs_have_deterministic_empty_change_impact() -> None:
    graph = _graph()

    first = compare_proofgraphs(graph, graph)
    second = compare_proofgraphs(graph, graph)

    assert first == second
    assert first["changed"] is False
    assert len(first["impact_sha256"]) == 64
    assert all(
        not section["added_ids"]
        and not section["removed_ids"]
        and not section["changed_ids"]
        for section in first["changes"].values()
    )
    assert all(not ids for ids in first["impact"].values())
    assert all(not ids for ids in first["potentially_stale_candidate"].values())


def test_source_revision_change_flags_unchanged_downstream_records_as_stale() -> None:
    baseline = _graph()
    revised_source = replace(
        baseline.evidence_sources[0],
        revision="c" * 64,
    )
    candidate = replace(baseline, evidence_sources=(revised_source,))

    impact = compare_proofgraphs(baseline, candidate)

    assert impact["changes"]["evidence_sources"]["changed_ids"] == ["source"]
    assert impact["changes"]["evidence"]["changed_ids"] == []
    assert impact["potentially_stale_candidate"]["evidence_ids"] == ["EV-1"]
    assert impact["potentially_stale_candidate"]["finding_ids"] == ["FINDING-1"]
    assert impact["potentially_stale_candidate"]["verdict_ids"] == ["VERDICT-1"]
    assert impact["potentially_stale_candidate"]["verification_run_ids"] == ["RUN-1"]
    assert impact["impact"]["impacted_requirement_ids"] == ["REQ-1"]



def test_provenance_source_revision_change_marks_unchanged_evidence_stale() -> None:
    baseline = _graph()
    secondary_source = EvidenceSource(
        id="secondary-source",
        kind="commissioning",
        reference="tab-results.csv",
        revision="d" * 64,
    )
    evidence = replace(
        baseline.evidence[0],
        provenance=(
            ProvenanceRecord(
                id="PROV-1",
                source_id=secondary_source.id,
                origin="tab-results.csv",
            ),
        ),
    )
    baseline = replace(
        baseline,
        evidence_sources=(baseline.evidence_sources[0], secondary_source),
        evidence=(evidence,),
    )
    candidate = replace(
        baseline,
        evidence_sources=(
            baseline.evidence_sources[0],
            replace(secondary_source, revision="e" * 64),
        ),
    )

    impact = compare_proofgraphs(baseline, candidate)

    assert impact["changes"]["evidence_sources"]["changed_ids"] == ["secondary-source"]
    assert impact["changes"]["evidence"]["changed_ids"] == []
    assert impact["potentially_stale_candidate"]["evidence_ids"] == ["EV-1"]
    assert impact["potentially_stale_candidate"]["finding_ids"] == ["FINDING-1"]
    assert impact["potentially_stale_candidate"]["verdict_ids"] == ["VERDICT-1"]
    assert impact["potentially_stale_candidate"]["verification_run_ids"] == ["RUN-1"]



def test_changed_evidence_propagates_impact_to_downstream_verification() -> None:
    baseline = _graph()
    changed_evidence = replace(baseline.evidence[0], value=14.0)
    changed_finding = replace(
        baseline.findings[0],
        actual=14.0,
        delta=4.0,
    )
    candidate = replace(
        baseline,
        evidence=(changed_evidence,),
        findings=(changed_finding,),
    )

    impact = compare_proofgraphs(baseline, candidate)

    assert impact["changes"]["evidence"]["changed_ids"] == ["EV-1"]
    assert impact["changes"]["findings"]["changed_ids"] == ["FINDING-1"]
    assert impact["impact"]["impacted_check_ids"] == ["CHECK-1"]
    assert impact["impact"]["impacted_verdict_ids"] == ["VERDICT-1"]
    assert impact["impact"]["impacted_verification_run_ids"] == ["RUN-1"]
    assert impact["potentially_stale_candidate"]["evidence_ids"] == []
    assert impact["potentially_stale_candidate"]["verdict_ids"] == ["VERDICT-1"]


def test_requirement_change_marks_unchanged_outcomes_for_review() -> None:
    baseline = _graph()
    requirement = replace(
        baseline.requirement_set.requirements[0],
        criteria={"operator": "min", "expected": 12.0, "unit": "Pa"},
    )
    candidate = replace(
        baseline,
        requirement_set=replace(
            baseline.requirement_set,
            version="2",
            requirements=(requirement,),
        ),
    )

    impact = compare_proofgraphs(baseline, candidate)

    assert impact["requirement_set_metadata"]["changed"] is True
    assert impact["changes"]["requirements"]["changed_ids"] == ["REQ-1"]
    assert impact["potentially_stale_candidate"]["finding_ids"] == ["FINDING-1"]
    assert impact["potentially_stale_candidate"]["verdict_ids"] == ["VERDICT-1"]
    assert impact["potentially_stale_candidate"]["verification_run_ids"] == ["RUN-1"]


def test_comparison_rejects_unrelated_graph_identity() -> None:
    baseline = _graph()
    candidate = replace(baseline, id="GRAPH-2")

    with pytest.raises(ValueError, match="matching graph ids"):
        compare_proofgraphs(baseline, candidate)
