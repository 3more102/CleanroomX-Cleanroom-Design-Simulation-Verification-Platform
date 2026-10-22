"""Reproducible bounded timestep-refinement screening for recorded one-way particles.

Only the particle numerical integrator's maximum step is varied. The OpenFOAM
velocity field is the SAME recorded steady snapshot for each rerun. This does
NOT test CFD mesh independence, physical particle convergence, deposition,
particle concentration or cleanroom certification.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .cfd_particle_diagnostics import analyze_particle_trajectories
from .cfd_particles import trace_screening_particle
from .cfd_streamlines import _finite

SCHEMA="cleanroomx.particle-timestep-refinement.v1"
_FACTORS=(1.0,0.5,0.25)
_HASH=re.compile(r"[0-9a-f]{64}\Z")


def _replay_settings(track):
    """Extract *recorded*, bounded initial conditions, never assume gravity."""
    keys=("initial_particle_velocity_m_s","gravity_m_s2",
          "max_steps","slip_mean_free_path_m")
    if any(k not in track for k in keys):
        raise ValueError(
            "Track lacks complete integration provenance; re-inject with the "
            "updated particle model rather than guessing missing settings")
    init=track["initial_particle_velocity_m_s"]
    gravity=track["gravity_m_s2"]
    if (type(init) not in (list,tuple) or len(init)!=3 or
        type(gravity) not in (list,tuple) or len(gravity)!=3):
        raise ValueError("Recorded particle initial velocity/gravity must have three components")
    v=tuple(_finite(x,"initial velocity") for x in init)
    g=tuple(_finite(x,"recorded gravity") for x in gravity)
    if (math.dist(g,(0,0,0))>20 or
        type(track["max_steps"]) is not int or
        not 1<=track["max_steps"]<=10000 or
        not math.isclose(_finite(track["slip_mean_free_path_m"],"slip mean free path"),
                         66e-9,rel_tol=1e-12,abs_tol=0)):
        raise ValueError("Recorded particle integration settings are unsupported")
    original=track["points"][0]
    if any(not math.isclose(v[i],_finite(original["particle_velocity_m_s"][i],
                                        "first sample velocity"),
                            rel_tol=0,abs_tol=1e-12) for i in range(3)):
        raise ValueError("Initial particle velocity disagrees with recorded first sample")
    step=_finite(track.get("max_step_s"),"recorded max_step_s")
    if not 1e-6<=step<=0.5:
        raise ValueError("Unsupported recorded maximum step")
    return {
        "diameter_um":track["diameter_um"],
        "particle_density_kg_m3":track["particle_density_kg_m3"],
        "air_density_kg_m3":track["air_density_kg_m3"],
        "air_dynamic_viscosity_pa_s":track["air_dynamic_viscosity_pa_s"],
        "max_time_s":track["max_time_s"],
        "max_steps":track["max_steps"],
        "initial_velocity_m_s":v,
        "gravity_m_s2":g,
    }, step


def analyze_particle_timestep_refinement(
    report, original_track, *, endpoint_tolerance_m=1e-3,
):
    """Replay 1x, 0.5x, 0.25x step caps with fixed exact source/physics.

    A bounded endpoint-difference screen is reported only if *actual* sampled
    timesteps shrink on every refinement, all scenarios complete the requested
    horizon, have the same room-transition pattern, and remain in the model's
    low-slip-Re range. It is NEVER labelled physical convergence or PASS.
    """
    tolerance=_finite(endpoint_tolerance_m,"endpoint tolerance")
    if not 0<tolerance<=1:
        raise ValueError("Endpoint tolerance must be finite and between 0 and 1 metre")
    # This validates every particle vertex against the solver's recorded U,
    # sourced hashes, occupied CFD geometry and original slip/elapsed metrics.
    validate=analyze_particle_trajectories(report,[original_track])
    settings, cap=_replay_settings(original_track)
    if cap*.25<1e-6:
        raise ValueError("Refined time-step cap is below the supported floor")
    seed=original_track["points"][0]["xyz_m"]
    runs=[]
    trajectories=[]
    for factor in _FACTORS:
        maximum=cap*factor
        simulated=trace_screening_particle(
            report,seed,max_step_s=maximum,**settings)
        # The original dataset is required to replay exactly, including
        # termination and all integration sample values at the baseline.
        if factor==1 and simulated!=original_track:
            raise ValueError("Recorded baseline trajectory cannot be reproduced exactly")
        row=analyze_particle_trajectories(report,[simulated])["tracks"][0]
        times=[p["elapsed_particle_s"] for p in simulated["points"]]
        increments=[b-a for a,b in zip(times,times[1:])]
        run={
            "step_cap_factor":factor,
            "configured_max_step_s":maximum,
            "largest_recorded_elapsed_step_s":max(increments,default=0.0),
            "integration_segments":len(increments),
            "sample_count":row["sample_count"],
            "actual_elapsed_s":row["recorded_sample_elapsed_s"],
            "endpoint_xyz_m":list(simulated["points"][-1]["xyz_m"]),
            "end_room_id":row["end_room_id"],
            "first_observed_transition_pairs":[
                [x["from_room"],x["to_room"]]
                for x in row["first_observed_room_transitions"]
            ],
            "polygonal_path_length_m":row["polygonal_path_length_m"],
            "termination":row["termination"],
            "stokes_regime_warning":row["stokes_regime_warning"],
        }
        trajectories.append(simulated)
        runs.append(run)
    delta_01=math.dist(runs[0]["endpoint_xyz_m"],runs[1]["endpoint_xyz_m"])
    delta_12=math.dist(runs[1]["endpoint_xyz_m"],runs[2]["endpoint_xyz_m"])
    # Detect the case where spatial CFL already controlled the step and
    # changing a nominal max cap made no numerical refinement at all.
    actual_refinement=all(
        runs[i+1]["largest_recorded_elapsed_step_s"] <
        runs[i]["largest_recorded_elapsed_step_s"]-1e-12 and
        runs[i+1]["integration_segments"]>runs[i]["integration_segments"]
        for i in (0,1))
    completed=all(
        row["termination"]=="max_particle_time" and
        math.isclose(row["actual_elapsed_s"],settings["max_time_s"],
                     abs_tol=1e-8,rel_tol=1e-9)
        for row in runs)
    consistent_topology=all(
        row["end_room_id"]==runs[0]["end_room_id"] and
        row["first_observed_transition_pairs"]==
        runs[0]["first_observed_transition_pairs"]
        for row in runs)
    regime=not any(row["stokes_regime_warning"] for row in runs)
    threshold_met=(delta_01<=tolerance and delta_12<=tolerance)
    eligible=(actual_refinement and completed and consistent_topology and
              regime and threshold_met)
    return {
        "schema":SCHEMA,
        "source_iteration":validate["source_iteration"],
        "source_manifest_sha256":validate["source_manifest_sha256"],
        "source_run_receipt_sha256":validate["source_run_receipt_sha256"],
        "original_particle_seed_m":list(seed),
        "original_diameter_um":settings["diameter_um"],
        "original_particle_density_kg_m3":settings["particle_density_kg_m3"],
        "original_max_time_s":settings["max_time_s"],
        "original_gravity_m_s2":list(settings["gravity_m_s2"]),
        "original_initial_velocity_m_s":list(settings["initial_velocity_m_s"]),
        "endpoint_tolerance_m":tolerance,
        "runs":runs,
        "endpoint_delta_baseline_to_half_m":delta_01,
        "endpoint_delta_half_to_quarter_m":delta_12,
        "actual_timestep_refinement_observed":actual_refinement,
        "all_runs_completed_full_integration_horizon":completed,
        "sampled_room_transition_pattern_consistent":consistent_topology,
        "low_slip_reynolds_on_all_runs":regime,
        "all_endpoint_deltas_under_user_tolerance":threshold_met,
        "screening_status":(
            "bounded_endpoint_change_under_tolerance"
            if eligible else "not_demonstrated"),
        "not_physical_convergence":True,
        "not_mesh_independence":True,
        "validated_particle_transport":False,
        "engineering_release":"HOLD",
        "limitations":[
            "Fixed recorded steady OpenFOAM cell-centred U only",
            "Two endpoint differences and recorded step-count checks are not a mathematical order-of-convergence proof",
            "No particle concentration, turbulence, collisions, deposition or resuspension",
            "Boundary contact or Stokes-regime warnings prevent numerical screening eligibility",
            "No cleanroom certification or closed-door 5 Pa pressure-cascade validation",
        ],
    }


def export_particle_timestep_refinement(study,destination):
    """Exclusively write bounded noncertifying numerical screening evidence."""
    if (type(study) is not dict or study.get("schema")!=SCHEMA or
        study.get("engineering_release")!="HOLD" or
        study.get("validated_particle_transport") is not False or
        study.get("not_physical_convergence") is not True or
        study.get("not_mesh_independence") is not True or
        type(study.get("runs")) is not list or
        [r.get("step_cap_factor") for r in study["runs"]]!=list(_FACTORS)):
        raise ValueError("Only complete noncertifying refinement screening may be exported")
    for key in ("source_manifest_sha256","source_run_receipt_sha256"):
        value=study.get(key)
        if type(value) is not str or not _HASH.fullmatch(value):
            raise ValueError("Source SHA-256 hashes must be present for export")
    if type(study.get("source_iteration")) is not str or not study["source_iteration"]:
        raise ValueError("Recorded CFD iteration is required for export")
    flags=("actual_timestep_refinement_observed",
           "all_runs_completed_full_integration_horizon",
           "sampled_room_transition_pattern_consistent",
           "low_slip_reynolds_on_all_runs",
           "all_endpoint_deltas_under_user_tolerance")
    if any(type(study.get(k)) is not bool for k in flags):
        raise ValueError("Refinement screening flags must be explicit booleans")
    expected=("bounded_endpoint_change_under_tolerance"
              if all(study[k] for k in flags) else "not_demonstrated")
    if study.get("screening_status")!=expected:
        raise ValueError("Refinement screening verdict contradicts the recorded flags")
    for record in study["runs"]:
        if (type(record) is not dict or
            type(record.get("integration_segments")) is not int or
            not 0<=record["integration_segments"]<=10000 or
            type(record.get("termination")) is not str or
            type(record.get("endpoint_xyz_m")) is not list or
            len(record["endpoint_xyz_m"])!=3 or
            any(not math.isfinite(_finite(x,"endpoint")) for x in record["endpoint_xyz_m"])):
            raise ValueError("Invalid recorded timestep-refinement run")
    content=json.dumps(study,allow_nan=False,indent=2)+"\n"
    target=Path(destination)
    with target.open("x",encoding="utf-8") as output:
        output.write(content)
    return target
