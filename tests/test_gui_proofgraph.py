from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui_proofgraph import (
    ProofGraphViewer,
    _filtered_projection,
    _node_detail_lines,
    _search_projection,
    proofgraph_projection,
)
from cleanroomx.proofgraph_models import (
    CalculationEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
)


def _sample_graph() -> dict:
    requirement = Requirement(
        id="REQ-PRESSURE",
        title="Room pressure",
        source="project",
        scope=("room-a",),
        criteria={"min_pa": 15.0},
    )
    requirement_set = RequirementSet(
        id="requirements",
        version="1",
        title="Project Requirements",
        source="project",
        requirements=(requirement,),
    )
    source = EvidenceSource(
        id="source-ifc",
        kind="ifc",
        reference="facility.ifc",
        revision="rev-1",
    )
    evidence = CalculationEvidence(
        id="evidence-pressure",
        property_name="pressure_pa",
        value=12.0,
        unit="Pa",
        source_id=source.id,
        project_id="project-a",
        subject_ref="room-a",
        provenance=(
            ProvenanceRecord(
                id="prov-pressure",
                source_id=source.id,
                origin="solver",
                ifc_global_id="3IFC",
                cleanroomx_entity_id="room-a",
                originating_calculation="pressure_solver",
                method="pressure cascade",
            ),
        ),
    )
    check = ComplianceCheck(
        id="check-pressure",
        requirement_id=requirement.id,
        evidence_ids=(evidence.id,),
        required_evidence_kinds=("calculation",),
    )
    finding = ComplianceFinding(
        id="finding-pressure",
        check_id=check.id,
        requirement_id=requirement.id,
        status="fail",
        reason="Pressure below target",
        evidence_ids=(evidence.id,),
        evidence_present=True,
        expected=15.0,
        actual=12.0,
        unit="Pa",
        delta=-3.0,
    )
    verdict = ComplianceVerdict(
        id="verdict-pressure",
        requirement_id=requirement.id,
        status="fail",
        finding_ids=(finding.id,),
        reason="Requirement not satisfied",
    )
    run = VerificationRun(
        id="run-1",
        requirement_set_id=requirement_set.id,
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
    )
    return ProofGraph(
        id="graph-room-pressure",
        requirement_set=requirement_set,
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    ).to_dict()


def _unresolved_graph() -> dict:
    requirement = Requirement(
        id="REQ-EVIDENCE",
        title="Qualification evidence",
        source="project",
    )
    requirement_set = RequirementSet(
        id="requirements-unresolved",
        version="1",
        title="Evidence Requirements",
        source="project",
        requirements=(requirement,),
    )
    check = ComplianceCheck(
        id="check-evidence",
        requirement_id=requirement.id,
        evidence_ids=(),
        required_evidence_kinds=("commissioning",),
    )
    finding = ComplianceFinding(
        id="finding-evidence",
        check_id=check.id,
        requirement_id=requirement.id,
        status="not_checked",
        reason="Required commissioning evidence is missing.",
        evidence_ids=(),
        evidence_present=False,
    )
    verdict = ComplianceVerdict(
        id="verdict-evidence",
        requirement_id=requirement.id,
        status="not_checked",
        finding_ids=(finding.id,),
        reason="Required commissioning evidence is missing.",
    )
    run = VerificationRun(
        id="run-unresolved",
        requirement_set_id=requirement_set.id,
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
    )
    return ProofGraph(
        id="graph-unresolved-evidence",
        requirement_set=requirement_set,
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    ).to_dict()


def test_proofgraph_projection_validates_and_builds_trace_chain():
    document = _sample_graph()
    before = copy.deepcopy(document)

    projection = proofgraph_projection(document)

    assert document == before
    nodes = {node["key"]: node for node in projection["nodes"]}
    assert "requirement:REQ-PRESSURE" in nodes
    assert "model_object:room-a" in nodes
    assert "ifc:3IFC" in nodes
    assert "calculation:pressure_solver" in nodes
    assert "evidence:evidence-pressure" in nodes
    assert nodes["finding:finding-pressure"]["status"] == "fail"
    assert nodes["verdict:verdict-pressure"]["status"] == "fail"

    edges = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in projection["edges"]
    }
    assert (
        "requirement:REQ-PRESSURE",
        "check:check-pressure",
        "checked_by",
    ) in edges
    assert (
        "evidence:evidence-pressure",
        "check:check-pressure",
        "supports",
    ) in edges
    assert (
        "check:check-pressure",
        "finding:finding-pressure",
        "produces",
    ) in edges
    assert (
        "finding:finding-pressure",
        "verdict:verdict-pressure",
        "verdict",
    ) in edges


