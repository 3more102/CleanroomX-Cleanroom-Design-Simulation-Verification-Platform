"""Read actual OpenFOAM polyMesh topology after recorded-run integrity checks."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct

from .cfd_multizone_results import _read, _recorded_outputs, analyze_multizone_case, read_ascii_field
from .cfd_multizone_vtk import MAX_3D_CELLS, select_recorded_cells


def load_recorded_multizone_mesh(directory, report):
    """Return an independent VTK mesh; never reconstruct topology from points.

    The selected report must equal a fresh hashed-field import from this case.
    VTK then reads the original polyMesh and U/p at the exact saved iteration.
    Cell count, centres, cell types and U/p are checked against that import.
    """
    import vtk
    root = Path(directory).resolve(strict=True)
    if not 0 < len(report.get("cells", [])) <= MAX_3D_CELLS:
        raise ValueError("Mesh review requires 1 to 100000 recorded CFD cells")
    actual = analyze_multizone_case(
        root, density_kg_m3=report["density_kg_m3"],
        reference_room_id=report["pressure_reference"]["room_id"],
        time_name=report["time_name"],
        vertical_tolerance_m_s=report["vertical_tolerance_m_s"],
    )
    if actual != report:
        raise ValueError("Mesh source differs from the selected recorded CFD report")
    reader = vtk.vtkOpenFOAMReader()
    # vtkOpenFOAMReader uses this path's parent directory. No marker file or
    # solver output is created/modified by this read-only review operation.
    reader.SetFileName(str(root/"cleanroomx-review.foam"))
    reader.SetCreateCellToPoint(False)
    reader.SetUse64BitFloats(True)
    reader.UpdateInformation()
    times = reader.GetTimeValues()
    selected = float(report["time_name"])
    if times is None or selected not in [times.GetValue(i) for i in range(times.GetNumberOfValues())]:
        raise ValueError("VTK reader lacks the exact selected recorded iteration")
    reader.SetTimeValue(selected)
    reader.SetCellArrayStatus("U", 1)
    reader.SetCellArrayStatus("p", 1)
    reader.Update()
    if reader.GetErrorCode():
        raise ValueError("VTK OpenFOAM mesh reader failed")
    output = reader.GetOutput()
    internal = None
    for index in range(output.GetNumberOfBlocks()):
        name = output.GetMetaData(index).Get(vtk.vtkCompositeDataSet.NAME())
        if name == "internalMesh":
            internal = output.GetBlock(index)
    if (internal is None or not internal.IsA("vtkUnstructuredGrid")
        or internal.GetNumberOfCells() != len(report["cells"])):
        raise ValueError("VTK internal mesh differs from recorded cell count")
    gas, pressure = internal.GetCellData().GetArray("U"), internal.GetCellData().GetArray("p")
    if gas is None or pressure is None or gas.GetNumberOfTuples() != len(report["cells"]) or pressure.GetNumberOfTuples() != len(report["cells"]):
        raise ValueError("VTK mesh lacks the selected recorded U/p arrays")
    def stored_value(array, value):
        # Some VTK releases keep field arrays as float32 even with 64-bit mesh
        # coordinates. Compare the EXACT source-to-array rounding, never relax
        # an engineering acceptance tolerance or replace canonical p/U values.
        if array.GetDataType() == vtk.VTK_FLOAT:
            return struct.unpack("!f", struct.pack("!f", value))[0]
        if array.GetDataType() == vtk.VTK_DOUBLE:
            return value
        raise ValueError("Unsupported VTK field storage precision")
    raw_pressure = read_ascii_field(
        _read(root, f"{report['time_name']}/p"), len(report["cells"]), (0,2,-2,0,0,0,0))
    centers = vtk.vtkCellCenters()
    centers.SetInputData(internal)
    centers.Update()
    points = centers.GetOutput().GetPoints()
    for index, cell in enumerate(report["cells"]):
        if internal.GetCellType(index) != vtk.VTK_HEXAHEDRON:
            raise ValueError("Recorded connected mesh requires original hexahedral cells")
        if any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-6)
               for a, b in zip(points.GetPoint(index), cell["center_m"])):
            raise ValueError("VTK cell centres do not match original recorded C")
        if any(a != stored_value(gas, b)
               for a, b in zip(gas.GetTuple3(index), cell["velocity_m_s"])):
            raise ValueError("VTK cell velocities do not match original recorded U")
        if pressure.GetTuple1(index) != stored_value(pressure, raw_pressure[index]):
            raise ValueError("VTK cell pressure does not match original recorded p")
    _recorded_outputs(root)
    if hashlib.sha256((root/"run-receipt.json").read_bytes()).hexdigest() != report["provenance"]["run_receipt_sha256"]:
        raise ValueError("Mesh execution receipt changed during VTK import")
    result = vtk.vtkUnstructuredGrid()
    result.DeepCopy(internal)
    return result


def recorded_mesh_edge_actor(mesh, report, **selection):
    """Display exact selected original cell edges with no invented field values."""
    import vtk
    if mesh.GetNumberOfCells() != len(report["cells"]):
        raise ValueError("Mesh cell count differs from recorded field")
    selected = select_recorded_cells(report, **selection)
    indices = {tuple(cell["center_m"]): i for i, cell in enumerate(report["cells"])}
    ids = vtk.vtkIdList()
    for cell in selected:
        ids.InsertNextId(indices[tuple(cell["center_m"])])
    extract = vtk.vtkExtractCells()
    extract.SetInputData(mesh)
    extract.SetCellList(ids)
    edges = vtk.vtkExtractEdges()
    edges.SetInputConnection(extract.GetOutputPort())
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(edges.GetOutputPort())
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(.48, .68, .84)
    actor.GetProperty().SetOpacity(.4)
    actor.GetProperty().SetLineWidth(1.)
    return actor
