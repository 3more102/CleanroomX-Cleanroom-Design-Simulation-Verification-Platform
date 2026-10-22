"""Synthetic *unit* tests for the streamline numerical contract.

These fixtures are explicitly NOT OpenFOAM runs or physical validation evidence.
Actual solver-field provenance is verified by the multizone integration suite.
"""
import copy
import json
import math

import pytest

from cleanroomx.cfd_streamlines import (
    ComputedVelocityGrid, TRACE_SCHEMA, trace_computed_streamline, export_computed_streamlines,
)


def _report(indices=range(8), velocity=(1.0, 0.0, 0.0)):
    return {
        "schema": "cleanroomx.multizone-results.v1",
        "voxel_pitch_m": [1.0, 1.0, 1.0],
        "time_name": "100",
        "provenance": {"manifest_sha256": "a"*64, "run_receipt_sha256": "b"*64},
        "cells": [
            {"center_m": [i + 0.5, 0.5, 0.5], "velocity_m_s": list(velocity),
             "room_id": "A" if i < 3 else "B"}
            for i in indices
        ],
    }


def test_constant_computed_velocity_has_bounded_time_and_displacement():
    trace = trace_computed_streamline(_report(), [0.5, 0.5, 0.5],
                                      max_integration_s=1.0)
    assert trace["schema"] == TRACE_SCHEMA
    assert trace["source_iteration"] == "100"
    assert trace["source_manifest_sha256"] == "a"*64
    assert trace["integration_parameter_not_physical_transient_time"] is True
    assert trace["validated_particle_tracking"] is False
    assert trace["termination"] == "max_integration_parameter"
    assert trace["points"][-1]["xyz_m"] == pytest.approx([1.5, 0.5, 0.5])
    assert trace["points"][-1]["integration_parameter_s"] == pytest.approx(1.0)


def test_never_crosses_missing_fluid_cell_between_rooms():
    trace = trace_computed_streamline(_report([0, 1, 3, 4, 5]),
                                      (0.5, 0.5, 0.5), max_integration_s=20)
    assert trace["termination"] == "domain_exit"
    assert max(p["xyz_m"][0] for p in trace["points"]) < 2.0
    assert all(p["room_id"] == "A" for p in trace["points"])


def test_connected_cells_can_cross_room_boundary_without_fabricated_door_flux():
    trace = trace_computed_streamline(_report(), (2.5, 0.5, 0.5),
                                      max_integration_s=1.5)
    assert {p["room_id"] for p in trace["points"]} == {"A", "B"}
    assert trace["points"][-1]["xyz_m"][0] == pytest.approx(4.0)


def test_stagnation_is_reported_without_artificial_movement():
    trace = trace_computed_streamline(_report(velocity=(0, 0, 0)),
                                      (1.5, 0.5, 0.5))
    assert trace["termination"] == "stagnation"
    assert len(trace["points"]) == 1


def test_reject_missing_seed_and_noncomputed_source():
    with pytest.raises(ValueError, match="Seed"):
        trace_computed_streamline(_report(), (20, 0.5, 0.5))
    with pytest.raises(ValueError, match="computed multiroom"):
        trace_computed_streamline({"schema": "synthetic"}, (0.5, 0.5, 0.5))
    with pytest.raises(ValueError, match="seed coordinate"):
        trace_computed_streamline(_report(), (math.nan, 0.5, 0.5))


@pytest.mark.parametrize("parameter,value", [
    ("max_integration_s", 0), ("max_integration_s", math.inf),
    ("step_fraction", 0), ("step_fraction", 0.9),
    ("min_speed_m_s", -1), ("max_steps", 0), ("max_steps", 1.5),
])
def test_invalid_integration_parameters_fail_closed(parameter, value):
    with pytest.raises(ValueError):
        trace_computed_streamline(_report(), (0.5, 0.5, 0.5),
                                  **{parameter: value})


def test_rejects_duplicate_cells_and_nonfinite_or_off_lattice_samples():
    report = _report()
    report["cells"].append(copy.deepcopy(report["cells"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        ComputedVelocityGrid(report)
    report = _report()
    report["cells"][1]["velocity_m_s"][0] = math.nan
    with pytest.raises(ValueError, match="finite"):
        ComputedVelocityGrid(report)
    report = _report()
    report["cells"][1]["center_m"][0] += 0.2
    with pytest.raises(ValueError, match="lattice"):
        ComputedVelocityGrid(report)


def test_gui_click_on_computed_cell_traces_recorded_three_dimensional_field():
    """Headless event-contract test; no screenshots or fake CFD execution."""
    from types import SimpleNamespace
    from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow

    updates = []
    redraws = []
    sample = _report()["cells"][0]
    fake_window = SimpleNamespace(
        report=_report(), running=False, trace_paths=[],
        _section_to_pixel=lambda x, y: (x*20, y*20),
        _section_plane_axes=(0, 1), _section_half_size=(0.5, 0.5),
        _section_scale=20, _section_samples=[sample],
        trace_status=SimpleNamespace(set=updates.append),
        draw_section=lambda: redraws.append(True),
    )
    MultizoneCFDWindow.seed_streamline_at_click(
        fake_window, SimpleNamespace(x=10, y=10))
    assert len(fake_window.trace_paths) == 1
    assert fake_window.trace_paths[0]["points"][0]["xyz_m"] == sample["center_m"]
    assert redraws == [True]
    assert "not transient particle motion" in updates[-1]


def test_exported_streamlines_are_provenance_tagged_and_never_overwritten(tmp_path):
    trace = trace_computed_streamline(_report(), (0.5, 0.5, 0.5),
                                      max_integration_s=1)
    destination = tmp_path / "traces.json"
    assert export_computed_streamlines([trace], destination) == destination
    payload = json.loads(destination.read_text())
    assert payload["source_manifest_sha256"] == "a"*64
    assert payload["source_run_receipt_sha256"] == "b"*64
    assert payload["source_iteration"] == "100"
    assert payload["traces"][0]["points"][-1]["xyz_m"] == pytest.approx([1.5, 0.5, 0.5])
    assert "NOT solver transient time" in payload["units"]["integration_parameter_s"]
    with pytest.raises(FileExistsError):
        export_computed_streamlines([trace], destination)
    other = copy.deepcopy(trace)
    other["source_iteration"] = "50"
    with pytest.raises(ValueError, match="one recorded CFD iteration"):
        export_computed_streamlines([trace, other], tmp_path / "invalid.json")
    assert not (tmp_path / "invalid.json").exists()
