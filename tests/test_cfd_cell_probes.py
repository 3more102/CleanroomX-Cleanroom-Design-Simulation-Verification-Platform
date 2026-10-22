"""Synthetic software contracts, not solver execution or physical evidence."""
import copy
import json
import math

import pytest

from cleanroomx.cfd_cell_probes import (
    EXPORT_SCHEMA, MAX_PROBES, RecordedCellProbeIndex, export_recorded_cell_probes,
)


def _report():
    return {
        "schema": "cleanroomx.multizone-results.v1",
        "status": "computed_fields_require_engineering_review",
        "scenario": "all_doors_open", "time_name": "100",
        "voxel_pitch_m": [1., 1., 1.], "density_kg_m3": 1.2,
        "pressure_reference": {"room_id": "A", "kinematic_pressure_m2_s2": 12.5},
        "solver_reported_convergence": False,
        "provenance": {"manifest_sha256": "a"*64, "run_receipt_sha256": "b"*64},
        "cells": [
            {"center_m": [i+.5, .5, .5], "velocity_m_s": [3.+i, 4., 0.],
             "pressure_pa_relative_to_reference": -3.25-i,
             "room_id": "A" if i == 0 else "B"}
            for i in (0, 1, 3)
        ],
    }


def test_probe_preserves_exact_cell_values_and_reporting_context():
    report = _report()
    original = copy.deepcopy(report)
    field = RecordedCellProbeIndex(report)
    probe = field.probe_at([.2, .7, .5])
    assert probe["cell_index"] == 0
    assert probe["requested_location_m"] == [.2, .7, .5]
    assert probe["cell_center_m"] == [.5, .5, .5]
    assert probe["velocity_m_s"] == [3., 4., 0.]
    assert probe["speed_m_s"] == 5.
    assert probe["pressure_pa_relative_to_reference"] == -3.25
    assert probe["pressure_reference"] == report["pressure_reference"]
    assert probe["source_iteration"] == "100"
    assert probe["source_run_receipt_sha256"] == "b"*64
    assert probe["density_kg_m3"] == 1.2
    assert probe["solver_reported_convergence"] is False
    assert probe["engineering_release"] == "HOLD"
    assert report == original
    # A caller cannot mutate the cached field or another probe via a result.
    probe["velocity_m_s"][0] = 999
    probe["pressure_reference"]["room_id"] = "changed"
    assert field.probe_at([.5, .5, .5])["velocity_m_s"] == [3., 4., 0.]
    assert field.probe_at([.5, .5, .5])["pressure_reference"]["room_id"] == "A"


def test_half_open_faces_missing_fluid_and_room_filter_never_use_nearest_value():
    field = RecordedCellProbeIndex(_report())
    assert field.probe_at([0., 0., 0.])["cell_index"] == 0
    assert field.probe_at([1., .5, .5])["cell_index"] == 1
    for point in ([2., .5, .5], [2.5, .5, .5], [4., .5, .5],
                  [-.001, .5, .5], [.5, 1., .5], [.5, .5, 1.], [1e308, .5, .5]):
        assert field.probe_at(point) is None
    assert field.probe_at([1.5, .5, .5], room_id="A") is None
    assert field.probe_at([1.5, .5, .5], room_id="B")["cell_index"] == 1
    # No interpolation between two distinct cell-centred values.
    assert field.probe_at([.99999, .5, .5])["pressure_pa_relative_to_reference"] == -3.25
    assert field.probe_at([1.00001, .5, .5])["pressure_pa_relative_to_reference"] == -4.25


def test_anisotropic_translated_voxels_return_original_array_indices():
    report = _report()
    report["voxel_pitch_m"] = [.25, 2., .5]
    for cell in report["cells"]:
        cell["center_m"] = [-10.+cell["center_m"][0]*.25, 15., -2.]
    field = RecordedCellProbeIndex(report)
    assert field.probe_at([-9.65, 15.8, -1.8])["cell_index"] == 1
    assert field.probe_at([-9.375, 15., -2.]) is None


