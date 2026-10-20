"""Deterministic unit checks for a limited *one-way frozen CFD field* particle model.

All reports in this file are deliberately synthetic and are not OpenFOAM
simulation, cleanroom performance or validated aerosol deposition evidence.
"""
import copy
import json
import math

import pytest

from cleanroomx.cfd_particles import (
    PARTICLE_SCHEMA, cunningham_slip, trace_screening_particle,
    export_screening_particles, particle_positions_at_elapsed,
)
from cleanroomx.cfd_streamlines import ComputedVelocityGrid


def _report(*, air=(1.,0.,0.), positions=range(8)):
    return {
        "schema":"cleanroomx.multizone-results.v1", "time_name":"100",
        "voxel_pitch_m":[1.,1.,1.],
        "provenance":{"manifest_sha256":"a"*64,"run_receipt_sha256":"b"*64},
        "cells":[{"center_m":[i+.5,.5,.5],"velocity_m_s":list(air),
                  "pressure_pa_relative_to_reference":0.,
                  "room_id":"first" if i<3 else "second"}
                 for i in positions],
    }


def test_constant_gas_velocity_particle_advects_in_elapsed_particle_time():
    report=_report()
    trace=trace_screening_particle(report,[.5,.5,.5],
        gravity_m_s2=(0,0,0),max_time_s=1,max_step_s=.05)
    assert trace["schema"]==PARTICLE_SCHEMA
    assert trace["termination"]=="max_particle_time"
    assert trace["points"][-1]["xyz_m"]==pytest.approx([1.5,.5,.5],abs=1e-9)
    assert trace["points"][-1]["elapsed_particle_s"]==pytest.approx(1.)
    assert trace["points"][-1]["particle_velocity_m_s"]==pytest.approx([1.,0.,0.])
    assert not trace["stokes_regime_warning"]
    assert trace["validated_particle_transport"] is False
    assert trace["source_run_receipt_sha256"]=="b"*64


def test_exact_stokes_velocity_relaxation_in_nonzero_carrier_gas():
    r=_report()
    d_um=20.
    trace=trace_screening_particle(
        r,[.5,.5,.5],diameter_um=d_um,max_time_s=.01,max_step_s=.01,
        initial_velocity_m_s=(0,0,0),gravity_m_s2=(0,0,0))
    tau=trace["particle_relaxation_s"]
    exp_factor=math.exp(-.01/tau)
    expected_v=1-exp_factor
    expected_x=.5+.01-tau*(1-exp_factor)
    assert trace["points"][-1]["particle_velocity_m_s"][0]==pytest.approx(expected_v,abs=1e-10)
    assert trace["points"][-1]["xyz_m"][0]==pytest.approx(expected_x,abs=1e-10)
    assert trace["cunningham_slip_correction"]>1.


def test_gravity_settling_scales_with_particle_size_for_still_air():
    # One stationary occupied fluid cell. Vertical movement stays inside.
    r=_report(air=(0,0,0),positions=[0])
    small=trace_screening_particle(r,[.5,.5,.5],
                                  diameter_um=1.,max_time_s=2.)
    large=trace_screening_particle(r,[.5,.5,.5],
                                  diameter_um=20.,max_time_s=2.)
    assert small["points"][-1]["xyz_m"][2]<.5
    assert large["points"][-1]["xyz_m"][2]<small["points"][-1]["xyz_m"][2]
    assert large["termination"]=="max_particle_time"
    assert large["particle_relaxation_s"]>small["particle_relaxation_s"]


def test_never_advects_a_particle_through_a_missing_fluid_voxel():
    r=_report(positions=[0,1,3,4,5])
    trace=trace_screening_particle(r,[.5,.5,.5],
        gravity_m_s2=(0,0,0),max_time_s=4.)
    assert trace["termination"]=="fluid_boundary_contact_unresolved"
    grid=ComputedVelocityGrid(r)
    assert all(grid.cell_at(p["xyz_m"]) for p in trace["points"])
    assert max(p["xyz_m"][0] for p in trace["points"])<=2.+1e-6
    assert all(p["room_id"]=="first" for p in trace["points"])


def test_particle_uses_cross_room_velocity_from_actual_recorded_cells():
    r=_report()
    trace=trace_screening_particle(r,[2.5,.5,.5],
        gravity_m_s2=(0,0,0),max_time_s=2.)
    assert {p["room_id"] for p in trace["points"]}=={"first","second"}
    assert trace["termination"]=="max_particle_time"


