import json
from pathlib import Path
import shutil

import pytest

from cleanroomx.cfd_sync import SyncError, synchronize_openfoam_vtk_once
from cleanroomx.cfd_pipeline_cli import build_parser


def _make_grid(vtk, velocity, contaminant, pressure=2.5):
    points = vtk.vtkPoints()
    for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
        points.InsertNextPoint(*point)
    tetra = vtk.vtkTetra()
    for index in range(4):
        tetra.GetPointIds().SetId(index, index)
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    grid.InsertNextCell(tetra.GetCellType(), tetra.GetPointIds())
    velocity_array = vtk.vtkDoubleArray()
    velocity_array.SetName("U")
    velocity_array.SetNumberOfComponents(3)
    velocity_array.InsertNextTuple3(*velocity)
    scalar_array = vtk.vtkDoubleArray()
    scalar_array.SetName("T")
    scalar_array.InsertNextValue(contaminant)
    pressure_array = vtk.vtkDoubleArray()
    pressure_array.SetName("p")
    pressure_array.InsertNextValue(pressure)
    grid.GetCellData().AddArray(velocity_array)
    grid.GetCellData().AddArray(scalar_array)
    grid.GetCellData().AddArray(pressure_array)
    return grid


def _write_vtu(path: Path, velocity=(0.25, -0.5, 1.0), contaminant=0.125, pressure=2.5):
    vtk = pytest.importorskip("vtk")
    grid = _make_grid(vtk, velocity, contaminant, pressure)
    writer = vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    writer.SetDataModeToAscii()
    assert writer.Write() == 1


def _write_legacy_vtk(path: Path, velocity=(0.25, -0.5, 1.0), contaminant=0.125, pressure=2.5):
    vtk = pytest.importorskip("vtk")
    grid = _make_grid(vtk, velocity, contaminant, pressure)
    writer = vtk.vtkUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    writer.SetFileTypeToASCII()
    assert writer.Write() == 1


def _case(tmp_path, *, simulation_id="run-1"):
    source = tmp_path / "VTK"
    source_time = source / "100"
    source_time.mkdir(parents=True)
    dataset = source_time / "internal.vtu"
    _write_vtu(dataset)
    configuration = tmp_path / "manifest.json"
    configuration.write_text('{"case":"cleanroom-A"}', encoding="utf-8")
    output = tmp_path / "results"
    kwargs = {
        "simulation_id": simulation_id,
        "configuration_file": configuration,
        "contaminant_array": "T",
        "stable_seconds": 0.0,
    }
    return source, dataset, configuration, output, kwargs


