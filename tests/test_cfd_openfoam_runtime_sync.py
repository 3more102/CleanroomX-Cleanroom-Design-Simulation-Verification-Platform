from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import cleanroomx.cfd_openfoam_runtime_sync as cfd_sync
from cleanroomx.cfd_pipeline_cli import build_parser


CONFIGURATION_HASH = "a" * 64
FOUNDATION_BANNER = (
    "\\ / F ield | OpenFOAM: The Open Source CFD Toolbox\n"
    "Website: https://openfoam.org\n"
    "Version: 10\n"
    "Build : 10-test-build\n"
)


def _field(name: str, field_class: str, dimensions: str, internal: str) -> str:
    return (
        "FoamFile\n{\n"
        f"    class {field_class};\n"
        f"    object {name};\n"
        "}\n"
        f"dimensions [{dimensions}];\n"
        f"internalField nonuniform List<{'vector' if field_class == 'volVectorField' else 'scalar'}>\n"
        "1\n(\n"
        f"{internal}\n"
        ");\n"
        "boundaryField\n{}\n"
    )


def _case(
    tmp_path: Path, *, time_name: str = "100", temperature: bool = True,
    contaminant: bool = False,
) -> Path:
    case = tmp_path / "case-a"
    (case / "system").mkdir(parents=True)
    (case / "constant" / "polyMesh").mkdir(parents=True)
    (case / "0").mkdir()
    time_zero = case / "0"
    (time_zero / "U").write_text("initial U\n", encoding="ascii")
    time = case / time_name
    time.mkdir()
    (time / "U").write_text(
        _field("U", "volVectorField", "0 1 -1 0 0 0 0", "(0 0 -0.5)"),
        encoding="ascii",
    )
    (time / "p").write_text(
        _field("p", "volScalarField", "0 2 -2 0 0 0 0", "1.25"),
        encoding="ascii",
    )
    if temperature:
        (time / "T").write_text(
            _field("T", "volScalarField", "0 0 0 1 0 0 0", "293.15"),
            encoding="ascii",
        )
    if contaminant:
        (time / "C").write_text(
            _field("C", "volScalarField", "0 -3 0 0 0 0 0", "12.0"),
            encoding="ascii",
        )
    return case


def _write_vtk(
    path: Path, *, temperature: bool, contaminant: bool = False,
    generic_t_scalar: bool = False,
) -> None:
    vtk = pytest.importorskip("vtk")
    points = vtk.vtkPoints()
    for point in (
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
    ):
        points.InsertNextPoint(*point)
    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    cell = vtk.vtkHexahedron()
    for index in range(8):
        cell.GetPointIds().SetId(index, index)
    grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())

    velocity = vtk.vtkFloatArray()
    velocity.SetName("U")
    velocity.SetNumberOfComponents(3)
    velocity.InsertNextTuple3(0, 0, -0.5)
    pressure = vtk.vtkFloatArray()
    pressure.SetName("p")
    pressure.InsertNextValue(1.25)
    cell_ids = vtk.vtkIntArray()
    cell_ids.SetName("cellID")
    cell_ids.InsertNextValue(0)
    for array in (velocity, pressure, cell_ids):
        grid.GetCellData().AddArray(array)
    if temperature or generic_t_scalar:
        temperature_array = vtk.vtkFloatArray()
        temperature_array.SetName("T")
        temperature_array.InsertNextValue(293.15 if temperature else 0.25)
        grid.GetCellData().AddArray(temperature_array)
    if contaminant:
        concentration = vtk.vtkFloatArray()
        concentration.SetName("C")
        concentration.InsertNextValue(12.0)
        grid.GetCellData().AddArray(concentration)
    writer = vtk.vtkUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetFileTypeToASCII()
    writer.SetInputData(grid)
    assert writer.Write() == 1


def _configured_sync(tmp_path, case: Path, monkeypatch, *, output: Path | None = None, **kwargs):
    pytest.importorskip(
        "vtk",
        reason="OpenFOAM runtime synchronization tests require the optional CFD VTK dependency",
    )
    executable = tmp_path / "foamToVTK"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
    executable.chmod(0o755)
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    monkeypatch.setattr(cfd_sync.shutil, "which", lambda _name: str(executable))
    output = output or (tmp_path / "sync")
    options = {
        "simulation_id": "simulation-001",
        "configuration_hash": CONFIGURATION_HASH,
        "expected_build": "10-test-build",
        "poll_interval_seconds": 0.1,
        "optional_fields": ("T",),
    }
    options.update(kwargs)
    return cfd_sync.OpenFOAMResultSynchronizer(case, output, **options)


