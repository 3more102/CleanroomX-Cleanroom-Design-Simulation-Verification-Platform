from __future__ import annotations

import copy

from cleanroomx.project_requirement_verification import RequirementEvidence
from cleanroomx.project_requirements import (
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
    project_requirements_from_dict,
)
from cleanroomx.proofgraph import (
    proofgraph_from_dict,
    proofgraphs_from_project_requirements_verification,
)


def _requirement(
    requirement_id: str,
    *,
    scope: list[str] | None = None,
    status: str = "approved",
    applicability: str = "applicable",
    required_evidence: list[str] | None = None,
) -> dict:
    return {
        "id": requirement_id,
        "title": f"Requirement {requirement_id}",
        "description": "Explicit project-owned engineering criterion.",
        "discipline": "HVAC",
        "category": "air_change_rate",
        "source": "Project URS",
        "source_revision": "Rev C",
        "reference": "7.2",
        "unit": "1/h",
        "target": None,
        "minimum": 20.0,
        "maximum": None,
        "tolerance": 0.1,
        "applicability": applicability,
        "scope": ["ROOM-A"] if scope is None else scope,
        "verification_method": "calculation",
        "required_evidence": (
            ["calculation"] if required_evidence is None else required_evidence
        ),
        "status": status,
        "assumptions": ["Normal operating mode."],
        "notes": "Project criterion.",
    }


def _registry(*sets: tuple[str, list[dict]]):
    return project_requirements_from_dict(
        {
            "schema": PROJECT_REQUIREMENTS_SCHEMA,
            "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
            "sets": [
                {
                    "id": set_id,
                    "title": f"Set {set_id}",
                    "description": "Project requirement set.",
                    "source": f"{set_id}.pdf",
                    "source_revision": "Rev C",
                    "requirements": requirements,
                }
                for set_id, requirements in sets
            ],
        }
    )


def _evidence(
    *,
    evidence_id: str = "E-ACH",
    requirement_id: str = "REQ-ACH",
    subject_ref: str | None = "ROOM-A",
    value=20.0,
    kinds: tuple[str, ...] = ("calculation",),
    freshness: str = "current",
) -> RequirementEvidence:
    return RequirementEvidence(
        id=evidence_id,
        requirement_id=requirement_id,
        subject_ref=subject_ref,
        property_name="air_change_rate",
        value=value,
        unit="1/h",
        source="CleanroomX air-system analysis",
        source_revision="analysis-sha-1",
        calculation_source="cleanroomx.air_system_design",
        project_revision="project-rev-7",
        evidence_kinds=kinds,
        freshness=freshness,
    )


def test_verified_project_requirement_maps_to_traceable_proofgraph() -> None:
    requirements = _registry(("urs-main", [_requirement("REQ-ACH")]))
    graphs = proofgraphs_from_project_requirements_verification(
        requirements,
        [_evidence()],
    )

    assert len(graphs) == 1
    graph = graphs[0]
    document = graph.to_dict()

    assert graph.requirement_set.id == "urs-main"
    assert graph.requirement_set.version == "Rev C"
    assert graph.requirement_set.requirements[0].criteria["criterion"] == {
        "operator": "minimum",
        "expected": 20.0,
        "tolerance": 0.1,
    }
    assert graph.requirement_set.requirements[0].criteria[
        "required_evidence"
    ] == ["calculation"]

    assert len(graph.evidence_sources) == 1
    assert graph.evidence_sources[0].revision == "analysis-sha-1"
    assert len(graph.evidence) == 1
    assert graph.evidence[0].id == "E-ACH"
    assert graph.evidence[0].kind == "calculation"
    assert graph.evidence[0].version == "project-rev-7"
    assert graph.evidence[0].provenance[0].originating_calculation == (
        "cleanroomx.air_system_design"
    )

    assert graph.checks[0].required_evidence_kinds == ("calculation",)
    assert graph.findings[0].status == "pass"
    assert graph.findings[0].evidence_present is True
    assert graph.verdicts[0].status == "pass"

    run = graph.verification_runs[0]
    assert run.metadata["adapter"] == "project_requirements_verification"
    assert run.metadata["project_verified"] is True
    assert run.metadata["project_no_failures_detected"] is True
    assert run.metadata["source_findings"][0]["state"] == "pass"
    assert len(document["graph_sha256"]) == 64
    assert proofgraph_from_dict(copy.deepcopy(document)).to_dict() == document


