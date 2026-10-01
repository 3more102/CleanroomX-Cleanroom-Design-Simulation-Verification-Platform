from __future__ import annotations

import copy

import pytest

from cleanroomx.proofgraph import (
    DesignEvidence,
    EvidencePrecedencePolicy,
    EvidenceSource,
    OperationalEvidence,
    ProofGraph,
    Requirement,
    RequirementSet,
    assess_evidence_precedence,
)


def _graph(*evidence):
    requirement = Requirement(
        id="REQ-1",
        title="Room pressure",
        source="Project URS",
        criteria={"operator": ">="},
    )
    sources = {
        item.source_id: EvidenceSource(
            id=item.source_id,
            kind="test",
            reference=item.source_id,
        )
        for item in evidence
    }
    return ProofGraph(
        id="graph-evidence-precedence",
        requirement_set=RequirementSet(
            id="urs",
            version="1",
            title="URS",
            source="Project URS",
            requirements=(requirement,),
        ),
        evidence_sources=tuple(sources[key] for key in sorted(sources)),
        evidence=tuple(evidence),
    )


def _design(evidence_id, value, *, source_id="design-source", unit="Pa", subject="room-a"):
    return DesignEvidence(
        id=evidence_id,
        property_name="pressure_pa",
        value=value,
        unit=unit,
        source_id=source_id,
        subject_ref=subject,
    )


def _operational(evidence_id, value, *, source_id="ops-source", unit="Pa", subject="room-a"):
    return OperationalEvidence(
        id=evidence_id,
        property_name="pressure_pa",
        value=value,
        unit=unit,
        source_id=source_id,
        subject_ref=subject,
    )


def test_policy_rejects_unknown_kinds_and_duplicate_sources() -> None:
    with pytest.raises(ValueError, match="unsupported kind"):
        EvidencePrecedencePolicy(id="bad", kind_precedence=("invented",))

    with pytest.raises(ValueError, match="duplicates"):
        EvidencePrecedencePolicy(
            id="bad",
            source_precedence=("source-a", "source-a"),
        )


def test_single_claim_is_selected_without_modifying_graph() -> None:
    graph = _graph(_design("design-a", 12.0))
    before = copy.deepcopy(graph.to_dict())

    report = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(id="project-policy", kind_precedence=("design",)),
    )
    payload = report.to_dict()

    assert payload["decision_scope"] == "assessment_only"
    assert payload["changes_canonical_verification"] is False
    assert payload["has_conflicts"] is False
    assert payload["resolutions"][0]["status"] == "single"
    assert payload["resolutions"][0]["selected_evidence_id"] == "design-a"
    assert graph.to_dict() == before


def test_explicit_kind_precedence_resolves_disagreement_without_deleting_history() -> None:
    graph = _graph(
        _design("design-a", 12.0),
        _operational("ops-a", 10.0),
    )

    payload = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(
            id="prefer-operational",
            kind_precedence=("operational", "design"),
        ),
    ).to_dict()
    resolution = payload["resolutions"][0]

    assert resolution["status"] == "selected"
    assert resolution["selected_evidence_id"] == "ops-a"
    assert resolution["preferred_evidence_ids"] == ["ops-a"]
    assert resolution["shadowed_evidence_ids"] == ["design-a"]
    assert [item["id"] for item in resolution["candidates"]] == [
        "design-a",
        "ops-a",
    ]


def test_equal_precedence_disagreement_fails_closed_as_conflict() -> None:
    graph = _graph(
        _design("design-a", 12.0, source_id="source-a"),
        _design("design-b", 10.0, source_id="source-b"),
    )

    payload = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(id="design-peer-policy", kind_precedence=("design",)),
    ).to_dict()
    resolution = payload["resolutions"][0]

    assert payload["has_conflicts"] is True
    assert resolution["status"] == "conflict"
    assert resolution["selected_evidence_id"] is None
    assert resolution["preferred_evidence_ids"] == ["design-a", "design-b"]


def test_equal_precedence_equal_claims_remain_coequal() -> None:
    graph = _graph(
        _design("design-a", {"value": 12.0}, source_id="source-a"),
        _design("design-b", {"value": 12.0}, source_id="source-b"),
    )

    resolution = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(id="coequal", kind_precedence=("design",)),
    ).to_dict()["resolutions"][0]

    assert resolution["status"] == "equivalent"
    assert resolution["selected_evidence_id"] is None
    assert resolution["shadowed_evidence_ids"] == []


def test_source_precedence_breaks_tie_within_same_kind() -> None:
    graph = _graph(
        _design("design-a", 12.0, source_id="source-a"),
        _design("design-b", 10.0, source_id="source-b"),
    )

    resolution = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(
            id="source-authority",
            kind_precedence=("design",),
            source_precedence=("source-b", "source-a"),
        ),
    ).to_dict()["resolutions"][0]

    assert resolution["status"] == "selected"
    assert resolution["selected_evidence_id"] == "design-b"


def test_units_are_not_silently_converted_when_peer_claims_disagree() -> None:
    graph = _graph(
        _design("design-pa", 10.0, source_id="source-a", unit="Pa"),
        _design("design-kpa", 0.01, source_id="source-b", unit="kPa"),
    )

    resolution = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(id="no-unit-guess", kind_precedence=("design",)),
    ).to_dict()["resolutions"][0]

    assert resolution["status"] == "conflict"
    assert resolution["selected_evidence_id"] is None


def test_assessment_is_deterministic_across_evidence_input_order() -> None:
    first = _design("design-a", 12.0, source_id="source-a")
    second = _operational("ops-a", 10.0, source_id="source-b")
    policy = EvidencePrecedencePolicy(
        id="deterministic",
        kind_precedence=("operational", "design"),
    )

    left = assess_evidence_precedence(_graph(first, second), policy).to_dict()
    right = assess_evidence_precedence(_graph(second, first), policy).to_dict()

    assert left == right


def test_subjects_are_resolved_independently() -> None:
    graph = _graph(
        _design("room-a", 12.0, subject="room-a"),
        _design("room-b", 8.0, subject="room-b"),
    )

    payload = assess_evidence_precedence(
        graph,
        EvidencePrecedencePolicy(id="per-subject", kind_precedence=("design",)),
    ).to_dict()

    assert [item["subject_ref"] for item in payload["resolutions"]] == [
        "room-a",
        "room-b",
    ]
    assert all(item["status"] == "single" for item in payload["resolutions"])