def test_high_slip_reynolds_emits_validity_warning_instead_of_certifying():
    r=_report(air=(0,0,0))
    track=trace_screening_particle(
        r,[.5,.5,.5],diameter_um=20.,initial_velocity_m_s=(5,0,0),
        max_time_s=.01,gravity_m_s2=(0,0,0))
    assert track["max_slip_reynolds"]>=1
    assert track["stokes_regime_warning"]
    assert not track["validated_particle_transport"]


@pytest.mark.parametrize("kwargs,error",[
    ({"diameter_um":0},"diameter"),
    ({"diameter_um":21},"diameter"),
    ({"particle_density_kg_m3":50},"density"),
    ({"air_density_kg_m3":10000},"density"),
    ({"air_dynamic_viscosity_pa_s":0},"viscosity"),
    ({"max_time_s":0},"duration"),
    ({"max_step_s":1},"time step"),
    ({"max_steps":0},"max_steps"),
    ({"gravity_m_s2":(0,0,100)},"Gravity"),
    ({"initial_velocity_m_s":(math.nan,0,0)},"finite"),
])
def test_invalid_particle_physics_fail_closed(kwargs,error):
    with pytest.raises(ValueError,match=error):
        trace_screening_particle(_report(),[.5,.5,.5],**kwargs)


def test_rejects_seed_outside_recorded_fluid_and_fake_report():
    with pytest.raises(ValueError,match="recorded fluid cell"):
        trace_screening_particle(_report(),[99,0,0])
    with pytest.raises(ValueError,match="computed multiroom"):
        trace_screening_particle({"schema":"fake"},[.5,.5,.5])


def test_particle_json_provenance_and_no_overwrite(tmp_path):
    t=trace_screening_particle(_report(),[.5,.5,.5],max_time_s=.1)
    path=tmp_path/"particle-screening.json"
    assert export_screening_particles([t],path)==path
    payload=json.loads(path.read_text())
    assert payload["schema"]=="cleanroomx.particle-screening-collection.v1"
    assert payload["source_manifest_sha256"]=="a"*64
    assert payload["validation"]=="one_way_frozen_field_screening_not_certified_particle_transport"
    with pytest.raises(FileExistsError):
        export_screening_particles([t],path)
    stale=copy.deepcopy(t)
    stale["source_iteration"]="different"
    with pytest.raises(ValueError,match="share a recorded"):
        export_screening_particles([t,stale],tmp_path/"bad.json")


def test_curved_inertial_trajectory_cannot_exit_cell_then_reenter_unseen():
    # Near the wall, the particle initially moves right but gas moves left.
    # Both endpoints of a long step may remain in cell 0 even though the
    # exact-in-time trajectory first crosses the wall. Testing only the
    # endpoint chord would silently allow false wall penetration.
    report=_report(air=(-5.,0,0),positions=[0])
    path=trace_screening_particle(
        report,(.999,.5,.5),diameter_um=20.,
        initial_velocity_m_s=(5,0,0),gravity_m_s2=(0,0,0),
        max_time_s=.01,max_step_s=.05)
    assert path["termination"]=="fluid_boundary_contact_unresolved"
    assert len(path["points"])>=1
    assert all(ComputedVelocityGrid(report).cell_at(p["xyz_m"])
               is not None for p in path["points"])


def test_playback_uses_only_recorded_particle_vertices_and_no_fabricated_positions():
    track=trace_screening_particle(
        _report(),[.5,.5,.5],max_time_s=.2,gravity_m_s2=(0,0,0))
    samples=track["points"]
    assert len(samples)>2
    t0=samples[1]["elapsed_particle_s"]
    t1=samples[2]["elapsed_particle_s"]
    between=(t0+t1)/2
    position=particle_positions_at_elapsed([track],between)
    assert len(position)==1
    assert position[0]["xyz_m"]==samples[1]["xyz_m"]
    assert position[0]["sample_time_s"]==t0
    assert position[0]["xyz_m"]!=samples[2]["xyz_m"]
    assert particle_positions_at_elapsed([],0)==[]
    with pytest.raises(ValueError,match="Playback time"):
        particle_positions_at_elapsed([track],-1)
