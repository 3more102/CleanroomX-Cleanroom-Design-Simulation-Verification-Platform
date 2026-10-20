"""One-way Lagrangian particle *screening* on recorded steady OpenFOAM U.

Deterministic spherical particle dynamics in a frozen cell-centred gas field:
Stokes drag (with fixed-condition Cunningham correction), particle inertia,
buoyancy-adjusted gravity and exact velocity relaxation per local fluid cell.
This is NOT OpenFOAM's Lagrangian solver, CFD re-simulation, turbulent
dispersion, deposition, bounce, resuspension or cleanroom certification.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .cfd_streamlines import ComputedVelocityGrid, SOURCE_SCHEMA, _finite

PARTICLE_SCHEMA = "cleanroomx.frozen-field-particle-screening.v1"
MAX_PARTICLES = 20


def _vector(values, label):
    try:
        result = tuple(_finite(v, label) for v in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be three finite components") from exc
    if len(result) != 3:
        raise ValueError(f"{label} must be three finite components")
    return result


def cunningham_slip(diameter_m, *, mean_free_path_m=66e-9):
    """Air slip correction approximation for smooth rigid spheres at 1 atm."""
    d = _finite(diameter_m, "particle diameter")
    lam = _finite(mean_free_path_m, "air mean free path")
    if not 0 < d <= 1e-3 or not 0 < lam <= 1e-5:
        raise ValueError("Invalid diameter or air mean free path")
    kn = 2*lam/d
    return 1 + kn*(1.257 + 0.4*math.exp(-1.1/kn))


def _advance(position, velocity, gas, tau, gravity, dt):
    """Exact constant-gas solution of dv/dt=(U-v)/tau+gravity."""
    decay = math.exp(-dt/tau)
    displacement_factor = -tau*math.expm1(-dt/tau)
    terminal = tuple(gas[i] + tau*gravity[i] for i in range(3))
    delta = tuple(velocity[i] - terminal[i] for i in range(3))
    end = tuple(position[i] + terminal[i]*dt + delta[i]*displacement_factor
                for i in range(3))
    vel = tuple(terminal[i] + delta[i]*decay for i in range(3))
    return end, vel


def _particle_substep_is_fluid(grid, position, velocity, gas, tau, gravity, dt):
    """Check the *curved* exact inertial trajectory, not just its chord.

    The occupied lattice is tested in time-ordered substeps. Even if a
    particle crosses a boundary and returns before the endpoint, it may
    not be reported as travelling freely through the wall.
    """
    previous=position
    for n in range(1,9):
        next_position, _=_advance(
            position,velocity,gas,tau,gravity,dt*n/8)
        if not grid.connected_segment(previous,next_position):
            return False
        previous=next_position
    return True


def trace_screening_particle(
    report, seed_m, *, diameter_um=5.0, particle_density_kg_m3=1000.0,
    air_density_kg_m3=1.2, air_dynamic_viscosity_pa_s=1.81e-5,
    max_time_s=2.0, max_step_s=0.05, max_steps=4000,
    initial_velocity_m_s=None, gravity_m_s2=(0.0, 0.0, -9.80665),
):
    """Integrate one-way sphere dynamics through occupied recorded fluid voxels.

    Stepping has a conservative CFL-style distance cap; drag is integrated
    exactly for a locally constant gas velocity, even when tau is very small.
    Contact with a missing fluid voxel terminates the trajectory without
    inventing collision response or deposition. Time is elapsed particle
    integration time in a FROZEN velocity field, not OpenFOAM transient output.
    """
    diameter = _finite(diameter_um, "diameter_um")*1e-6
    density = _finite(particle_density_kg_m3, "particle density")
    rho_air = _finite(air_density_kg_m3, "air density")
    viscosity = _finite(air_dynamic_viscosity_pa_s, "dynamic viscosity")
    horizon = _finite(max_time_s, "max_time_s")
    dt_cap = _finite(max_step_s, "max_step_s")
    if not 0.5e-6 <= diameter <= 20e-6:
        raise ValueError("Particle diameter must be 0.5 to 20 micrometres")
    if not 100 <= density <= 20000 or not 0 < rho_air < density:
        raise ValueError("Particle density must exceed positive air density")
    if not 1e-6 <= viscosity <= 1e-3:
        raise ValueError("Invalid air dynamic viscosity")
    if not 0 < horizon <= 60 or not 0 < dt_cap <= 0.5:
        raise ValueError("Invalid particle integration duration or time step")
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise ValueError("max_steps must be an integer from 1 to 10000")
    gravity = _vector(gravity_m_s2, "gravity")
    if math.dist((0, 0, 0), gravity) > 20:
        raise ValueError("Gravity must be physically bounded")
    grid = ComputedVelocityGrid(report)
    position = _vector(seed_m, "seed")
    fluid = grid.cell_at(position)
    if fluid is None:
        raise ValueError("Particle injection seed must be a recorded fluid cell")
    velocity = (tuple(fluid[0]) if initial_velocity_m_s is None
                else _vector(initial_velocity_m_s, "initial particle velocity"))
    cc = cunningham_slip(diameter)
    tau = density*diameter**2*cc/(18*viscosity)
    buoyant_gravity = tuple(g*(1-rho_air/density) for g in gravity)
    particle_points = []
    time = 0.0
    max_reynolds = 0.0
    reason = "max_steps"
    for step in range(max_steps+1):
        fluid = grid.cell_at(position)
        if fluid is None:
            raise ValueError("Particle integrator moved outside occupied CFD fluid")
        gas, room = fluid
        slip = math.dist(velocity, gas)
        reynolds = rho_air*diameter*slip/viscosity
        max_reynolds = max(max_reynolds, reynolds)
        particle_points.append({
            "xyz_m": list(position), "elapsed_particle_s": time,
            "particle_velocity_m_s": list(velocity),
            "recorded_gas_velocity_m_s": list(gas),
            "slip_reynolds": reynolds, "room_id": room,
        })
        if time >= horizon-1e-12:
            reason = "max_particle_time"
            break
        if step >= max_steps:
            reason = "max_steps"
            break
        # Keep each step below a fraction of one solved voxel. This is NOT
        # a substitute for a mesh/time-step independence analysis.
        speed_bound = max(math.dist(velocity,(0,0,0)),
                          math.dist(gas,(0,0,0))) + math.dist(buoyant_gravity,(0,0,0))*tau
        dt = min(horizon-time, dt_cap,
                 0.2*min(grid.pitch)/max(speed_bound,1e-9))
        target, new_velocity = _advance(
            position, velocity, gas, tau, buoyant_gravity, dt)
        if not _particle_substep_is_fluid(
                grid,position,velocity,gas,tau,buoyant_gravity,dt):
            # Find a bounded fluid trajectory prefix, not merely an in-cell
            # endpoint. Never classify a wall crossing as successful flight.
            low, high = 0.0, dt
            for _ in range(24):
                mid = (low+high)*0.5
                if _particle_substep_is_fluid(
                        grid,position,velocity,gas,tau,buoyant_gravity,mid):
                    low = mid
                else:
                    high = mid
            if low > 1e-12:
                safe, safe_velocity = _advance(
                    position, velocity, gas, tau, buoyant_gravity, low)
                if grid.cell_at(safe) is not None:
                    position, velocity = safe, safe_velocity
                    time += low
                    gas_at, room_at = grid.cell_at(position)
                    max_reynolds = max(
                        max_reynolds,
                        rho_air*diameter*math.dist(velocity,gas_at)/viscosity)
                    particle_points.append({
                        "xyz_m": list(position), "elapsed_particle_s": time,
                        "particle_velocity_m_s": list(velocity),
                        "recorded_gas_velocity_m_s": list(gas_at),
                        "slip_reynolds":rho_air*diameter*math.dist(
                            velocity,gas_at)/viscosity, "room_id":room_at,
                    })
            reason = "fluid_boundary_contact_unresolved"
            break
        position, velocity = target, new_velocity
        time += dt
    provenance = report.get("provenance", {})
    return {
        "schema": PARTICLE_SCHEMA, "source_schema": SOURCE_SCHEMA,
        "source_iteration": report.get("time_name"),
        "source_manifest_sha256": provenance.get("manifest_sha256"),
        "source_run_receipt_sha256": provenance.get("run_receipt_sha256"),
        "model": "one_way_stokes_cunningham_gravity_frozen_recorded_u",
        "validated_particle_transport": False,
        "frozen_steady_velocity_no_solver_transient": True,
        "turbulent_dispersion_modeled": False,
        "deposition_or_resuspension_modeled": False,
        "diameter_um": diameter*1e6,
        "particle_density_kg_m3": density,
        "air_density_kg_m3": rho_air,
        "air_dynamic_viscosity_pa_s": viscosity,
        "cunningham_slip_correction": cc,
        "particle_relaxation_s": tau,
        "max_time_s": horizon, "max_step_s": dt_cap,
        "max_slip_reynolds": max_reynolds,
        "stokes_regime_warning": max_reynolds >= 1.0,
        "termination": reason, "points": particle_points,
    }


def export_screening_particles(tracks, destination):
    """Export single-iteration screening tracks; refuse to clobber evidence."""
    if type(tracks) is not list or not 1 <= len(tracks) <= MAX_PARTICLES:
        raise ValueError("Export requires 1 to 20 particle screening tracks")
    first = tracks[0]
    if (first.get("schema") != PARTICLE_SCHEMA or
        any(t.get("schema") != PARTICLE_SCHEMA or
            t.get("source_iteration") != first.get("source_iteration") or
            t.get("source_manifest_sha256") != first.get("source_manifest_sha256") or
            t.get("source_run_receipt_sha256") != first.get("source_run_receipt_sha256")
            for t in tracks)):
        raise ValueError("Particle tracks must share a recorded CFD iteration and run")
    payload = {
        "schema": "cleanroomx.particle-screening-collection.v1",
        "validation": "one_way_frozen_field_screening_not_certified_particle_transport",
        "source_iteration": first["source_iteration"],
        "source_manifest_sha256": first["source_manifest_sha256"],
        "source_run_receipt_sha256": first["source_run_receipt_sha256"],
        "units": {"xyz_m":"m", "elapsed_particle_s":"s",
                  "particle_velocity_m_s":"m/s", "recorded_gas_velocity_m_s":"m/s"},
        "tracks": tracks,
    }
    serialized = json.dumps(payload, indent=2, allow_nan=False)+"\n"
    output = Path(destination)
    with output.open("x",encoding="utf-8") as f:
        f.write(serialized)
    return output
