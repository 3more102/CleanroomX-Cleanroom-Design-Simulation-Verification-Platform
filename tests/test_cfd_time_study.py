"""Selected-time analysis tests use synthetic VTK data, never physical validation."""
from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import sys

import pytest

import cleanroomx.cfd_time_study as time_study_module
from cleanroomx.cfd_pipeline_cli import main
from cleanroomx.cfd_time_study import (
    SCHEMA,
    _pairwise_field_change,
    _weighted_quantile,
    analyze_vtk_time_study,
    render_time_study_plot,
    validate_time_study,
)


def _write_vtu(path: Path, velocities, *, contaminant=None, shift=0.0):
    vtk = pytest.importorskip("vtk")
    count = len(velocities)
    points = vtk.vtkPoints()
    for k in range(2):
        for j in range(2):
            for i in range(count + 1):
                points.InsertNextPoint(i + shift, j, k)

    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    velocity_array = vtk.vtkDoubleArray()
    velocity_array.SetName("U")
    velocity_array.SetNumberOfComponents(3)
    scalar_array = vtk.vtkDoubleArray()
    scalar_array.SetName("Tracer")
    scalar_array.SetNumberOfComponents(1)
    for i, velocity in enumerate(velocities):
        cell = vtk.vtkHexahedron()
        ids = (
            i, i + 1, i + 1 + count + 1, i + count + 1,
            i + (count + 1) * 2, i + 1 + (count + 1) * 2,
            i + 1 + count + 1 + (count + 1) * 2,
            i + count + 1 + (count + 1) * 2,
        )
        for local_id, point_id in enumerate(ids):
            cell.GetPointIds().SetId(local_id, point_id)
        grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
        velocity_array.InsertNextTuple3(velocity, 0.0, 0.0)
        scalar_array.InsertNextValue(
            contaminant[i] if contaminant is not None else float(velocity)
        )
    grid.GetCellData().AddArray(velocity_array)
    grid.GetCellData().AddArray(scalar_array)
    writer = vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    assert writer.Write() == 1


def _write_log(path: Path, *, initial="1e-6", final="1e-8"):
    path.write_text(
        "Time = 1\n"
        f"Solving for p, Initial residual = {initial}, Final residual = {final}, No Iterations 2\n"
        "Time = 2\n"
        f"Solving for p, Initial residual = {initial}, Final residual = {final}, No Iterations 2\n"
        "Time = 3\n"
        f"Solving for p, Initial residual = {initial}, Final residual = {final}, No Iterations 2\n"
        "End\n",
        encoding="utf-8",
    )


def _spec(times=("50", "75", "100"), *, quantity="velocity_mean_m_s"):
    return {
        "schema_version": SCHEMA,
        "name": "Synthetic selected-time trend fixture",
        "configuration": 1,
        "solver": "OpenFOAM Foundation v10 simpleFoam",
        "run_id": "synthetic-run-1",
        "conditions_sha256": "a" * 64,
        "room_volume_m3": 1.0,
        "quantity": quantity,
        "unit": "m/s" if quantity == "velocity_mean_m_s" else "g/m3",
        "contaminant_array": None if quantity == "velocity_mean_m_s" else "Tracer",
        "solver_log": "solver.log",
        "log_audit": {
            "fields": ["p"],
            "window": 2,
            "max_initial_residual": 1e-4,
            "max_final_residual": 1e-6,
            "max_global_continuity": None,
        },
        "criteria": {
            "minimum_samples": 3,
            "max_relative_range": 0.04,
            "max_relative_volume_error": 0.001,
            "max_relative_field_change": 0.04,
        },
        "samples": [
            {"solver_time_name": value, "vtk_file": f"sample-{index}.vtu"}
            for index, value in enumerate(times)
        ],
    }


def _fixture_files(tmp_path, values=(1.0, 1.02, 1.03), *, shift_last=0.0,
                   log_initial="1e-6"):
    _write_log(tmp_path / "solver.log", initial=log_initial)
    for index, value in enumerate(values):
        _write_vtu(
            tmp_path / f"sample-{index}.vtu",
            [value],
            contaminant=[value * 2],
            shift=shift_last if index == len(values) - 1 else 0.0,
        )


