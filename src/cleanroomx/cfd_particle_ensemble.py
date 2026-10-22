"""Deterministic, bounded multi-seed screening on recorded CFD cell centres.

This is a *sampling strategy* for the preexisting one-way frozen-velocity
particle model. It does not estimate concentration, emission probability,
statistical independence, transient CFD or cleanroom acceptance.
"""
from __future__ import annotations

import math

from .cfd_particle_diagnostics import analyze_particle_trajectories
from .cfd_particles import MAX_PARTICLES, trace_screening_particle
from .cfd_streamlines import ComputedVelocityGrid, _finite

SCHEMA = "cleanroomx.recorded-cell-particle-ensemble.v1"


def choose_recorded_particle_seeds(
    report, *, count=4, room_id="all", plane_axis="all",
    plane_position_m=None, excluded_centres=(),
):
    """Deterministic maximin layout from *existing CFD centres* only.

    Start with the observed centre closest to the eligible-set centroid,
    then greedily choose the centre furthest from selected/excluded centres,
    breaking all ties lexicographically by physical coordinates. Seed spacing
    is a geometric visualization choice, never a probability distribution.
    """
    if type(count) is not int or not 1 <= count <= MAX_PARTICLES:
        raise ValueError("Select 1 to 20 additional particle seeds")
    if type(excluded_centres) not in (list, tuple) or len(excluded_centres)>MAX_PARTICLES:
        raise ValueError("Excluded seeds must be a bounded list of recorded centres")
    # Lazy import avoids circular dependency with the 3D UI.
    from .cfd_multizone_vtk import select_recorded_cells
    candidates=select_recorded_cells(
        report,room_id=room_id,plane_axis=plane_axis,
        plane_position_m=plane_position_m,
    )
    grid=ComputedVelocityGrid(report)
    valid_centres={
        tuple(_finite(v,"recorded CFD centre") for v in c["center_m"])
        for c in report["cells"]
    }
    excluded=[]
    for item in excluded_centres:
        if type(item) not in (list,tuple) or len(item)!=3:
            raise ValueError("Excluded seed must be a recorded CFD centre")
        position=tuple(_finite(v,"excluded seed") for v in item)
        if position not in valid_centres or grid.cell_at(position) is None:
            raise ValueError("Excluded seed does not match a recorded CFD cell centre")
        excluded.append(position)
    blocked=set(excluded)
    coords=sorted({
        tuple(_finite(v,"candidate seed") for v in cell["center_m"])
        for cell in candidates
    }-blocked)
    if len(coords)<count:
        raise ValueError("Not enough distinct recorded fluid centres for the requested ensemble")
    reference=sorted({
        tuple(_finite(v,"candidate seed") for v in cell["center_m"])
        for cell in candidates
    })
    centroid=tuple(math.fsum(p[i] for p in reference)/len(reference) for i in range(3))
    selected=[]
    available=coords
    if not excluded:
        first=min(coords,key=lambda p:(math.dist(p,centroid),p))
        selected.append(first)
        available=[p for p in available if p!=first]
    distances={
        p: min((math.dist(p,s)**2 for s in (*excluded,*selected)),default=math.inf)
        for p in available
    }
    while len(selected)<count:
        # The current running nearest-neighbour distance is used, with stable
        # lexicographic coordinate tie-breaking, independent of file order.
        chosen=min(available,key=lambda p:(-distances[p],p))
        selected.append(chosen)
        available.remove(chosen)
        for p in available:
            distances[p]=min(distances[p],math.dist(p,chosen)**2)
    return {
        "method":"observed_cell_centroid_then_deterministic_farthest_centres",
        "nonstatistical_geometry_sampling":True,
        "candidate_recorded_centres":len(reference),
        "selected_centres_m":[list(p) for p in selected],
        "requested_count":count,
    }


def inject_recorded_particle_ensemble(
    report, current_tracks, *, count=4,
    room_id="all", plane_axis="all", plane_position_m=None,
    diameter_um=5.0, particle_density_kg_m3=1000.0, max_time_s=2.0,
):
    """Run new seeds in the *same recorded* field without mutating current paths.

    A failed integration never partially appends trajectories to the 3D scene.
    """
    if type(current_tracks) is not list or len(current_tracks)>MAX_PARTICLES:
        raise ValueError("Existing particle tracks must be a bounded list")
    if type(count) is not int or not 1<=count<=MAX_PARTICLES-len(current_tracks):
        raise ValueError("Requested ensemble exceeds remaining 20-particle capacity")
    if current_tracks:
        analyze_particle_trajectories(report,current_tracks)
    previous=[t["points"][0]["xyz_m"] for t in current_tracks]
    choice=choose_recorded_particle_seeds(
        report,count=count,room_id=room_id,plane_axis=plane_axis,
        plane_position_m=plane_position_m,excluded_centres=previous,
    )
    additions=[
        trace_screening_particle(
            report,centre,diameter_um=diameter_um,
            particle_density_kg_m3=particle_density_kg_m3,
            max_time_s=max_time_s,
        )
        for centre in choice["selected_centres_m"]
    ]
    # Fully verify the final collection before handing it back to a GUI.
    diagnostics=analyze_particle_trajectories(report,current_tracks+additions)
    return {
        "schema":SCHEMA,
        "sampling":choice,
        "new_tracks":additions,
        "noncertifying_diagnostics":diagnostics,
        "engineering_release":"HOLD",
        "statistical_or_certified_particle_transport":False,
    }
