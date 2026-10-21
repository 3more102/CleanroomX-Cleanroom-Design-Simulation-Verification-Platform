"""Replay original hash-checked solver fields; no new solver execution claimed."""
import json
from pathlib import Path
import tarfile

import pytest

from cleanroomx.cfd_cell_probes import RecordedCellProbeIndex, export_recorded_cell_probes
from cleanroomx.cfd_multizone_results import analyze_multizone_case, read_ascii_field


@pytest.fixture(scope="module")
def archived_case(tmp_path_factory):
    source = Path(__file__).resolve().parents[1]/"reports/engineering-session-20261021/reproduction-case.tar.gz"
    destination = tmp_path_factory.mktemp("original-probe-source")
    with tarfile.open(source) as archive:
        archive.extractall(destination, filter="data")
    return destination/"case"


@pytest.mark.parametrize("iteration", ["25", "50", "75", "100"])
def test_every_archived_probe_matches_original_pressure_and_velocity_arrays(archived_case, iteration, tmp_path):
    report = analyze_multizone_case(
        archived_case, density_kg_m3=1.2, reference_room_id="corridor", time_name=iteration)
    count = len(report["cells"])
    pressure = read_ascii_field((archived_case/iteration/"p").read_text(), count, (0, 2, -2, 0, 0, 0, 0))
    velocity = read_ascii_field((archived_case/iteration/"U").read_text(), count, (0, 1, -1, 0, 0, 0, 0), vector=True)
    index = RecordedCellProbeIndex(report)
    examples = []
    for i, cell in enumerate(report["cells"]):
        probe = index.probe_at(cell["center_m"])
        assert probe["cell_index"] == i
        assert probe["source_iteration"] == iteration
        assert probe["velocity_m_s"] == velocity[i]
        assert probe["pressure_pa_relative_to_reference"] == (
            1.2*(pressure[i]-report["pressure_reference"]["kinematic_pressure_m2_s2"]))
        if i in (0, count//3, count//2, count-1):
            examples.append(probe)
    exported = export_recorded_cell_probes(report, examples, tmp_path/"original-probes.json")
    assert json.loads(exported.read_text())["probes"] == examples
    assert count == 13210


def test_archived_same_receipt_with_different_density_or_reference_cannot_reuse_probe(archived_case, tmp_path):
    original = analyze_multizone_case(archived_case, density_kg_m3=1.2, reference_room_id="corridor")
    point = original["cells"][0]["center_m"]
    probe = RecordedCellProbeIndex(original).probe_at(point)
    other_room = next(rid for rid in original["rooms"] if rid != "corridor")
    for density, reference in ((1.3, "corridor"), (1.2, other_room)):
        changed = analyze_multizone_case(archived_case, density_kg_m3=density, reference_room_id=reference)
        assert changed["provenance"] == original["provenance"]
        with pytest.raises(ValueError, match="stale, altered"):
            export_recorded_cell_probes(changed, [probe], tmp_path/"stale.json")
        assert not (tmp_path/"stale.json").exists()
