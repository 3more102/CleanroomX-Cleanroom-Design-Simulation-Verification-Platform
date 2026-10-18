"""Analysis/export regression tests using synthetic files, never a live solver."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

import pytest

pytest.importorskip("vtk")

from cleanroomx.cfd_analysis_export import export_analysis_bundle, graph_csv
from cleanroomx.cfd_result_analysis import (
    analyze_synced_results, analyze_two_room_results, build_analysis_graph,
    compute_supply_ach, read_residual_history,
    _reduce_history,
)
from cleanroomx.proofgraph_io import proofgraph_from_dict
from cfd_analysis_fixtures import write_sync_store, write_two_room_analysis_fixture, residual_log


def session(tmp_path, **kwargs):
    store = tmp_path / "store"
    write_sync_store(store, **kwargs)
    return analyze_synced_results(store, kwargs.get("run", "SYNTHETIC-run-a"))


def test_volume_weighted_fields_and_numeric_time_order(tmp_path):
    result = session(tmp_path)
    snapshots = result.report["snapshots"]
    assert [s["time_name"] for s in snapshots] == ["2", "10"]
    first = snapshots[0]
    assert first["volume_m3"] == pytest.approx(3)
    assert first["statistics"]["speed"]["mean"] == pytest.approx(50/3)
    assert first["statistics"]["p"]["mean"] == pytest.approx(6)
    assert first["statistics"]["T"]["mean"] == pytest.approx(320)
    assert first["statistics"]["T"]["units"] == "K"
    assert first["statistics"]["p"]["units"] != "Pa"
    assert "whole mesh" in first["region"]
    assert result.report["reproducibility"]["native_source_bytes_rehashed"] is False
    assert result.report["scientific_validation"] == "BLOCKED"


def test_missing_fields_and_unmodeled_analyses_never_receive_values(tmp_path):
    result = session(tmp_path, thermal=False)
    graph = build_analysis_graph([result], field_name="T")
    assert graph["status"] == "not_available"
    assert graph["series"] == []
    assert "Not available" in graph["reason"]
    for kind in ("pressure_history", "flow_balance", "air_change_rate", "residual_history"):
        assert build_analysis_graph([result], kind=kind)["status"] == "not_available"
    assert any(a["analysis"] == "room_airflow_ach" for a in result.report["availability"])


def test_dimensionless_t_is_never_labeled_temperature(tmp_path):
    result = session(tmp_path, kelvin=False)
    stats = result.report["snapshots"][0]["statistics"]["T"]
    assert stats["label"] == "T"
    assert stats["units"] != "K"


def test_run_comparison_uses_matching_time_and_preserves_sources(tmp_path):
    store = tmp_path / "store"
    write_sync_store(store, run="SYNTHETIC-before", times=("2", "10"))
    write_sync_store(store, run="SYNTHETIC-after", times=("10",), factor=2)
    sessions = [analyze_synced_results(store, name) for name in ("SYNTHETIC-before", "SYNTHETIC-after")]
    graph = build_analysis_graph(sessions, kind="comparison", time_name="1e1")
    assert len(graph["series"]) == 2
    assert graph["series"][1]["points"][0]["y"] == pytest.approx(graph["series"][0]["points"][0]["y"]*2)
    assert all(p["time_name"] == "10" for s in graph["series"] for p in s["points"])
    assert all(source["sha256"] and source["path"] for source in graph["sources"])
    at_two = build_analysis_graph(sessions, kind="comparison", time_name="2")
    assert len(at_two["series"]) == 1  # no substitution of the after run's latest time


@pytest.mark.parametrize("kind", ["cell_slab", "cell_3d"])
def test_spatial_values_retain_indices_time_units_and_region(tmp_path, kind):
    result = session(tmp_path)
    graph = build_analysis_graph([result], kind=kind, field_name="p", case_id="configuration_1",
                                 time_name="2", axis="z", position_m=0.5, thickness_m=0.1)
    assert graph["selected_cell_count"] == 2
    assert [p["value"] for p in graph["series"][0]["points"]] == [2, 8]
    assert graph["series"][0]["points"][0]["cell_index"] == 0
    assert graph["series"][0]["points"][0]["time_name"] == "2"
    assert "m^2/s^2" in graph["color_label"]
    assert "interpolation" in graph["method"]
    empty = build_analysis_graph([result], kind="cell_slab", case_id="configuration_1", time_name="2",
                                 position_m=99, thickness_m=0.1)
    assert empty["status"] == "not_available"


def test_spatial_access_rejects_changed_vtk_and_bad_selection(tmp_path):
    result = session(tmp_path)
    with pytest.raises(ValueError, match="explicit case"):
        build_analysis_graph([result], kind="cell_slab")
    vtk_path = Path(result.report["snapshots"][0]["vtk_source"]["path"])
    vtk_path.write_bytes(vtk_path.read_bytes() + b"\nchanged\n")
    with pytest.raises(ValueError, match="changed"):
        build_analysis_graph([result], kind="cell_3d", case_id="configuration_1", time_name="2")


def test_residual_history_keeps_correctors_zeros_and_line_numbers(tmp_path):
    path = tmp_path / "simpleFoam.log"
    path.write_text(residual_log())
    result = read_residual_history(path)
    assert len(result["samples"]) == 4
    assert [s["time"] for s in result["samples"]] == [1,1,1,2]
    assert result["samples"][0]["final"] == 0
    assert result["samples"][0]["line"] == 3
    assert "MISSING_REQUIRED_FIELD" in result["diagnosis"]["problems"]
    assert result["status"] == "INCOMPLETE_OR_INVALID"


@pytest.mark.parametrize("replacement", ["Time = 1\nTime = 0\n", "Time = nan\n", "Time = 1\nSolving for p, Initial residual = nan\n"])
def test_bad_residual_histories_fail_closed(tmp_path, replacement):
    path = tmp_path / "simpleFoam.log"
    path.write_text(replacement)
    with pytest.raises(ValueError):
        read_residual_history(path)


@pytest.mark.parametrize("flow,volume,expected", [(0.1,72,5), (0,72,0), (1,3600,1)])
def test_supply_ach_formula(flow, volume, expected):
    assert compute_supply_ach(flow, volume) == pytest.approx(expected)


@pytest.mark.parametrize("flow,volume", [(True,72),(-1,72),(1,0),(1,float("nan"))])
def test_supply_ach_rejects_invalid_inputs(flow, volume):
    with pytest.raises(ValueError):
        compute_supply_ach(flow, volume)


def test_two_room_graphs_reparse_actual_probes_phi_and_mesh(tmp_path):
    case, receipt = write_two_room_analysis_fixture(tmp_path)
    result = analyze_two_room_results(case, receipt)
    pressure = build_analysis_graph([result], kind="pressure_history")
    difference = next(s for s in pressure["series"] if "difference" in s["label"])
    assert [p["y"] for p in difference["points"]] == pytest.approx([1.2,4.92])
    assert "not room-average" in difference["region"]
    flow = result.report["flow_balance"]
    assert flow["outlet_net_outward_m3_s"] == pytest.approx(0.09)  # receipt had 0.1: reparse phi
    assert flow["net_boundary_outward_m3_s"] == pytest.approx(0, abs=1e-12)
    assert result.report["ventilation"]["mesh_volume_m3"] > 0
    assert build_analysis_graph([result],kind="air_change_rate")["series"]
    assert result.report["diagnostics"][0]["mesh"]["source_log_sha256"]
    residuals = build_analysis_graph([result],kind="residual_history",field_name="all")
    assert any(p["y"] == 0 for s in residuals["series"] for p in s["points"])


def test_complete_export_hashes_figures_data_and_valid_proofgraph(tmp_path):
    pytest.importorskip("matplotlib")
    result = session(tmp_path)
    graphs = [build_analysis_graph([result]), build_analysis_graph([result],kind="comparison",time_name="10")]
    output = export_analysis_bundle([result],graphs,tmp_path/"export")
    manifest = json.loads((output/"manifest.json").read_text())
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == sha
    assert (output/"figure-01.png").read_bytes().startswith(b"\x89PNG")
    assert "<svg" in (output/"figure-01.svg").read_text()
    assert list(csv.DictReader(io.StringIO((output/"graphs.csv").read_text())))[0]["case_id"] == "configuration_1"
    graph_doc = json.loads((output/"proofgraph-01.json").read_text())
    proofgraph_from_dict(graph_doc)
    derived = graph_doc["evidence"][-1]["value"]
    assert derived["report"]["scientific_validation"] == "BLOCKED"
    assert "figure-01.png" in derived["exported_artifact_sha256"]
    assert derived["graphs"] == graphs
    validation = [v for v in graph_doc["verdicts"] if "SCIENTIFIC-VALIDATION" in v["id"]]
    assert all(v["status"] == "not_checked" for v in validation)
    with pytest.raises(FileExistsError):
        export_analysis_bundle([result],graphs,output)


def test_export_rejects_edited_graph_changed_source_and_source_destination(tmp_path):
    result = session(tmp_path)
    graph = build_analysis_graph([result])
    edited = copy.deepcopy(graph)
    edited["series"][0]["points"][0]["y"] = 999
    with pytest.raises(ValueError, match="no longer matches"):
        export_analysis_bundle([result],[edited],tmp_path/"edited")
    with pytest.raises(ValueError, match="outside source"):
        export_analysis_bundle([result],[graph],tmp_path/"store"/"export")
    path = Path(result.report["snapshots"][0]["vtk_source"]["path"])
    path.write_bytes(path.read_bytes()+b"\nchanged\n")
    with pytest.raises(ValueError, match="source changed"):
        export_analysis_bundle([result],[graph],tmp_path/"changed")
    assert not (tmp_path/"changed").exists()


def test_csv_protects_spreadsheet_formulas(tmp_path):
    result = session(tmp_path)
    graph = build_analysis_graph([result])
    graph["series"][0]["label"] = "=1+1"
    row = next(csv.DictReader(io.StringIO(graph_csv([graph]))))
    assert row["series"] == "'=1+1"


def test_analysis_cli_exports_real_parser_fixture(tmp_path, monkeypatch, capsys):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_pipeline_cli import main
    write_sync_store(tmp_path/"store")
    monkeypatch.setattr(sys,"argv",["cleanroomx-cfd-pipeline","analyze-results",str(tmp_path/"store"),
                                    "--simulation-id","SYNTHETIC-run-a","--output",str(tmp_path/"cli-export")])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scientific_validation"] == "BLOCKED"
    assert (tmp_path/"cli-export"/"graphs.csv").exists()


def test_history_reduction_preserves_endpoints_and_narrow_extrema():
    points = [{"x": i, "y": 0} for i in range(20000)]
    points[7919]["y"] = 1000
    points[8001]["y"] = -1000
    reduced = _reduce_history(points, 100)
    assert len(reduced) <= 100
    assert reduced[0] == points[0] and reduced[-1] == points[-1]
    assert points[7919] in reduced and points[8001] in reduced


def test_spatial_export_includes_all_selected_cell_data(tmp_path):
    result = session(tmp_path)
    graph = build_analysis_graph([result],kind="cell_3d",case_id="configuration_1",time_name="2")
    output = export_analysis_bundle([result],[graph],tmp_path/"spatial-export")
    rows = list(csv.DictReader((output/"cell-data-01.csv").open()))
    assert len(rows) == 2
    assert [float(row["value"]) for row in rows] == pytest.approx([10,20])


def test_export_cleans_up_after_render_failure(tmp_path, monkeypatch):
    import cleanroomx.cfd_analysis_export as module
    result = session(tmp_path)
    graph = build_analysis_graph([result])
    def fail(*_args):
        raise RuntimeError("test renderer failed")
    monkeypatch.setattr(module,"draw_analysis_graph",fail)
    with pytest.raises(RuntimeError,match="renderer failed"):
        export_analysis_bundle([result],[graph],tmp_path/"failed-export")
    assert not (tmp_path/"failed-export").exists()
    assert not list(tmp_path.glob(".cleanroomx-analysis-*"))
