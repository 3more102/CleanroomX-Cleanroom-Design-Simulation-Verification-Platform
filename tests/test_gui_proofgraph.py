from __future__ import annotations

import copy

from cleanroomx.gui_proofgraph import _filtered_projection, proofgraph_projection


def _sample_graph() -> dict:
    return {
        "schema": "cleanroomx.proofgraph",
        "schema_version": 1,
        "id": "graph-room-pressure",
        "graph_sha256": "a" * 64,
        "requirement_set": {
            "id": "requirements",
            "version": "1",
            "title": "Project Requirements",
            "source": "project",
            "requirements": [
                {
                    "id": "REQ-PRESSURE",
                    "title": "Room pressure",
                    "source": "project",
                    "reference": None,
                    "scope": ["room-a"],
                    "criteria": {"min_pa": 15.0},
                }
            ],
        },
        "evidence_sources": [
            {
                "id": "source-project",
                "kind": "project",
                "reference": "project.cleanroomx.json",
                "revision": "rev-1",
            }
        ],
        "evidence": [
            {
                "id": "evidence-pressure",
                "kind": "calculation",
                "property_name": "pressure_pa",
                "value": 12.0,
                "unit": "Pa",
                "source_id": "source-project",
                "version": None,
                "timestamp": None,
                "project_id": "project-a",
                "subject_ref": "room-a",
                "provenance": [
                    {
                        "id": "prov-pressure",
                        "source_id": "source-project",
                        "origin": "solver",
                        "upstream_evidence_ids": [],
                        "ifc_global_id": "3IFC",
                        "cleanroomx_entity_id": "room-a",
                        "originating_file": None,
                        "originating_calculation": "pressure_solver",
                        "method": "pressure cascade",
                    }
                ],
                "confidence": None,
            }
        ],
        "checks": [
            {
                "id": "check-pressure",
                "requirement_id": "REQ-PRESSURE",
                "evidence_ids": ["evidence-pressure"],
                "required_evidence_kinds": ["calculation"],
            }
        ],
        "findings": [
            {
                "id": "finding-pressure",
                "check_id": "check-pressure",
                "requirement_id": "REQ-PRESSURE",
                "status": "fail",
                "reason": "Pressure below target",
                "evidence_ids": ["evidence-pressure"],
                "evidence_present": True,
                "expected": 15.0,
                "actual": 12.0,
                "unit": "Pa",
                "delta": -3.0,
            }
        ],
        "verdicts": [
            {
                "id": "verdict-pressure",
                "requirement_id": "REQ-PRESSURE",
                "status": "fail",
                "finding_ids": ["finding-pressure"],
                "reason": "Requirement not satisfied",
                "confidence": None,
            }
        ],
        "corrective_actions": [],
        "verification_runs": [
            {
                "id": "run-1",
                "requirement_set_id": "requirements",
                "check_ids": ["check-pressure"],
                "verdict_ids": ["verdict-pressure"],
                "timestamp": None,
                "input_sha256": None,
                "metadata": {},
            }
        ],
    }


def test_proofgraph_projection_preserves_canonical_document_and_builds_trace_chain():
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