def _fake_foam_to_vtk(
    monkeypatch, *, expected_temperature=True, expected_contaminant=False,
    expected_generic_t_scalar=False, calls=None
):
    calls = calls if calls is not None else []

    def fake_run(command, *, cwd, **_kwargs):
        calls.append(tuple(command))
        time_name = command[command.index("-time") + 1]
        vtk_dir = cwd / "VTK"
        vtk_dir.mkdir()
        _write_vtk(
            vtk_dir / f"{cwd.name}_{time_name}.vtk",
            temperature=expected_temperature,
            contaminant=expected_contaminant,
            generic_t_scalar=expected_generic_t_scalar,
        )
        selected_fields = command[command.index("-fields") + 1]
        if "phi" in selected_fields and "-surfaceFields" in command:
            surface_dir = vtk_dir / "surfaceFields"
            surface_dir.mkdir()
            (surface_dir / f"surfaceFields_{time_name}.vtk").write_text(
                "surface flux fixture\n", encoding="ascii"
            )
        return SimpleNamespace(
            returncode=0,
            stdout=(FOUNDATION_BANNER + f"Time: {time_name}\nEnd\n").encode(),
        )

    monkeypatch.setattr(cfd_sync.subprocess, "run", fake_run)
    return calls


def test_sync_waits_for_stable_result_and_imports_real_vtk_fields_once(tmp_path, monkeypatch):
    case = _case(tmp_path, contaminant=True)
    calls = _fake_foam_to_vtk(monkeypatch, expected_contaminant=True)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, contaminant_field="C")

    assert synchronizer.poll_once()["imported_times"] == []
    result = synchronizer.poll_once()

    assert result["imported_times"] == ["100"]
    assert len(calls) == 1
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    record = manifest["records"]["100"]
    assert manifest["scientific_validation"] == "BLOCKED"
    assert record["fields"]["U"]["units"] == "m/s"
    assert record["fields"]["p"]["units"] == "m^2/s^2 (kinematic pressure)"
    assert record["fields"]["T"]["units"] == "K"
    assert record["native_vtk_parity"]["U"]["status"] == "PASS"
    assert record["native_vtk_parity"]["p"]["status"] == "PASS"
    assert record["native_vtk_parity"]["T"]["status"] == "PASS"
    assert record["fields"]["C"]["units"] == "OpenFOAM dimensions [0 -3 0 0 0 0 0]"
    assert record["native_vtk_parity"]["C"]["status"] == "PASS"
    assert record["cleanroomx_analysis_import"]["status"] == "PASS"
    assert record["cleanroomx_analysis_import"]["has_contaminant_field"] is True
    assert record["cleanroomx_analysis_import"]["contaminant_field"] == "C"
    assert record["cleanroomx_analysis_import"]["has_temperature_field"] is True
    assert record["cleanroomx_analysis_import"]["temperature_field"]["units"] == "K"
    assert record["cell_count"] == 1
    assert all((tmp_path / "sync" / asset["path"]).is_file() for asset in record["assets"])
    assert synchronizer.poll_once()["imported_times"] == []
    assert len(calls) == 1


def test_sync_selects_phi_for_surface_field_export(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    (case / "100" / "phi").write_text(
        "FoamFile { class surfaceScalarField; object phi; }\n"
        "dimensions [0 3 -1 0 0 0 0];\n",
        encoding="ascii",
    )
    calls = _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    monkeypatch.setattr(
        cfd_sync,
        "audit_openfoam_vtk_surface_flux",
        lambda *_args: {"status": "PASS", "field": "phi"},
    )
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())

    synchronizer.poll_once()
    result = synchronizer.poll_once()

    assert result["imported_times"] == ["100"]
    fields_argument = calls[0][calls[0].index("-fields") + 1]
    assert "phi" in fields_argument
    assert "-surfaceFields" in calls[0]
    record = json.loads(
        (tmp_path / "sync" / "sync_manifest.json").read_text(encoding="utf-8")
    )["records"]["100"]
    assert record["fields"]["phi"]["units"] == "m^3/s"
    assert record["surface_phi_parity"]["status"] == "PASS"