def test_proofgraph_projection_fails_closed_on_tampered_digest():
    document = _sample_graph()
    document["evidence"][0]["value"] = 13.0

    with pytest.raises(ValueError, match="graph_sha256 does not match"):
        proofgraph_projection(document)


def test_proofgraph_filters_keep_immediate_context_without_deriving_new_verdicts():
    projection = proofgraph_projection(_sample_graph())

    failures = _filtered_projection(projection, "Failures")
    failure_keys = {node["key"] for node in failures["nodes"]}
    assert "finding:finding-pressure" in failure_keys
    assert "verdict:verdict-pressure" in failure_keys
    assert "check:check-pressure" in failure_keys
    assert "verification_run:run-1" in failure_keys

    ifc = _filtered_projection(projection, "IFC")
    ifc_keys = {node["key"] for node in ifc["nodes"]}
    assert "ifc:3IFC" in ifc_keys
    assert "evidence:evidence-pressure" in ifc_keys

    calculations = _filtered_projection(projection, "Calculations")
    calculation_keys = {node["key"] for node in calculations["nodes"]}
    assert "calculation:pressure_solver" in calculation_keys
    assert "evidence:evidence-pressure" in calculation_keys


def test_unresolved_evidence_filter_uses_canonical_not_checked_state():
    projection = proofgraph_projection(_unresolved_graph())

    unresolved = _filtered_projection(projection, "Unresolved Evidence")
    unresolved_keys = {node["key"] for node in unresolved["nodes"]}

    assert "finding:finding-evidence" in unresolved_keys
    assert "check:check-evidence" in unresolved_keys
    assert "verdict:verdict-evidence" not in unresolved_keys



def test_proofgraph_node_detail_is_engineering_facing_not_raw_json():
    projection = proofgraph_projection(_sample_graph())
    node = next(
        item for item in projection["nodes"]
        if item["key"] == "finding:finding-pressure"
    )

    rendered = "\n".join(_node_detail_lines(node))

    assert "FINDING" in rendered
    assert "Pressure below target" in rendered
    assert "Status: FAIL" in rendered
    assert "TRACEABILITY DETAILS" in rendered
    assert "{\"" not in rendered

def test_proofgraph_search_matches_persisted_fields_and_keeps_context():
    projection = proofgraph_projection(_sample_graph())
    before = copy.deepcopy(projection)

    matched = _search_projection(projection, "pressure_solver")
    keys = {node["key"] for node in matched["nodes"]}

    assert "calculation:pressure_solver" in keys
    assert "evidence:evidence-pressure" in keys
    assert projection == before
    assert _search_projection(projection, "definitely missing") == {
        "nodes": [],
        "edges": [],
    }


def test_proofgraph_viewer_zoom_is_bounded_and_searchable():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    viewer = ProofGraphViewer(root)
    viewer.pack(fill="both", expand=True)
    try:
        viewer.set_documents([_sample_graph()])
        root.update_idletasks()

        viewer.search_var.set("pressure_solver")
        root.update_idletasks()
        assert viewer._projection["nodes"]
        assert "search: pressure_solver" in viewer.summary_var.get()

        viewer._zoom_graph(1.15)
        root.update_idletasks()
        assert viewer._graph_scale > 1.0
        assert viewer.zoom_var.get().endswith("%")

        for _ in range(30):
            viewer._zoom_graph(1.15)
        assert viewer._graph_scale <= 2.25

        viewer._reset_graph_zoom()
        assert viewer._graph_scale == 1.0
        assert viewer.zoom_var.get() == "100%"
    finally:
        root.destroy()

