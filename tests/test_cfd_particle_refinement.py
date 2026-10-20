"""Synthetic particle integrator step checks; not OpenFOAM or physical evidence."""
from __future__ import annotations

import copy
import json
import math

import pytest

from cleanroomx.cfd_particle_refinement import (
    SCHEMA, analyze_particle_timestep_refinement,
    export_particle_timestep_refinement,
)
from cleanroomx.cfd_particles import trace_screening_particle


def _report(*, u=(1.,0.,0.), occupied=range(8)):
    return {
        "schema":"cleanroomx.multizone-results.v1",
        "time_name":"50",
        "voxel_pitch_m":[1.,1.,1.],
        "provenance":{
            "manifest_sha256":"a"*64,
            "run_receipt_sha256":"b"*64,
        },
        "cells":[{
            "center_m":[i+.5,.5,.5],
            "room_id":"left" if i<3 else "right",
            "velocity_m_s":list(u),
        } for i in occupied],
    }


def _baseline(report=None, *, seed=(.5,.5,.5), **kwargs):
    r=report if report is not None else _report()
    defaults={
        "max_time_s":.4,
        "max_step_s":.05,
        "gravity_m_s2":(0,0,0),
    }
    defaults.update(kwargs)
    return trace_screening_particle(r,seed,**defaults)


def test_particle_original_conditions_are_recorded_and_exactly_replayed():
    r=_report()
    path=_baseline(
        r,initial_velocity_m_s=(0,0,0),max_steps=1000)
    assert path["initial_particle_velocity_m_s"]==[0.,0.,0.]
    assert path["gravity_m_s2"]==[0.,0.,0.]
    assert path["max_steps"]==1000
    assert path["slip_mean_free_path_m"]==pytest.approx(66e-9)
    original=copy.deepcopy(path)
    study=analyze_particle_timestep_refinement(
        r,path,endpoint_tolerance_m=1e-5)
    assert original==path
    assert study["schema"]==SCHEMA
    assert study["screening_status"]=="bounded_endpoint_change_under_tolerance"
    assert study["actual_timestep_refinement_observed"]
    assert study["low_slip_reynolds_on_all_runs"]
    assert study["all_runs_completed_full_integration_horizon"]
    assert study["source_run_receipt_sha256"]=="b"*64
    assert [round(row["configured_max_step_s"],5)
            for row in study["runs"]]==[.05,.025,.0125]
    assert [row["integration_segments"] for row in study["runs"]]==[8,16,32]
    assert all(row["termination"]=="max_particle_time" for row in study["runs"])
    assert study["endpoint_delta_half_to_quarter_m"]<=1e-5
    assert study["validated_particle_transport"] is False
    assert study["engineering_release"]=="HOLD"
    assert study["not_physical_convergence"]


def test_replay_respects_gravity_and_initial_velocity():
    report=_report(u=(0,0,0))
    trajectory=_baseline(
        report,seed=(.5,.5,.5),max_time_s=.03,max_step_s=.02,
        initial_velocity_m_s=(.2,0,.1),gravity_m_s2=(0,0,-9.80665))
    study=analyze_particle_timestep_refinement(report,trajectory)
    assert study["original_gravity_m_s2"]==[0.,0.,-9.80665]
    assert study["original_initial_velocity_m_s"]==[.2,0.,.1]
    assert study["engineering_release"]=="HOLD"
    assert len(study["runs"])==3


def test_nominal_smaller_caps_do_not_count_as_refinement_if_actual_step_unchanged():
    report=_report()
    # End the study before any step cap limits the integration.
    path=_baseline(report,max_time_s=.001,max_step_s=.05)
    result=analyze_particle_timestep_refinement(report,path)
    assert not result["actual_timestep_refinement_observed"]
    assert result["screening_status"]=="not_demonstrated"
    assert all(x["integration_segments"]==1 for x in result["runs"])


def test_wall_contact_is_explicit_not_deposition_or_converged():
    report=_report(occupied=[0,1])
    path=_baseline(report,seed=(1.5,.5,.5),max_time_s=2.)
    assert path["termination"]=="fluid_boundary_contact_unresolved"
    study=analyze_particle_timestep_refinement(report,path)
    assert study["screening_status"]=="not_demonstrated"
    assert not study["all_runs_completed_full_integration_horizon"]
    assert "No particle concentration" in study["limitations"][2]


def test_high_slip_reynolds_prevents_positive_screening_verdict():
    report=_report(u=(0,0,0))
    path=_baseline(
        report,max_time_s=.04,max_step_s=.02,
        diameter_um=20.,initial_velocity_m_s=(5,0,0))
    assert path["stokes_regime_warning"]
    study=analyze_particle_timestep_refinement(report,path)
    assert not study["low_slip_reynolds_on_all_runs"]
    assert study["screening_status"]=="not_demonstrated"


@pytest.mark.parametrize("mutate,expected",[
    (lambda t:t.pop("initial_particle_velocity_m_s"),"lacks complete"),
    (lambda t:t.pop("gravity_m_s2"),"lacks complete"),
    (lambda t:t.pop("max_steps"),"lacks complete"),
    (lambda t:t.update({"gravity_m_s2":[0,0,10]}),"baseline trajectory"),
    (lambda t:t.update({"max_steps":1}),"baseline trajectory"),
    (lambda t:t.update({"initial_particle_velocity_m_s":[10,0,0]}),
     "disagrees with recorded first sample"),
    (lambda t:t.update({"slip_mean_free_path_m":1e-7}),"unsupported"),
    (lambda t:t.update({"source_iteration":"wrong"}),"another run"),
])
def test_legacy_or_tampered_settings_fail_closed(mutate,expected):
    r=_report()
    t=_baseline(r)
    mutate(t)
    with pytest.raises(ValueError,match=expected):
        analyze_particle_timestep_refinement(r,t)


def test_refinement_rejects_invalid_tolerance_and_source():
    r=_report()
    t=_baseline(r)
    for invalid in (0, -1, math.nan, math.inf, 1.01, True):
        with pytest.raises(ValueError,match="tolerance|finite"):
            analyze_particle_timestep_refinement(
                r,t,endpoint_tolerance_m=invalid)
    changed=copy.deepcopy(r)
    changed["provenance"]["run_receipt_sha256"]="c"*64
    with pytest.raises(ValueError,match="another run"):
        analyze_particle_timestep_refinement(changed,t)


def test_new_json_export_is_noncertifying_and_refuses_overwrite(tmp_path):
    r=_report()
    study=analyze_particle_timestep_refinement(r,_baseline(r))
    destination=tmp_path/"timestep-refinement.json"
    assert export_particle_timestep_refinement(study,destination)==destination
    parsed=json.loads(destination.read_text())
    assert parsed["engineering_release"]=="HOLD"
    assert len(parsed["runs"])==3
    assert parsed["not_mesh_independence"]
    with pytest.raises(FileExistsError):
        export_particle_timestep_refinement(study,destination)
    corrupted=copy.deepcopy(study)
    corrupted["validated_particle_transport"]=True
    with pytest.raises(ValueError,match="noncertifying"):
        export_particle_timestep_refinement(corrupted,tmp_path/"fake.json")