def test_sync_can_disable_optional_surface_flux_capture(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    (case / "100" / "phi").write_text("unused unsupported surface flux fixture\n", encoding="ascii")
    calls = _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    synchronizer = _configured_sync(
        tmp_path,
        case,
        monkeypatch,
        optional_fields=(),
        include_surface_flux=False,
    )

    synchronizer.poll_once()
    result = synchronizer.poll_once()

    assert result["imported_times"] == ["100"]
    fields_argument = calls[0][calls[0].index("-fields") + 1]
    assert "phi" not in fields_argument
    assert "-surfaceFields" not in calls[0]
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    record = manifest["records"]["100"]
    assert manifest["include_surface_flux"] is False
    assert "phi" not in record["fields"]

    with pytest.raises(ValueError, match="does not match this simulation/configuration"):
        _configured_sync(
            tmp_path,
            case,
            monkeypatch,
            output=tmp_path / "sync",
            optional_fields=(),
            include_surface_flux=True,
        )


def test_sync_resume_reuses_hash_bound_record_without_duplicate_export(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    calls = _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    output = tmp_path / "sync"
    first = _configured_sync(
        tmp_path, case, monkeypatch, output=output, optional_fields=()
    )
    first.poll_once()
    first.poll_once()

    resumed = _configured_sync(
        tmp_path, case, monkeypatch, output=output, optional_fields=()
    )
    assert resumed.poll_once()["imported_times"] == []
    assert len(calls) == 1
    assert resumed.summary()["times"] == ["100"]


def test_sync_refuses_old_manifest_schema_without_relabeling_snapshots(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    output = tmp_path / "sync"
    first = _configured_sync(tmp_path, case, monkeypatch, output=output, optional_fields=())
    first.poll_once()
    manifest_path = output / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "cleanroomx.openfoam-result-sync.v1"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match this simulation/configuration"):
        _configured_sync(tmp_path, case, monkeypatch, output=output, optional_fields=())


def test_sync_does_not_publish_a_field_while_its_signature_changes(tmp_path, monkeypatch):
    case = _case(tmp_path)
    calls = _fake_foam_to_vtk(monkeypatch)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch)
    assert synchronizer.poll_once()["imported_times"] == []
    with (case / "100" / "U").open("a", encoding="ascii") as stream:
        stream.write("\n// completed write changed the signature\n")
    assert synchronizer.poll_once()["imported_times"] == []
    assert synchronizer.poll_once()["imported_times"] == ["100"]
    assert len(calls) == 1


def test_sync_rejects_changed_source_and_preserves_previously_imported_result(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())
    synchronizer.poll_once()
    synchronizer.poll_once()
    dataset = tmp_path / "sync" / "results" / "time_100" / "VTK" / "case-a_100.vtk"
    original_digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    with (case / "100" / "p").open("a", encoding="ascii") as stream:
        stream.write("\n// changed after import\n")

    with pytest.raises(ValueError, match="Already synchronized"):
        synchronizer.poll_once()
    assert hashlib.sha256(dataset.read_bytes()).hexdigest() == original_digest
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert manifest["records"]["100"]["import_status"] == "PASS_DIAGNOSTIC_ONLY"
    assert manifest["errors"][-1]["status"] == "not_imported"


def test_sync_resume_rejects_corrupted_imported_dataset(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    output = tmp_path / "sync"
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, output=output, optional_fields=())
    synchronizer.poll_once()
    synchronizer.poll_once()
    dataset = output / "results" / "time_100" / "VTK" / "case-a_100.vtk"
    dataset.write_text("corrupted\n", encoding="ascii")

    with pytest.raises(ValueError, match="corrupt or outdated"):
        _configured_sync(tmp_path, case, monkeypatch, output=output, optional_fields=())


def test_sync_records_incomplete_field_and_never_accepts_it(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    (case / "100" / "p").write_text(
        _field("p", "volScalarField", "0 1 -1 0 0 0 0", "1.25"),
        encoding="ascii",
    )
    calls = _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())
    for _ in range(6):
        synchronizer.poll_once()
    report = synchronizer.finish(solver_returncode=1)

    assert report["status"] == "no_results_available"
    assert report["record_count"] == 0
    assert not calls
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert len(manifest["errors"]) == 3
    assert "kinematic-pressure dimensions" in manifest["errors"][0]["message"]


def test_dimensionless_scalar_transport_t_is_not_classified_as_temperature(
    tmp_path, monkeypatch
):
    case = _case(tmp_path, temperature=False)
    (case / "100" / "T").write_text(
        _field("T", "volScalarField", "0 0 0 0 0 0 0", "0.25"),
        encoding="ascii",
    )
    _fake_foam_to_vtk(
        monkeypatch, expected_temperature=False, expected_generic_t_scalar=True
    )
    synchronizer = _configured_sync(tmp_path, case, monkeypatch)
    synchronizer.poll_once()
    synchronizer.poll_once()
    solver_log = case / "scalarTransportFoam.log"
    solver_log.write_text("End\n", encoding="ascii")
    report = synchronizer.finish(solver_returncode=0, solver_log=solver_log)

    assert report["status"] == "results_synced"
    record = json.loads(
        (tmp_path / "sync" / "sync_manifest.json").read_text()
    )["records"]["100"]
    assert record["fields"]["T"]["units"] == "OpenFOAM dimensions [0 0 0 0 0 0 0]"
    assert record["cleanroomx_analysis_import"]["has_temperature_field"] is False
    assert record["cleanroomx_analysis_import"]["has_contaminant_field"] is False
    assert record["native_vtk_parity"]["T"]["status"] == "PASS"


def test_u_only_scalar_solver_sync_maps_dimensionless_tracer_explicitly(
    tmp_path, monkeypatch
):
    case = _case(tmp_path, temperature=False)
    (case / "100" / "p").unlink()
    (case / "100" / "T").write_text(
        _field("T", "volScalarField", "0 0 0 0 0 0 0", "0.25"),
        encoding="ascii",
    )
    calls = _fake_foam_to_vtk(
        monkeypatch, expected_temperature=False, expected_generic_t_scalar=True
    )
    field_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"T": {"semantic": "normalized_tracer", "units": "1"}},
    }
    synchronizer = _configured_sync(
        tmp_path,
        case,
        monkeypatch,
        required_fields=("U",),
        optional_fields=("T",),
        field_map=field_map,
    )

    synchronizer.poll_once()
    result = synchronizer.poll_once()

    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    record = manifest["records"]["100"]
    assert result["imported_times"] == ["100"]
    assert manifest["required_fields"] == ["U"]
    assert manifest["field_map"] == field_map
    assert "p" not in record["fields"]
    assert record["fields"]["T"]["dimensions"] == "[0 0 0 0 0 0 0]"
    assert record["native_vtk_parity"]["U"]["status"] == "PASS"
    assert record["native_vtk_parity"]["T"]["status"] == "PASS"
    assert record["cleanroomx_analysis_import"]["has_temperature_field"] is False
    assert record["cleanroomx_analysis_import"]["has_contaminant_field"] is False
    assert record["cleanroomx_analysis_import"]["field_data_names"] == ["normalized_tracer"]
    assert len(calls) == 1


