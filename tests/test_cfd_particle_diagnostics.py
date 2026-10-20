"""Unit-only trajectory diagnostics; synthetic cells are NOT CFD evidence."""
import copy
import json
import math

import pytest

from cleanroomx.cfd_particle_diagnostics import (
    SCHEMA, analyze_particle_trajectories, export_particle_trajectory_diagnostics,
)
from cleanroomx.cfd_particles import trace_screening_particle


def _computed_fixture(*, occupied=range(8)):
    return {
        "schema":"cleanroomx.multizone-results.v1",
        "time_name":"100",
        "voxel_pitch_m":[1.,1.,1.],
        "provenance":{
            "manifest_sha256":"a"*64,"run_receipt_sha256":"b"*64,
        },
        "cells":[{
            "center_m":[float(i)+.5,.5,.5],
            "velocity_m_s":[1.,0.,0.],
            "room_id":"first" if i<3 else "second",
        } for i in occupied],
    }


def _track(report=None, *, seed=(.5,.5,.5), max_time_s=1.):
    report = report or _computed_fixture()
    return trace_screening_particle(
        report,seed,max_time_s=max_time_s,max_step_s=.05,
        gravity_m_s2=(0,0,0),
    )


def test_polygonal_distance_elapsed_and_explicit_noncertification():
    report=_computed_fixture()
    track=_track(report,max_time_s=1.)
    d=analyze_particle_trajectories(report,[track])
    assert d["schema"]==SCHEMA
    assert d["engineering_release"]=="HOLD"
    assert d["validated_particle_transport"] is False
    assert d["source_manifest_sha256"]=="a"*64
    assert d["number_of_screening_tracks"]==1
    row=d["tracks"][0]
    assert row["polygonal_path_length_m"]==pytest.approx(1.)
    assert row["end_to_end_displacement_m"]==pytest.approx(1.)
    assert row["polygonal_tortuosity"]==pytest.approx(1.)
    assert row["recorded_sample_elapsed_s"]==pytest.approx(1.)
    assert row["first_observed_transition_count"]==0
    assert row["sample_labelled_time_by_room_s"]["first"]==pytest.approx(1.)
    assert "deposition efficiency" in d["interpretation"]["not_inferred"]


def test_cross_room_reports_first_observed_sampling_not_exact_crossing():
    report=_computed_fixture()
    track=_track(report,seed=(2.5,.5,.5),max_time_s=2.)
    d=analyze_particle_trajectories(report,[track])
    row=d["tracks"][0]
    assert row["start_room_id"]=="first"
    assert row["end_room_id"]=="second"
    assert row["first_observed_transition_count"]==1
    change=row["first_observed_room_transitions"][0]
    assert change["from_room"]=="first"
    assert change["to_room"]=="second"
    assert change["first_observed_at_sample_s"]>0
    assert sum(row["sample_labelled_time_by_room_s"].values())==pytest.approx(2)
    assert d["aggregate"]["first_observed_room_transitions"]==1


def test_multiple_tracks_and_stokes_warning_count():
    report=_computed_fixture()
    first=_track(report,max_time_s=.1)
    second=trace_screening_particle(
        report,(1.5,.5,.5),diameter_um=20.,
        initial_velocity_m_s=(5,0,0),
        max_time_s=.01,max_step_s=.01,gravity_m_s2=(0,0,0))
    d=analyze_particle_trajectories(report,[first,second])
    assert d["number_of_screening_tracks"]==2
    assert d["aggregate"]["tracks_with_stokes_regime_warning"]==1
    assert d["aggregate"]["termination_counts"]["max_particle_time"]==2
    assert d["aggregate"]["mean_polygonal_path_length_m"]>0


@pytest.mark.parametrize("field,value",[
    ("source_iteration","stale"),
    ("source_manifest_sha256","0"*64),
    ("source_run_receipt_sha256","0"*64),
    ("model","imaginary_physics"),
    ("validated_particle_transport",True),
    ("frozen_steady_velocity_no_solver_transient",False),
    ("turbulent_dispersion_modeled",True),
    ("deposition_or_resuspension_modeled",True),
])
def test_wrong_run_and_invented_physics_are_rejected(field,value):
    report=_computed_fixture()
    t=_track(report)
    t[field]=value
    with pytest.raises(ValueError,match="another run or unsupported physics"):
        analyze_particle_trajectories(report,[t])


@pytest.mark.parametrize("field,value,error",[
    ("room_id","invented","occupied cells"),
    ("recorded_gas_velocity_m_s",[100.,0.,0.],"occupied cells"),
    ("slip_reynolds",1e6,"slip Reynolds"),
    ("elapsed_particle_s",0.,"strictly"),
    ("xyz_m",[99.,0.,0.],"occupied cells"),
    ("particle_velocity_m_s",[math.nan,0.,0.],"finite"),
])
def test_tampered_vertex_rejected(field,value,error):
    report=_computed_fixture()
    track=_track(report)
    track["points"][1][field]=value
    with pytest.raises(ValueError,match=error):
        analyze_particle_trajectories(report,[track])


def test_crossing_missing_solid_voxel_rejected_even_if_both_endpoints_fluid():
    report=_computed_fixture(occupied=[0,2,3])
    # Manufactured jump from recorded cell 0 to recorded cell 2 is forbidden.
    track=_track(_computed_fixture(),max_time_s=.1)
    track["points"][-1]["xyz_m"]=[2.5,.5,.5]
    track["points"][-1]["room_id"]="first"
    with pytest.raises(ValueError,match="segment crosses"):
        analyze_particle_trajectories(report,[track])


def test_wrong_warning_and_max_reynolds_rejected():
    report=_computed_fixture()
    track=_track(report)
    track["stokes_regime_warning"]=True
    with pytest.raises(ValueError,match="summary is inconsistent"):
        analyze_particle_trajectories(report,[track])
    track=_track(report)
    track["max_slip_reynolds"]=99.
    with pytest.raises(ValueError,match="summary is inconsistent"):
        analyze_particle_trajectories(report,[track])


def test_nonfinite_bad_empty_and_invalid_source_rejected():
    report=_computed_fixture()
    with pytest.raises(ValueError,match="1 to 20"):
        analyze_particle_trajectories(report,[])
    with pytest.raises(ValueError,match="SHA-256"):
        analyze_particle_trajectories({**report,"provenance":{}},[_track(report)])
    track=_track(report)
    track["points"][1]["elapsed_particle_s"]=math.nan
    with pytest.raises(ValueError,match="finite"):
        analyze_particle_trajectories(report,[track])


def test_export_preserves_provenance_and_exclusively_creates(tmp_path):
    report=_computed_fixture()
    d=analyze_particle_trajectories(report,[_track(report)])
    file=tmp_path/"screening-diagnostics.json"
    assert export_particle_trajectory_diagnostics(d,file)==file
    loaded=json.loads(file.read_text())
    assert loaded["engineering_release"]=="HOLD"
    assert loaded["tracks"][0]["polygonal_path_length_m"]==pytest.approx(1)
    with pytest.raises(FileExistsError):
        export_particle_trajectory_diagnostics(d,file)
    fabricated=copy.deepcopy(d)
    fabricated["validated_particle_transport"]=True
    with pytest.raises(ValueError,match="noncertifying"):
        export_particle_trajectory_diagnostics(fabricated,tmp_path/"bad.json")