def test_stale_requirement_evidence_maps_to_unknown_without_pass() -> None:
    requirements = _registry(("urs-main", [_requirement("REQ-ACH")]))

    graph = proofgraphs_from_project_requirements_verification(
        requirements,
        [_evidence(freshness="stale")],
    )[0]

    assert graph.findings[0].status == "unknown"
    assert graph.verdicts[0].status == "unknown"
    assert graph.findings[0].evidence_present is True
    assert graph.verification_runs[0].metadata["source_findings"][0][
        "state"
    ] == "stale"
    assert "stale" in graph.findings[0].reason


def test_inactive_and_not_applicable_states_remain_explicit() -> None:
    requirements = _registry(
        (
            "urs-main",
            [
                _requirement(
                    "REQ-SUPERSEDED",
                    status="superseded",
                    scope=["ROOM-A"],
                ),
                _requirement(
                    "REQ-NOT-APPLICABLE",
                    applicability="not_applicable",
                    scope=["ROOM-B"],
                ),
            ],
        )
    )

    graph = proofgraphs_from_project_requirements_verification(requirements, [])[0]

    by_requirement = {
        finding.requirement_id: finding for finding in graph.findings
    }
    assert by_requirement["REQ-SUPERSEDED"].status == "not_checked"
    assert by_requirement["REQ-NOT-APPLICABLE"].status == "not_checked"

    metadata = {
        item["requirement_id"]: item
        for item in graph.verification_runs[0].metadata["source_findings"]
    }
    assert metadata["REQ-SUPERSEDED"]["state"] == "inactive"
    assert metadata["REQ-SUPERSEDED"]["included"] is False
    assert metadata["REQ-NOT-APPLICABLE"]["state"] == "not_applicable"
    assert metadata["REQ-NOT-APPLICABLE"]["included"] is False


def test_multiple_requirement_sets_emit_separate_graphs_deterministically() -> None:
    requirements = _registry(
        ("set-a", [_requirement("REQ-A", scope=["ROOM-A"])]),
        ("set-b", [_requirement("REQ-B", scope=["ROOM-B"])]),
    )
    first = _evidence(
        evidence_id="E-A",
        requirement_id="REQ-A",
        subject_ref="ROOM-A",
        value=20.0,
    )
    second = _evidence(
        evidence_id="E-B",
        requirement_id="REQ-B",
        subject_ref="ROOM-B",
        value=21.0,
    )

    forward = proofgraphs_from_project_requirements_verification(
        requirements,
        [first, second],
    )
    reverse = proofgraphs_from_project_requirements_verification(
        requirements,
        [second, first],
    )

    assert [graph.requirement_set.id for graph in forward] == ["set-a", "set-b"]
    assert [graph.to_dict() for graph in forward] == [
        graph.to_dict() for graph in reverse
    ]
    assert forward[0].requirement_set.requirements[0].id == "REQ-A"
    assert forward[1].requirement_set.requirements[0].id == "REQ-B"


def test_multi_kind_binding_does_not_fabricate_proofgraph_evidence_layers() -> None:
    requirements = _registry(
        (
            "urs-main",
            [
                _requirement(
                    "REQ-ACH",
                    required_evidence=["design", "calculation"],
                )
            ],
        )
    )

    graph = proofgraphs_from_project_requirements_verification(
        requirements,
        [_evidence(kinds=("design", "calculation"))],
    )[0]

    assert graph.findings[0].status == "pass"
    assert graph.evidence[0].kind == "declared"
    assert graph.checks[0].required_evidence_kinds == ()
    assert graph.requirement_set.requirements[0].criteria[
        "required_evidence"
    ] == ["calculation", "design"]


def test_missing_evidence_value_preserves_incomplete_source_state() -> None:
    requirements = _registry(("urs-main", [_requirement("REQ-ACH")]))

    graph = proofgraphs_from_project_requirements_verification(
        requirements,
        [_evidence(value=None)],
    )[0]

    assert graph.findings[0].status == "unknown"
    assert graph.findings[0].actual is None
    assert graph.findings[0].evidence_present is True
    assert graph.verification_runs[0].metadata["source_findings"][0][
        "state"
    ] == "incomplete"


def test_empty_requirement_sets_do_not_fabricate_empty_proofgraphs() -> None:
    requirements = _registry(("empty", []))

    assert (
        proofgraphs_from_project_requirements_verification(requirements, [])
        == ()
    )
