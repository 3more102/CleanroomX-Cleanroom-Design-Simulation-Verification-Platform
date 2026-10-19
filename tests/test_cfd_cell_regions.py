"""Region statistics are checked against an independent two-cell mesh calculation."""
import copy
import csv
import io
import json
from pathlib import Path
import sys

import pytest

from cleanroomx.cfd_cell_regions import REGION_SCHEMA, region_contains, validate_cell_region


def box(bounds=None, label="East room selection"):
    return {"schema_version": REGION_SCHEMA, "label": label, "bounds_m": bounds or [1, 3, 0, 1, 0, 1]}


@pytest.mark.parametrize("bounds", [[0, 0, 0, 1, 0, 1], [2, 1, 0, 1, 0, 1], [0, 1, 0, 1],
                                    [0, 1, 0, 1, 0, float("nan")], [0, 1, 0, 1, False, 1],
                                    [0, 1, 0, 1, 0, "1"]])
def test_invalid_region_geometry_is_rejected(bounds):
    with pytest.raises(ValueError):
        validate_cell_region(box(bounds))


def test_bounds_must_remain_finite_and_ordered_in_mesh_precision():
    for bounds in ([0, 10 ** 400, 0, 1, 0, 1], [10 ** 20, 10 ** 20 + 1, 0, 1, 0, 1]):
        with pytest.raises(ValueError):
            validate_cell_region(box(bounds))


def test_adjacent_regions_partition_centers_without_double_counting():
    left = validate_cell_region(box([0, 2, 0, 1, 0, 1]))
    right = validate_cell_region(box([2, 3, 0, 1, 0, 1]))
    assert region_contains([2, .5, .5], left["bounds_m"]) is False
    assert region_contains([2, .5, .5], right["bounds_m"]) is True
    assert region_contains([3, .5, .5], right["bounds_m"]) is False


@pytest.fixture
def result(tmp_path):
    pytest.importorskip("vtk")
    from cfd_analysis_fixtures import write_sync_store
    from cleanroomx.cfd_result_analysis import analyze_synced_results
    write_sync_store(tmp_path / "store")
    return analyze_synced_results(tmp_path / "store", "SYNTHETIC-run-a")


