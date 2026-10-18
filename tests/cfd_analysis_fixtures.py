"""Deterministic SYNTHETIC parser/analysis fixtures. No OpenFOAM execution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_vtk(path, *, factor=1.0, thermal=True, kelvin=True):
    import vtk
    points = vtk.vtkPoints()
    grid = vtk.vtkUnstructuredGrid()
    # Two adjacent hexahedra with volumes 1 and 2 m3.
    for start, length in ((0, 1), (1, 2)):
        offset = points.GetNumberOfPoints()
        for x, y, z in ((0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)):
            points.InsertNextPoint(start + length*x, y, z)
        cell = vtk.vtkHexahedron()
        for i in range(8):
            cell.GetPointIds().SetId(i, offset+i)
        grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    grid.SetPoints(points)
    for name, values, components in (
        ("U", [(3*factor, 4*factor, 0), (0, 0, 10*factor)], 3),
        ("p", [2, 8], 1), ("cellID", [0, 1], 1),
        *(([("T", [300, 330] if kelvin else [0.2, 0.8], 1)]) if thermal else []),
    ):
        array = vtk.vtkDoubleArray()
        array.SetName(name)
        array.SetNumberOfComponents(components)
        for value in values:
            array.InsertNextTuple(value if components == 3 else (value,))
        grid.GetCellData().AddArray(array)
    writer = vtk.vtkUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    writer.SetFileTypeToASCII()
    assert writer.Write() == 1


def write_sync_store(root: Path, run="SYNTHETIC-run-a", *, times=("2", "10"), thermal=True, kelvin=True, factor=1.0,
                     case_id="configuration_1"):
    case = root / run / case_id
    case.mkdir(parents=True)
    records = {}
    for time in times:
        output = case / "results" / f"time_{time}"
        (output / "VTK").mkdir(parents=True)
        vtk_path = output / "VTK" / f"{Path(case_id).name}_{time}.vtk"
        write_vtk(vtk_path, factor=factor*float(time), thermal=thermal, kelvin=kelvin)
        log = output / "foamToVTK.log"
        log.write_text("SYNTHETIC exporter fixture\nEnd\n")
        fields = {"U": {"components": 3, "dimensions": "[0 1 -1 0 0 0 0]", "units": "m/s"},
                  "p": {"components": 1, "dimensions": "[0 2 -2 0 0 0 0]", "units": "m^2/s^2 (kinematic pressure)"}}
        if thermal:
            fields["T"] = {"components": 1, "dimensions": "[0 0 0 1 0 0 0]" if kelvin else "[0 0 0 0 0 0 0]",
                           "units": "K" if kelvin else "OpenFOAM dimensions [0 0 0 0 0 0 0]"}
        source_fields = {name: {"path": f"{time}/{name}", "sha256": sha(("SYNTHETIC native " + name).encode()), "size_bytes": 20}
                         for name in fields}
        fingerprint = sha(json.dumps(source_fields, sort_keys=True, separators=(",", ":")).encode())
        assets = [{"path": p.relative_to(case).as_posix(), "sha256": sha(p.read_bytes()), "size_bytes": p.stat().st_size}
                  for p in (vtk_path, log)]
        record = {"time_name": time, "selected_times": [time], "input_fingerprint_sha256": fingerprint,
                  "source_fields": source_fields, "fields": fields, "cell_count": 2,
                  "imported_field_summary": {}, "native_vtk_parity": {}, "cleanroomx_analysis_import": {},
                  "surface_phi_parity": None, "assets": assets, "foamToVTK_log_sha256": sha(log.read_bytes()),
                  "import_status": "PASS_DIAGNOSTIC_ONLY", "scientific_validation": "BLOCKED"}
        receipt = {"schema_version": "cleanroomx.openfoam-result-sync.v2", "simulation_id": run,
                   "case_id": case_id, "configuration_hash": "a"*64, "time_name": time, "record": record}
        receipt_path = output / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, sort_keys=True))
        record["receipt"] = {"path": receipt_path.relative_to(case).as_posix(), "sha256": sha(receipt_path.read_bytes())}
        records[time] = record
    manifest = {"schema_version": "cleanroomx.openfoam-result-sync.v2", "simulation_id": run,
                "case_id": case_id, "configuration_hash": "a"*64,
                "solver_release": "OpenFOAM Foundation v10", "solver_build": "SYNTHETIC-test-fixture",
                "interpretation": "solver_output_import_and_integrity_only", "scientific_validation": "BLOCKED",
                "status": "results_synced", "solver_returncode": 0, "solver_log_status": "completed",
                "record_count": len(records), "error_count": 0, "records": records, "errors": []}
    (case / "sync_manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return case


def write_dense_sync_store(root: Path, run="SYNTHETIC-room-grid"):
    """576 uniform volume cells for sampling/export and GUI review; never solver evidence."""
    import vtk
    case = write_sync_store(root, run=run)
    manifest_path = case / "sync_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for record in manifest["records"].values():
        mesh = vtk.vtkImageData()
        mesh.SetDimensions(13, 9, 7)
        mesh.SetSpacing(.5, .5, .5)
        conversion = vtk.vtkAppendFilter()
        conversion.AddInputData(mesh)
        conversion.Update()
        grid = conversion.GetOutput()
        centers = vtk.vtkCellCenters()
        centers.SetInputData(grid)
        centers.Update()
        for name, components in (("U", 3), ("p", 1), ("T", 1)):
            array = vtk.vtkDoubleArray()
            array.SetName(name)
            array.SetNumberOfComponents(components)
            for i in range(grid.GetNumberOfCells()):
                x, y, z = centers.GetOutput().GetPoint(i)
                value = {"U": (.2 + .01 * x, -.03 * y, .1 * z),
                         "p": (3 + .1 * x - .1 * y,), "T": (300 + x + y + z,)}[name]
                array.InsertNextTuple(value)
            grid.GetCellData().AddArray(array)
        asset = next(a for a in record["assets"] if a["path"].endswith(".vtk"))
        path = case / asset["path"]
        writer = vtk.vtkUnstructuredGridWriter()
        writer.SetFileName(str(path))
        writer.SetInputData(grid)
        writer.SetFileTypeToASCII()
        assert writer.Write() == 1
        asset.update(sha256=sha(path.read_bytes()), size_bytes=path.stat().st_size)
        record["cell_count"] = grid.GetNumberOfCells()
        receipt_path = case / record["receipt"]["path"]
        receipt = json.loads(receipt_path.read_text())
        receipt["record"] = {k: v for k, v in record.items() if k != "receipt"}
        receipt_path.write_text(json.dumps(receipt, sort_keys=True))
        record["receipt"]["sha256"] = sha(receipt_path.read_bytes())
    manifest_path.write_text(json.dumps(manifest, sort_keys=True))
    return case


def write_two_room_analysis_fixture(root: Path):
    from cleanroomx.cfd_two_room import export_two_room_case, _write_json
    from test_cfd_two_room import _spec
    from test_cfd_proofgraph import _write_two_room_receipt
    case = root / "two-room-case"
    receipt_path = root / "receipt" / "two_room_run_receipt.json"
    export_two_room_case(_spec(), case)
    receipt = _write_two_room_receipt(case, receipt_path)
    probe = case / receipt["pressure_probe"]["path"]
    probe.write_text("# SYNTHETIC two-room pressure fixture\n1 2 1\n2 4.2 0.1\n")
    receipt["pressure_probe"].update(sample_count=2, last_solver_time=2, sha256=sha(probe.read_bytes()))
    phi = case / "2" / "phi"
    phi.parent.mkdir()
    phi.write_text("dimensions [0 3 -1 0 0 0 0];\nboundaryField\n{\n"
                   "inlet\n{\n value uniform -0.1;\n}\noutlet\n{\n value uniform 0.09;\n}\n"
                   "walls\n{\n value uniform 0.01;\n}\n}\n")
    boundary = case / "constant/polyMesh/boundary"
    boundary.write_text("3\n(\ninlet\n{\n type patch; nFaces 1; startFace 0;\n}\n"
                        "outlet\n{\n type patch; nFaces 1; startFace 1;\n}\n"
                        "walls\n{\n type wall; nFaces 1; startFace 2;\n}\n)\n")
    receipt["solver_flux"].update(phi_path="2/phi", phi_sha256=sha(phi.read_bytes()),
                                  poly_mesh_boundary_sha256=sha(boundary.read_bytes()), last_solver_time="2")
    mesh = case / "checkMesh.log"
    mesh.write_bytes((Path(__file__).parent / "fixtures/openfoam_foundation_v10_checkmesh.log").read_bytes())
    log = case / "simpleFoam.log"
    log.write_text(residual_log())
    for stage in receipt["stages"]:
        stage["log_sha256"] = sha((case/stage["log_path"]).read_bytes())
    receipt["result_sha256"].pop("150/phi")
    receipt["result_sha256"].update({"2/phi": sha(phi.read_bytes()), "constant/polyMesh/boundary": sha(boundary.read_bytes()),
                                    receipt["pressure_probe"]["path"]: sha(probe.read_bytes()),
                                    "simpleFoam.log": sha(log.read_bytes()), "checkMesh.log": sha(mesh.read_bytes())})
    _write_json(receipt_path, receipt)
    return case, receipt_path


def residual_log():
    return ("SYNTHETIC residual history test fixture\nTime = 1\n"
            "smoothSolver: Solving for Ux, Initial residual = 0.1, Final residual = 0, No Iterations 2\n"
            "GAMG: Solving for p, Initial residual = 0.2, Final residual = 0.01, No Iterations 3\n"
            "GAMG: Solving for p, Initial residual = 0.02, Final residual = 0.001, No Iterations 3\n"
            "Time = 2\nGAMG: Solving for p, Initial residual = 0.002, Final residual = 0, No Iterations 2\nEnd\n")