def test_sync_waits_for_stable_vtk_then_imports_atomically_and_resumes(tmp_path):
    source, dataset, configuration, output, kwargs = _case(tmp_path)
    first = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert first["counts"] == {"pending_stability": 1}
    assert not (output / "snapshots").exists()

    second = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert second["counts"]["imported"] == 1
    item = second["imported"][0]
    snapshot_path = output / item["snapshot_relative_path"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["simulation_id"] == "run-1"
    assert snapshot["solver_time"] == "100"
    assert snapshot["scientific_validation"] == "BLOCKED"
    assert snapshot["fields"]["mesh_cells"] == 1
    assert snapshot["fields"]["cells"][0]["velocity_m_s"] == [0.25, -0.5, 1.0]
    assert snapshot["fields"]["cells"][0]["contaminant_concentration"] == pytest.approx(0.125)
    saved_bytes = snapshot_path.read_bytes()

    resumed = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert resumed["counts"]["imported"] == 1
    assert snapshot_path.read_bytes() == saved_bytes


def test_sync_discovers_foam_to_vtk_case_time_filenames(tmp_path):
    source = tmp_path / "VTK"
    source.mkdir()
    _write_legacy_vtk(source / "coarse_50.vtk")
    configuration = tmp_path / "manifest.json"
    configuration.write_text('{"case":"coarse"}', encoding="utf-8")
    output = tmp_path / "results"
    kwargs = {
        "simulation_id": "foam-run-50",
        "configuration_file": configuration,
        "stable_seconds": 0,
    }

    synchronize_openfoam_vtk_once(source, output, **kwargs)
    report = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert report["counts"]["imported"] == 1
    record = report["imported"][0]
    assert record["relative_path"] == "coarse_50.vtk"
    assert record["solver_time"] == "50"
    snapshot = json.loads((output / record["snapshot_relative_path"]).read_text(encoding="utf-8"))
    assert snapshot["case_id"] == "coarse"


def test_sync_imports_explicitly_mapped_pressure_and_tracks_absent_fields(tmp_path):
    source, _, _, output, kwargs = _case(tmp_path)
    field_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {
            "p": {"semantic": "kinematic_pressure", "units": "m^2/s^2"},
            "k": {"semantic": "turbulent_kinetic_energy", "units": "m^2/s^2"},
        },
    }
    synchronize_openfoam_vtk_once(source, output, field_map=field_map, **kwargs)
    report = synchronize_openfoam_vtk_once(source, output, field_map=field_map, **kwargs)
    item = report["imported"][0]
    snapshot = json.loads((output / item["snapshot_relative_path"]).read_text(encoding="utf-8"))
    fields = snapshot["fields"]
    assert snapshot["field_map_sha256"] == report["field_map_sha256"]
    assert fields["field_map_schema"] == "cleanroomx.cfd-vtk-field-map.v1"
    pressure = fields["field_data"]["kinematic_pressure"]
    assert pressure["array_name"] == "p"
    assert pressure["units"] == "m^2/s^2"
    assert pressure["units_source"] == "explicit_caller_field_map"
    assert pressure["values"] == [2.5]
    assert pressure["summary"] == {"minimum": [2.5], "maximum": [2.5], "mean": [2.5]}
    assert fields["unavailable_fields"] == [{
        "array_name": "k",
        "semantic": "turbulent_kinetic_energy",
        "units": "m^2/s^2",
        "reason": "not_present_in_vtk_cell_data",
    }]
    assert item["field_data_names"] == ["kinematic_pressure"]
    assert item["unavailable_field_names"] == ["turbulent_kinetic_energy"]


def test_sync_rejects_field_map_changes_when_resuming(tmp_path):
    source, _, _, output, kwargs = _case(tmp_path)
    base_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"p": {"semantic": "kinematic_pressure", "units": "m^2/s^2"}},
    }
    changed_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"p": {"semantic": "pressure_pa", "units": "Pa"}},
    }
    synchronize_openfoam_vtk_once(source, output, field_map=base_map, **kwargs)
    synchronize_openfoam_vtk_once(source, output, field_map=base_map, **kwargs)
    with pytest.raises(SyncError, match="different simulation or configuration"):
        synchronize_openfoam_vtk_once(source, output, field_map=changed_map, **kwargs)


def test_sync_rejects_nonfinite_mapped_values_without_publishing_snapshot(tmp_path):
    source, dataset, _, output, kwargs = _case(tmp_path)
    _write_vtu(dataset, pressure=float("nan"))
    field_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"p": {"semantic": "kinematic_pressure", "units": "m^2/s^2"}},
    }
    synchronize_openfoam_vtk_once(source, output, field_map=field_map, **kwargs)
    report = synchronize_openfoam_vtk_once(source, output, field_map=field_map, **kwargs)
    assert report["counts"] == {"waiting_for_valid_export": 1}
    assert not (output / "snapshots").exists()


def test_sync_cli_does_not_assume_vtk_array_t_is_contaminant():
    args = build_parser().parse_args([
        "sync-vtk", "VTK", "results", "--simulation-id", "run-1",
        "--configuration-file", "manifest.json", "--once",
    ])
    assert args.contaminant_array is None


@pytest.mark.parametrize("field_map", [
    {"schema_version": "wrong", "fields": {}},
    {"schema_version": "cleanroomx.cfd-vtk-field-map.v1", "fields": {
        "p": {"semantic": "kinematic_pressure", "units": "m^2/s^2"},
        "k": {"semantic": "kinematic_pressure", "units": "m^2/s^2"},
    }},
    {"schema_version": "cleanroomx.cfd-vtk-field-map.v1", "fields": {
        "p": {"semantic": "kinematic_pressure", "units": " "},
    }},
])
def test_sync_rejects_invalid_explicit_field_maps_before_creating_store(tmp_path, field_map):
    source, _, _, output, kwargs = _case(tmp_path)
    with pytest.raises(ValueError, match="field_map"):
        synchronize_openfoam_vtk_once(source, output, field_map=field_map, **kwargs)
    assert not output.exists()