def test_scalar_sync_waits_for_both_u_and_t_before_export(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    calls = _fake_foam_to_vtk(
        monkeypatch, expected_temperature=False, expected_generic_t_scalar=True
    )
    field_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"T": {"semantic": "normalized_tracer", "units": "1"}},
    }
    synchronizer = _configured_sync(
        tmp_path,
        case,
        monkeypatch,
        required_fields=("U", "T"),
        optional_fields=(),
        field_map=field_map,
    )
    assert synchronizer.poll_once()["imported_times"] == []
    assert synchronizer.poll_once()["imported_times"] == []
    assert calls == []

    (case / "100" / "T").write_text(
        _field("T", "volScalarField", "0 0 0 0 0 0 0", "0.25"),
        encoding="ascii",
    )
    synchronizer.poll_once()
    result = synchronizer.poll_once()
    assert result["imported_times"] == ["100"]
    assert len(calls) == 1


def test_u_only_sync_rejects_field_map_for_unselected_source_field(
    tmp_path, monkeypatch
):
    case = _case(tmp_path, temperature=False)
    field_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"T": {"semantic": "normalized_tracer", "units": "1"}},
    }
    with pytest.raises(ValueError, match="selected as required or optional"):
        _configured_sync(
            tmp_path,
            case,
            monkeypatch,
            required_fields=("U",),
            optional_fields=(),
            field_map=field_map,
        )


def test_kelvin_temperature_cannot_receive_a_second_field_map_semantic(
    tmp_path, monkeypatch
):
    case = _case(tmp_path, temperature=True)
    _fake_foam_to_vtk(monkeypatch, expected_temperature=True)
    field_map = {
        "schema_version": "cleanroomx.cfd-vtk-field-map.v1",
        "fields": {"T": {"semantic": "normalized_tracer", "units": "1"}},
    }
    synchronizer = _configured_sync(
        tmp_path, case, monkeypatch, optional_fields=("T",), field_map=field_map
    )

    synchronizer.poll_once()
    synchronizer.poll_once()

    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert manifest["records"] == {}
    assert "Kelvin T cannot also be assigned" in manifest["errors"][-1]["message"]


