"""Deterministic synthetic particle-seed fixtures, NOT physical CFD evidence."""
from __future__ import annotations

import copy

import pytest

from cleanroomx.cfd_particle_ensemble import (
    SCHEMA, choose_recorded_particle_seeds, inject_recorded_particle_ensemble,
)
from cleanroomx.cfd_particles import trace_screening_particle


def _source():
    return {
        "schema":"cleanroomx.multizone-results.v1",
        "time_name":"50",
        "voxel_pitch_m":[1.,1.,1.],
        "provenance":{"manifest_sha256":"a"*64,"run_receipt_sha256":"b"*64},
        "cells":[
            {"center_m":[i+.5,.5,.5],"room_id":"A" if i<4 else "B",
             "velocity_m_s":[1.,0.,0.]}
            for i in range(8)
        ],
    }


def test_deterministic_farthest_seeding_uses_actual_centres_independent_of_order():
    report=_source()
    a=choose_recorded_particle_seeds(report,count=4)
    assert a["requested_count"]==4
    assert a["candidate_recorded_centres"]==8
    assert a["selected_centres_m"]==[
        [3.5,.5,.5],[7.5,.5,.5],[.5,.5,.5],[5.5,.5,.5],
    ]
    shuffled=copy.deepcopy(report)
    shuffled["cells"].reverse()
    b=choose_recorded_particle_seeds(shuffled,count=4)
    assert b["selected_centres_m"]==a["selected_centres_m"]
    assert a["nonstatistical_geometry_sampling"] is True


def test_room_and_plane_filter_do_not_create_uncomputed_cells():
    report=_source()
    a=choose_recorded_particle_seeds(report,count=2,room_id="B")
    assert len(a["selected_centres_m"])==2
    assert all(p[0]>=4.5 for p in a["selected_centres_m"])
    plane=choose_recorded_particle_seeds(
        report,count=1,room_id="A",plane_axis="x",plane_position_m=2.5)
    assert plane["selected_centres_m"]==[[2.5,.5,.5]]
    with pytest.raises(ValueError,match="Not enough distinct"):
        choose_recorded_particle_seeds(report,count=2,plane_axis="x",plane_position_m=2.5)
    with pytest.raises(ValueError,match="No computed cells"):
        choose_recorded_particle_seeds(report,count=1,plane_axis="z",plane_position_m=50)


def test_existing_seed_is_not_selected_twice_and_tracks_not_mutated():
    r=_source()
    original=trace_screening_particle(
        r,[3.5,.5,.5],max_time_s=.05,gravity_m_s2=(0,0,0))
    prior=copy.deepcopy(original)
    result=inject_recorded_particle_ensemble(
        r,[original],count=2,max_time_s=.1)
    assert original==prior
    assert result["schema"]==SCHEMA
    assert result["engineering_release"]=="HOLD"
    assert result["statistical_or_certified_particle_transport"] is False
    assert len(result["new_tracks"])==2
    selected=result["sampling"]["selected_centres_m"]
    assert [3.5,.5,.5] not in selected
    assert len(set(tuple(x) for x in selected))==2
    assert result["noncertifying_diagnostics"]["number_of_screening_tracks"]==3
    assert result["noncertifying_diagnostics"]["engineering_release"]=="HOLD"


@pytest.mark.parametrize("count",[-1,0,21,True,1.5])
def test_rejects_invalid_or_unbounded_seed_count(count):
    with pytest.raises(ValueError,match="1 to 20"):
        choose_recorded_particle_seeds(_source(),count=count)


def test_exclusions_must_be_recorded_cell_centres():
    with pytest.raises(ValueError,match="Excluded seed"):
        choose_recorded_particle_seeds(
            _source(),count=1,excluded_centres=[[1.,.5,.5]])
    with pytest.raises(ValueError,match="Excluded seed"):
        choose_recorded_particle_seeds(
            _source(),count=1,excluded_centres=[[99.,.5,.5]])


def test_fails_closed_on_stale_current_particles_and_capacity():
    r=_source()
    old=trace_screening_particle(r,[.5,.5,.5],max_time_s=.1)
    stale=copy.deepcopy(old)
    stale["source_iteration"]="100"
    with pytest.raises(ValueError,match="another run"):
        inject_recorded_particle_ensemble(r,[stale],count=1)
    with pytest.raises(ValueError,match="remaining 20-particle capacity"):
        inject_recorded_particle_ensemble(r,[old]*20,count=1)
    with pytest.raises(ValueError,match="remaining 20-particle capacity"):
        inject_recorded_particle_ensemble(r,[],count=0)


def test_atomic_result_and_invalid_physics():
    report=_source()
    tracks=[]
    before=copy.deepcopy(tracks)
    with pytest.raises(ValueError,match="diameter"):
        inject_recorded_particle_ensemble(
            report,tracks,count=2,diameter_um=0)
    assert tracks==before
    result=inject_recorded_particle_ensemble(
        report,tracks,count=2,max_time_s=.1)
    assert tracks==before
    assert len(result["new_tracks"])==2
    for item in result["new_tracks"]:
        assert item["source_iteration"]=="50"
        assert item["source_manifest_sha256"]=="a"*64
        assert item["validated_particle_transport"] is False
