"""Scheduled numerical particles in a single recorded, frozen CFD U field.

Source counts are representative numerical particles, NOT measured emission
rates or airborne concentrations. Release time is a modeled clock, separate
from both particle age and the source OpenFOAM SIMPLE iteration label.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re

from .cfd_particle_diagnostics import analyze_particle_trajectories
from .cfd_particles import MAX_PARTICLES, ParticleRunCancelled, trace_screening_particle
from .cfd_streamlines import ComputedVelocityGrid, _finite
from .strict_json import load_strict_json

CONFIG_SCHEMA = "cleanroomx.recorded-u-particle-sources.v1"
RUN_SCHEMA = "cleanroomx.scheduled-particle-screening.v1"
_KEYS = frozenset((
    "source_id", "enabled", "position_m", "particle_count", "start_time_s",
    "duration_s", "diameter_um", "particle_density_kg_m3", "initial_velocity_m_s",
))
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,47}\Z")


def _source_identity(report):
    provenance = report.get("provenance", {})
    identity = {
        "source_iteration": report.get("time_name"),
        "source_manifest_sha256": provenance.get("manifest_sha256"),
        "source_run_receipt_sha256": provenance.get("run_receipt_sha256"),
    }
    if (type(identity["source_iteration"]) is not str or not identity["source_iteration"]
        or any(type(identity[k]) is not str or not _HASH.fullmatch(identity[k])
               for k in ("source_manifest_sha256", "source_run_receipt_sha256"))):
        raise ValueError("Recorded CFD iteration and two SHA-256 source identities are required")
    return identity


def _vector(value, label):
    if type(value) not in (tuple, list) or len(value) != 3:
        raise ValueError(f"{label} requires three finite components")
    return [_finite(v, label) for v in value]


def validate_particle_sources(report, sources, observation_end_s):
    """Validate the entire source collection before integration or GUI mutation."""
    end = _finite(observation_end_s, "observation end")
    if not 0 < end <= 60:
        raise ValueError("Observation end must be in (0, 60] seconds")
    _source_identity(report)
    grid = ComputedVelocityGrid(report)
    if type(sources) is not list or not 1 <= len(sources) <= MAX_PARTICLES:
        raise ValueError("Configure 1 to 20 particle sources")
    normalized, ids, enabled_count = [], set(), 0
    for source in sources:
        if type(source) is not dict or set(source) != _KEYS:
            raise ValueError("Particle source has missing or unknown fields")
        sid = source["source_id"]
        if type(sid) is not str or not _ID.fullmatch(sid) or sid in ids:
            raise ValueError("Source ID must be unique and contain letters, digits, _ or -")
        ids.add(sid)
        if type(source["enabled"]) is not bool:
            raise ValueError("Source enabled flag must be a boolean")
        count = source["particle_count"]
        if type(count) is not int or not 1 <= count <= MAX_PARTICLES:
            raise ValueError("Each source needs 1 to 20 numerical particles")
        xyz = _vector(source["position_m"], "injection position")
        if grid.cell_at(xyz) is None:
            raise ValueError("Injection position must be inside a recorded fluid voxel")
        initial = source["initial_velocity_m_s"]
        if initial is not None:
            initial = _vector(initial, "initial particle velocity")
        start = _finite(source["start_time_s"], "source start time")
        duration = _finite(source["duration_s"], "source duration")
        if start < 0 or duration < 0 or start + duration >= end:
            raise ValueError("All source releases must precede observation end")
        if count == 1 and duration != 0:
            raise ValueError("A single-particle source requires zero release duration")
        diameter = _finite(source["diameter_um"], "particle diameter")
        density = _finite(source["particle_density_kg_m3"], "particle density")
        if not .5 <= diameter <= 20 or not 100 <= density <= 20000:
            raise ValueError("Particle diameter/density exceed the existing Stokes screening bounds")
        enabled_count += count if source["enabled"] else 0
        normalized.append({
            **source, "position_m": xyz, "start_time_s": start, "duration_s": duration,
            "diameter_um": diameter, "particle_density_kg_m3": density,
            "initial_velocity_m_s": initial,
        })
    if enabled_count > MAX_PARTICLES:
        raise ValueError("Enabled sources exceed the 20-particle run capacity")
    return normalized


def particle_source_configuration(report, sources, observation_end_s):
    sources = validate_particle_sources(report, sources, observation_end_s)
    return {
        "schema": CONFIG_SCHEMA, **_source_identity(report),
        "observation_end_s": float(observation_end_s), "sources": sources,
        "release_rule": "uniform_inclusive_endpoints_or_simultaneous_zero_duration",
        "numerical_counts_not_physical_emission_rates": True,
    }


def export_particle_source_configuration(report, sources, observation_end_s, destination):
    config = particle_source_configuration(report, sources, observation_end_s)
    path = Path(destination)
    serialized = json.dumps(config, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    return path


def load_particle_source_configuration(report, path):
    payload = load_strict_json(path, max_bytes=128_000)
    if type(payload) is not dict or payload.get("schema") != CONFIG_SCHEMA:
        raise ValueError("Unsupported particle source configuration")
    if any(payload.get(k) != v for k, v in _source_identity(report).items()):
        raise ValueError("Source configuration belongs to another CFD run/iteration")
    expected = particle_source_configuration(
        report, payload.get("sources"), payload.get("observation_end_s"))
    if payload != expected:
        raise ValueError("Source configuration contains unsupported or altered metadata")
    return expected


def _releases(config):
    events = []
    for source in config["sources"]:
        if not source["enabled"]:
            continue
        count = source["particle_count"]
        for index in range(count):
            release = source["start_time_s"]
            if count > 1:
                release += source["duration_s"] * index / (count - 1)
            events.append((release, source["source_id"], index + 1, source))
    return sorted(events, key=lambda event: event[:3])


def run_particle_sources(report, sources, *, observation_end_s=2., cancel_check=None):
    """Atomic deterministic source run, ordered by release time, source ID, index.

    Uses the existing Stokes/Cunningham/inertia/gravity integrator unchanged.
    Every release is integrated only until the common observation end, with
    particle age starting at zero. Failed/cancelled batches return no result.
    """
    config = particle_source_configuration(report, sources, observation_end_s)
    events = _releases(config)
    if not events:
        raise ValueError("Enable at least one particle source before running")
    tracks = []
    for release, sid, index, source in events:
        if cancel_check is not None and cancel_check():
            raise ParticleRunCancelled("Particle source run cancelled")
        track = trace_screening_particle(
            report, source["position_m"], diameter_um=source["diameter_um"],
            particle_density_kg_m3=source["particle_density_kg_m3"],
            initial_velocity_m_s=source["initial_velocity_m_s"],
            max_time_s=config["observation_end_s"] - release,
            cancel_check=cancel_check,
        )
        track.update(injection_source_id=sid, source_particle_index=index,
                     release_time_s=release)
        tracks.append(track)
    diagnostics = analyze_particle_trajectories(report, tracks)
    if cancel_check is not None and cancel_check():
        raise ParticleRunCancelled("Particle source run cancelled")
    return {
        "schema": RUN_SCHEMA, "configuration": config, "tracks": tracks,
        **_source_identity(report), "diagnostics": diagnostics,
        "engineering_release": "HOLD", "validated_particle_transport": False,
        "boundary_contact_is_not_escape_or_deposition": True,
    }


def _validate_run(report, run):
    if type(run) is not dict or run.get("schema") != RUN_SCHEMA:
        raise ValueError("Expected a scheduled particle screening run")
    config = run.get("configuration", {})
    expected = particle_source_configuration(
        report, config.get("sources"), config.get("observation_end_s"))
    if config != expected or any(run.get(k) != v for k, v in _source_identity(report).items()):
        raise ValueError("Scheduled particle run has stale source provenance/configuration")
    if (run.get("engineering_release") != "HOLD"
        or run.get("validated_particle_transport") is not False
        or run.get("boundary_contact_is_not_escape_or_deposition") is not True):
        raise ValueError("Scheduled particle run cannot claim physical acceptance")
    events, tracks = _releases(config), run.get("tracks")
    if type(tracks) is not list or len(events) != len(tracks):
        raise ValueError("Scheduled particle accounting does not match releases")
    diagnostics = analyze_particle_trajectories(report, tracks)
    if diagnostics != run.get("diagnostics"):
        raise ValueError("Particle diagnostics differ from recorded trajectories")
    for (release, sid, index, source), track in zip(events, tracks):
        if (track.get("injection_source_id") != sid
            or track.get("source_particle_index") != index
            or type(track.get("source_particle_index")) is not int
            or _finite(track.get("release_time_s"), "release time") != release
            or track["points"][0]["xyz_m"] != source["position_m"]
            or track["diameter_um"] != source["diameter_um"]
            or track["particle_density_kg_m3"] != source["particle_density_kg_m3"]
            or track["max_time_s"] != config["observation_end_s"] - release):
            raise ValueError("Particle trajectory does not match its source/release schedule")
    return config, tracks


def particle_source_population(report, run, times_s):
    """Conserved numerical ledger from recorded samples; no physical fractions.

    The latest sample at/before each requested observation time supplies the
    room label. Boundary contacts remain unresolved, never deposition/escape.
    """
    config, tracks = _validate_run(report, run)
    if type(times_s) not in (tuple, list) or not 1 <= len(times_s) <= 1001:
        raise ValueError("Request 1 to 1001 observation times")
    rows = []
    for value in times_s:
        time = _finite(value, "observation time")
        if not 0 <= time <= config["observation_end_s"]:
            raise ValueError("Observation time is outside the source run horizon")
        counts = dict(not_yet_released=0, tracked=0, boundary_unresolved=0,
                      step_limited=0, observation_complete=0)
        rooms = {}
        for track in tracks:
            age = time - track["release_time_s"]
            if age < 0:
                counts["not_yet_released"] += 1
                continue
            final = track["points"][-1]["elapsed_particle_s"]
            if age >= final:
                key = {"fluid_boundary_contact_unresolved": "boundary_unresolved",
                       "max_steps": "step_limited", "max_particle_time": "observation_complete"}[
                           track["termination"]]
                counts[key] += 1
            else:
                counts["tracked"] += 1
            sample = track["points"][0]
            for point in track["points"]:
                if point["elapsed_particle_s"] > age:
                    break
                sample = point
            room = sample["room_id"]
            rooms[room] = rooms.get(room, 0) + 1
        rows.append({
            "observation_time_s": time, "scheduled_particles": len(tracks),
            **counts, "last_sample_room_counts": dict(sorted(rooms.items())),
            "accounting_complete": sum(counts.values()) == len(tracks),
        })
    return rows


def _verified_replay(report, run, cancel_check=None):
    config, _ = _validate_run(report, run)
    replay = run_particle_sources(report, config["sources"],
                                  observation_end_s=config["observation_end_s"], cancel_check=cancel_check)
    if replay != run:
        raise ValueError("Scheduled particle run does not exactly reproduce from its inputs")


def export_particle_source_run(report, run, destination, *, cancel_check=None):
    """Independent replay rejects altered samples before any file is opened."""
    _verified_replay(report, run, cancel_check)
    serialized = json.dumps(run, indent=2, allow_nan=False) + "\n"
    path = Path(destination)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(serialized)
    return path


def export_particle_source_csv(report, run, destination, *, cancel_check=None):
    """Export actual integration vertices with both age and scheduled time."""
    _verified_replay(report, run, cancel_check)
    path = Path(destination)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("source_id", "particle_index", "release_time_s", "particle_age_s",
                         "observation_time_s", "x_m", "y_m", "z_m", "vx_m_s", "vy_m_s", "vz_m_s",
                         "recorded_Ux_m_s", "recorded_Uy_m_s", "recorded_Uz_m_s", "room_id",
                         "termination", "source_iteration", "manifest_sha256", "run_receipt_sha256"))
        for track in run["tracks"]:
            for point in track["points"]:
                writer.writerow((
                    track["injection_source_id"], track["source_particle_index"],
                    track["release_time_s"], point["elapsed_particle_s"],
                    track["release_time_s"] + point["elapsed_particle_s"],
                    *point["xyz_m"], *point["particle_velocity_m_s"],
                    *point["recorded_gas_velocity_m_s"], point["room_id"], track["termination"],
                    run["source_iteration"], run["source_manifest_sha256"], run["source_run_receipt_sha256"],
                ))
    return path
