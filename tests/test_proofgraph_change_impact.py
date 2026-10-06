from __future__ import annotations

from dataclasses import replace

import pytest

from cleanroomx.proofgraph import (
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    CorrectiveAction,
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


def test_impacted_unchanged_corrective_action_is_reported_stale() -> None:
    baseline = _graph()
    action = CorrectiveAction(
        id="ACTION-1",
        requirement_id="REQ-1",
        title="Review pressure correction",
        description="Confirm the corrective pressure action against refreshed evidence.",
        evidence_ids=("EV-1",),
    )
    baseline = replace(baseline, corrective_actions=(action,))
    candidate = replace(
        baseline,
        evidence_sources=(
            replace(baseline.evidence_sources[0], revision="f" * 64),
        ),
    )

    impact = compare_proofgraphs(baseline, candidate)

    assert impact["impact"]["impacted_corrective_action_ids"] == ["ACTION-1"]
    assert impact["potentially_stale_candidate"]["corrective_action_ids"] == ["ACTION-1"]


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


def _derived(graph: ProofGraph, evidence_id: str, upstream: tuple[str, ...]):
    return replace(
        graph.evidence[0],
        id=evidence_id,
        property_name=f"derived-{evidence_id}",
        provenance=(
            ProvenanceRecord(
                id=f"provenance-{evidence_id}",
                source_id=graph.evidence_sources[0].id,
                origin="derived calculation",
                upstream_evidence_ids=upstream,
            ),
        ),
    )


@pytest.mark.parametrize("reverse_order", [False, True])
@pytest.mark.parametrize("refresh_intermediate", [False, True])
def test_branched_change_impact_preserves_unrelated_evidence_and_refreshed_records(
    reverse_order: bool, refresh_intermediate: bool
) -> None:
    graph = _graph()
    root = graph.evidence[0]
    left = _derived(graph, "LEFT", (root.id,))
    right = _derived(graph, "RIGHT", (root.id,))
    join = _derived(graph, "JOIN", (left.id, right.id))
    unrelated = _derived(graph, "UNRELATED", ())
    evidence = [root, left, right, join, unrelated]
    if reverse_order:
        evidence.reverse()
    baseline = replace(
        graph,
        evidence=tuple(evidence),
        checks=(replace(graph.checks[0], evidence_ids=(join.id,)),),
        findings=(replace(graph.findings[0], evidence_ids=(join.id,)),),
        corrective_actions=(
            CorrectiveAction(
                id="ACTION", requirement_id="REQ-1", title="Review derived result",
                description="Review changed upstream evidence.", evidence_ids=(join.id,),
            ),
        ),
    )
    candidate = replace(
        baseline,
        evidence=tuple(
            replace(item, value=14.0)
            if item.id == root.id or (refresh_intermediate and item.id == right.id)
            else item
            for item in baseline.evidence
        ),
    )

    report = compare_proofgraphs(baseline, candidate)

    assert report["impact"]["impacted_evidence_ids"] == ["EV-1", "JOIN", "LEFT", "RIGHT"]
    assert report["potentially_stale_candidate"] == {
        "evidence_ids": ["JOIN", "LEFT"] if refresh_intermediate else ["JOIN", "LEFT", "RIGHT"],
        "finding_ids": ["FINDING-1"],
        "verdict_ids": ["VERDICT-1"],
        "corrective_action_ids": ["ACTION"],
        "verification_run_ids": ["RUN-1"],
    }
    assert report == compare_proofgraphs(baseline, candidate)


def test_deep_reverse_ordered_dependency_chain_reaches_verification_outcomes() -> None:
    graph = _graph()
    evidence = [graph.evidence[0]]
    for index in range(1_500):
        evidence.append(_derived(graph, f"CHAIN-{index:04d}", (evidence[-1].id,)))
    final_id = evidence[-1].id
    baseline = replace(
        graph,
        evidence=tuple(reversed(evidence)),
        checks=(replace(graph.checks[0], evidence_ids=(final_id,)),),
        findings=(replace(graph.findings[0], evidence_ids=(final_id,)),),
    )
    candidate = replace(
        baseline,
        evidence=tuple(
            replace(item, value=14.0) if item.id == "EV-1" else item
            for item in baseline.evidence
        ),
    )

    report = compare_proofgraphs(baseline, candidate)

    assert report["potentially_stale_candidate"]["evidence_ids"] == sorted(
        item.id for item in evidence[1:]
    )
    assert report["potentially_stale_candidate"]["finding_ids"] == ["FINDING-1"]
    assert report["potentially_stale_candidate"]["verdict_ids"] == ["VERDICT-1"]
    assert report["potentially_stale_candidate"]["verification_run_ids"] == ["RUN-1"]
