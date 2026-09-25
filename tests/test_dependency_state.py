from __future__ import annotations

import pytest

from cleanroomx.dependency_state import (
    DependencyGraph,
    DependencyGraphError,
    EvidenceState,
)


def test_explicit_dependency_chain_propagates_staleness_without_inferred_edges():
    graph = DependencyGraph()
    graph.set_source("geometry", "g1")
    graph.set_artifact(
        "spatial-validation",
        "sv1",
        dependencies={"geometry": "g1"},
    )
    graph.set_artifact(
        "synchronized-input",
        "sync1",
        dependencies={"spatial-validation": "sv1"},
    )
    graph.set_artifact(
        "hvac-run",
        "run1",
        dependencies={"synchronized-input": "sync1"},
    )
    graph.set_source("unrelated-analysis-input", "other1")

    assert graph.state("hvac-run") is EvidenceState.CURRENT

    graph.set_source("geometry", "g2")
    assert graph.state("spatial-validation") is EvidenceState.STALE
    assert graph.state("synchronized-input") is EvidenceState.STALE
    assert graph.state("hvac-run") is EvidenceState.STALE
    assert graph.state("unrelated-analysis-input") is EvidenceState.CURRENT


def test_missing_authoritative_dependency_is_unresolved():
    graph = DependencyGraph()
    graph.set_artifact("run", "r1", dependencies={"external-file": "f1"})

    assert graph.state("run") is EvidenceState.UNRESOLVED

    graph.set_source("external-file", None)
    assert graph.state("run") is EvidenceState.UNRESOLVED


def test_historical_and_invalid_are_distinct_from_current_and_stale():
    graph = DependencyGraph()
    graph.set_source("input", "i1")
    graph.set_artifact(
        "old-run",
        "r1",
        dependencies={"input": "i1"},
        historical=True,
    )
    graph.set_artifact(
        "tampered-run",
        "r2",
        dependencies={"input": "i1"},
        integrity_valid=False,
    )

    assert graph.state("old-run") is EvidenceState.HISTORICAL
    assert graph.state("tampered-run") is EvidenceState.INVALID


def test_artifact_bound_to_different_source_revision_is_stale():
    graph = DependencyGraph()
    graph.set_source("input", "i2")
    graph.set_artifact("run", "r1", dependencies={"input": "i1"})
    assert graph.state("run") is EvidenceState.STALE


def test_dependency_graph_rejects_cycles_and_restores_previous_node():
    graph = DependencyGraph()
    graph.set_source("a", "a1")
    graph.set_artifact("b", "b1", dependencies={"a": "a1"})

    with pytest.raises(DependencyGraphError, match="cycle"):
        graph.set_artifact("a", "a2", dependencies={"b": "b1"})

    assert graph.node("a") is not None
    assert graph.node("a").revision == "a1"
    assert graph.state("b") is EvidenceState.CURRENT


def test_snapshot_is_deterministic_and_exposes_five_state_labels():
    graph = DependencyGraph()
    graph.set_source("z-source", "z1")
    graph.set_source("a-source", None)
    graph.set_artifact(
        "historical",
        "h1",
        dependencies={"z-source": "z1"},
        historical=True,
    )
    graph.set_artifact(
        "invalid",
        "bad1",
        dependencies={"z-source": "z1"},
        integrity_valid=False,
    )
    graph.set_artifact("stale", "s1", dependencies={"z-source": "z0"})
    graph.set_artifact("current", "c1", dependencies={"z-source": "z1"})

    snapshot = graph.snapshot()
    assert [node["key"] for node in snapshot["nodes"]] == sorted(
        node["key"] for node in snapshot["nodes"]
    )
    states = {node["state"] for node in snapshot["nodes"]}
    assert states == {"current", "stale", "historical", "unresolved", "invalid"}
