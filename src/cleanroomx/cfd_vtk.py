"""Bounded VTK CFD cell-field reader for the CleanroomX comparison schema.

Requires optional VTK. Solver convergence and measurement validation are external.
"""
from __future__ import annotations
import copy
import hashlib
import math
from pathlib import Path
from .cfd_study import validate_study, analyze_cfd_study

MAX_VTK_BYTES=256*1024*1024
MAX_VTK_CELLS=100_000

def _read_vtk(path):
    try:
        import vtk
    except ImportError as exc:
        raise RuntimeError("pip install vtk to read VTK/VTU external field data") from exc
    ext=path.suffix.lower()
    if ext==".vtu": reader=vtk.vtkXMLUnstructuredGridReader()
    elif ext==".vtk": reader=vtk.vtkUnstructuredGridReader()
    else: raise ValueError("Only .vtk and .vtu unstructured grids are supported")
    reader.SetFileName(str(path))
    reader.Update()
    grid=reader.GetOutput()
    if grid is None or not 0<grid.GetNumberOfCells()<=MAX_VTK_CELLS:
        raise ValueError("Missing cells or exceeded bounded VTK cell count")
    if grid.GetCellData().GetArray("U") is None and grid.GetPointData().GetArray("U") is not None:
        converter=vtk.vtkPointDataToCellData()
        converter.SetInputData(grid)
        converter.Update()
        grid=converter.GetOutput()
    sizes=vtk.vtkCellSizeFilter()
    sizes.SetInputData(grid)
    sizes.SetComputeVolume(True)
    sizes.SetComputeArea(False)
    sizes.SetComputeLength(False)
    sizes.SetComputeVertexCount(False)
    sizes.SetVolumeArrayName("CleanroomXVolume")
    sizes.Update()
    return sizes.GetOutput()

def import_vtk_case(path,*,contaminant_array="T",recirculation_array="recirculating"):
    source=Path(path)
    if not source.is_file(): raise FileNotFoundError(source)
    before=source.stat()
    if before.st_size>MAX_VTK_BYTES: raise ValueError("VTK file exceeds bounded input limit")
    with source.open("rb") as fp:
        source_sha=hashlib.file_digest(fp,"sha256").hexdigest()
    grid=_read_vtk(source)
    after=source.stat()
    if (after.st_mtime_ns,after.st_size)!=(before.st_mtime_ns,before.st_size):
        raise ValueError("VTK file changed during ingestion")
    with source.open("rb") as fp:
        if hashlib.file_digest(fp,"sha256").hexdigest()!=source_sha:
            raise ValueError("VTK file content changed while parsing")
    arrays=grid.GetCellData()
    u=arrays.GetArray("U")
    volumes=arrays.GetArray("CleanroomXVolume")
    if u is None or u.GetNumberOfComponents()!=3:
        raise ValueError("VTK requires three-component U cell velocity in m/s")
    if volumes is None: raise ValueError("Cannot compute VTK cell volumes")
    c=arrays.GetArray(contaminant_array)
    mask=arrays.GetArray(recirculation_array)
    if c is not None and c.GetNumberOfComponents()!=1:
        raise ValueError("Contaminant field must be scalar")
    if mask is not None and mask.GetNumberOfComponents()!=1:
        raise ValueError("Recirculation mask must be scalar")
    cells=[]
    for i in range(grid.GetNumberOfCells()):
        volume=float(volumes.GetTuple1(i))
        velocity=[float(x) for x in u.GetTuple3(i)]
        if not math.isfinite(volume) or volume<=0:
            raise ValueError(f"Cell {i}: invalid volume")
        if not all(math.isfinite(v) for v in velocity):
            raise ValueError(f"Cell {i}: invalid velocity")
        cell={"volume_m3":volume,"velocity_m_s":velocity}
        if c is not None:
            val=float(c.GetTuple1(i))
            if not math.isfinite(val) or val<0:
                raise ValueError(f"Cell {i}: invalid contaminant concentration")
            cell["contaminant_concentration"]=val
        if mask is not None:
            value=float(mask.GetTuple1(i))
            if value not in (0,1):
                raise ValueError(f"Cell {i}: recirculating must be exactly 0 or 1")
            cell["recirculating"]=bool(value)
        cells.append(cell)
    return {"cells":cells,"source_sha256":source_sha,"mesh_cells":len(cells),
            "has_contaminant_field":c is not None,"has_recirculation_labels":mask is not None}

def populate_study_from_vtk(study,sources,*,solver_name,contaminant_array="T"):
    if type(solver_name) is not str or not solver_name.strip():
        raise ValueError("solver_name must be nonempty")
    if set(sources)!={1,2,3}: raise ValueError("Provide three VTK source files (1, 2, 3)")
    updated=copy.deepcopy(study)
    cases={item.get("configuration"):item for item in updated.get("cases",[])}
    if set(cases)!={1,2,3} or len(updated["cases"])!=3:
        raise ValueError("Study must contain unique cases 1, 2, 3")
    manifest={}
    for cfg in (1,2,3):
        imported=import_vtk_case(sources[cfg],contaminant_array=contaminant_array)
        case=cases[cfg]
        if case.get("cells"): raise ValueError(f"Case {cfg}: refuse to overwrite existing samples")
        case["cells"]=imported["cells"]
        case["solver"]={"name":solver_name,
                        "run_id":imported["source_sha256"][:24],
                        "mesh_cells":imported["mesh_cells"],
                        "source_reference":"sha256:"+imported["source_sha256"]}
        manifest[str(cfg)]={k:v for k,v in imported.items() if k!="cells"}
    validate_study(updated)
    return {"study":updated,"import_manifest":manifest,
            "analysis":analyze_cfd_study(updated)}