@pytest.mark.parametrize("origin", [0., -.9])
def test_decimal_faces_preserve_half_open_ownership_without_snapping_nearby_points(origin):
    report = _report()
    report["voxel_pitch_m"] = [.1, 1., 1.]
    report["cells"] = [dict(report["cells"][0], center_m=[round(origin+(i+.5)*.1, 2), .5, .5])
                       for i in range(8)]
    field = RecordedCellProbeIndex(report)
    for i in range(1, 8):
        face = round(origin+i*.1, 1)
        assert field.probe_at([face, .5, .5])["cell_index"] == i
        before = math.nextafter(face, -math.inf)
        after = math.nextafter(face, math.inf)
        assert field.probe_at([before, .5, .5])["cell_index"] == i-1
        assert field.probe_at([after, .5, .5])["cell_index"] == i
    assert field.probe_at([round(origin+.8, 1), .5, .5]) is None


@pytest.mark.parametrize("point", [[math.nan, 0, 0], [0, math.inf, 0],
                                   [True, 0, 0], [0, 0], "0,0,0", None])
def test_invalid_probe_coordinates_rejected(point):
    with pytest.raises(ValueError):
        RecordedCellProbeIndex(_report()).probe_at(point)


@pytest.mark.parametrize("key,value", [
    ("schema", "synthetic"), ("density_kg_m3", 0), ("density_kg_m3", math.nan),
    ("time_name", "nan"), ("solver_reported_convergence", 1),
    ("pressure_reference", {}), ("provenance", None), ("provenance", {}),
])
def test_missing_or_invalid_source_context_rejected(key, value):
    report = _report()
    report[key] = value
    with pytest.raises(ValueError):
        RecordedCellProbeIndex(report)


def test_invalid_cell_values_and_duplicate_lattice_cells_rejected():
    report = _report()
    report["cells"][0]["pressure_pa_relative_to_reference"] = math.nan
    with pytest.raises(ValueError, match="Computed pressure"):
        RecordedCellProbeIndex(report)
    report = _report()
    report["cells"].append(copy.deepcopy(report["cells"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        RecordedCellProbeIndex(report)


def test_export_checks_source_values_reference_and_never_overwrites(tmp_path):
    report = _report()
    field = RecordedCellProbeIndex(report)
    probes = [field.probe_at([.5, .5, .5]), field.probe_at([3.5, .5, .5])]
    path = tmp_path/"probes.json"
    assert export_recorded_cell_probes(report, probes, path) == path
    payload = json.loads(path.read_text())
    assert payload["schema"] == EXPORT_SCHEMA
    assert payload["probes"] == probes
    assert payload["engineering_release"] == "HOLD"
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        export_recorded_cell_probes(report, probes, path)
    assert path.read_bytes() == before
    for changed in ("time_name", "density_kg_m3", "pressure_reference", "provenance", "cells"):
        other = copy.deepcopy(report)
        if changed == "time_name":
            other[changed] = "75"
        elif changed == "density_kg_m3":
            other[changed] = 1.3
        elif changed == "pressure_reference":
            other[changed]["room_id"] = "B"
        elif changed == "provenance":
            other[changed]["run_receipt_sha256"] = "c"*64
        else:
            other[changed][0]["velocity_m_s"][0] += .01
        invalid = tmp_path/(changed+".json")
        with pytest.raises(ValueError, match="stale, altered"):
            export_recorded_cell_probes(other, probes, invalid)
        assert not invalid.exists()
    probes[0]["pressure_pa_relative_to_reference"] += 1
    with pytest.raises(ValueError, match="stale, altered"):
        export_recorded_cell_probes(report, probes, tmp_path/"altered.json")


@pytest.mark.parametrize("count", [0, MAX_PROBES+1])
def test_export_requires_bounded_nonempty_selections(tmp_path, count):
    report = _report()
    probe = RecordedCellProbeIndex(report).probe_at([.5, .5, .5])
    with pytest.raises(ValueError, match="Select 1 to"):
        export_recorded_cell_probes(report, [probe]*count, tmp_path/"invalid.json")
    assert not (tmp_path/"invalid.json").exists()
