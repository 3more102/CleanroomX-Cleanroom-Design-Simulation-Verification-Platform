"""Bounded VTK CFD cell-field reader for the CleanroomX comparison schema.

Requires optional VTK. Solver convergence and measurement validation are external.
"""
from __future__ import annotations
import copy
import hashlib
import math
import re
import struct
from pathlib import Path
from .cfd_study import validate_study, analyze_cfd_study

MAX_VTK_BYTES=256*1024*1024
MAX_VTK_CELLS=100_000

def _read_vtk(path, *, require_cell_velocity=False):
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
        if require_cell_velocity:
            raise ValueError("VTK field parity requires native cell-data U; point interpolation is not accepted")
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


_FOAM_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_FOAM_VECTOR = re.compile(
    rf"\(\s*({_FOAM_NUMBER})\s+({_FOAM_NUMBER})\s+({_FOAM_NUMBER})\s*\)"
)
_FOAM_INTERNAL_VECTOR_FIELD = re.compile(
    r"\binternalField\s+nonuniform\s+List\s*<\s*vector\s*>\s*(\d+)\s*\((.*?)\)\s*;",
    re.DOTALL,
)
MAX_OPENFOAM_FIELD_BYTES = 64 * 1024 * 1024
# The current Foundation v10 run artifacts write legacy VTK FIELD values with
# six significant decimal digits unless a different writer precision is used.
OPENFOAM_VTK_ASCII_PRECISION = 6


