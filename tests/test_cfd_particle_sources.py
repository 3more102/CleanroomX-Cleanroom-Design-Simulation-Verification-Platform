"""Synthetic numerical source contracts; these are NOT executed CFD evidence."""
import copy
import csv
import json
import math

import pytest

from cleanroomx.cfd_particle_sources import (
    export_particle_source_configuration, export_particle_source_csv,
    export_particle_source_run, load_particle_source_configuration,
    particle_source_configuration, particle_source_population, run_particle_sources,
    validate_particle_sources,
)
from cleanroomx.cfd_particles import ParticleRunCancelled, particle_positions_at_elapsed


def _report():
    return {
        "schema": "cleanroomx.multizone-results.v1", "time_name": "100",
        "voxel_pitch_m": [1., 1., 1.],
        "provenance": {"manifest_sha256": "a"*64, "run_receipt_sha256": "b"*64},
        "cells": [{"center_m": [i+.5, .5, .5], "velocity_m_s": [.1, 0., 0.],
                   "room_id": "A" if i < 4 else "B"} for i in range(8)],
    }


def _source(**changes):
    return dict(source_id="source_A", enabled=True, position_m=[.5, .5, .5],
                particle_count=3, start_time_s=.2, duration_s=.4, diameter_um=5.,
                particle_density_kg_m3=1000., initial_velocity_m_s=[0., 0., 0.], **{}) | changes


def test_scheduled_releases_have_distinct_age_clock_and_exact_relaxation():
    report, source = _report(), _source()
    original = copy.deepcopy(source)
    run = run_particle_sources(report, [source], observation_end_s=1.)
    assert source == original
    assert [t["release_time_s"] for t in run["tracks"]] == pytest.approx([.2, .4, .6])
    for track in run["tracks"]:
        age = 1. - track["release_time_s"]
        assert track["max_time_s"] == age
        assert track["points"][0]["elapsed_particle_s"] == 0
        assert track["points"][-1]["elapsed_particle_s"] == pytest.approx(age)
        tau = track["particle_relaxation_s"]
        exact_x = .5 + .1 * (age - tau * (1-math.exp(-age/tau)))
        assert track["points"][-1]["xyz_m"][0] == pytest.approx(exact_x, abs=1e-12)
    assert run["engineering_release"] == "HOLD"
    assert run["validated_particle_transport"] is False


def test_playback_does_not_show_particles_before_their_source_releases():
    tracks = run_particle_sources(_report(), [_source()], observation_end_s=1.)["tracks"]
    assert particle_positions_at_elapsed(tracks, 0) == []
    assert len(particle_positions_at_elapsed(tracks, .2)) == 1
    assert len(particle_positions_at_elapsed(tracks, .5)) == 2
    shown = particle_positions_at_elapsed(tracks, .65)
    assert len(shown) == 3
    for marker, track in zip(shown, tracks):
        assert marker["observation_sample_time_s"] <= .65 + 1e-12
        assert marker["xyz_m"] in [p["xyz_m"] for p in track["points"]]
    tracks[0]["release_time_s"] = True
    with pytest.raises(ValueError, match="finite"):
        particle_positions_at_elapsed(tracks, .2)


def test_population_counts_partition_every_scheduled_particle_and_room_sample():
    report = _report()
    run = run_particle_sources(report, [_source()], observation_end_s=1.)
    times = [0., .2, .5, 1.]
    rows = particle_source_population(report, run, times)
    assert [r["not_yet_released"] for r in rows] == [3, 2, 1, 0]
    assert rows[-1]["observation_complete"] == 3
    assert rows[-1]["last_sample_room_counts"] == {"A": 3}
    for row in rows:
        assert row["accounting_complete"]
        assert sum(row[key] for key in (
            "not_yet_released", "tracked", "boundary_unresolved", "step_limited",
            "observation_complete")) == row["scheduled_particles"] == 3
        assert sum(row["last_sample_room_counts"].values()) == 3-row["not_yet_released"]


def test_multi_source_order_reproducibility_disabled_and_simultaneous_releases():
    a = _source(source_id="A", start_time_s=0., duration_s=0.)
    b = _source(source_id="B", start_time_s=0., duration_s=0., position_m=[4.5, .5, .5])
    off = _source(source_id="off", enabled=False, particle_count=20)
    report = _report()
    x = run_particle_sources(report, [b, a, off], observation_end_s=1.)
    y = run_particle_sources(report, [b, a, off], observation_end_s=1.)
    assert x == y
    assert [(t["injection_source_id"], t["source_particle_index"]) for t in x["tracks"]] == [
        (sid, i) for sid in ("A", "B") for i in range(1, 4)]
    assert len(x["tracks"]) == 6
    with pytest.raises(ValueError, match="Enable at least"):
        run_particle_sources(report, [off])