def test_sync_rejects_a_configuration_change_in_an_existing_store(tmp_path):
    source, _, configuration, output, kwargs = _case(tmp_path)
    synchronize_openfoam_vtk_once(source, output, **kwargs)
    synchronize_openfoam_vtk_once(source, output, **kwargs)
    configuration.write_text('{"case":"cleanroom-B"}', encoding="utf-8")
    with pytest.raises(SyncError, match="different simulation or configuration"):
        synchronize_openfoam_vtk_once(source, output, **kwargs)


def test_sync_preserves_an_accepted_snapshot_when_source_changes(tmp_path):
    source, dataset, _, output, kwargs = _case(tmp_path)
    synchronize_openfoam_vtk_once(source, output, **kwargs)
    report = synchronize_openfoam_vtk_once(source, output, **kwargs)
    snapshot_path = output / report["imported"][0]["snapshot_relative_path"]
    saved_bytes = snapshot_path.read_bytes()
    _write_vtu(dataset, velocity=(9.0, 8.0, 7.0))

    with pytest.raises(SyncError, match="changed after import"):
        synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert snapshot_path.read_bytes() == saved_bytes
    state = json.loads((output / "sync-state.json").read_text(encoding="utf-8"))
    record = state["records"]["100/internal.vtu"]
    assert record["status"] == "stale_changed_after_import"


def test_sync_detects_corruption_of_a_saved_snapshot(tmp_path):
    source, _, _, output, kwargs = _case(tmp_path)
    synchronize_openfoam_vtk_once(source, output, **kwargs)
    report = synchronize_openfoam_vtk_once(source, output, **kwargs)
    snapshot_path = output / report["imported"][0]["snapshot_relative_path"]
    snapshot_path.write_bytes(snapshot_path.read_bytes()[:-2] + b"xx")

    with pytest.raises(SyncError, match="integrity check failed"):
        synchronize_openfoam_vtk_once(source, output, **kwargs)
    state = json.loads((output / "sync-state.json").read_text(encoding="utf-8"))
    assert state["records"]["100/internal.vtu"]["status"] == "snapshot_integrity_failure"


def test_sync_retries_a_parse_failure_after_the_writer_completes(tmp_path):
    source, dataset, _, output, kwargs = _case(tmp_path)
    dataset.write_bytes(b"incomplete VTK output")
    synchronize_openfoam_vtk_once(source, output, **kwargs)
    failed_parse = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert failed_parse["counts"]["waiting_for_valid_export"] == 1
    assert not (output / "snapshots").exists()

    _write_vtu(dataset)
    pending = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert pending["counts"]["pending_stability"] == 1
    completed = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert completed["counts"]["imported"] == 1


def test_sync_deduplicates_byte_identical_time_exports(tmp_path):
    source, dataset, _, output, kwargs = _case(tmp_path)
    duplicate = dataset.parent / "region0" / "internal.vtu"
    duplicate.parent.mkdir()
    shutil.copyfile(dataset, duplicate)
    synchronize_openfoam_vtk_once(source, output, **kwargs)
    report = synchronize_openfoam_vtk_once(source, output, **kwargs)
    assert report["counts"] == {"imported": 1, "duplicate": 1}
    state = json.loads((output / "sync-state.json").read_text(encoding="utf-8"))
    duplicate_records = [record for record in state["records"].values() if record["status"] == "duplicate"]
    assert duplicate_records[0]["duplicate_of"] == "100/internal.vtu"


def test_sync_enforces_source_file_limits_before_import(tmp_path):
    source, _, _, output, kwargs = _case(tmp_path)
    with pytest.raises(SyncError, match="file limit"):
        synchronize_openfoam_vtk_once(source, output, max_file_bytes=1, **kwargs)
