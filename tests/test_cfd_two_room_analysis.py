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
    log = case / "simpleFoam.log"
    log_raw = (
        "Time = 1\n"
        "smoothSolver:  Solving for Ux, Initial residual = 0.01, Final residual = 0.001, No Iterations 2\n"
        "GAMG: Solving for p, Initial residual = 0.025, Final residual = 0.002, No Iterations 3\n"
        "time step continuity errors : sum local = 0.0001, global = -0.00001, cumulative = 0\n"
        "Time = 2\n"
        "smoothSolver:  Solving for Ux, Initial residual = 0.008, Final residual = 0.0008, No Iterations 2\n"
        "GAMG: Solving for p, Initial residual = 0.020, Final residual = 0.0015, No Iterations 3\n"
        "End\n"
    ).encode("utf-8")
    log.write_bytes(log_raw)
    log_sha = hashlib.sha256(log_raw).hexdigest()
    receipt = tmp_path / "receipt.json"
    document = {
        "receipt_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "vtk_assets_sha256": {},
        "stages": [{"command": "simpleFoam", "log_path": "simpleFoam.log", "log_sha256": log_sha}],
        "solver_flux": {
            "inlet": {"net_inward_m3_s": 0.1},
            "outlet": {"net_outward_m3_s": 0.09},
        },
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
    assert result["residual_history"]["fields"]["p"]["initial"] == pytest.approx([0.025, 0.020])
    assert result["residual_history"]["continuity"][0]["global"] == pytest.approx(-0.00001)


def test_export_creates_actual_graphs_and_refuses_overwrite(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "analysis"
    report = analysis.export_two_room_analysis(case, receipt, output)
    assert sorted(report["graphs"]) == ["inlet_outlet_flux.svg", "pressure_probe_history.svg", "simplefoam_continuity_history.svg", "simplefoam_residual_Ux.svg", "simplefoam_residual_p.svg"]
    assert report["scientific_validation"] == "BLOCKED"
    assert report["artifact_integrity"] == "VERIFIED_LOCAL_ARTIFACT_INTEGRITY"
    assert (output / "artifact_manifest.json").is_file()
    data = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    assert data["pressure"]["time_axis"].startswith("OpenFOAM solver indices")
    assert "<svg " in (output / "pressure_probe_history.svg").read_text(encoding="utf-8")
    dashboard = (output / "index.html").read_text(encoding="utf-8")
    assert "Scientific validation: BLOCKED" in dashboard
    assert "inlet_outlet_flux.svg" in dashboard
    assert "simplefoam_residual_p.svg" in dashboard
    assert "<script" not in dashboard
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
    audit = build_parser().parse_args(["two-room-analysis-audit", "graphs"])
    assert audit.command == "two-room-analysis-audit"
    assert audit.directory == "graphs"


def test_solver_log_change_fails_after_receipt_gate(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    (case / "simpleFoam.log").write_text("fake residual\n", encoding="utf-8")
    with pytest.raises(ValueError, match="simpleFoam log changed"):
        analysis.export_two_room_analysis(case, receipt, tmp_path / "graphs")


def test_nonfinite_residual_markers_retained_without_convergence_claim(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    log = case / "simpleFoam.log"
    content = log.read_text(encoding="utf-8") + "\nFOAM FATAL ERROR\n"
    log.write_text(content, encoding="utf-8")
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    doc["stages"][0]["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(doc), encoding="utf-8")
    result = analysis.analyze_two_room_evidence(case, receipt)
    assert result["residual_history"]["fatal_or_nonfinite_marker"] is True
    assert result["residual_history"]["solver_convergence"] == "NOT_ASSESSED"


def test_residual_chart_never_uses_physical_time():
    svg = analysis._residual_svg("Ux", {"initial": [0.1, 0.05], "final": [0.01, 0.005]})
    assert "Per-field solve number" in svg
    assert "physical time" not in svg.lower()


def test_real_vtk_volume_weighted_room_field_statistics(tmp_path):
    vtk = pytest.importorskip("vtk")
    case = tmp_path / "case"
    source = case / "VTK" / "case_150.vtu"
    source.parent.mkdir(parents=True)
    points = vtk.vtkPoints()
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    for x0, x1 in ((0.0, 1.0), (6.0, 8.0)):
        corners = (
            (x0, 0, 0), (x1, 0, 0), (x1, 1, 0), (x0, 1, 0),
            (x0, 0, 1), (x1, 0, 1), (x1, 1, 1), (x0, 1, 1),
        )
        first = points.GetNumberOfPoints()
        for pt in corners:
            points.InsertNextPoint(*pt)
        cell = vtk.vtkHexahedron()
        for vertex in range(8):
            cell.GetPointIds().SetId(vertex, first + vertex)
        grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    velocity = vtk.vtkDoubleArray()
    velocity.SetName("U")
    velocity.SetNumberOfComponents(3)
    velocity.InsertNextTuple3(1.0, 0.0, 0.0)
    velocity.InsertNextTuple3(3.0, 0.0, 0.0)
    grid.GetCellData().AddArray(velocity)
    p = vtk.vtkDoubleArray()
    p.SetName("p")
    p.InsertNextValue(-2.0)
    p.InsertNextValue(4.0)
    grid.GetCellData().AddArray(p)
    writer = vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(source))
    writer.SetInputData(grid)
    assert writer.Write() == 1
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = analysis._vtk_room_fields(
        case, {"VTK/case_150.vtu": digest}, room_length=6.0, density=1.2
    )
    assert result["status"] == "MEASURED_DIAGNOSTIC_ONLY"
    rooms = result["rooms"]
    assert rooms["room_1"]["velocity_magnitude"]["sampled_volume_m3"] == pytest.approx(1)
    assert rooms["room_2"]["velocity_magnitude"]["sampled_volume_m3"] == pytest.approx(2)
    assert rooms["room_1"]["velocity_magnitude"]["volume_weighted_mean"] == pytest.approx(1)
    assert rooms["room_2"]["velocity_magnitude"]["volume_weighted_mean"] == pytest.approx(3)
    assert rooms["room_1"]["pressure_gauge"]["volume_weighted_mean"] == pytest.approx(-2.4)
    assert rooms["room_2"]["pressure_gauge"]["volume_weighted_mean"] == pytest.approx(4.8)
    assert sum(
        rooms["room_2"]["pressure_gauge"]["bin_volume_percent"]
    ) == pytest.approx(100)


@pytest.mark.parametrize("mutation, expected", [
    ("flow", "Inlet/outlet relative difference disagrees"),
    ("band", "Pressure target screen disagrees"),
    ("phi", "Solver phi flow and engineering screen disagree"),
])
def test_recomputed_physics_screens_reject_forged_receipt_values(tmp_path, monkeypatch, mutation, expected):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    if mutation == "flow":
        doc["engineering_screens"]["relative_inlet_outlet_difference_percent"] = 0
    elif mutation == "band":
        doc["engineering_screens"]["pressure_target_screen"] = "within_declared_band"
    else:
        doc["solver_flux"]["inlet"]["net_inward_m3_s"] = 0.5
    receipt.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        analysis.analyze_two_room_evidence(case, receipt)


def test_signed_solver_continuity_graph_preserves_zero_line_and_record_axis():
    svg = analysis._continuity_svg([
        {"sum_local": 0.0001, "global": -0.00001},
        {"sum_local": 0.0002, "global": 0.00003},
        {"sum_local": 0.0001, "global": 0.0},
    ])
    assert "Continuity record index (not seconds)" in svg
    assert "zero" not in svg
    assert 'y1="145" x2="670" y2="145"' in svg
    assert svg.count("<polyline") == 2
    assert "<script" not in svg


@pytest.mark.parametrize("records", [
    [],
    [{"sum_local": 1.0}],
    [{"sum_local": float("nan"), "global": 0.0}],
    [{"sum_local": 0.0, "global": float("inf")}],
])
def test_solver_continuity_graph_rejects_unbounded_or_missing_values(records):
    with pytest.raises(ValueError):
        analysis._continuity_svg(records)


def test_offline_dashboard_uses_verified_volume_weighted_room_statistics(tmp_path, monkeypatch):
    case, receipt, _ = _fixture(tmp_path, monkeypatch)
    report = analysis.analyze_two_room_evidence(case, receipt)
    report["graphs"] = ["pressure_probe_history.svg"]
    assert "Unavailable: no supported" in analysis._offline_dashboard(report)

    room_1_speed = analysis._weighted_distribution([(1.0, 1.0)], "m/s")
    room_2_speed = analysis._weighted_distribution([(2.0, 2.0)], "m/s")
    room_1_p = analysis._weighted_distribution([(-2.0, 1.0)], "Pa")
    report["vtk_fields"] = {
        "status": "MEASURED_DIAGNOSTIC_ONLY",
        "rooms": {
            "room_1": {
                "velocity_magnitude": room_1_speed,
                "pressure_gauge": room_1_p,
            },
            "room_2": {
                "velocity_magnitude": room_2_speed,
                "pressure_gauge": {"status": "UNAVAILABLE"},
            },
        },
    }
    html = analysis._offline_dashboard(report)
    assert "Room-by-room solver cell statistics" in html
    assert "Sampled volume (m³)" in html
    assert "Mean speed (m/s)" in html
    assert "Gauge p P05–P95 (Pa)" in html
    assert "Room 1" in html and "Room 2" in html
    assert "Unavailable</td>" in html
    assert "<script" not in html