def test_fixed_mesh_series_reports_distribution_trend_and_threshold_screen(tmp_path):
    pytest.importorskip("vtk")
    data = _spec()
    _fixture_files(tmp_path)

    report = analyze_vtk_time_study(data, base_directory=tmp_path)

    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"
    assert report["engineering_review"] == "READY_FOR_ENGINEERING_REVIEW"
    assert report["all_mesh_geometry_identical"] is True
    assert report["solver_time_semantics"].startswith("OpenFOAM time-directory labels")
    assert [item["field_summary"]["volume_weighted_mean"] for item in report["samples"]] == [
        1.0, 1.02, 1.03
    ]
    assert report["samples"][0]["field_summary"]["volume_weighted_p50"] == 1.0
    summary = report["series_analysis"]
    assert summary["relative_range_over_mean_absolute_value"] == pytest.approx(0.03 / 1.0166666667)
    assert summary["linear_trend_slope_per_solver_time_unit"] == pytest.approx(0.0006)
    assert summary["screening_status"] == "WITHIN_PROJECT_RANGE_SCREEN"
    field_change = report["field_change_analysis"]
    assert field_change["pair_count"] == 2
    assert field_change["maximum_symmetric_relative_l2_change"] == pytest.approx(
        0.02 / 1.01
    )
    assert field_change["screening_status"] == "WITHIN_PROJECT_FIELD_CHANGE_SCREEN"
    assert report["blockers"] == []


def test_spatial_distribution_is_volume_weighted_and_scalar_field_is_supported(tmp_path):
    pytest.importorskip("vtk")
    spec = _spec(quantity="contaminant_mean")
    _write_log(tmp_path / "solver.log")
    for index, _ in enumerate(spec["samples"]):
        _write_vtu(
            tmp_path / f"sample-{index}.vtu",
            [1.0, 3.0],
            contaminant=[1.0, 3.0],
        )
    report = analyze_vtk_time_study(spec, base_directory=tmp_path)
    first = report["samples"][0]["field_summary"]
    assert first["volume_weighted_mean"] == pytest.approx(2.0)
    assert first["volume_weighted_standard_deviation"] == pytest.approx(1.0)
    assert first["volume_weighted_p05"] == 1.0
    assert first["volume_weighted_p50"] == 1.0
    assert first["volume_weighted_p95"] == 3.0
    assert first["cell_count"] == 2


def test_two_selected_times_are_described_but_not_temporally_screened(tmp_path):
    pytest.importorskip("vtk")
    spec = _spec(times=("50", "100"))
    _fixture_files(tmp_path, values=(1.0, 1.0))

    report = analyze_vtk_time_study(spec, base_directory=tmp_path)

    assert report["series_analysis"]["absolute_range"] == 0.0
    assert report["series_analysis"]["screening_status"] == "INSUFFICIENT_SELECTED_TIMES"
    assert report["engineering_review"] == "BLOCKED"
    assert "Selected-time count is below" in report["blockers"][0]


def test_distinct_mesh_geometry_blocks_review_but_keeps_metrics(tmp_path):
    pytest.importorskip("vtk")
    _fixture_files(tmp_path, shift_last=0.001)

    report = analyze_vtk_time_study(_spec(), base_directory=tmp_path)

    assert report["all_mesh_geometry_identical"] is False
    assert report["series_analysis"]["selected_sample_count"] == 3
    assert report["engineering_review"] == "BLOCKED"
    assert any("identical point-and-cell mesh" in value for value in report["blockers"])


def test_field_change_screen_catches_redistribution_hidden_by_constant_mean(tmp_path):
    pytest.importorskip("vtk")
    _write_log(tmp_path / "solver.log")
    spec = _spec()
    spec["room_volume_m3"] = 2.0
    spec["criteria"]["max_relative_range"] = 0.0
    spec["criteria"]["max_relative_field_change"] = 0.1
    for index, velocities in enumerate(([1.0, 3.0], [3.0, 1.0], [1.0, 3.0])):
        _write_vtu(
            tmp_path / f"sample-{index}.vtu",
            velocities,
            contaminant=[1.0, 1.0],
        )

    report = analyze_vtk_time_study(spec, base_directory=tmp_path)

    assert report["series_analysis"]["relative_range_over_mean_absolute_value"] == 0.0
    assert report["series_analysis"]["screening_status"] == "WITHIN_PROJECT_RANGE_SCREEN"
    assert report["field_change_analysis"]["maximum_symmetric_relative_l2_change"] == pytest.approx(
        2.0 / math.sqrt(5.0)
    )
    assert report["field_change_analysis"]["screening_status"] == "ABOVE_PROJECT_FIELD_CHANGE_SCREEN"
    assert "Cell-field change exceeds the project-defined screen" in report["blockers"]
    assert report["engineering_review"] == "BLOCKED"


