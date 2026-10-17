from __future__ import annotations

import hashlib
import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from cleanroomx.gui_openfoam_trends import (
    openfoam_field_series_from_proofgraph,
)
from cleanroomx.gui_proofgraph import ProofGraphViewer
from cleanroomx.proofgraph_models import (
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    SimulationEvidence,
)


def _graph(
    *,
    malformed: bool = False,
    times: tuple[str, str] = ("10", "20"),
    partial: bool = False,
    unlinked: bool = False,
) -> dict:
    source = EvidenceSource(
        id="source:openfoam-sync:abc",
        kind="openfoam_result_sync",
        reference="sync-state.json",
        revision="a" * 64,
    )
    snapshot_ids = ("evidence:openfoam-snapshot:one", "evidence:openfoam-snapshot:two")
    snapshot_hashes = ("a" * 64, "b" * 64)
    snapshots = tuple(
        SimulationEvidence(
            id=identity,
            property_name="openfoam_vtk_snapshot",
            value={"solver_time": time, "snapshot_sha256": digest},
            source_id=source.id,
            version=digest,
        )
        for identity, time, digest in zip(snapshot_ids, times, snapshot_hashes)
    )
    samples = [
        {
            "solver_time_label": times[1],
            "snapshot_sha256": snapshot_hashes[1],
            "mesh_cells": 4,
            "minimum": [0.1],
            "volume_weighted_mean": [0.55],
            "maximum": [1.0],
        },
        {
            "solver_time_label": times[0],
            "snapshot_sha256": snapshot_hashes[0],
            "mesh_cells": 4,
            "minimum": [0.0],
            "volume_weighted_mean": [0.12345678901234566],
            "maximum": [0.8],
        },
    ]
    if malformed:
        samples[0]["volume_weighted_mean"] = [1.5]
    if partial:
        samples = samples[:1]
    if unlinked:
        samples[0]["snapshot_sha256"] = "c" * 64
    series = SimulationEvidence(
        id="evidence:openfoam-field-series:abc",
        property_name="openfoam_field_time_series",
        value={
            "simulation_id": "simulation-1",
            "case_id": "configuration-1/fine",
            "semantic": "normalized_tracer",
            "array_name": "C",
            "units": "1",
            "components": 1,
            "mean_weighting": "cell_volume",
            "case_snapshot_count": 2,
            "available_sample_count": len(samples),
            "coverage_status": "partial" if partial else "complete",
            "same_mesh_verified": False,
            "solver_time_semantics": "Numeric OpenFOAM time labels; physical-time units are not asserted.",
            "samples": samples,
            "interpretation": "descriptive field summaries only",
            "scientific_validation": "BLOCKED",
        },
        source_id=source.id,
        version="b" * 64,
        subject_ref="configuration-1/fine",
        provenance=(
            ProvenanceRecord(
                id="provenance:openfoam-field-series:abc",
                source_id=source.id,
                origin="verified retained snapshots",
                upstream_evidence_ids=(snapshot_ids[1],) if partial else snapshot_ids,
                method="summary only",
            ),
        ),
    )
    return ProofGraph(
        id="proofgraph:openfoam-trend-test",
        requirement_set=RequirementSet(
            id="requirements:openfoam-trend-test",
            version="1",
            title="OpenFOAM diagnostic trend fixture",
            source="test fixture",
            requirements=(
                Requirement(
                    id="requirement:openfoam-trend-test",
                    title="Retain imported field summaries",
                    source="test fixture",
                ),
            ),
        ),
        evidence_sources=(source,),
        evidence=(*snapshots, series),
    ).to_dict()


def test_openfoam_field_series_extracts_sorted_summary_points_only():
    series = openfoam_field_series_from_proofgraph(_graph())

    assert len(series) == 1
    assert series[0]["semantic"] == "normalized_tracer"
    assert [point["solver_time"] for point in series[0]["points"]] == ["10", "20"]
    assert [point["mean"] for point in series[0]["points"]] == [
        [0.12345678901234566],
        [0.55],
    ]
    assert [point["snapshot_evidence_id"] for point in series[0]["points"]] == [
        "evidence:openfoam-snapshot:one",
        "evidence:openfoam-snapshot:two",
    ]
    assert series[0]["coverage_status"] == "complete"
    assert all("values" not in point for point in series[0]["points"])
    assert series[0]["scientific_validation"] == "BLOCKED"


def test_openfoam_field_series_suppresses_invalid_numeric_payloads():
    assert openfoam_field_series_from_proofgraph(_graph(malformed=True)) == []


def test_openfoam_field_series_preserves_partial_coverage_and_snapshot_links():
    series = openfoam_field_series_from_proofgraph(_graph(partial=True))

    assert len(series) == 1
    assert len(series[0]["points"]) == 1
    assert series[0]["coverage_status"] == "partial"
    assert series[0]["available_sample_count"] == 1
    assert series[0]["case_snapshot_count"] == 2


def test_openfoam_field_series_rejects_samples_without_upstream_snapshot_evidence():
    assert openfoam_field_series_from_proofgraph(_graph(unlinked=True)) == []


def test_openfoam_field_series_accepts_zero_start_and_rejects_negative_times():
    series = openfoam_field_series_from_proofgraph(_graph(times=("0", "20")))
    assert [point["solver_time"] for point in series[0]["points"]] == ["0", "20"]

    assert openfoam_field_series_from_proofgraph(_graph(times=("-1", "20"))) == []


def test_openfoam_field_series_rejects_times_that_collapse_on_float_axis():
    series = openfoam_field_series_from_proofgraph(
        _graph(times=("0.1", "0.10000000000000000000001"))
    )

    assert series == []


def test_openfoam_field_trend_window_draws_a_theme_aware_line():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    viewer = ProofGraphViewer(root)
    viewer.pack(fill="both", expand=True)
    viewer.set_documents([_graph()])
    try:
        root.update()
        assert str(viewer.field_trends_button.cget("state")) == "normal"
        viewer.field_trends_button.invoke()
        window = viewer._field_trend_window
        assert window is not None
        assert window.window.winfo_exists()
        assert window.series_var.get().startswith("configuration-1/fine")
        assert window.canvas.find_all()
        assert "2/2 snapshots" in window.note_var.get()
        assert "same mesh not verified" in window.note_var.get()
        x, y, _point, _value = window._screen_points[0]
        window._on_motion(SimpleNamespace(x=x, y=y))
        assert "0.12345678901234566" in window.hover_var.get()
        assert "4 cells" in window.hover_var.get()
        window.apply_theme("dark")
        assert window.canvas.cget("background") == "#131920"
    finally:
        if viewer._field_trend_window is not None:
            viewer._field_trend_window.window.destroy()
        root.destroy()
