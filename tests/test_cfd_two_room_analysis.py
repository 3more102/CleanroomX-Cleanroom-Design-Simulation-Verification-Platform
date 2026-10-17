"""Headless numerical/graph regression for two-room evidence analysis."""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from cleanroomx import cfd_two_room_analysis as analysis
from cleanroomx.cfd_pipeline_cli import build_parser


def _fixture(tmp_path, monkeypatch):
    case = tmp_path / "case"
    case.mkdir()
    manifest = {"spec": {"density_kg_m3": 1.2, "room_m": [6.0, 4.0, 3.0]}}
    (case / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    probe = case / "postProcessing" / "roomPressureProbes" / "150" / "p"
    probe.parent.mkdir(parents=True)
    payload = b"# probe time values\n0 3 1\n1 4 1\n"
    probe.write_bytes(payload)
    probe_sha = hashlib.sha256(payload).hexdigest()
    receipt = tmp_path / "receipt.json"
    document = {
        "receipt_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "vtk_assets_sha256": {},
        "pressure_probe": {
            "path": "postProcessing/roomPressureProbes/150/p",
            "sha256": probe_sha,
            "sample_count": 2,
            "last_solver_time": 1.0,
            "room_1_pressure_pa_gauge": 4.8,
            "room_2_pressure_pa_gauge": 1.2,
            "delta_pressure_pa_room_1_minus_room_2": 3.6,
        },
        "engineering_screens": {
            "pressure_target_pa": 5.0,
            "pressure_tolerance_pa": 1.0,
            "pressure_target_screen": "outside_declared_band",
            "actual_inlet_flow_m3_s": 0.1,
            "actual_outlet_flow_m3_s": 0.09,
            "relative_inlet_outlet_difference_percent": 10.526315789473685,
        },
    }
    receipt.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(analysis, "proofgraph_from_two_room_receipt", lambda *_: None)
    monkeypatch.setattr(analysis, "_vtk_room_fields", lambda *_: {
        "status": "UNAVAILABLE", "reason": "fixture_does_not_model_fields"
    })
    return case, receipt, probe


def test_weighted_distribution_is_volume_weighted_not_cell_count_weighted():
    stats = analysis._weighted_distribution([(1, 1), (3, 3)], "m/s")
    assert stats["cell_count"] == 2
    assert stats["sampled_volume_m3"] == 4
    assert stats["volume_weighted_mean"] == pytest.approx(2.5)
    assert stats["volume_weighted_median"] == 3
    assert sum(stats["bin_volume_percent"]) == pytest.approx(100)


@pytest.mark.parametrize("samples", [[(0.1, 0.0)], [(float("nan"), 1)], [(1, -2)]])
def test_weighted_distribution_rejects_invalid_cells(samples):
    with pytest.raises(ValueError):
        analysis._weighted_distribution(samples, "m/s")


def test_receipt_values_are_recomputed_from_actual_probe_file(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    result = analysis.analyze_two_room_evidence(case, receipt)
    assert result["pressure"]["series"][-1]["delta_pressure_pa"] == pytest.approx(3.6)
    assert result["flow"]["inlet_m3_s"] == 0.1
    assert result["solver_convergence"] == "NOT_ASSESSED"
    assert result["scientific_validation"] == "BLOCKED"
    assert result["vtk_fields"]["status"] == "UNAVAILABLE"


def test_export_creates_actual_graphs_and_refuses_overwrite(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "analysis"
    report = analysis.export_two_room_analysis(case, receipt, output)
    assert sorted(report["graphs"]) == ["inlet_outlet_flux.svg", "pressure_probe_history.svg"]
    assert report["scientific_validation"] == "BLOCKED"
    data = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    assert data["pressure"]["time_axis"].startswith("OpenFOAM solver indices")
    assert "<svg " in (output / "pressure_probe_history.svg").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        analysis.export_two_room_analysis(case, receipt, output)


def test_evidence_gate_runs_before_any_graph_calculation(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    def fail(*_):
        raise ValueError("tampered solver evidence")
    monkeypatch.setattr(analysis, "proofgraph_from_two_room_receipt", fail)
    with pytest.raises(ValueError, match="tampered solver evidence"):
        analysis.export_two_room_analysis(case, receipt, tmp_path / "graphs")
    assert not (tmp_path / "graphs").exists()


def test_probe_hash_changes_abort_export(tmp_path, monkeypatch):
    case, receipt, probe = _fixture(tmp_path, monkeypatch)
    probe.write_text("0 20 10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Probe changed"):
        analysis.export_two_room_analysis(case, receipt, tmp_path / "graphs")


def test_probe_metadata_forgery_is_rejected(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["pressure_probe"]["delta_pressure_pa_room_1_minus_room_2"] = 99
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Recomputed probe value differs"):
        analysis.analyze_two_room_evidence(case, receipt)


def test_gauge_pressure_graph_supports_negative_values():
    svg = analysis._bars_svg("Gauge p", ["Room 1", "Room 2"], [-1.8, 2.4], "Pa")
    rectangles = re.findall(r'<rect x="\d+" y="([\d.]+)" width="85" height="([\d.]+)"', svg)
    assert len(rectangles) == 2
    assert all(0 <= float(y) <= 235 and 0 < float(h) <= 170 for y, h in rectangles)


def test_cli_parser_exposes_analysis_command():
    args = build_parser().parse_args(["two-room-analyze", "case", "receipt.json", "graphs"])
    assert args.command == "two-room-analyze"
    assert args.output_directory == "graphs"