def _read_native_openfoam_velocity(path):
    """Read an ASCII volVectorField's internalField without accepting patches."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Native OpenFOAM U must be a regular, non-symlink file")
    before = source.stat()
    if before.st_size > MAX_OPENFOAM_FIELD_BYTES:
        raise ValueError("Native OpenFOAM U exceeds the bounded field size")
    raw = source.read_bytes()
    if len(raw) != before.st_size:
        raise ValueError("Native OpenFOAM U changed while being read")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Native OpenFOAM U must be an ASCII field") from exc
    stable = source.stat()
    if (stable.st_mtime_ns, stable.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError("Native OpenFOAM U changed during ingestion")

    # Remove OpenFOAM comments before matching so commented examples cannot be
    # mistaken for the active internalField declaration.
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\r\n]*", " ", text)
    if not re.search(r"\bclass\s+volVectorField\s*;", text):
        raise ValueError("Native OpenFOAM U is not a volVectorField")
    if not re.search(r"\bobject\s+U\s*;", text):
        raise ValueError("Native OpenFOAM field object is not U")
    matches = list(_FOAM_INTERNAL_VECTOR_FIELD.finditer(text))
    if len(matches) != 1:
        raise ValueError("Native OpenFOAM U must contain exactly one nonuniform vector internalField")
    match = matches[0]
    count = int(match.group(1))
    if not 0 < count <= MAX_VTK_CELLS:
        raise ValueError("Native OpenFOAM U has an invalid or unsupported cell count")
    body = match.group(2)
    vector_matches = list(_FOAM_VECTOR.finditer(body))
    if len(vector_matches) != count or _FOAM_VECTOR.sub("", body).strip():
        raise ValueError("Native OpenFOAM U vector list does not match its declared count")
    values = []
    for item in vector_matches:
        vector = tuple(float(component) for component in item.groups())
        if not all(math.isfinite(component) for component in vector):
            raise ValueError("Native OpenFOAM U contains a non-finite velocity")
        values.append(vector)
    return values, hashlib.sha256(raw).hexdigest()


def _float32(value):
    try:
        rounded = struct.unpack(">f", struct.pack(">f", value))[0]
    except (OverflowError, struct.error) as exc:
        raise ValueError("Native OpenFOAM U cannot be represented by VTK float32") from exc
    if not math.isfinite(rounded):
        raise ValueError("Native OpenFOAM U overflows VTK float32")
    return rounded


def _next_float32(value, direction):
    if value == 0.0:
        bits = 1 if direction > 0 else 0x80000001
    else:
        bits = struct.unpack(">I", struct.pack(">f", value))[0]
        toward_larger_magnitude = (value > 0) == (direction > 0)
        bits += 1 if toward_larger_magnitude else -1
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def _float32_rounding_bound(value):
    rounded = _float32(value)
    adjacent = (
        _next_float32(rounded, -1),
        _next_float32(rounded, 1),
    )
    finite_spacings = [
        abs(rounded - candidate)
        for candidate in adjacent
        if math.isfinite(candidate)
    ]
    if not finite_spacings:
        raise ValueError("Native OpenFOAM U has no finite adjacent VTK float32 value")
    spacing = max(finite_spacings)
    return rounded, spacing / 2.0


def _ascii_rounding_bound(value, significant_digits):
    if value == 0.0:
        return 0.0
    exponent = math.floor(math.log10(abs(value)))
    return 0.5 * (10.0 ** (exponent - significant_digits + 1))


def audit_openfoam_vtk_velocity(native_u_path, vtk_path, *, ascii_precision=OPENFOAM_VTK_ASCII_PRECISION):
    """Compare native OpenFOAM cell U to foamToVTK U using exported cellID.

    `foamToVTK` writes an internal-cell `cellID` alongside cell fields. The IDs
    establish correspondence explicitly; VTK array position is never used as a
    presumed OpenFOAM cell index. Its current legacy output declares U as
    float32, so the comparison separates native-to-float32 rounding from the
    bounded ASCII serialization error.
    """
    if type(ascii_precision) is not int or ascii_precision < 6 or ascii_precision > 17:
        raise ValueError("ASCII precision must be an integer from 6 through 17 significant digits")
    native_values, native_sha = _read_native_openfoam_velocity(native_u_path)
    source = Path(vtk_path)
    if not source.is_file() or source.is_symlink():
        raise ValueError("foamToVTK dataset must be a regular, non-symlink file")
    before = source.stat()
    if before.st_size > MAX_VTK_BYTES:
        raise ValueError("VTK file exceeds bounded input limit")
    with source.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    grid = _read_vtk(source, require_cell_velocity=True)
    after = source.stat()
    if (after.st_mtime_ns, after.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError("VTK file changed during field-parity ingestion")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source_sha:
            raise ValueError("VTK file content changed during field-parity ingestion")

    cell_data = grid.GetCellData()
    cell_ids = cell_data.GetArray("cellID")
    velocity = cell_data.GetArray("U")
    count = len(native_values)
    if grid.GetNumberOfCells() != count:
        raise ValueError("Native OpenFOAM and VTK cell counts differ")
    if cell_ids is None or cell_ids.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK dataset must contain scalar cellID cell data")
    if velocity is None or velocity.GetNumberOfComponents() != 3:
        raise ValueError("foamToVTK dataset must contain three-component cell-data U")
    if velocity.GetDataTypeAsString() != "float":
        raise ValueError("Field-parity tolerance requires the foamToVTK float32 U representation")

    mapped = {}
    maximum_absolute_error = 0.0
    maximum_relative_error = 0.0
    maximum_float32_residual = 0.0
    maximum_allowed_output_error = 0.0
    compared_components = 0
    for vtk_index in range(count):
        raw_id = float(cell_ids.GetTuple1(vtk_index))
        if not math.isfinite(raw_id) or not raw_id.is_integer():
            raise ValueError("foamToVTK cellID contains a non-integer value")
        cell_id = int(raw_id)
        if not 0 <= cell_id < count or cell_id in mapped:
            raise ValueError("foamToVTK cellID is not a unique in-range native cell index")
        mapped[cell_id] = vtk_index
    if set(mapped) != set(range(count)):
        raise ValueError("foamToVTK cellID does not cover every native cell exactly once")

    for native_id, vtk_index in mapped.items():
        native_vector = native_values[native_id]
        vtk_vector = tuple(float(v) for v in velocity.GetTuple3(vtk_index))
        if not all(math.isfinite(component) for component in vtk_vector):
            raise ValueError("foamToVTK U contains a non-finite velocity")
        for native_component, vtk_component in zip(native_vector, vtk_vector):
            expected_float32, conversion_bound = _float32_rounding_bound(native_component)
            serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
            # The writer serializes a single-precision field to decimal text,
            # then the VTK reader stores that text back into float32.
            reader_rounding_bound = conversion_bound + serialization_bound
            allowed = conversion_bound + reader_rounding_bound
            float32_residual = abs(vtk_component - expected_float32)
            if float32_residual > reader_rounding_bound + 4.0 * math.ulp(expected_float32):
                raise ValueError("foamToVTK U differs from the native field beyond its ASCII precision")
            error = abs(vtk_component - native_component)
            maximum_absolute_error = max(maximum_absolute_error, error)
            if native_component != 0.0:
                maximum_relative_error = max(maximum_relative_error, error / abs(native_component))
            maximum_float32_residual = max(maximum_float32_residual, float32_residual)
            maximum_allowed_output_error = max(maximum_allowed_output_error, allowed)
            compared_components += 1

    return {
        "status": "PASS",
        "cell_id_mapping": "complete_unique_permutation_of_native_cell_indices",
        "cell_count": count,
        "compared_velocity_components": compared_components,
        "native_field_sha256": native_sha,
        "vtk_sha256": source_sha,
        "vtk_velocity_scalar_type": velocity.GetDataTypeAsString(),
        "ascii_significant_digits": ascii_precision,
        "max_absolute_error_native_to_vtk_m_s": maximum_absolute_error,
        "max_relative_error_native_to_vtk": maximum_relative_error,
        "max_float32_reference_residual_m_s": maximum_float32_residual,
        "max_allowed_native_to_vtk_error_m_s": maximum_allowed_output_error,
        "tolerance_basis": "two IEEE-754 binary32 round-to-nearest bounds (field cast and VTK reader) plus half-unit in the last place for the configured ASCII significant-digit precision",
    }

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