def test_missing_project_field_change_limit_keeps_review_blocked(tmp_path):
    pytest.importorskip("vtk")
    _fixture_files(tmp_path)
    spec = _spec()
    spec["criteria"]["max_relative_field_change"] = None

    report = analyze_vtk_time_study(spec, base_directory=tmp_path)

    assert report["field_change_analysis"]["screening_status"] == "NO_PROJECT_FIELD_CHANGE_CRITERION"
    assert report["engineering_review"] == "BLOCKED"
    assert "No project-defined maximum relative field change was supplied" in report["blockers"]


def test_failed_solver_log_screen_does_not_hide_field_analysis(tmp_path):
    pytest.importorskip("vtk")
    _fixture_files(tmp_path, log_initial="1e-2")

    report = analyze_vtk_time_study(_spec(), base_directory=tmp_path)

    assert report["series_analysis"]["selected_sample_count"] == 3
    assert report["solver_log_screen"]["status"] == "incomplete_or_failed"
    assert report["engineering_review"] == "BLOCKED"
    assert "Solver-log residual screen did not pass" in report["blockers"]


def test_missing_project_volume_limit_keeps_review_blocked(tmp_path):
    pytest.importorskip("vtk")
    _fixture_files(tmp_path)
    spec = _spec()
    spec["criteria"]["max_relative_volume_error"] = None

    report = analyze_vtk_time_study(spec, base_directory=tmp_path)

    assert report["engineering_review"] == "BLOCKED"
    assert "No project-defined room-volume limit was supplied" in report["blockers"]


def test_time_study_rejects_duplicate_numeric_times_and_noncanonical_numbers():
    data = _spec(times=("1", "1.0", "2"))
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_time_study(data)
    data = _spec(times=("1", "٢", "3"))
    with pytest.raises(ValueError, match="numeric OpenFOAM time label"):
        validate_time_study(data)


@pytest.mark.parametrize("bad_limit", [True, -0.1, math.inf])
def test_time_study_rejects_invalid_user_defined_range_criteria(bad_limit):
    data = _spec()
    data["criteria"]["max_relative_range"] = bad_limit
    with pytest.raises(ValueError, match="max_relative_range"):
        validate_time_study(data)


@pytest.mark.parametrize("bad_limit", [True, -0.1, 2.001, math.inf])
def test_time_study_rejects_invalid_user_defined_field_change_criteria(bad_limit):
    data = _spec()
    data["criteria"]["max_relative_field_change"] = bad_limit
    with pytest.raises(ValueError, match="max_relative_field_change"):
        validate_time_study(data)


def test_time_study_rejects_relative_and_symlinked_input_paths(tmp_path):
    pytest.importorskip("vtk")
    _fixture_files(tmp_path)
    outside = tmp_path.parent / "outside-time-sample.vtu"
    outside.write_bytes((tmp_path / "sample-0.vtu").read_bytes())
    spec = _spec()
    spec["samples"][0]["vtk_file"] = "../outside-time-sample.vtu"
    with pytest.raises(ValueError, match="outside"):
        analyze_vtk_time_study(spec, base_directory=tmp_path)

    link = tmp_path / "sample-link.vtu"
    try:
        link.symlink_to(tmp_path / "sample-0.vtu")
    except (OSError, NotImplementedError):
        pytest.skip("This runner cannot create symbolic links")
    spec = _spec()
    spec["samples"][0]["vtk_file"] = "sample-link.vtu"
    with pytest.raises(ValueError, match="symbolic link"):
        analyze_vtk_time_study(spec, base_directory=tmp_path)


