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
    computed_trace_polydata, sampled_velocity_glyph_actor, select_recorded_cells,
    seed_streamline_from_displayed_point, _recorded_cell_actor,
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


def test_3d_velocity_glyphs_use_recorded_vectors_and_are_bounded():
    report=_source()
    actor=sampled_velocity_glyph_actor(report,max_arrows=2)
    poly=actor.GetMapper().GetInput()
    actor.GetMapper().Update()
    poly=actor.GetMapper().GetInput()
    assert isinstance(actor,vtk.vtkActor)
    assert poly.GetNumberOfPoints() > 0
    renderer=build_multizone_vtk_renderer(report,[],vectors=True)
    base=build_multizone_vtk_renderer(report,[],vectors=False)
    assert renderer.GetActors().GetNumberOfItems() == base.GetActors().GetNumberOfItems()+1
    with pytest.raises(ValueError, match="boolean"):
        build_multizone_vtk_renderer(report,[],vectors=1)
    with pytest.raises(ValueError, match="max_arrows"):
        sampled_velocity_glyph_actor(report,max_arrows=0)


def test_3d_velocity_glyphs_handle_zero_velocity_without_invented_arrows():
    report=_source()
    for cell in report["cells"]:
        cell["velocity_m_s"]=[0.,0.,0.]
    actor=sampled_velocity_glyph_actor(report,max_arrows=3)
    actor.GetMapper().Update()
    assert actor.GetMapper().GetInput().GetNumberOfPoints()==0


def test_recorded_3d_plane_does_not_interpolate_missing_solver_values():
    report=_source()
    original=select_recorded_cells(report)
    assert len(original)==3
    x_plane=select_recorded_cells(
        report,plane_axis="x",plane_position_m=1.5)
    assert len(x_plane)==1
    assert x_plane[0]["center_m"]==[1.5,0.5,0.5]
    filtered=computed_field_polydata(
        report,plane_axis="x",plane_position_m=1.5)
    assert filtered.GetNumberOfPoints()==filtered.GetNumberOfVerts()==1
    assert filtered.GetPoint(0)==pytest.approx([1.5,0.5,0.5])
    assert filtered.GetPointData().GetArray(
        "Computed pressure relative (Pa)").GetTuple1(0)==pytest.approx(0.0)
    assert select_recorded_cells(report,plane_axis="y",plane_position_m=.5)==original
    assert select_recorded_cells(report,plane_axis="z",plane_position_m=.5)==original
    renderer=build_multizone_vtk_renderer(
        report,[],room_id="r1",plane_axis="x",plane_position_m=1.5)
    assert isinstance(renderer,vtk.vtkRenderer)
    with pytest.raises(ValueError,match="No computed cells"):
        computed_field_polydata(report,plane_axis="x",plane_position_m=50)


@pytest.mark.parametrize("kwargs,error",[
    ({"room_id":"unknown"},"existing computed room"),
    ({"plane_axis":"t"},"Plane axis"),
    ({"plane_axis":"z","plane_position_m":float("nan")},"finite"),
    ({"plane_axis":"x","plane_position_m":float("inf")},"finite"),
    ({"plane_axis":"x"},"finite"),
    ({"plane_axis":"all","plane_position_m":.5},"omitted"),
])
def test_recorded_3d_filter_rejects_invalid_or_unsolved_selection(kwargs,error):
    with pytest.raises(ValueError,match=error):
        select_recorded_cells(_source(),**kwargs)


def test_recorded_3d_room_filter_preserves_only_selected_room_membership():
    report=_source()
    report["cells"][-1]["room_id"]="r2"
    report["geometry"]["r1"]["length_m"]=2.
    report["geometry"]["r2"]={
        "x_m":2.,"y_m":0.,"floor_elevation_m":0.,
        "length_m":1.,"width_m":1.,"height_m":1.
    }
    chosen=select_recorded_cells(report,room_id="r2")
    assert len(chosen)==1
    assert chosen[0]["center_m"]==[2.5,0.5,0.5]
    field=computed_field_polydata(report,room_id="r2")
    assert field.GetNumberOfPoints()==1
    only_one_room=build_multizone_vtk_renderer(
        report,[],room_id="r2",vectors=False)
    two_rooms=build_multizone_vtk_renderer(
        report,[],vectors=False)
    assert two_rooms.GetActors().GetNumberOfItems()==only_one_room.GetActors().GetNumberOfItems()+1


def test_3d_point_seed_comes_from_displayed_recorded_cell_only():
    report=_source()
    trace=seed_streamline_from_displayed_point(report,[],1,
        room_id="r1",plane_axis="x",plane_position_m=1.5)
    assert trace["points"][0]["xyz_m"]==[1.5,.5,.5]
    assert trace["source_iteration"]==report["time_name"]
    assert trace["validated_particle_tracking"] is False
    selected=build_multizone_vtk_renderer(report,[],vectors=False)
    actor=_recorded_cell_actor(selected)
    assert actor.GetMapper().GetInput().GetNumberOfPoints()==3
    assert actor.GetMapper().GetInput().GetPointData().GetArray(
        "Computed U (m/s)") is not None
    with pytest.raises(ValueError,match="not in the displayed"):
        seed_streamline_from_displayed_point(
            report,[],2,plane_axis="x",plane_position_m=1.5)
    with pytest.raises(ValueError,match="integer"):
        seed_streamline_from_displayed_point(report,[],True)
    with pytest.raises(ValueError,match="at most 20"):
        seed_streamline_from_displayed_point(report,[trace]*20,0)
    tampered=copy.deepcopy(trace)
    tampered["source_iteration"]="stale"
    with pytest.raises(ValueError,match="originate"):
        seed_streamline_from_displayed_point(report,[tampered],0)
