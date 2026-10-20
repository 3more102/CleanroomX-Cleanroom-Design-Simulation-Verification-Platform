"""VTK structural checks; no display, synthetic solver fields or CFD claims.

The real OpenFOAM reader/tracing integration is exercised independently in
tests/test_cfd_multizone_execution.py when Foundation v10 is installed.
"""
import copy
import math

import pytest

vtk = pytest.importorskip("vtk")

from cleanroomx.cfd_multizone_vtk import (
    MAX_3D_CELLS, build_multizone_vtk_renderer, computed_field_polydata,
    computed_trace_polydata,
)
from cleanroomx.cfd_streamlines import trace_computed_streamline


def _source():
    return {
        "schema": "cleanroomx.multizone-results.v1",
        "time_name": "50",
        "provenance": {"manifest_sha256": "a"*64, "run_receipt_sha256": "b"*64},
        "voxel_pitch_m": [1.,1.,1.],
        "geometry": {"r1": {"x_m":0., "y_m":0., "floor_elevation_m":0.,
                             "length_m":3., "width_m":1., "height_m":1.}},
        "cells": [
            {"center_m":[i+0.5,0.5,0.5], "velocity_m_s":[1.,0.,0.],
             "pressure_pa_relative_to_reference":float(i-1),"room_id":"r1"}
            for i in range(3)
        ],
    }


def test_native_vtk_points_are_recorded_velocity_and_pressure_not_fabricated():
    report = _source()
    data = computed_field_polydata(report)
    assert data.GetNumberOfPoints() == 3
    assert data.GetNumberOfVerts() == 3
    for i, cell in enumerate(report["cells"]):
        assert data.GetPoint(i) == pytest.approx(cell["center_m"])
        assert data.GetPointData().GetArray("Computed U (m/s)").GetTuple3(i) == pytest.approx(
            cell["velocity_m_s"])
        assert data.GetPointData().GetArray("Computed speed (m/s)").GetTuple1(i) == pytest.approx(1.)
        assert data.GetPointData().GetArray("Computed pressure relative (Pa)").GetTuple1(i) == pytest.approx(i-1)


def test_native_vtk_3d_trace_comes_only_from_this_solver_run():
    report = _source()
    trace = trace_computed_streamline(report,(0.5,0.5,0.5),max_integration_s=1.5)
    paths = computed_trace_polydata(report,[trace])
    assert paths.GetNumberOfLines() == 1
    assert paths.GetNumberOfPoints() == len(trace["points"])
    assert paths.GetPoint(paths.GetNumberOfPoints()-1) == pytest.approx((2.,0.5,0.5))
    assert computed_trace_polydata(report,[]).GetNumberOfPoints() == 0
    wrong = copy.deepcopy(trace)
    wrong["source_iteration"] = "100"
    with pytest.raises(ValueError,match="originate"):
        computed_trace_polydata(report,[wrong])


def test_vtk_renderer_is_a_true_3d_scene_with_scalar_bars_and_room_bounds():
    report = _source()
    line = trace_computed_streamline(report,(0.5,0.5,0.5),max_integration_s=1.0)
    renderer = build_multizone_vtk_renderer(report,[line],field="speed")
    assert isinstance(renderer,vtk.vtkRenderer)
    assert renderer.GetActors().GetNumberOfItems() >= 3  # Field, streamlines, room outline
    renderer2 = build_multizone_vtk_renderer(report,[line],field="pressure")
    assert isinstance(renderer2,vtk.vtkRenderer)
    with pytest.raises(ValueError,match="speed or pressure"):
        build_multizone_vtk_renderer(report,[line],field="bogus")


def test_vtk_rejects_missing_solved_cells_nonfinite_and_wall_crossing_paths():
    report = _source()
    report["cells"][0]["pressure_pa_relative_to_reference"] = math.nan
    with pytest.raises(ValueError,match="pressure"):
        computed_field_polydata(report)
    report = _source()
    trace = trace_computed_streamline(report,(0.5,0.5,0.5),max_integration_s=1.)
    trace["points"][-1]["xyz_m"] = [99.,0.5,0.5]
    with pytest.raises(ValueError,match="outside computed fluid"):
        computed_trace_polydata(report,[trace])
    report = _source()
    report["cells"][1]["center_m"][0] += 0.13
    with pytest.raises(ValueError,match="lattice"):
        computed_field_polydata(report)