def test_region_uses_cell_volumes_and_preserves_pressure_units(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    selected = build_analysis_graph([result], field_name="p", region=box())
    assert [p["y"] for s in selected["series"] for p in s["points"]] == pytest.approx([8, 8])
    for summary in selected["selections"]:
        assert summary["cell_count"] == 1
        assert summary["volume_m3"] == pytest.approx(2)
        assert summary["volume_fraction_of_mesh"] == pytest.approx(2 / 3)
        assert summary["statistics"]["minimum"] == summary["statistics"]["maximum"] == 8
        assert summary["statistics"]["units"] != "Pa"
    whole_box = build_analysis_graph([result], field_name="p", region=box([0, 3, 0, 1, 0, 1]))
    # Volumes are 1 and 2 m³: (1*2 + 2*8)/3 = 6; arithmetic mean would be 5.
    assert whole_box["selections"][0]["statistics"]["mean"] == pytest.approx(6)
    assert selected["scientific_validation"] == "BLOCKED"
    assert any(a["analysis"] == "room_airflow_ach" and a["status"] == "not_available"
               for a in result.report["availability"])


def test_signed_velocity_components_are_distinct_from_speed(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    first = result.report["snapshots"][0]
    assert first["statistics"]["U_x"]["mean"] == pytest.approx(2)
    assert first["statistics"]["U_y"]["mean"] == pytest.approx(8 / 3)
    assert first["statistics"]["U_z"]["mean"] == pytest.approx(40 / 3)
    upward = build_analysis_graph([result], field_name="U_z", region=box())
    assert [p["y"] for s in upward["series"] for p in s["points"]] == pytest.approx([20, 100])
    assert all(s["statistics"]["units"] == "m/s" for s in upward["selections"])


def test_empty_box_does_not_fall_back_to_whole_mesh(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    graph = build_analysis_graph([result], region=box([8, 9, 0, 1, 0, 1]))
    assert graph["status"] == "not_available"
    assert graph["series"] == []
    assert len(graph["sources"]) > 0
    assert all(s["cell_count"] == 0 and s["volume_m3"] == 0 and s["statistics"] is None
               for s in graph["selections"])


def test_empty_3d_region_renders_and_exports_an_unavailable_result(result, tmp_path):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    from cleanroomx.cfd_analysis_export import draw_analysis_graph, export_analysis_bundle
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    graph = build_analysis_graph([result], kind="cell_3d", case_id="configuration_1", time_name="2",
                                 region=box([8, 9, 0, 1, 0, 1]))
    figure = Figure()
    canvas = FigureCanvasAgg(figure)
    draw_analysis_graph(figure, graph, include_provenance=False)
    canvas.draw()
    assert "Not available" in figure.axes[0].texts[0].get_text()
    target = export_analysis_bundle([result], [graph], tmp_path / "empty-3d-export")
    row = next(csv.DictReader(io.StringIO((target / "selections.csv").read_text())))
    assert row["status"] == "not_available"
    assert row["cell_count"] == "0"
    assert row["mean"] == ""
    assert (target / "figure-01.png").read_bytes().startswith(b"\x89PNG")


def test_spatial_box_intersects_slab_and_retains_source_cell_identity(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    graph = build_analysis_graph([result], kind="cell_slab", field_name="p", case_id="configuration_1",
                                 time_name="2", axis="x", position_m=2, thickness_m=.2, region=box())
    assert [p["cell_index"] for p in graph["series"][0]["points"]] == [1]
    assert graph["series"][0]["points"][0]["volume_m3"] == pytest.approx(2)
    assert graph["selections"][0]["statistics"]["mean"] == 8
    outside = build_analysis_graph([result], kind="cell_slab", case_id="configuration_1", time_name="2",
                                   axis="x", position_m=.5, thickness_m=.2, region=box())
    assert outside["status"] == "not_available"
    assert outside["selected_cell_count"] == 0


def test_region_comparison_matches_exact_times_and_copies_its_bounds(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    region = box()
    graph = build_analysis_graph([result], kind="comparison", time_name="1e1", region=region)
    assert len(graph["selections"]) == 1
    assert graph["selections"][0]["time_name"] == "10"
    assert graph["selections"][0]["statistics"]["mean"] == pytest.approx(100)
    region["bounds_m"][0] = 50
    assert graph["filters"]["region"]["bounds_m"][0] == 1


def test_region_cannot_relabel_flux_residuals_or_supply_ach(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    for kind in ("flow_balance", "residual_history", "air_change_rate", "pressure_history"):
        with pytest.raises(ValueError, match="only to field"):
            build_analysis_graph([result], kind=kind, region=box())


def test_region_analysis_rejects_source_mutation(result):
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    path = Path(result.report["snapshots"][0]["vtk_source"]["path"])
    path.write_bytes(path.read_bytes() + b"\nchanged\n")
    with pytest.raises(ValueError, match="changed"):
        build_analysis_graph([result], region=box())


def test_export_cell_selection_and_statistics_are_reproducible(result, tmp_path):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_result_analysis import build_analysis_graph
    from cleanroomx.cfd_analysis_export import export_analysis_bundle
    graph = build_analysis_graph([result], kind="cell_3d", field_name="p", case_id="configuration_1",
                                 time_name="2", region=box())
    target = export_analysis_bundle([result], [graph], tmp_path / "export")
    points = list(csv.DictReader(io.StringIO((target / "cell-data-01.csv").read_text())))
    assert [int(p["cell_index"]) for p in points] == [1]
    assert [float(p["value"]) for p in points] == [8]
    assert [float(p["volume_m3"]) for p in points] == pytest.approx([2])
    stats = next(csv.DictReader(io.StringIO((target / "selections.csv").read_text())))
    assert float(stats["mean"]) == 8
    assert float(stats["volume_fraction_of_mesh"]) == pytest.approx(2 / 3)
    assert stats["cell_indices_sha256"]
    assert json.loads((target / "graphs.json").read_text())[0]["filters"]["region"] == validate_cell_region(box())
    assert "Mesh volume coverage" in (target / "report.md").read_text(encoding="utf-8")
    altered = copy.deepcopy(graph)
    altered["selections"][0]["volume_m3"] = 99
    with pytest.raises(ValueError, match="no longer matches"):
        export_analysis_bundle([result], [altered], tmp_path / "edited")


def test_cli_region_is_carried_into_the_analysis_export(result, tmp_path, monkeypatch, capsys):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_pipeline_cli import main
    target = tmp_path / "cli-export"
    monkeypatch.setattr(sys, "argv", ["cleanroomx-cfd-pipeline", "analyze-results", str(tmp_path / "store"),
                                    "--simulation-id", "SYNTHETIC-run-a", "--output", str(target),
                                    "--field", "p", "--region-label", "East box",
                                    "--region-bounds", "1", "3", "0", "1", "0", "1"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["scientific_validation"] == "BLOCKED"
    graph = json.loads((target / "graphs.json").read_text())[0]
    assert graph["filters"]["region"]["label"] == "East box"
    assert graph["series"][0]["points"][0]["y"] == 8


def test_display_reduction_keeps_all_region_cells_in_statistics_and_export(tmp_path):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from cfd_analysis_fixtures import write_dense_sync_store
    from cleanroomx.cfd_result_analysis import analyze_synced_results, build_analysis_graph
    from cleanroomx.cfd_analysis_export import export_analysis_bundle
    write_dense_sync_store(tmp_path / "store")
    result = analyze_synced_results(tmp_path / "store", "SYNTHETIC-room-grid")
    graph = build_analysis_graph([result], kind="cell_3d", field_name="T", case_id="configuration_1", time_name="2",
                                 region=box([0, 3, 0, 4, 0, 3]), max_points=10)
    assert graph["selected_cell_count"] == 288
    assert graph["displayed_cell_count"] == 10
    summary = graph["selections"][0]
    assert summary["statistics"]["mean"] == pytest.approx(305)  # 300 + mean x=1.5 + y=2 + z=1.5
    assert summary["volume_m3"] == pytest.approx(36)
    assert summary["volume_fraction_of_mesh"] == pytest.approx(.5)
    target = export_analysis_bundle([result], [graph], tmp_path / "dense-export")
    rows = list(csv.DictReader(io.StringIO((target / "cell-data-01.csv").read_text())))
    assert len(rows) == 288
    assert len({row["cell_index"] for row in rows}) == 288
    assert sum(float(row["volume_m3"]) for row in rows) == pytest.approx(36)