def test_occupied_voxel_interior_allowed_and_boundary_contact_never_called_deposition():
    report = _report()
    source = _source(position_m=[7.99, .5, .5], start_time_s=0., duration_s=0.)
    run = run_particle_sources(report, [source], observation_end_s=1.)
    row = particle_source_population(report, run, [1.])[0]
    assert row["boundary_unresolved"] == 3
    assert row["accounting_complete"]
    assert "deposited" not in row and "escaped" not in row


@pytest.mark.parametrize("changes", [
    {"particle_count": True}, {"particle_count": 0}, {"particle_count": 21},
    {"particle_count": 1.5}, {"enabled": 1}, {"source_id": "../source"},
    {"position_m": [9., .5, .5]}, {"position_m": [.5, float("nan"), .5]},
    {"position_m": [1, 2]}, {"initial_velocity_m_s": [0, True, 0]},
    {"duration_s": -.1}, {"start_time_s": True}, {"start_time_s": float("inf")},
    {"duration_s": .8}, {"particle_count": 1}, {"diameter_um": .4},
    {"diameter_um": 21}, {"particle_density_kg_m3": 99}, {"unknown": "field"},
])
def test_source_input_validation(changes):
    with pytest.raises(ValueError):
        validate_particle_sources(_report(), [_source(**changes)], 1.)


def test_identity_capacity_and_duplicate_source_validation():
    report = _report()
    with pytest.raises(ValueError, match="unique"):
        validate_particle_sources(report, [_source(), _source()], 1.)
    with pytest.raises(ValueError, match="capacity"):
        validate_particle_sources(report, [_source(particle_count=20),
                                  _source(source_id="B")], 1.)
    report["provenance"]["run_receipt_sha256"] = "invented"
    with pytest.raises(ValueError, match="SHA-256"):
        particle_source_configuration(report, [_source()], 1.)


def test_cancellation_during_integration_returns_no_partial_collection():
    sources = [_source()]
    snapshot = copy.deepcopy(sources)
    calls = []
    def cancelled():
        calls.append(True)
        return len(calls) > 5
    with pytest.raises(ParticleRunCancelled, match="cancelled"):
        run_particle_sources(_report(), sources, observation_end_s=1., cancel_check=cancelled)
    assert sources == snapshot


def test_source_configuration_roundtrip_stale_identity_duplicates_and_no_overwrite(tmp_path):
    report = _report()
    path = tmp_path/"sources.json"
    export_particle_source_configuration(report, [_source()], 1., path)
    loaded = load_particle_source_configuration(report, path)
    assert loaded == particle_source_configuration(report, [_source()], 1.)
    with pytest.raises(FileExistsError):
        export_particle_source_configuration(report, [_source()], 1., path)
    stale = copy.deepcopy(report)
    stale["time_name"] = "200"
    with pytest.raises(ValueError, match="another CFD"):
        load_particle_source_configuration(stale, path)
    path.write_text('{"schema":"first", "schema":"second"}')
    with pytest.raises(ValueError):
        load_particle_source_configuration(report, path)


def test_run_and_csv_exports_replay_underlying_velocity_and_preserve_units(tmp_path):
    report = _report()
    run = run_particle_sources(report, [_source(diameter_um=9.)], observation_end_s=1.)
    path = export_particle_source_run(report, run, tmp_path/"run.json")
    assert json.loads(path.read_text()) == run
    csv_path = export_particle_source_csv(report, run, tmp_path/"tracks.csv")
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == sum(len(t["points"]) for t in run["tracks"])
    assert float(rows[0]["release_time_s"]) == .2
    assert float(rows[0]["observation_time_s"]) == .2
    assert rows[0]["manifest_sha256"] == "a"*64
    with pytest.raises(FileExistsError):
        export_particle_source_run(report, run, path)


@pytest.mark.parametrize("change", ["release", "count", "sample", "acceptance", "diagnostic"])
def test_tampered_run_rejected_before_output_is_created(tmp_path, change):
    report = _report()
    run = run_particle_sources(report, [_source()], observation_end_s=1.)
    if change == "release":
        run["tracks"][0]["release_time_s"] += .01
    elif change == "count":
        run["tracks"].pop()
    elif change == "sample":
        # Still in the same fluid cell: exact replay must detect this change.
        run["tracks"][0]["points"][1]["xyz_m"][0] += .00001
        run["diagnostics"] = __import__(
            "cleanroomx.cfd_particle_diagnostics", fromlist=["analyze_particle_trajectories"]
        ).analyze_particle_trajectories(report, run["tracks"])
    elif change == "acceptance":
        run["engineering_release"] = "PASS"
    else:
        run["diagnostics"]["number_of_screening_tracks"] += 1
    path = tmp_path/"rejected.json"
    with pytest.raises(ValueError):
        export_particle_source_run(report, run, path)
    assert not path.exists()