def test_explicitly_selected_dimensionless_t_is_not_also_classified_as_temperature(
    tmp_path, monkeypatch
):
    case = _case(tmp_path, temperature=False)
    (case / "100" / "T").write_text(
        _field("T", "volScalarField", "0 0 0 0 0 0 0", "0.25"),
        encoding="ascii",
    )
    _fake_foam_to_vtk(
        monkeypatch, expected_temperature=False, expected_generic_t_scalar=True
    )
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, contaminant_field="T")
    synchronizer.poll_once()
    synchronizer.poll_once()
    solver_log = case / "scalarTransportFoam.log"
    solver_log.write_text("End\n", encoding="ascii")
    report = synchronizer.finish(solver_returncode=0, solver_log=solver_log)

    assert report["status"] == "results_synced"
    record = json.loads(
        (tmp_path / "sync" / "sync_manifest.json").read_text()
    )["records"]["100"]
    assert record["cleanroomx_analysis_import"]["has_temperature_field"] is False
    assert record["cleanroomx_analysis_import"]["has_contaminant_field"] is True
    assert record["cleanroomx_analysis_import"]["contaminant_field"] == "T"


@pytest.mark.parametrize(
    ("name", "dimensions", "units"),
    [
        ("k", "0 2 -2 0 0 0 0", "m^2/s^2"),
        ("epsilon", "0 2 -3 0 0 0 0", "m^2/s^3"),
        ("omega", "0 0 -1 0 0 0 0", "1/s"),
        ("nut", "0 2 -1 0 0 0 0", "m^2/s"),
    ],
)
def test_standard_turbulence_fields_require_their_documented_dimensions(
    tmp_path, name, dimensions, units
):
    path = tmp_path / name
    path.write_text(
        _field(name, "volScalarField", dimensions, "1.0"), encoding="ascii"
    )

    metadata = cfd_sync._field_metadata(path, name)

    assert metadata["dimensions"] == f"[{dimensions}]"
    assert metadata["units"] == units
    path.write_text(
        _field(name, "volScalarField", "0 0 0 0 0 0 0", "1.0"),
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="standard dimensions|turbulent|dissipation|kelvin"):
        cfd_sync._field_metadata(path, name)


def test_sync_rejects_a_missing_explicit_contaminant_field(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    calls = _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, contaminant_field="C")
    for _ in range(7):
        synchronizer.poll_once()
    report = synchronizer.finish(solver_returncode=1)

    assert report["status"] == "no_results_available"
    assert report["record_count"] == 0
    assert len(calls) == 3
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert any(
        "Configured contaminant array 'C' is missing" in error["message"]
        for error in manifest["errors"]
    )


def test_sync_requires_target_release_and_rejects_unsupported_fields(tmp_path, monkeypatch):
    case = _case(tmp_path)
    executable = tmp_path / "foamToVTK"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
    executable.chmod(0o755)
    monkeypatch.setattr(cfd_sync.shutil, "which", lambda _name: str(executable))
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "2312")
    with pytest.raises(RuntimeError, match="Foundation v10"):
        cfd_sync.OpenFOAMResultSynchronizer(
            case, tmp_path / "sync", simulation_id="simulation-001",
            configuration_hash=CONFIGURATION_HASH,
        )

    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    with pytest.raises(ValueError, match="safe OpenFOAM field names"):
        cfd_sync.OpenFOAMResultSynchronizer(
            case, tmp_path / "sync2", simulation_id="simulation-001",
            configuration_hash=CONFIGURATION_HASH, optional_fields=("bad-name",),
        )