def test_time_study_enforces_aggregate_vtk_size_before_import(tmp_path, monkeypatch):
    _write_log(tmp_path / "solver.log")
    spec = _spec()
    for index in range(3):
        (tmp_path / f"sample-{index}.vtu").write_bytes(b"synthetic placeholder")
    monkeypatch.setattr(time_study_module, "MAX_TOTAL_VTK_BYTES", 1)
    monkeypatch.setattr(
        time_study_module, "import_vtk_case",
        lambda *args, **kwargs: pytest.fail("VTK import must not start over the aggregate size limit"),
    )

    with pytest.raises(ValueError, match="aggregate input limit"):
        analyze_vtk_time_study(spec, base_directory=tmp_path)


def test_cli_writes_report_without_overwriting_any_study_input(tmp_path, monkeypatch):
    pytest.importorskip("vtk")
    spec = _spec()
    _fixture_files(tmp_path)
    study_path = tmp_path / "study.json"
    study_path.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "analysis.json"
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "time-audit", str(study_path), "--output", str(output)
    ])

    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["engineering_review"] == "READY_FOR_ENGINEERING_REVIEW"
    original = study_path.read_bytes()
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "time-audit", str(study_path), "--output", str(study_path)
    ])
    assert main() == 1
    assert study_path.read_bytes() == original


def test_time_study_plot_renders_actual_report_and_never_replaces_existing_png(tmp_path):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    _fixture_files(tmp_path)
    report = analyze_vtk_time_study(_spec(), base_directory=tmp_path)
    plot = tmp_path / "analysis.png"

    result = render_time_study_plot(report, plot)

    content = plot.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", content[16:24])
    assert (width, height) == (1600, 880)
    assert result == {
        "path": str(plot.resolve()),
        "format": "png",
        "sample_count": 3,
        "series": "volume_weighted_mean_with_p05_p95_band",
        "solver_time_semantics": "selected OpenFOAM labels; not physical seconds",
        "scientific_validation": "BLOCKED",
    }
    original = plot.read_bytes()
    with pytest.raises(FileExistsError, match="Refusing to replace"):
        render_time_study_plot(report, plot)
    assert plot.read_bytes() == original
    with pytest.raises(ValueError, match="distinct from its input"):
        render_time_study_plot(report, tmp_path / "study-input.png", protected_inputs=(tmp_path / "study-input.png",))


def test_time_study_plot_cli_adds_plot_provenance_and_guards_inputs(tmp_path, monkeypatch):
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    spec = _spec()
    _fixture_files(tmp_path)
    study_path = tmp_path / "study.json"
    study_path.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "analysis.json"
    plot = tmp_path / "analysis.png"
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "time-audit", str(study_path),
        "--output", str(output), "--plot", str(plot),
    ])

    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["plot"]["path"] == str(plot.resolve())
    assert report["plot"]["sample_count"] == 3
    assert plot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    original_spec = study_path.read_bytes()
    monkeypatch.setattr(sys, "argv", [
        "cleanroomx-cfd-pipeline", "time-audit", str(study_path),
        "--plot", str(study_path),
    ])
    assert main() == 1
    assert study_path.read_bytes() == original_spec


def test_weighted_quantile_uses_cell_volume():
    assert _weighted_quantile([(1.0, 9.0), (3.0, 1.0)], 0.5) == 1.0


def test_symmetric_field_change_handles_zero_fields_without_division_by_zero():
    zero_cells = [{"volume_m3": 1.0, "velocity_m_s": [0.0, 0.0, 0.0]}]
    unchanged = _pairwise_field_change(
        zero_cells,
        zero_cells,
        quantity="velocity_mean_m_s",
        previous_time_name="0",
        current_time_name="1",
    )
    activated = _pairwise_field_change(
        zero_cells,
        [{"volume_m3": 1.0, "velocity_m_s": [1.0, 0.0, 0.0]}],
        quantity="velocity_mean_m_s",
        previous_time_name="0",
        current_time_name="1",
    )

    assert unchanged["volume_weighted_rms_absolute_change"] == 0.0
    assert unchanged["symmetric_relative_l2_change"] == 0.0
    assert activated["volume_weighted_rms_absolute_change"] == 1.0
    assert activated["symmetric_relative_l2_change"] == 2.0
