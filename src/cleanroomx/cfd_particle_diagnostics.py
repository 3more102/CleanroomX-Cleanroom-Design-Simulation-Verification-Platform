"""Independent, provenance-checked diagnostics for frozen-field particle screening.

These metrics summarize ALREADY RECORDED one-way particle integration vertices,
not concentration, deposition, exposure or real transient CFD. Residence
labels refer to left-endpoint sampling of particle integration intervals; room
crossing time is not calculated from an interpolated interface event.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

from .cfd_particles import MAX_PARTICLES, PARTICLE_SCHEMA
from .cfd_streamlines import ComputedVelocityGrid, SOURCE_SCHEMA, _finite

SCHEMA = "cleanroomx.particle-screening-diagnostics.v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TERMINATIONS = frozenset((
    "max_particle_time", "max_steps", "fluid_boundary_contact_unresolved",
))
_MODEL = "one_way_stokes_cunningham_gravity_frozen_recorded_u"


def _components(value, label):
    if type(value) not in (list, tuple) or len(value) != 3:
        raise ValueError(f"{label} must have three components")
    return tuple(_finite(v, label) for v in value)


def _same_vector(a, b):
    return all(math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-10)
               for x, y in zip(a, b))


def analyze_particle_trajectories(report, tracks):
    """Summarize only validated sampled vertices from exactly one computed run.

    Segment path lengths are polygonal approximations, NOT exact inertial
    arc lengths; room-labelled elapsed intervals use the preceding sample's
    room and are NOT precise door-crossing instants or exposure/residence time.
    """
    grid = ComputedVelocityGrid(report)
    provenance = report.get("provenance", {})
    manifest = provenance.get("manifest_sha256")
    receipt = provenance.get("run_receipt_sha256")
    iteration = report.get("time_name")
    if (type(iteration) is not str or not iteration or
        type(manifest) is not str or not _HASH.fullmatch(manifest) or
        type(receipt) is not str or not _HASH.fullmatch(receipt)):
        raise ValueError("Recorded CFD iteration and SHA-256 provenance are required")
    if type(tracks) is not list or not 1 <= len(tracks) <= MAX_PARTICLES:
        raise ValueError("Analyze 1 to 20 recorded screening tracks")

    rows=[]
    all_room_labels=set()
    termination_counts={key:0 for key in sorted(_TERMINATIONS)}
    warnings=0
    total_polyline_m=0.
    total_time_s=0.
    crossings=0

    for number, track in enumerate(tracks, start=1):
        if not isinstance(track, dict) or any((
            track.get("schema") != PARTICLE_SCHEMA,
            track.get("source_schema") != SOURCE_SCHEMA,
            track.get("source_iteration") != iteration,
            track.get("source_manifest_sha256") != manifest,
            track.get("source_run_receipt_sha256") != receipt,
            track.get("model") != _MODEL,
            track.get("validated_particle_transport") is not False,
            track.get("frozen_steady_velocity_no_solver_transient") is not True,
            track.get("turbulent_dispersion_modeled") is not False,
            track.get("deposition_or_resuspension_modeled") is not False,
        )):
            raise ValueError("Particle track is from another run or unsupported physics")
        if track.get("termination") not in _TERMINATIONS:
            raise ValueError("Unrecognized particle termination classification")
        diameter = _finite(track.get("diameter_um"), "diameter_um")
        density = _finite(track.get("particle_density_kg_m3"), "particle density")
        air_density = _finite(track.get("air_density_kg_m3"), "air density")
        viscosity = _finite(track.get("air_dynamic_viscosity_pa_s"), "air viscosity")
        if (not 0.5 <= diameter <= 20 or not 100 <= density <= 20000 or
            not 0 < air_density < density or not 1e-6 <= viscosity <= 1e-3):
            raise ValueError("Particle physics is outside the recorded integration limits")

        points=track.get("points")
        if type(points) is not list or not 1 <= len(points) <= 10002:
            raise ValueError("Particle requires bounded recorded integration vertices")
        source_rooms={}
        transitions=[]
        previous=None
        path_m=0.
        max_re=0.
        for index, point in enumerate(points):
            if not isinstance(point,dict):
                raise ValueError("Malformed recorded particle vertex")
            p=_components(point.get("xyz_m"),"particle xyz")
            particle_v=_components(point.get("particle_velocity_m_s"),"particle velocity")
            gas_v=_components(point.get("recorded_gas_velocity_m_s"),"recorded gas velocity")
            t=_finite(point.get("elapsed_particle_s"),"elapsed particle time")
            re_actual=_finite(point.get("slip_reynolds"),"slip Reynolds")
            cell=grid.cell_at(p)
            if cell is None or point.get("room_id") != cell[1] or not _same_vector(gas_v,cell[0]):
                raise ValueError("Particle vertex does not match recorded CFD occupied cells/U")
            slip_re=air_density*(diameter*1e-6)*math.dist(particle_v, gas_v)/viscosity
            if (not math.isclose(re_actual,slip_re,rel_tol=1e-8,abs_tol=1e-10)
                or re_actual<0):
                raise ValueError("Recorded particle slip Reynolds is inconsistent")
            max_re=max(max_re,slip_re)
            room=cell[1]
            all_room_labels.add(room)
            if previous is None:
                if not math.isclose(t,0,abs_tol=1e-12):
                    raise ValueError("Particle trajectory must start at elapsed zero")
            else:
                before_p,before_t,before_room=previous
                if t <= before_t or t>60+1e-10:
                    raise ValueError("Elapsed particle samples must increase strictly")
                if not grid.connected_segment(before_p,p):
                    raise ValueError("Particle segment crosses an uncomputed/solid CFD voxel")
                dt=t-before_t
                # Classify this interval by its PRECEDING sample label.
                # No exact room crossing instant is reconstructed.
                source_rooms[before_room]=source_rooms.get(before_room,0.)+dt
                path_m+=math.dist(before_p,p)
                if room != before_room:
                    transitions.append({
                        "from_room":before_room,
                        "to_room":room,
                        "first_observed_at_sample_s":t,
                    })
            previous=(p,t,room)
        first,last=points[0],points[-1]
        final_t=_finite(last["elapsed_particle_s"],"end time")
        if (not math.isclose(final_t,math.fsum(source_rooms.values()),
                             rel_tol=1e-9,abs_tol=1e-9) or
            not math.isclose(max_re,_finite(track.get("max_slip_reynolds"),"maximum Reynolds"),
                             rel_tol=1e-8,abs_tol=1e-10) or
            track.get("stokes_regime_warning") is not (max_re>=1)):
            raise ValueError("Particle summary is inconsistent with its recorded samples")
        requested=_finite(track.get("max_time_s"),"requested duration")
        if not 0<requested<=60 or final_t>requested+1e-8:
            raise ValueError("Particle elapsed time exceeds recorded integration horizon")
        if track["termination"]=="max_particle_time" and not math.isclose(
            final_t,requested,abs_tol=1e-8,rel_tol=1e-9):
            raise ValueError("Completed trajectory does not reach requested horizon")
        displacement=math.dist(first["xyz_m"],last["xyz_m"])
        row={
            "particle_index":number,
            "start_room_id":first["room_id"],
            "end_room_id":last["room_id"],
            "diameter_um":diameter,
            "particle_density_kg_m3":density,
            "sample_count":len(points),
            "recorded_sample_elapsed_s":final_t,
            "polygonal_path_length_m":path_m,
            "end_to_end_displacement_m":displacement,
            "polygonal_tortuosity":(
                path_m/displacement if displacement>1e-12 else None),
            "sample_labelled_time_by_room_s":dict(sorted(source_rooms.items())),
            "first_observed_room_transitions":transitions,
            "first_observed_transition_count":len(transitions),
            "termination":track["termination"],
            "max_slip_reynolds":max_re,
            "stokes_regime_warning":max_re>=1,
            "boundary_contact_is_not_deposition":True,
        }
        rows.append(row)
        total_polyline_m+=path_m
        total_time_s+=final_t
        crossings+=len(transitions)
        warnings+=int(max_re>=1)
        termination_counts[track["termination"]]+=1
    return {
        "schema":SCHEMA,
        "source_schema":SOURCE_SCHEMA,
        "source_iteration":iteration,
        "source_manifest_sha256":manifest,
        "source_run_receipt_sha256":receipt,
        "number_of_screening_tracks":len(rows),
        "aggregate":{
            "sum_polygonal_path_length_m":total_polyline_m,
            "mean_polygonal_path_length_m":total_polyline_m/len(rows),
            "mean_recorded_elapsed_particle_s":total_time_s/len(rows),
            "first_observed_room_transitions":crossings,
            "tracks_with_stokes_regime_warning":warnings,
            "termination_counts":termination_counts,
            "recorded_room_ids":sorted(all_room_labels),
        },
        "tracks":rows,
        "interpretation":{
            "validation":"one-way frozen recorded-U screening only; no certified transport",
            "path_length":"chords between sampled integration vertices; lower bound on true curved distance",
            "room_time":"left-endpoint sampled room label; crossing times are not resolved",
            "room_transition":"first observed in a new room at a recorded sample, not measured door crossing",
            "boundary_contact":"unresolved contact with computed fluid boundary, NOT deposition",
            "not_inferred":[
                "particle concentration", "deposition efficiency", "real residence time",
                "time-varying OpenFOAM flow", "turbulent dispersion",
                "cleanroom certification", "5 Pa closed-door performance",
            ],
        },
        "validated_particle_transport":False,
        "engineering_release":"HOLD",
    }


def export_particle_trajectory_diagnostics(diagnostics, destination):
    """Write a new JSON artifact; reject unchecked/certifying inputs and overwrites."""
    if (not isinstance(diagnostics,dict) or diagnostics.get("schema")!=SCHEMA or
        diagnostics.get("engineering_release")!="HOLD" or
        diagnostics.get("validated_particle_transport") is not False or
        not isinstance(diagnostics.get("tracks"),list) or
        len(diagnostics["tracks"])!=diagnostics.get("number_of_screening_tracks")):
        raise ValueError("Only bounded, noncertifying particle diagnostics may be exported")
    for name in ("source_manifest_sha256","source_run_receipt_sha256"):
        value=diagnostics.get(name)
        if type(value) is not str or not _HASH.fullmatch(value):
            raise ValueError("Source SHA-256 provenance is mandatory")
    output=Path(destination)
    encoded=json.dumps(diagnostics,allow_nan=False,indent=2)+"\n"
    with output.open("x",encoding="utf-8") as stream:
        stream.write(encoded)
    return output