def test_sync_command_runner_keeps_solver_log_and_drains_final_snapshot(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    _fake_foam_to_vtk(monkeypatch, expected_temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())
    synchronizer.record_monitor_error(ValueError("transient polling failure"))

    class FakeProcess:
        def __init__(self, command, *, cwd, stdout, stderr):
            assert command == ["simpleFoam"]
            assert cwd == case
            assert stderr is cfd_sync.subprocess.STDOUT
            stdout.write((FOUNDATION_BANNER + "Time = 101\nEnd\n").encode())

        def poll(self):
            return 0

        def wait(self, **_kwargs):
            return 0

    monkeypatch.setattr(cfd_sync.subprocess, "Popen", FakeProcess)
    log_path = case / "simpleFoam.log"
    returncode = cfd_sync.run_solver_with_sync(
        ["simpleFoam"], cwd=case, log_path=log_path,
        timeout_seconds=60, synchronizer=synchronizer,
    )
    result = synchronizer.finish(solver_returncode=returncode, solver_log=log_path)

    assert returncode == 0
    assert result["status"] == "results_synced"
    assert log_path.read_text(encoding="utf-8").endswith("End\n")
    assert result["times"] == ["100"]
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert manifest["errors"][0]["status"] == "recovered_after_retry"


def test_sync_watcher_classifies_fatal_log_as_incomplete(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())
    log_path = case / "simpleFoam.log"
    log_path.write_text("FOAM FATAL ERROR: solver diverged\n", encoding="ascii")

    report = synchronizer.watch(solver_log=log_path)

    assert report["status"] == "incomplete"
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert manifest["solver_log_status"] == "fatal_error_detected"
    assert manifest["solver_returncode"] is None


def test_sync_watcher_journals_and_survives_polling_errors(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())
    log_path = case / "simpleFoam.log"
    log_path.write_text("End\n", encoding="ascii")

    def broken_poll():
        raise ValueError("temporary field scan failure")

    monkeypatch.setattr(synchronizer, "poll_once", broken_poll)
    report = synchronizer.watch(solver_log=log_path)

    assert report["status"] == "no_results_available"
    assert report["error_count"] == 1
    manifest = json.loads((tmp_path / "sync" / "sync_manifest.json").read_text())
    assert manifest["errors"][0]["status"] == "monitor_error"


def test_solver_spawn_failure_is_recorded_and_returns_a_failure_code(tmp_path, monkeypatch):
    case = _case(tmp_path, temperature=False)
    synchronizer = _configured_sync(tmp_path, case, monkeypatch, optional_fields=())

    def fail_spawn(*_args, **_kwargs):
        raise FileNotFoundError("simpleFoam disappeared from PATH")

    monkeypatch.setattr(cfd_sync.subprocess, "Popen", fail_spawn)
    log_path = case / "simpleFoam.log"
    returncode = cfd_sync.run_solver_with_sync(
        ["simpleFoam"], cwd=case, log_path=log_path,
        timeout_seconds=60, synchronizer=synchronizer,
    )
    result = synchronizer.finish(solver_returncode=returncode, solver_log=log_path)

    assert returncode == 127
    assert result["status"] == "no_results_available"
    assert result["error_count"] == 1
    assert log_path.is_file()


def test_cli_exposes_sync_resource_limits_for_runner_and_watcher():
    parser = build_parser()
    runner = parser.parse_args([
        "run", "cases", "--sync-results", "outputs", "--sync-timeout-seconds", "90",
        "--sync-max-field-mib", "8", "--sync-max-snapshot-mib", "16",
        "--sync-max-output-mib", "64", "--sync-max-retries", "2",
    ])
    watcher = parser.parse_args([
        "sync-case", "case", "outputs", "--timeout-seconds", "90", "--max-field-mib", "8",
        "--max-snapshot-mib", "16", "--max-output-mib", "64", "--max-retries", "2",
    ])

    assert (runner.sync_timeout_seconds, runner.sync_max_field_mib,
            runner.sync_max_snapshot_mib, runner.sync_max_output_mib,
            runner.sync_max_retries) == (90, 8, 16, 64, 2)
    assert (watcher.timeout_seconds, watcher.max_field_mib,
            watcher.max_snapshot_mib, watcher.max_output_mib,
            watcher.max_retries) == (90, 8, 16, 64, 2)


def test_import_vtk_cli_does_not_infer_contamination_from_t_array_name():
    parser = build_parser()
    defaults = parser.parse_args([
        "import-vtk", "study.json", "--case-1", "c1.vtu", "--case-2", "c2.vtu",
        "--case-3", "c3.vtu", "--solver-name", "OpenFOAM", "--output", "out.json",
    ])
    temperature = parser.parse_args([
        "import-vtk", "study.json", "--case-1", "c1.vtu", "--case-2", "c2.vtu",
        "--case-3", "c3.vtu", "--solver-name", "OpenFOAM", "--output", "out.json",
        "--temperature-array", "T", "--temperature-units", "K",
    ])

    assert defaults.contaminant_array is None
    assert defaults.temperature_array is None
    assert temperature.temperature_array == "T"
    assert temperature.temperature_units == "K"
