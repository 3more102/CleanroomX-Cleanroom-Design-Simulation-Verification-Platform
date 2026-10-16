"""Bounded VTK CFD cell-field reader for the CleanroomX comparison schema.

Requires optional VTK. Solver convergence and measurement validation are external.
"""
from __future__ import annotations
import copy
import hashlib
import math
import re
import struct
from decimal import Decimal, InvalidOperation
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


def _vtk_mesh_geometry_sha256(grid):
    """Hash VTK point coordinates and ordered cell topology, excluding fields."""
    point_count = grid.GetNumberOfPoints()
    cell_count = grid.GetNumberOfCells()
    if point_count <= 0 or cell_count <= 0:
        raise ValueError("VTK mesh geometry requires points and cells")
    digest = hashlib.sha256()
    digest.update(b"CleanroomX-VTK-mesh-geometry-v1\0")
    digest.update(struct.pack(">QQ", point_count, cell_count))
    for point_id in range(point_count):
        point = grid.GetPoint(point_id)
        coordinates = tuple(float(component) for component in point)
        if len(coordinates) != 3 or not all(math.isfinite(value) for value in coordinates):
            raise ValueError(f"VTK point {point_id} has non-finite coordinates")
        digest.update(struct.pack(">ddd", *coordinates))
    for cell_id in range(cell_count):
        cell = grid.GetCell(cell_id)
        if cell is None:
            raise ValueError(f"VTK cell {cell_id} is missing")
        ids = cell.GetPointIds()
        size = ids.GetNumberOfIds()
        if size <= 0:
            raise ValueError(f"VTK cell {cell_id} has no points")
        digest.update(struct.pack(">qQ", int(grid.GetCellType(cell_id)), size))
        for local_id in range(size):
            point_id = int(ids.GetId(local_id))
            if point_id < 0 or point_id >= point_count:
                raise ValueError(f"VTK cell {cell_id} references an invalid point")
            digest.update(struct.pack(">Q", point_id))
    return digest.hexdigest()


_FOAM_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_FOAM_VECTOR = re.compile(
    rf"\(\s*({_FOAM_NUMBER})\s+({_FOAM_NUMBER})\s+({_FOAM_NUMBER})\s*\)"
)
_FOAM_INTERNAL_VECTOR_FIELD = re.compile(
    r"\binternalField\s+nonuniform\s+List\s*<\s*vector\s*>\s*(\d+)\s*\((.*?)\)\s*;",
    re.DOTALL,
)
_FOAM_INTERNAL_SCALAR_FIELD = re.compile(
    rf"\binternalField\s+nonuniform\s+List\s*<\s*scalar\s*>\s*(\d+)\s*\((.*?)\)\s*;",
    re.DOTALL,
)
MAX_OPENFOAM_FIELD_BYTES = 64 * 1024 * 1024
MAX_OPENFOAM_FACES = 600_000
VTK_FIELD_MAP_SCHEMA = "cleanroomx.cfd-vtk-field-map.v1"
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


def _read_native_openfoam_pressure(path):
    """Read an ASCII volScalarField p's kinematic-pressure internalField."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Native OpenFOAM p must be a regular, non-symlink file")
    before = source.stat()
    if before.st_size > MAX_OPENFOAM_FIELD_BYTES:
        raise ValueError("Native OpenFOAM p exceeds the bounded field size")
    raw = source.read_bytes()
    if len(raw) != before.st_size:
        raise ValueError("Native OpenFOAM p changed while being read")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Native OpenFOAM p must be an ASCII field") from exc
    stable = source.stat()
    if (stable.st_mtime_ns, stable.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError("Native OpenFOAM p changed during ingestion")

    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\r\n]*", " ", text)
    if not re.search(r"\bclass\s+volScalarField\s*;", text):
        raise ValueError("Native OpenFOAM p is not a volScalarField")
    if not re.search(r"\bobject\s+p\s*;", text):
        raise ValueError("Native OpenFOAM field object is not p")
    if not re.search(r"\bdimensions\s+\[\s*0\s+2\s+-2\s+0\s+0\s+0\s+0\s*\]\s*;", text):
        raise ValueError("Native OpenFOAM p must have kinematic-pressure dimensions")
    matches = list(_FOAM_INTERNAL_SCALAR_FIELD.finditer(text))
    if len(matches) != 1:
        raise ValueError("Native OpenFOAM p must contain exactly one nonuniform scalar internalField")
    match = matches[0]
    count = int(match.group(1))
    if not 0 < count <= MAX_VTK_CELLS:
        raise ValueError("Native OpenFOAM p has an invalid or unsupported cell count")
    tokens = re.findall(_FOAM_NUMBER, match.group(2))
    if len(tokens) != count or re.sub(_FOAM_NUMBER, "", match.group(2)).strip():
        raise ValueError("Native OpenFOAM p scalar list does not match its declared count")
    values = [float(token) for token in tokens]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Native OpenFOAM p contains a non-finite pressure")
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


def audit_openfoam_vtk_pressure(native_p_path, vtk_path, *, ascii_precision=OPENFOAM_VTK_ASCII_PRECISION):
    """Compare native kinematic-pressure cell p to foamToVTK p by cellID."""
    if type(ascii_precision) is not int or ascii_precision < 6 or ascii_precision > 17:
        raise ValueError("ASCII precision must be an integer from 6 through 17 significant digits")
    native_values, native_sha = _read_native_openfoam_pressure(native_p_path)
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
    pressure = cell_data.GetArray("p")
    count = len(native_values)
    if grid.GetNumberOfCells() != count:
        raise ValueError("Native OpenFOAM and VTK cell counts differ")
    if cell_ids is None or cell_ids.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK dataset must contain scalar cellID cell data")
    if pressure is None or pressure.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK dataset must contain scalar cell-data p")
    if pressure.GetDataTypeAsString() != "float":
        raise ValueError("Field-parity tolerance requires the foamToVTK float32 p representation")

    mapped = {}
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

    maximum_absolute_error = 0.0
    maximum_relative_error = 0.0
    maximum_float32_residual = 0.0
    maximum_allowed_output_error = 0.0
    for native_id, vtk_index in mapped.items():
        native_value = native_values[native_id]
        vtk_value = float(pressure.GetTuple1(vtk_index))
        if not math.isfinite(vtk_value):
            raise ValueError("foamToVTK p contains a non-finite pressure")
        expected_float32, conversion_bound = _float32_rounding_bound(native_value)
        serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
        reader_rounding_bound = conversion_bound + serialization_bound
        allowed = conversion_bound + reader_rounding_bound
        float32_residual = abs(vtk_value - expected_float32)
        if float32_residual > reader_rounding_bound + 4.0 * math.ulp(expected_float32):
            raise ValueError("foamToVTK p differs from the native field beyond its ASCII precision")
        error = abs(vtk_value - native_value)
        maximum_absolute_error = max(maximum_absolute_error, error)
        if native_value != 0.0:
            maximum_relative_error = max(maximum_relative_error, error / abs(native_value))
        maximum_float32_residual = max(maximum_float32_residual, float32_residual)
        maximum_allowed_output_error = max(maximum_allowed_output_error, allowed)

    return {
        "status": "PASS",
        "field": "p",
        "dimensions": "[0 2 -2 0 0 0 0]",
        "cell_id_mapping": "complete_unique_permutation_of_native_cell_indices",
        "cell_count": count,
        "compared_scalar_values": count,
        "native_field_sha256": native_sha,
        "vtk_sha256": source_sha,
        "vtk_scalar_type": pressure.GetDataTypeAsString(),
        "ascii_significant_digits": ascii_precision,
        "max_absolute_error_native_to_vtk_m2_s2": maximum_absolute_error,
        "max_relative_error_native_to_vtk": maximum_relative_error,
        "max_float32_reference_residual_m2_s2": maximum_float32_residual,
        "max_allowed_native_to_vtk_error_m2_s2": maximum_allowed_output_error,
        "tolerance_basis": "two IEEE-754 binary32 round-to-nearest bounds (field cast and VTK reader) plus half-unit in the last place for the configured ASCII significant-digit precision",
    }


def _read_stable_ascii_file(path, description, *, root=None):
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{description} must be a regular, non-symlink file")
    if root is not None:
        resolved_root = Path(root).resolve(strict=True)
        resolved_source = source.resolve(strict=True)
        if not resolved_source.is_relative_to(resolved_root):
            raise ValueError(f"{description} escaped its input directory")
    before = source.stat()
    if before.st_size > MAX_OPENFOAM_FIELD_BYTES:
        raise ValueError(f"{description} exceeds the bounded input size")
    raw = source.read_bytes()
    if len(raw) != before.st_size:
        raise ValueError(f"{description} changed while being read")
    after = source.stat()
    if (after.st_mtime_ns, after.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError(f"{description} changed during ingestion")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{description} must be an ASCII file") from exc
    return text, hashlib.sha256(raw).hexdigest()


def _strip_foam_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", " ", text)


def _extract_foam_braced_block(text, name, description):
    matches = list(re.finditer(rf"\b{re.escape(name)}\s*\{{", text))
    if len(matches) != 1:
        raise ValueError(f"{description} must contain exactly one {name} dictionary")
    start = text.find("{", matches[0].start())
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    raise ValueError(f"{description} contains an unterminated {name} dictionary")


def _extract_foam_counted_list(text, description):
    match = re.search(r"\b(\d+)\s*\(", text)
    if match is None:
        raise ValueError(f"{description} is missing its counted list")
    count = int(match.group(1))
    start = text.find("(", match.start())
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return count, text[start + 1:index]
    raise ValueError(f"{description} contains an unterminated counted list")


def _read_openfoam_mesh_points(path, mesh_root):
    text, digest = _read_stable_ascii_file(path, "OpenFOAM mesh points", root=mesh_root)
    clean = _strip_foam_comments(text)
    count, body = _extract_foam_counted_list(clean, "OpenFOAM mesh points")
    matches = list(_FOAM_VECTOR.finditer(body))
    if len(matches) != count or _FOAM_VECTOR.sub("", body).strip():
        raise ValueError("OpenFOAM mesh point list does not match its declared count")
    points = [tuple(float(component) for component in match.groups()) for match in matches]
    if not all(math.isfinite(component) for point in points for component in point):
        raise ValueError("OpenFOAM mesh points contain a non-finite coordinate")
    return points, digest


def _read_openfoam_mesh_faces(path, point_count, mesh_root):
    text, digest = _read_stable_ascii_file(path, "OpenFOAM mesh faces", root=mesh_root)
    clean = _strip_foam_comments(text)
    count, body = _extract_foam_counted_list(clean, "OpenFOAM mesh faces")
    matches = list(re.finditer(r"(\d+)\s*\(([^()]*)\)", body))
    if len(matches) != count:
        raise ValueError("OpenFOAM mesh face list does not match its declared count")
    faces = []
    for match in matches:
        face_count = int(match.group(1))
        point_ids = [int(token) for token in re.findall(r"[+-]?\d+", match.group(2))]
        if (
            len(point_ids) != face_count
            or face_count < 3
            or len(set(point_ids)) != face_count
            or any(point_id < 0 for point_id in point_ids)
            or any(point_id >= point_count for point_id in point_ids)
        ):
            raise ValueError("OpenFOAM mesh contains an invalid face")
        faces.append(point_ids)
    if re.sub(r"\d+\s*\([^()]*\)", "", body).strip():
        raise ValueError("OpenFOAM mesh face list contains unexpected data")
    return faces, digest


def _read_openfoam_mesh_owners(path, face_count, mesh_root):
    text, digest = _read_stable_ascii_file(path, "OpenFOAM mesh owners", root=mesh_root)
    clean = _strip_foam_comments(text)
    count, body = _extract_foam_counted_list(clean, "OpenFOAM mesh owners")
    tokens = re.findall(r"[+-]?\d+", body)
    owners = [int(token) for token in tokens]
    if (
        count != face_count
        or len(tokens) != count
        or re.sub(r"[+-]?\d+", "", body).strip()
        or any(owner < 0 for owner in owners)
    ):
        raise ValueError("OpenFOAM mesh owner list does not match its declared face count")
    return owners, digest


def _read_openfoam_mesh_neighbours(path, face_count, mesh_root):
    text, digest = _read_stable_ascii_file(path, "OpenFOAM mesh neighbours", root=mesh_root)
    clean = _strip_foam_comments(text)
    count, body = _extract_foam_counted_list(clean, "OpenFOAM mesh neighbours")
    tokens = re.findall(r"[+-]?\d+", body)
    if (
        count != len(tokens)
        or count > face_count
        or re.sub(r"[+-]?\d+", "", body).strip()
    ):
        raise ValueError("OpenFOAM mesh neighbour list has an invalid face count")
    neighbours = [int(token) for token in tokens]
    if any(cell_id < 0 for cell_id in neighbours):
        raise ValueError("OpenFOAM mesh neighbour list contains a negative cell index")
    return neighbours, digest


def _read_openfoam_boundary_patches(path, face_count, mesh_root):
    text, digest = _read_stable_ascii_file(path, "OpenFOAM mesh boundary", root=mesh_root)
    clean = _strip_foam_comments(text)
    declared_count, body = _extract_foam_counted_list(clean, "OpenFOAM mesh boundary")
    matches = list(re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\{([^{}]*)\}", body))
    if len(matches) != declared_count:
        raise ValueError("OpenFOAM boundary patch count does not match its declaration")
    patches = []
    names = set()
    for patch_index, match in enumerate(matches):
        name, patch_text = match.groups()
        if name in names:
            raise ValueError("OpenFOAM boundary contains duplicate patch names")
        names.add(name)
        face_counts = re.findall(r"\bnFaces\s+(\d+)\s*;", patch_text)
        starts = re.findall(r"\bstartFace\s+(\d+)\s*;", patch_text)
        if len(face_counts) != 1 or len(starts) != 1:
            raise ValueError("OpenFOAM boundary patch must declare one startFace and nFaces")
        start_face, patch_face_count = int(starts[0]), int(face_counts[0])
        if (
            patch_face_count <= 0
            or start_face < 0
            or start_face + patch_face_count > face_count
        ):
            raise ValueError("OpenFOAM boundary patch face range is invalid")
        patches.append({
            "name": name,
            "patch_id": patch_index,
            "start_face": start_face,
            "face_count": patch_face_count,
        })
    ordered_ranges = sorted((item["start_face"], item["start_face"] + item["face_count"]) for item in patches)
    if not ordered_ranges or ordered_ranges[0][0] + sum(end - start for start, end in ordered_ranges) != face_count:
        raise ValueError("OpenFOAM boundary patches do not cover every mesh face exactly once")
    cursor = ordered_ranges[0][0]
    for start, end in ordered_ranges:
        if start != cursor:
            raise ValueError("OpenFOAM boundary patch face ranges overlap or contain gaps")
        cursor = end
    return patches, digest


def _foam_scalar_values(body, declared_count, description):
    tokens = re.findall(_FOAM_NUMBER, body)
    if len(tokens) != declared_count or re.sub(_FOAM_NUMBER, "", body).strip():
        raise ValueError(f"{description} does not match its declared scalar count")
    values = [float(token) for token in tokens]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{description} contains a non-finite value")
    return values


def _read_native_openfoam_surface_flux(path, internal_face_count, patches):
    """Read a Foundation v10 ASCII surfaceScalarField phi in mesh-face order."""
    text, digest = _read_stable_ascii_file(path, "Native OpenFOAM phi")
    clean = _strip_foam_comments(text)
    if not re.search(r"\bclass\s+surfaceScalarField\s*;", clean):
        raise ValueError("Native OpenFOAM phi is not a surfaceScalarField")
    if not re.search(r"\bobject\s+phi\s*;", clean):
        raise ValueError("Native OpenFOAM field object is not phi")
    if not re.search(r"\bdimensions\s+\[\s*0\s+3\s+-1\s+0\s+0\s+0\s+0\s*\]\s*;", clean):
        raise ValueError("Native OpenFOAM phi must have volume-flux dimensions")

    internal_uniform = re.findall(rf"\binternalField\s+uniform\s+({_FOAM_NUMBER})\s*;", clean)
    internal_nonuniform = re.findall(
        r"\binternalField\s+nonuniform\s+List\s*<\s*scalar\s*>\s*(\d+)\s*\((.*?)\)\s*;",
        clean,
        flags=re.DOTALL,
    )
    if len(internal_uniform) == 1 and not internal_nonuniform:
        internal_values = [float(internal_uniform[0])] * internal_face_count
    elif not internal_uniform and len(internal_nonuniform) == 1:
        declared_count, body = internal_nonuniform[0]
        if int(declared_count) != internal_face_count:
            raise ValueError("Native OpenFOAM phi internal values do not match the neighbour face count")
        internal_values = _foam_scalar_values(body, internal_face_count, "Native OpenFOAM phi internal field")
    else:
        raise ValueError("Native OpenFOAM phi must contain one supported internal scalar field")

    boundary = _extract_foam_braced_block(clean, "boundaryField", "Native OpenFOAM phi")
    field_patch_names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\{", boundary)
    expected_patch_names = [patch["name"] for patch in patches]
    if len(field_patch_names) != len(expected_patch_names) or set(field_patch_names) != set(expected_patch_names):
        raise ValueError("Native OpenFOAM phi patch names do not match the polyMesh boundary")

    boundary_values = {}
    boundary_types = {}
    for patch in patches:
        patch_name = patch["name"]
        patch_text = _extract_foam_braced_block(
            boundary, patch_name, "Native OpenFOAM phi boundaryField"
        )
        types = re.findall(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", patch_text)
        if len(types) != 1:
            raise ValueError(f"Native OpenFOAM phi patch {patch_name} must declare one type")

        uniform = re.findall(rf"\bvalue\s+uniform\s+({_FOAM_NUMBER})\s*;", patch_text)
        nonuniform = re.findall(
            r"\bvalue\s+nonuniform\s+List\s*<\s*scalar\s*>\s*(\d+)\s*\((.*?)\)\s*;",
            patch_text,
            flags=re.DOTALL,
        )
        if len(uniform) == 1 and not nonuniform:
            values = [float(uniform[0])] * patch["face_count"]
        elif not uniform and len(nonuniform) == 1:
            declared_count, body = nonuniform[0]
            if int(declared_count) != patch["face_count"]:
                raise ValueError(f"Native OpenFOAM phi patch {patch_name} count is invalid")
            values = _foam_scalar_values(body, patch["face_count"], f"Native OpenFOAM phi patch {patch_name}")
        else:
            raise ValueError(f"Native OpenFOAM phi patch {patch_name} has no supported scalar values")
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Native OpenFOAM phi patch {patch_name} contains a non-finite value")
        boundary_values[patch_name] = values
        boundary_types[patch_name] = types[0]

    ordered_patches = sorted(patches, key=lambda patch: patch["start_face"])
    expected_start = internal_face_count
    values = list(internal_values)
    for patch in ordered_patches:
        if patch["start_face"] != expected_start:
            raise ValueError("OpenFOAM boundary patches do not start after the internal faces")
        values.extend(boundary_values[patch["name"]])
        expected_start += patch["face_count"]
    return values, digest, boundary_types


def _openfoam_face_centres_and_normals(points, faces):
    centres = []
    normals = []
    for face in faces:
        origin = points[face[0]]
        area_vector = [0.0, 0.0, 0.0]
        weighted_centre = [0.0, 0.0, 0.0]
        total_triangle_area = 0.0
        triangle_vectors = []
        for index in range(1, len(face) - 1):
            left = points[face[index]]
            right = points[face[index + 1]]
            left_delta = tuple(left[axis] - origin[axis] for axis in range(3))
            right_delta = tuple(right[axis] - origin[axis] for axis in range(3))
            cross = (
                left_delta[1] * right_delta[2] - left_delta[2] * right_delta[1],
                left_delta[2] * right_delta[0] - left_delta[0] * right_delta[2],
                left_delta[0] * right_delta[1] - left_delta[1] * right_delta[0],
            )
            triangle_area_vector = tuple(component * 0.5 for component in cross)
            triangle_area = math.sqrt(sum(component * component for component in triangle_area_vector))
            if not math.isfinite(triangle_area) or triangle_area <= 0.0:
                raise ValueError("OpenFOAM mesh contains a degenerate face triangle")
            triangle_vectors.append(triangle_area_vector)
            for axis in range(3):
                area_vector[axis] += triangle_area_vector[axis]
                weighted_centre[axis] += triangle_area * (
                    origin[axis] + left[axis] + right[axis]
                ) / 3.0
            total_triangle_area += triangle_area

        area_magnitude = math.sqrt(sum(component * component for component in area_vector))
        if not math.isfinite(area_magnitude) or area_magnitude <= 0.0:
            raise ValueError("OpenFOAM mesh contains a face with zero oriented area")
        normal = tuple(component / area_magnitude for component in area_vector)
        if any(sum(a * b for a, b in zip(triangle, normal)) <= 0.0 for triangle in triangle_vectors):
            raise ValueError("OpenFOAM face is not a convex, consistently wound polygon")
        centre = tuple(component / total_triangle_area for component in weighted_centre)
        scale = max(
            math.sqrt(sum((points[face[i]][axis] - origin[axis]) ** 2 for axis in range(3)))
            for i in range(1, len(face))
        )
        planar_tolerance = max(1e-12, scale * 1e-10)
        if any(
            abs(sum((points[point_id][axis] - origin[axis]) * normal[axis] for axis in range(3)))
            > planar_tolerance
            for point_id in face
        ):
            raise ValueError("OpenFOAM surface-field parity supports planar faces only")
        centres.append(centre)
        normals.append(normal)
    return centres, normals


def _foam_patch_expected_values(text, field_name, patch_name, components, internal_values, owners, face_ids):
    clean = _strip_foam_comments(text)
    expected_class = "volVectorField" if components == 3 else "volScalarField"
    if not re.search(rf"\bclass\s+{expected_class}\s*;", clean):
        raise ValueError(f"Native OpenFOAM {field_name} is not a {expected_class}")
    if not re.search(rf"\bobject\s+{re.escape(field_name)}\s*;", clean):
        raise ValueError(f"Native OpenFOAM field object is not {field_name}")
    boundary = _extract_foam_braced_block(clean, "boundaryField", f"Native OpenFOAM {field_name}")
    patch_text = _extract_foam_braced_block(boundary, patch_name, f"Native OpenFOAM {field_name} boundary")
    types = re.findall(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", patch_text)
    if len(types) != 1:
        raise ValueError(f"Native OpenFOAM {field_name} patch must declare exactly one boundary type")
    boundary_type = types[0]
    if boundary_type == "zeroGradient":
        values = []
        for face_id in face_ids:
            if not 0 <= face_id < len(owners) or not 0 <= owners[face_id] < len(internal_values):
                raise ValueError("OpenFOAM boundary owner is outside the native internal field")
            values.append(internal_values[owners[face_id]])
        return values, boundary_type
    if boundary_type == "noSlip" and components == 3:
        return [(0.0, 0.0, 0.0)] * len(face_ids), boundary_type

    uniform = re.findall(r"\bvalue\s+uniform\s+([^;]+);", patch_text)
    nonuniform = re.findall(
        r"\bvalue\s+nonuniform\s+List\s*<\s*(vector|scalar)\s*>\s*(\d+)\s*\((.*?)\)\s*;",
        patch_text,
        flags=re.DOTALL,
    )
    if len(uniform) == 1 and not nonuniform:
        token = uniform[0].strip()
        if components == 3:
            match = _FOAM_VECTOR.fullmatch(token)
            if match is None:
                raise ValueError(f"Native OpenFOAM {field_name} uniform patch value is not a vector")
            one_value = tuple(float(component) for component in match.groups())
        else:
            if re.fullmatch(_FOAM_NUMBER, token) is None:
                raise ValueError(f"Native OpenFOAM {field_name} uniform patch value is not a scalar")
            one_value = float(token)
        values = [one_value] * len(face_ids)
    elif not uniform and len(nonuniform) == 1:
        value_type, declared_count, value_body = nonuniform[0]
        expected_type = "vector" if components == 3 else "scalar"
        if value_type != expected_type or int(declared_count) != len(face_ids):
            raise ValueError(f"Native OpenFOAM {field_name} patch value count or type is invalid")
        if components == 3:
            matches = list(_FOAM_VECTOR.finditer(value_body))
            if len(matches) != len(face_ids) or _FOAM_VECTOR.sub("", value_body).strip():
                raise ValueError(f"Native OpenFOAM {field_name} patch vectors do not match their declared count")
            values = [tuple(float(value) for value in match.groups()) for match in matches]
        else:
            tokens = re.findall(_FOAM_NUMBER, value_body)
            if len(tokens) != len(face_ids) or re.sub(_FOAM_NUMBER, "", value_body).strip():
                raise ValueError(f"Native OpenFOAM {field_name} patch scalars do not match their declared count")
            values = [float(token) for token in tokens]
    else:
        raise ValueError(
            f"Native OpenFOAM {field_name} patch type {boundary_type} lacks a supported explicit value"
        )
    scalars = (component for value in values for component in value) if components == 3 else iter(values)
    if not all(math.isfinite(value) for value in scalars):
        raise ValueError(f"Native OpenFOAM {field_name} patch values contain non-finite values")
    return values, boundary_type


def _patch_face_signature(coordinates, precision):
    formatted = []
    for coordinate in coordinates:
        point = []
        for component in coordinate:
            value = float(component)
            if not math.isfinite(value):
                raise ValueError("VTK or OpenFOAM patch geometry contains a non-finite coordinate")
            point.append("0" if value == 0.0 else format(value, f".{precision}g"))
        formatted.append(tuple(point))
    return tuple(sorted(formatted))


def audit_openfoam_vtk_boundary_patch(
    native_u_path,
    native_p_path,
    poly_mesh_directory,
    vtk_patch_path,
    patch_name,
    *,
    ascii_precision=OPENFOAM_VTK_ASCII_PRECISION,
):
    """Audit one foamToVTK boundary patch against native v10 U and p faces.

    Patch-face correspondence is established from the serialized face geometry,
    not from the VTK cell-array position. The audit supports explicit uniform or
    nonuniform patch values, zeroGradient fields, and noSlip velocity.
    """
    if type(ascii_precision) is not int or not 6 <= ascii_precision <= 17:
        raise ValueError("ASCII precision must be an integer from 6 through 17 significant digits")
    if not isinstance(patch_name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", patch_name) is None:
        raise ValueError("OpenFOAM patch name must be a simple word")
    mesh_root = Path(poly_mesh_directory)
    if mesh_root.is_symlink() or not mesh_root.is_dir():
        raise ValueError("OpenFOAM polyMesh directory must be a regular, non-symlink directory")

    points, points_sha = _read_openfoam_mesh_points(mesh_root / "points", mesh_root)
    faces, faces_sha = _read_openfoam_mesh_faces(mesh_root / "faces", len(points), mesh_root)
    owners, owners_sha = _read_openfoam_mesh_owners(mesh_root / "owner", len(faces), mesh_root)
    patches, boundary_sha = _read_openfoam_boundary_patches(mesh_root / "boundary", len(faces), mesh_root)
    matching_patches = [patch for patch in patches if patch["name"] == patch_name]
    if len(matching_patches) != 1:
        raise ValueError("Requested OpenFOAM patch is missing or ambiguous")
    patch = matching_patches[0]
    face_ids = list(range(patch["start_face"], patch["start_face"] + patch["face_count"]))

    native_u, native_u_sha = _read_native_openfoam_velocity(native_u_path)
    native_p, native_p_sha = _read_native_openfoam_pressure(native_p_path)
    u_text, checked_u_sha = _read_stable_ascii_file(native_u_path, "Native OpenFOAM U")
    p_text, checked_p_sha = _read_stable_ascii_file(native_p_path, "Native OpenFOAM p")
    if native_u_sha != checked_u_sha or native_p_sha != checked_p_sha:
        raise ValueError("Native OpenFOAM field changed during patch-parity ingestion")
    expected_u, u_boundary_type = _foam_patch_expected_values(
        u_text, "U", patch_name, 3, native_u, owners, face_ids
    )
    expected_p, p_boundary_type = _foam_patch_expected_values(
        p_text, "p", patch_name, 1, native_p, owners, face_ids
    )

    source = Path(vtk_patch_path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("foamToVTK patch must be a regular, non-symlink file")
    before = source.stat()
    if before.st_size > MAX_VTK_BYTES:
        raise ValueError("VTK patch file exceeds bounded input limit")
    with source.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    try:
        import vtk
    except ImportError as exc:
        raise RuntimeError("pip install vtk to read VTK patch surface data") from exc
    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(str(source))
    reader.Update()
    dataset = reader.GetOutput()
    after = source.stat()
    if (after.st_mtime_ns, after.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError("VTK patch file changed during field-parity ingestion")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source_sha:
            raise ValueError("VTK patch content changed during field-parity ingestion")
    count = patch["face_count"]
    if dataset is None or dataset.GetNumberOfCells() != count:
        raise ValueError("Native OpenFOAM and VTK patch face counts differ")

    cell_data = dataset.GetCellData()
    patch_ids = cell_data.GetArray("patchID")
    velocity = cell_data.GetArray("U")
    pressure = cell_data.GetArray("p")
    if patch_ids is None or patch_ids.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK patch must contain scalar patchID cell data")
    if velocity is None or velocity.GetNumberOfComponents() != 3:
        raise ValueError("foamToVTK patch must contain three-component cell-data U")
    if pressure is None or pressure.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK patch must contain scalar cell-data p")
    if velocity.GetDataTypeAsString() != "float" or pressure.GetDataTypeAsString() != "float":
        raise ValueError("Patch parity tolerance requires foamToVTK float32 U and p representations")

    native_faces = {}
    for face_id in face_ids:
        native_signature = _patch_face_signature(
            (points[point_id] for point_id in faces[face_id]), ascii_precision
        )
        if native_signature in native_faces:
            raise ValueError("OpenFOAM patch contains ambiguous duplicate face geometry")
        native_faces[native_signature] = face_id
    mapped = {}
    for vtk_index in range(count):
        vtk_cell = dataset.GetCell(vtk_index)
        if vtk_cell is None or vtk_cell.GetNumberOfPoints() < 3:
            raise ValueError("foamToVTK patch contains a non-polygon cell")
        vtk_signature = _patch_face_signature(
            (dataset.GetPoint(vtk_cell.GetPointId(point_index))
             for point_index in range(vtk_cell.GetNumberOfPoints())),
            ascii_precision,
        )
        face_id = native_faces.pop(vtk_signature, None)
        if face_id is None:
            raise ValueError("foamToVTK patch face geometry does not match the native boundary")
        mapped[vtk_index] = face_id
        patch_id = float(patch_ids.GetTuple1(vtk_index))
        if not math.isfinite(patch_id) or not patch_id.is_integer() or int(patch_id) != patch["patch_id"]:
            raise ValueError("foamToVTK patchID does not match the native boundary patch index")
    if native_faces:
        raise ValueError("foamToVTK patch does not cover every native boundary face")

    maximum_u_error = maximum_p_error = 0.0
    maximum_u_allowed = maximum_p_allowed = 0.0
    maximum_u_float32_residual = maximum_p_float32_residual = 0.0
    maximum_u_relative = maximum_p_relative = 0.0
    for vtk_index, face_id in mapped.items():
        local_index = face_id - patch["start_face"]
        vtk_u = tuple(float(value) for value in velocity.GetTuple3(vtk_index))
        vtk_p = float(pressure.GetTuple1(vtk_index))
        native_vector = expected_u[local_index]
        native_scalar = expected_p[local_index]
        if not all(math.isfinite(value) for value in vtk_u) or not math.isfinite(vtk_p):
            raise ValueError("foamToVTK patch U or p contains a non-finite value")
        for native_value, vtk_value in zip(native_vector, vtk_u):
            expected_float32, conversion_bound = _float32_rounding_bound(native_value)
            serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
            reader_bound = conversion_bound + serialization_bound
            allowed = conversion_bound + reader_bound
            residual = abs(vtk_value - expected_float32)
            if residual > reader_bound + 4.0 * math.ulp(expected_float32):
                raise ValueError("foamToVTK patch U differs from the native boundary value beyond ASCII precision")
            error = abs(vtk_value - native_value)
            maximum_u_error = max(maximum_u_error, error)
            maximum_u_allowed = max(maximum_u_allowed, allowed)
            maximum_u_float32_residual = max(maximum_u_float32_residual, residual)
            if native_value != 0.0:
                maximum_u_relative = max(maximum_u_relative, error / abs(native_value))
        expected_float32, conversion_bound = _float32_rounding_bound(native_scalar)
        serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
        reader_bound = conversion_bound + serialization_bound
        allowed = conversion_bound + reader_bound
        residual = abs(vtk_p - expected_float32)
        if residual > reader_bound + 4.0 * math.ulp(expected_float32):
            raise ValueError("foamToVTK patch p differs from the native boundary value beyond ASCII precision")
        error = abs(vtk_p - native_scalar)
        maximum_p_error = max(maximum_p_error, error)
        maximum_p_allowed = max(maximum_p_allowed, allowed)
        maximum_p_float32_residual = max(maximum_p_float32_residual, residual)
        if native_scalar != 0.0:
            maximum_p_relative = max(maximum_p_relative, error / abs(native_scalar))

    mesh_hashes = {
        "points": points_sha,
        "faces": faces_sha,
        "owner": owners_sha,
        "boundary": boundary_sha,
    }
    return {
        "status": "PASS",
        "patch": patch_name,
        "patch_id": patch["patch_id"],
        "native_face_count": count,
        "vtk_face_count": dataset.GetNumberOfCells(),
        "face_mapping": "complete_unique_geometry_signature_at_ascii_precision",
        "compared_velocity_components": count * 3,
        "compared_pressure_values": count,
        "native_u_boundary_type": u_boundary_type,
        "native_p_boundary_type": p_boundary_type,
        "native_mesh_sha256": mesh_hashes,
        "native_u_sha256": native_u_sha,
        "native_p_sha256": native_p_sha,
        "vtk_sha256": source_sha,
        "ascii_significant_digits": ascii_precision,
        "max_absolute_velocity_error_m_s": maximum_u_error,
        "max_allowed_velocity_error_m_s": maximum_u_allowed,
        "max_float32_velocity_residual_m_s": maximum_u_float32_residual,
        "max_relative_velocity_error": maximum_u_relative,
        "max_absolute_pressure_error_m2_s2": maximum_p_error,
        "max_allowed_pressure_error_m2_s2": maximum_p_allowed,
        "max_float32_pressure_residual_m2_s2": maximum_p_float32_residual,
        "max_relative_pressure_error": maximum_p_relative,
        "tolerance_basis": "two IEEE-754 binary32 round-to-nearest bounds (field cast and VTK reader) plus half-unit in the last place for the configured ASCII significant-digit precision",
    }


def audit_openfoam_vtk_surface_flux(
    native_phi_path,
    poly_mesh_directory,
    vtk_surface_path,
    *,
    ascii_precision=OPENFOAM_VTK_ASCII_PRECISION,
):
    """Compare Foundation v10 surfaceScalarField phi with foamToVTK output.

    Foundation v10 writes surface fields as face-centre points, with phi
    represented as the vector phi times the oriented unit face normal. The
    native polyMesh face index is checked against each serialized centre before
    comparing its vector components.
    """
    if type(ascii_precision) is not int or not 6 <= ascii_precision <= 17:
        raise ValueError("ASCII precision must be an integer from 6 through 17 significant digits")
    mesh_root = Path(poly_mesh_directory)
    if mesh_root.is_symlink() or not mesh_root.is_dir():
        raise ValueError("OpenFOAM polyMesh directory must be a regular, non-symlink directory")

    points, points_sha = _read_openfoam_mesh_points(mesh_root / "points", mesh_root)
    faces, faces_sha = _read_openfoam_mesh_faces(mesh_root / "faces", len(points), mesh_root)
    if not 0 < len(faces) <= MAX_OPENFOAM_FACES:
        raise ValueError("OpenFOAM mesh face count is invalid or exceeds the audit limit")
    owners, owners_sha = _read_openfoam_mesh_owners(mesh_root / "owner", len(faces), mesh_root)
    neighbours, neighbours_sha = _read_openfoam_mesh_neighbours(
        mesh_root / "neighbour", len(faces), mesh_root
    )
    patches, boundary_sha = _read_openfoam_boundary_patches(mesh_root / "boundary", len(faces), mesh_root)
    if not patches or min(patch["start_face"] for patch in patches) != len(neighbours):
        raise ValueError("OpenFOAM boundary does not begin after the internal faces")
    if any(owner < 0 for owner in owners) or any(neighbour < 0 for neighbour in neighbours):
        raise ValueError("OpenFOAM mesh contains a negative cell reference")

    native_values, native_sha, boundary_types = _read_native_openfoam_surface_flux(
        native_phi_path, len(neighbours), patches
    )
    if len(native_values) != len(faces):
        raise ValueError("Native OpenFOAM phi does not cover every polyMesh face")
    centres, normals = _openfoam_face_centres_and_normals(points, faces)

    source = Path(vtk_surface_path)
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".vtk":
        raise ValueError("foamToVTK surface-field output must be a regular legacy VTK file")
    before = source.stat()
    if before.st_size > MAX_VTK_BYTES:
        raise ValueError("VTK surface-field file exceeds bounded input limit")
    with source.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    try:
        import vtk
    except ImportError as exc:
        raise RuntimeError("pip install vtk to read VTK surface-field data") from exc
    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(str(source))
    reader.Update()
    dataset = reader.GetOutput()
    after = source.stat()
    if (after.st_mtime_ns, after.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError("VTK surface-field file changed during parity ingestion")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source_sha:
            raise ValueError("VTK surface-field content changed during parity ingestion")
    if dataset is None or dataset.GetNumberOfPoints() != len(faces) or dataset.GetNumberOfCells() != 0:
        raise ValueError("foamToVTK surface-field points do not cover the native mesh faces")

    flux_vectors = dataset.GetPointData().GetArray("phi")
    if flux_vectors is None or flux_vectors.GetNumberOfComponents() != 3:
        raise ValueError("foamToVTK surface fields must contain three-component phi vectors")
    if flux_vectors.GetNumberOfTuples() != len(faces):
        raise ValueError("foamToVTK phi vector count differs from the native mesh face count")
    if flux_vectors.GetDataTypeAsString() != "float":
        raise ValueError("Surface-flux parity requires the foamToVTK float32 representation")

    max_flux_error = 0.0
    max_flux_allowed = 0.0
    max_centre_error = 0.0
    max_centre_allowed = 0.0
    compared_components = 0
    for face_id, (native_phi, centre, normal) in enumerate(zip(native_values, centres, normals)):
        vtk_centre = tuple(float(value) for value in dataset.GetPoint(face_id))
        vtk_vector = tuple(float(value) for value in flux_vectors.GetTuple3(face_id))
        if not all(math.isfinite(value) for value in (*vtk_centre, *vtk_vector)):
            raise ValueError("foamToVTK surface-field points or phi vectors contain non-finite values")
        expected_vector = tuple(native_phi * component for component in normal)
        for native_value, vtk_value in zip(centre, vtk_centre):
            expected_float32, conversion_bound = _float32_rounding_bound(native_value)
            serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
            reader_bound = conversion_bound + serialization_bound
            allowed = conversion_bound + reader_bound
            residual = abs(vtk_value - expected_float32)
            if residual > reader_bound + 4.0 * math.ulp(expected_float32):
                raise ValueError("foamToVTK face centre differs from the native polyMesh face ordering")
            max_centre_error = max(max_centre_error, abs(vtk_value - native_value))
            max_centre_allowed = max(max_centre_allowed, allowed)
        for native_value, vtk_value in zip(expected_vector, vtk_vector):
            expected_float32, conversion_bound = _float32_rounding_bound(native_value)
            serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
            reader_bound = conversion_bound + serialization_bound
            allowed = conversion_bound + reader_bound
            residual = abs(vtk_value - expected_float32)
            if residual > reader_bound + 4.0 * math.ulp(expected_float32):
                raise ValueError("foamToVTK phi differs from native face flux beyond float32/ASCII precision")
            max_flux_error = max(max_flux_error, abs(vtk_value - native_value))
            max_flux_allowed = max(max_flux_allowed, allowed)
            compared_components += 1

    return {
        "status": "PASS",
        "field": "phi",
        "dimensions": "[0 3 -1 0 0 0 0]",
        "field_representation": "phi_times_oriented_unit_face_normal",
        "face_mapping": "native_polyMesh_face_index_verified_by_serialized_face_centres",
        "face_count": len(faces),
        "internal_face_count": len(neighbours),
        "boundary_face_count": len(faces) - len(neighbours),
        "compared_flux_vector_components": compared_components,
        "boundary_field_types": boundary_types,
        "native_field_sha256": native_sha,
        "vtk_sha256": source_sha,
        "vtk_phi_scalar_type": flux_vectors.GetDataTypeAsString(),
        "ascii_significant_digits": ascii_precision,
        "max_absolute_flux_error_m3_s": max_flux_error,
        "max_allowed_flux_error_m3_s": max_flux_allowed,
        "max_face_centre_error_m": max_centre_error,
        "max_allowed_face_centre_error_m": max_centre_allowed,
        "native_mesh_sha256": {
            "points": points_sha,
            "faces": faces_sha,
            "owner": owners_sha,
            "neighbour": neighbours_sha,
            "boundary": boundary_sha,
        },
        "tolerance_basis": "two IEEE-754 binary32 round-to-nearest bounds (field cast and VTK reader) plus half-unit in the last place for the configured ASCII significant-digit precision",
    }

def _cell_polyhedron_volume(points, oriented_faces):
    point_ids = sorted({point_id for face in oriented_faces for point_id in face})
    if len(oriented_faces) < 4 or len(point_ids) < 4:
        raise ValueError("OpenFOAM mesh cell has an incomplete polyhedron")

    # A local reference keeps the signed tetrahedron sum well-conditioned for
    # rooms whose origin is far from (0, 0, 0).
    reference = tuple(
        math.fsum(points[point_id][axis] for point_id in point_ids) / len(point_ids)
        for axis in range(3)
    )
    terms = []
    edge_uses = {}
    for face in oriented_faces:
        for start, end in zip(face, face[1:] + face[:1]):
            key = (min(start, end), max(start, end))
            count, direction = edge_uses.get(key, (0, 0))
            edge_uses[key] = (count + 1, direction + (1 if start < end else -1))

        origin = tuple(points[face[0]][axis] - reference[axis] for axis in range(3))
        for index in range(1, len(face) - 1):
            first = tuple(points[face[index]][axis] - reference[axis] for axis in range(3))
            second = tuple(points[face[index + 1]][axis] - reference[axis] for axis in range(3))
            cross = (
                first[1] * second[2] - first[2] * second[1],
                first[2] * second[0] - first[0] * second[2],
                first[0] * second[1] - first[1] * second[0],
            )
            terms.append(sum(origin[axis] * cross[axis] for axis in range(3)))

    if any(count != 2 or direction != 0 for count, direction in edge_uses.values()):
        raise ValueError("OpenFOAM mesh cell faces do not form a closed oriented shell")
    volume = math.fsum(terms) / 6.0
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("OpenFOAM mesh cell has a non-positive or invalid volume")
    return volume


def _decimal_significant_digits(token):
    mantissa = re.split(r"[eE]", token, maxsplit=1)[0].lstrip("+-")
    digits = mantissa.replace(".", "").lstrip("0")
    return max(1, len(digits))


def _decimal_half_step(token, significant_digits):
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError("checkMesh volume summary contains an invalid number") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("checkMesh volume summary must contain finite positive values")
    quantum = Decimal(1).scaleb(value.adjusted() - significant_digits + 1)
    return float(quantum / Decimal(2))


def _binary64_roundoff_bound(*values):
    scale = max(1.0, *(abs(value) for value in values))
    return 128.0 * math.ulp(1.0) * scale


def _parse_checkmesh_volume_summary(log_text):
    number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    summary_pattern = re.compile(
        rf"(?m)^\s*Min volume\s*=\s*(?P<minimum>{number})\.\s*"
        rf"Max volume\s*=\s*(?P<maximum>{number})\.\s*"
        rf"Total volume\s*=\s*(?P<total>{number})\.\s*Cell volumes OK\.\s*$"
    )
    summaries = list(summary_pattern.finditer(log_text))
    cell_counts = re.findall(r"(?m)^\s*cells:\s*(\d+)\s*$", log_text)
    if len(summaries) != 1 or len(cell_counts) != 1 or log_text.count("Mesh OK.") != 1:
        raise ValueError("checkMesh log must have one complete volume summary and Mesh OK marker")
    summary = summaries[0]
    tokens = {name: summary.group(name) for name in ("minimum", "maximum", "total")}
    try:
        reported = {name: float(Decimal(token)) for name, token in tokens.items()}
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("checkMesh volume summary contains an invalid number") from exc
    cells = int(cell_counts[0])
    precision = max(_decimal_significant_digits(token) for token in tokens.values())
    rounding_bounds = {
        name: _decimal_half_step(token, precision) for name, token in tokens.items()
    }
    lower_total = cells * max(0.0, reported["minimum"] - rounding_bounds["minimum"])
    upper_total = cells * (reported["maximum"] + rounding_bounds["maximum"])
    arithmetic_bound = _binary64_roundoff_bound(lower_total, upper_total, reported["total"])
    if (
        cells <= 0
        or not all(math.isfinite(value) and value > 0 for value in reported.values())
        or reported["minimum"] > reported["maximum"]
        or reported["total"] < lower_total - rounding_bounds["total"] - arithmetic_bound
        or reported["total"] > upper_total + rounding_bounds["total"] + arithmetic_bound
    ):
        raise ValueError("checkMesh volume summary has inconsistent cell volumes")
    return {
        "cell_count": cells,
        "tokens": tokens,
        "volumes_m3": reported,
        "inferred_significant_digits": precision,
    }


def audit_openfoam_checkmesh_poly_mesh_volume(
    case_directory,
    *,
    expected_cell_count,
    expected_nominal_cell_volume_m3,
    checkmesh_log_sha256,
):
    """Cross-check receipt-bound checkMesh volumes against raw polyMesh geometry.

    The volume reconstruction uses OpenFOAM points, faces, owner and neighbour
    lists directly. It is a mesh-integrity check for generated synthetic cases;
    it is not a mesh-quality acceptance rule or physical validation.
    """
    if type(expected_cell_count) is not int or not 0 < expected_cell_count <= MAX_VTK_CELLS:
        raise ValueError("Expected mesh cell count is invalid")
    if type(expected_nominal_cell_volume_m3) not in (int, float):
        raise ValueError("Expected nominal cell volume must be numeric")
    expected_nominal_cell_volume_m3 = float(expected_nominal_cell_volume_m3)
    if (
        not math.isfinite(expected_nominal_cell_volume_m3)
        or expected_nominal_cell_volume_m3 <= 0
    ):
        raise ValueError("Expected nominal cell volume must be finite and positive")
    expected_room_volume_m3 = expected_cell_count * expected_nominal_cell_volume_m3
    if not isinstance(checkmesh_log_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", checkmesh_log_sha256) is None:
        raise ValueError("checkMesh receipt digest is invalid")

    case_root = Path(case_directory)
    if case_root.is_symlink() or not case_root.is_dir():
        raise ValueError("OpenFOAM case directory must be regular and non-symbolic")
    case_root = case_root.resolve(strict=True)
    log_text, log_sha256 = _read_stable_ascii_file(
        case_root / "checkMesh.log", "OpenFOAM checkMesh log", root=case_root
    )
    if log_sha256 != checkmesh_log_sha256:
        raise ValueError("checkMesh log digest differs from its execution receipt")

    checkmesh_summary = _parse_checkmesh_volume_summary(log_text)
    tokens = checkmesh_summary["tokens"]
    reported = checkmesh_summary["volumes_m3"]
    reported_cells = checkmesh_summary["cell_count"]
    if (
        reported_cells != expected_cell_count
        or not all(math.isfinite(value) and value > 0 for value in reported.values())
        or reported["minimum"] > reported["maximum"]
    ):
        raise ValueError("checkMesh summary is inconsistent with expected mesh dimensions")

    mesh_root = case_root / "constant" / "polyMesh"
    if (case_root / "constant").is_symlink() or mesh_root.is_symlink() or not mesh_root.is_dir():
        raise ValueError("OpenFOAM polyMesh directory must be regular and non-symbolic")
    points, points_sha = _read_openfoam_mesh_points(mesh_root / "points", mesh_root)
    faces, faces_sha = _read_openfoam_mesh_faces(mesh_root / "faces", len(points), mesh_root)
    owners, owners_sha = _read_openfoam_mesh_owners(mesh_root / "owner", len(faces), mesh_root)
    neighbours, neighbours_sha = _read_openfoam_mesh_neighbours(
        mesh_root / "neighbour", len(faces), mesh_root
    )
    patches, boundary_sha = _read_openfoam_boundary_patches(
        mesh_root / "boundary", len(faces), mesh_root
    )
    if not points or len(owners) != len(faces) or not neighbours:
        raise ValueError("OpenFOAM polyMesh is incomplete or has no internal faces")
    if not patches or min(patch["start_face"] for patch in patches) != len(neighbours):
        raise ValueError("OpenFOAM internal and boundary face ranges do not match neighbour count")

    cell_ids = owners + neighbours
    if any(cell_id < 0 for cell_id in cell_ids):
        raise ValueError("OpenFOAM polyMesh contains a negative cell index")
    cell_count = max(cell_ids) + 1
    if cell_count != expected_cell_count or set(cell_ids) != set(range(cell_count)):
        raise ValueError("OpenFOAM polyMesh cell addressing is incomplete or differs from inputs")

    cell_faces = [[] for _ in range(cell_count)]
    for face_id, face in enumerate(faces):
        owner = owners[face_id]
        cell_faces[owner].append(face)
        if face_id < len(neighbours):
            neighbour = neighbours[face_id]
            if neighbour == owner or neighbour >= cell_count:
                raise ValueError("OpenFOAM polyMesh has invalid internal face ownership")
            cell_faces[neighbour].append(list(reversed(face)))
    volumes = [_cell_polyhedron_volume(points, oriented_faces) for oriented_faces in cell_faces]
    total_volume = math.fsum(volumes)
    lower = [min(point[axis] for point in points) for axis in range(3)]
    upper = [max(point[axis] for point in points) for axis in range(3)]
    extents = [high - low for low, high in zip(lower, upper)]
    if any(not math.isfinite(extent) or extent <= 0 for extent in extents):
        raise ValueError("OpenFOAM polyMesh has an invalid bounding box")
    bounding_box_volume = math.prod(extents)

    precision = checkmesh_summary["inferred_significant_digits"]
    serialization_bounds = {
        name: _decimal_half_step(token, precision) for name, token in tokens.items()
    }
    comparisons = {
        "minimum_cell_volume_m3": {
            "difference": abs(reported["minimum"] - min(volumes)),
            "allowed_difference": serialization_bounds["minimum"]
            + _binary64_roundoff_bound(reported["minimum"], min(volumes)),
        },
        "maximum_cell_volume_m3": {
            "difference": abs(reported["maximum"] - max(volumes)),
            "allowed_difference": serialization_bounds["maximum"]
            + _binary64_roundoff_bound(reported["maximum"], max(volumes)),
        },
        "total_volume_m3": {
            "difference": abs(reported["total"] - total_volume),
            "allowed_difference": serialization_bounds["total"]
            + _binary64_roundoff_bound(reported["total"], total_volume),
        },
    }
    room_tolerance = _binary64_roundoff_bound(
        expected_room_volume_m3, total_volume, bounding_box_volume
    )
    comparisons["poly_mesh_total_to_room_volume_m3"] = {
        "difference": abs(total_volume - expected_room_volume_m3),
        "allowed_difference": room_tolerance,
    }
    comparisons["poly_mesh_total_to_bounding_box_volume_m3"] = {
        "difference": abs(total_volume - bounding_box_volume),
        "allowed_difference": room_tolerance,
    }
    comparisons["checkmesh_total_to_room_volume_m3"] = {
        "difference": abs(reported["total"] - expected_room_volume_m3),
        "allowed_difference": serialization_bounds["total"] + room_tolerance,
    }
    if any(row["difference"] > row["allowed_difference"] for row in comparisons.values()):
        raise ValueError("checkMesh, polyMesh and room-bound volumes do not agree")

    return {
        "schema_version": "cleanroomx.openfoam-poly-mesh-volume-audit.v1",
        "status": "PASS",
        "qualification_status": "DIAGNOSTIC_ONLY",
        "scientific_validation": "BLOCKED",
        "cell_count": cell_count,
        "checkmesh_log_sha256": log_sha256,
        "checkmesh": {
            "minimum_cell_volume_m3": reported["minimum"],
            "maximum_cell_volume_m3": reported["maximum"],
            "total_volume_m3": reported["total"],
            "reported_cell_count": reported_cells,
            "printed_volume_tokens": tokens,
        },
        "poly_mesh": {
            "point_count": len(points),
            "face_count": len(faces),
            "internal_face_count": len(neighbours),
            "boundary_patch_count": len(patches),
            "minimum_cell_volume_m3": min(volumes),
            "maximum_cell_volume_m3": max(volumes),
            "total_cell_volume_m3": total_volume,
            "bounding_box_extents_m": extents,
            "bounding_box_volume_m3": bounding_box_volume,
            "files_sha256": {
                "points": points_sha,
                "faces": faces_sha,
                "owner": owners_sha,
                "neighbour": neighbours_sha,
                "boundary": boundary_sha,
            },
        },
        "room_bound": {
            "cell_count": expected_cell_count,
            "nominal_cell_volume_m3": expected_nominal_cell_volume_m3,
            "volume_m3": expected_room_volume_m3,
        },
        "comparisons": comparisons,
        "checkmesh_inferred_significant_digits": precision,
        "tolerance_basis": (
            "checkMesh decimal serialization half-step inferred from the longest numeric "
            "lexeme in its Min/Max/Total volume record, plus 128 * binary64 epsilon * "
            "max(1, abs(value)); room-bound comparisons use the same scaled bound. "
            "These are data-representation tolerances, "
            "not CFD or physical acceptance thresholds."
        ),
    }


def _foam_patch_expected_values(text, field_name, patch_name, components, internal_values, owners, face_ids):
    clean = _strip_foam_comments(text)
    expected_class = "volVectorField" if components == 3 else "volScalarField"
    if not re.search(rf"\bclass\s+{expected_class}\s*;", clean):
        raise ValueError(f"Native OpenFOAM {field_name} is not a {expected_class}")
    if not re.search(rf"\bobject\s+{re.escape(field_name)}\s*;", clean):
        raise ValueError(f"Native OpenFOAM field object is not {field_name}")
    boundary = _extract_foam_braced_block(clean, "boundaryField", f"Native OpenFOAM {field_name}")
    patch_text = _extract_foam_braced_block(boundary, patch_name, f"Native OpenFOAM {field_name} boundary")
    types = re.findall(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", patch_text)
    if len(types) != 1:
        raise ValueError(f"Native OpenFOAM {field_name} patch must declare exactly one boundary type")
    boundary_type = types[0]
    if boundary_type == "zeroGradient":
        values = []
        for face_id in face_ids:
            if not 0 <= face_id < len(owners) or not 0 <= owners[face_id] < len(internal_values):
                raise ValueError("OpenFOAM boundary owner is outside the native internal field")
            values.append(internal_values[owners[face_id]])
        return values, boundary_type
    if boundary_type == "noSlip" and components == 3:
        return [(0.0, 0.0, 0.0)] * len(face_ids), boundary_type

    uniform = re.findall(r"\bvalue\s+uniform\s+([^;]+);", patch_text)
    nonuniform = re.findall(
        r"\bvalue\s+nonuniform\s+List\s*<\s*(vector|scalar)\s*>\s*(\d+)\s*\((.*?)\)\s*;",
        patch_text,
        flags=re.DOTALL,
    )
    if len(uniform) == 1 and not nonuniform:
        token = uniform[0].strip()
        if components == 3:
            match = _FOAM_VECTOR.fullmatch(token)
            if match is None:
                raise ValueError(f"Native OpenFOAM {field_name} uniform patch value is not a vector")
            one_value = tuple(float(component) for component in match.groups())
        else:
            if re.fullmatch(_FOAM_NUMBER, token) is None:
                raise ValueError(f"Native OpenFOAM {field_name} uniform patch value is not a scalar")
            one_value = float(token)
        values = [one_value] * len(face_ids)
    elif not uniform and len(nonuniform) == 1:
        value_type, declared_count, value_body = nonuniform[0]
        expected_type = "vector" if components == 3 else "scalar"
        if value_type != expected_type or int(declared_count) != len(face_ids):
            raise ValueError(f"Native OpenFOAM {field_name} patch value count or type is invalid")
        if components == 3:
            matches = list(_FOAM_VECTOR.finditer(value_body))
            if len(matches) != len(face_ids) or _FOAM_VECTOR.sub("", value_body).strip():
                raise ValueError(f"Native OpenFOAM {field_name} patch vectors do not match their declared count")
            values = [tuple(float(value) for value in match.groups()) for match in matches]
        else:
            tokens = re.findall(_FOAM_NUMBER, value_body)
            if len(tokens) != len(face_ids) or re.sub(_FOAM_NUMBER, "", value_body).strip():
                raise ValueError(f"Native OpenFOAM {field_name} patch scalars do not match their declared count")
            values = [float(token) for token in tokens]
    else:
        raise ValueError(
            f"Native OpenFOAM {field_name} patch type {boundary_type} lacks a supported explicit value"
        )
    scalars = (component for value in values for component in value) if components == 3 else iter(values)
    if not all(math.isfinite(value) for value in scalars):
        raise ValueError(f"Native OpenFOAM {field_name} patch values contain non-finite values")
    return values, boundary_type


def _patch_face_signature(coordinates, precision):
    formatted = []
    for coordinate in coordinates:
        point = []
        for component in coordinate:
            value = float(component)
            if not math.isfinite(value):
                raise ValueError("VTK or OpenFOAM patch geometry contains a non-finite coordinate")
            point.append("0" if value == 0.0 else format(value, f".{precision}g"))
        formatted.append(tuple(point))
    return tuple(sorted(formatted))


def audit_openfoam_vtk_boundary_patch(
    native_u_path,
    native_p_path,
    poly_mesh_directory,
    vtk_patch_path,
    patch_name,
    *,
    ascii_precision=OPENFOAM_VTK_ASCII_PRECISION,
):
    """Audit one foamToVTK boundary patch against native v10 U and p faces.

    Patch-face correspondence is established from the serialized face geometry,
    not from the VTK cell-array position. The audit supports explicit uniform or
    nonuniform patch values, zeroGradient fields, and noSlip velocity.
    """
    if type(ascii_precision) is not int or not 6 <= ascii_precision <= 17:
        raise ValueError("ASCII precision must be an integer from 6 through 17 significant digits")
    if not isinstance(patch_name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", patch_name) is None:
        raise ValueError("OpenFOAM patch name must be a simple word")
    mesh_root = Path(poly_mesh_directory)
    if mesh_root.is_symlink() or not mesh_root.is_dir():
        raise ValueError("OpenFOAM polyMesh directory must be a regular, non-symlink directory")

    points, points_sha = _read_openfoam_mesh_points(mesh_root / "points", mesh_root)
    faces, faces_sha = _read_openfoam_mesh_faces(mesh_root / "faces", len(points), mesh_root)
    owners, owners_sha = _read_openfoam_mesh_owners(mesh_root / "owner", len(faces), mesh_root)
    patches, boundary_sha = _read_openfoam_boundary_patches(mesh_root / "boundary", len(faces), mesh_root)
    matching_patches = [patch for patch in patches if patch["name"] == patch_name]
    if len(matching_patches) != 1:
        raise ValueError("Requested OpenFOAM patch is missing or ambiguous")
    patch = matching_patches[0]
    face_ids = list(range(patch["start_face"], patch["start_face"] + patch["face_count"]))

    native_u, native_u_sha = _read_native_openfoam_velocity(native_u_path)
    native_p, native_p_sha = _read_native_openfoam_pressure(native_p_path)
    u_text, checked_u_sha = _read_stable_ascii_file(native_u_path, "Native OpenFOAM U")
    p_text, checked_p_sha = _read_stable_ascii_file(native_p_path, "Native OpenFOAM p")
    if native_u_sha != checked_u_sha or native_p_sha != checked_p_sha:
        raise ValueError("Native OpenFOAM field changed during patch-parity ingestion")
    expected_u, u_boundary_type = _foam_patch_expected_values(
        u_text, "U", patch_name, 3, native_u, owners, face_ids
    )
    expected_p, p_boundary_type = _foam_patch_expected_values(
        p_text, "p", patch_name, 1, native_p, owners, face_ids
    )

    source = Path(vtk_patch_path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("foamToVTK patch must be a regular, non-symlink file")
    before = source.stat()
    if before.st_size > MAX_VTK_BYTES:
        raise ValueError("VTK patch file exceeds bounded input limit")
    with source.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    try:
        import vtk
    except ImportError as exc:
        raise RuntimeError("pip install vtk to read VTK patch surface data") from exc
    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(str(source))
    reader.Update()
    dataset = reader.GetOutput()
    after = source.stat()
    if (after.st_mtime_ns, after.st_size) != (before.st_mtime_ns, before.st_size):
        raise ValueError("VTK patch file changed during field-parity ingestion")
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source_sha:
            raise ValueError("VTK patch content changed during field-parity ingestion")
    count = patch["face_count"]
    if dataset is None or dataset.GetNumberOfCells() != count:
        raise ValueError("Native OpenFOAM and VTK patch face counts differ")

    cell_data = dataset.GetCellData()
    patch_ids = cell_data.GetArray("patchID")
    velocity = cell_data.GetArray("U")
    pressure = cell_data.GetArray("p")
    if patch_ids is None or patch_ids.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK patch must contain scalar patchID cell data")
    if velocity is None or velocity.GetNumberOfComponents() != 3:
        raise ValueError("foamToVTK patch must contain three-component cell-data U")
    if pressure is None or pressure.GetNumberOfComponents() != 1:
        raise ValueError("foamToVTK patch must contain scalar cell-data p")
    if velocity.GetDataTypeAsString() != "float" or pressure.GetDataTypeAsString() != "float":
        raise ValueError("Patch parity tolerance requires foamToVTK float32 U and p representations")

    native_faces = {}
    for face_id in face_ids:
        native_signature = _patch_face_signature(
            (points[point_id] for point_id in faces[face_id]), ascii_precision
        )
        if native_signature in native_faces:
            raise ValueError("OpenFOAM patch contains ambiguous duplicate face geometry")
        native_faces[native_signature] = face_id
    mapped = {}
    for vtk_index in range(count):
        vtk_cell = dataset.GetCell(vtk_index)
        if vtk_cell is None or vtk_cell.GetNumberOfPoints() < 3:
            raise ValueError("foamToVTK patch contains a non-polygon cell")
        vtk_signature = _patch_face_signature(
            (dataset.GetPoint(vtk_cell.GetPointId(point_index))
             for point_index in range(vtk_cell.GetNumberOfPoints())),
            ascii_precision,
        )
        face_id = native_faces.pop(vtk_signature, None)
        if face_id is None:
            raise ValueError("foamToVTK patch face geometry does not match the native boundary")
        mapped[vtk_index] = face_id
        patch_id = float(patch_ids.GetTuple1(vtk_index))
        if not math.isfinite(patch_id) or not patch_id.is_integer() or int(patch_id) != patch["patch_id"]:
            raise ValueError("foamToVTK patchID does not match the native boundary patch index")
    if native_faces:
        raise ValueError("foamToVTK patch does not cover every native boundary face")

    maximum_u_error = maximum_p_error = 0.0
    maximum_u_allowed = maximum_p_allowed = 0.0
    maximum_u_float32_residual = maximum_p_float32_residual = 0.0
    maximum_u_relative = maximum_p_relative = 0.0
    for vtk_index, face_id in mapped.items():
        local_index = face_id - patch["start_face"]
        vtk_u = tuple(float(value) for value in velocity.GetTuple3(vtk_index))
        vtk_p = float(pressure.GetTuple1(vtk_index))
        native_vector = expected_u[local_index]
        native_scalar = expected_p[local_index]
        if not all(math.isfinite(value) for value in vtk_u) or not math.isfinite(vtk_p):
            raise ValueError("foamToVTK patch U or p contains a non-finite value")
        for native_value, vtk_value in zip(native_vector, vtk_u):
            expected_float32, conversion_bound = _float32_rounding_bound(native_value)
            serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
            reader_bound = conversion_bound + serialization_bound
            allowed = conversion_bound + reader_bound
            residual = abs(vtk_value - expected_float32)
            if residual > reader_bound + 4.0 * math.ulp(expected_float32):
                raise ValueError("foamToVTK patch U differs from the native boundary value beyond ASCII precision")
            error = abs(vtk_value - native_value)
            maximum_u_error = max(maximum_u_error, error)
            maximum_u_allowed = max(maximum_u_allowed, allowed)
            maximum_u_float32_residual = max(maximum_u_float32_residual, residual)
            if native_value != 0.0:
                maximum_u_relative = max(maximum_u_relative, error / abs(native_value))
        expected_float32, conversion_bound = _float32_rounding_bound(native_scalar)
        serialization_bound = _ascii_rounding_bound(expected_float32, ascii_precision)
        reader_bound = conversion_bound + serialization_bound
        allowed = conversion_bound + reader_bound
        residual = abs(vtk_p - expected_float32)
        if residual > reader_bound + 4.0 * math.ulp(expected_float32):
            raise ValueError("foamToVTK patch p differs from the native boundary value beyond ASCII precision")
        error = abs(vtk_p - native_scalar)
        maximum_p_error = max(maximum_p_error, error)
        maximum_p_allowed = max(maximum_p_allowed, allowed)
        maximum_p_float32_residual = max(maximum_p_float32_residual, residual)
        if native_scalar != 0.0:
            maximum_p_relative = max(maximum_p_relative, error / abs(native_scalar))

    mesh_hashes = {
        "points": points_sha,
        "faces": faces_sha,
        "owner": owners_sha,
        "boundary": boundary_sha,
    }
    return {
        "status": "PASS",
        "patch": patch_name,
        "patch_id": patch["patch_id"],
        "native_face_count": count,
        "vtk_face_count": dataset.GetNumberOfCells(),
        "face_mapping": "complete_unique_geometry_signature_at_ascii_precision",
        "compared_velocity_components": count * 3,
        "compared_pressure_values": count,
        "native_u_boundary_type": u_boundary_type,
        "native_p_boundary_type": p_boundary_type,
        "native_mesh_sha256": mesh_hashes,
        "native_u_sha256": native_u_sha,
        "native_p_sha256": native_p_sha,
        "vtk_sha256": source_sha,
        "ascii_significant_digits": ascii_precision,
        "max_absolute_velocity_error_m_s": maximum_u_error,
        "max_allowed_velocity_error_m_s": maximum_u_allowed,
        "max_float32_velocity_residual_m_s": maximum_u_float32_residual,
        "max_relative_velocity_error": maximum_u_relative,
        "max_absolute_pressure_error_m2_s2": maximum_p_error,
        "max_allowed_pressure_error_m2_s2": maximum_p_allowed,
        "max_float32_pressure_residual_m2_s2": maximum_p_float32_residual,
        "max_relative_pressure_error": maximum_p_relative,
        "tolerance_basis": "two IEEE-754 binary32 round-to-nearest bounds (field cast and VTK reader) plus half-unit in the last place for the configured ASCII significant-digit precision",
    }


def validate_vtk_field_map(field_map):
    """Validate explicit semantics/units for extra VTK cell arrays.

    VTK arrays do not preserve OpenFOAM dimension declarations. The caller
    supplies semantic labels and units; CleanroomX never infers them from an
    array name.
    """
    if type(field_map) is not dict or set(field_map) != {"schema_version", "fields"}:
        raise ValueError("field_map must contain schema_version and fields")
    if field_map.get("schema_version") != VTK_FIELD_MAP_SCHEMA:
        raise ValueError(f"field_map schema_version must equal {VTK_FIELD_MAP_SCHEMA}")
    fields = field_map.get("fields")
    if type(fields) is not dict or len(fields) > 12:
        raise ValueError("field_map.fields must be an object with at most twelve arrays")
    normalized = {}
    semantics = set()
    for array_name, definition in fields.items():
        if type(array_name) is not str or not array_name.strip() or len(array_name) > 128:
            raise ValueError("field_map array names must be nonempty text of at most 128 characters")
        if type(definition) is not dict or set(definition) != {"semantic", "units"}:
            raise ValueError(f"field_map entry {array_name!r} must contain semantic and units")
        semantic = definition.get("semantic")
        units = definition.get("units")
        if type(semantic) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", semantic):
            raise ValueError(f"field_map entry {array_name!r} has an invalid semantic identifier")
        if semantic in semantics:
            raise ValueError("field_map semantic identifiers must be unique")
        if type(units) is not str or not units.strip() or len(units) > 64:
            raise ValueError(f"field_map entry {array_name!r} needs explicit units")
        semantics.add(semantic)
        normalized[array_name] = {"semantic": semantic, "units": units.strip()}
    return {"schema_version": VTK_FIELD_MAP_SCHEMA, "fields": normalized}


def import_vtk_case(
    path, *, contaminant_array=None, temperature_array=None,
    temperature_units=None, recirculation_array="recirculating", field_map=None,
    include_mesh_fingerprint=False,
):
    if type(include_mesh_fingerprint) is not bool:
        raise ValueError("include_mesh_fingerprint must be boolean")
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
    cell_count = grid.GetNumberOfCells()
    u=arrays.GetArray("U")
    volumes=arrays.GetArray("CleanroomXVolume")
    if cell_count <= 0:
        raise ValueError("VTK requires at least one volume cell")
    if u is None or u.GetNumberOfComponents()!=3 or u.GetNumberOfTuples()!=cell_count:
        raise ValueError("VTK requires three-component U cell velocity in m/s")
    if volumes is None or volumes.GetNumberOfTuples()!=cell_count:
        raise ValueError("Cannot compute VTK cell volumes")
    for label, array_name in (
        ("contaminant_array", contaminant_array), ("temperature_array", temperature_array)
    ):
        if array_name is not None and (
            type(array_name) is not str or not array_name.strip() or len(array_name) > 128
        ):
            raise ValueError(f"{label} must be a nonempty VTK array name of at most 128 characters")
    if contaminant_array is not None and temperature_array is not None and contaminant_array == temperature_array:
        raise ValueError("One VTK array cannot be both temperature and contaminant concentration")
    if temperature_array is None:
        if temperature_units is not None:
            raise ValueError("temperature_units requires temperature_array")
    elif temperature_units != "K":
        raise ValueError("temperature_array requires explicit temperature_units='K'")
    c=arrays.GetArray(contaminant_array) if contaminant_array is not None else None
    temp=arrays.GetArray(temperature_array) if temperature_array is not None else None
    mask=arrays.GetArray(recirculation_array) if recirculation_array is not None else None
    if contaminant_array is not None and c is None:
        raise ValueError(f"Configured contaminant array {contaminant_array!r} is missing from VTK cell data")
    if temperature_array is not None and temp is None:
        raise ValueError(f"Configured temperature array {temperature_array!r} is missing from VTK cell data")
    if c is not None and (c.GetNumberOfComponents()!=1 or c.GetNumberOfTuples()!=cell_count):
        raise ValueError("Contaminant field must be scalar")
    if temp is not None and (temp.GetNumberOfComponents()!=1 or temp.GetNumberOfTuples()!=cell_count):
        raise ValueError("Temperature field must be scalar")
    if mask is not None and (mask.GetNumberOfComponents()!=1 or mask.GetNumberOfTuples()!=cell_count):
        raise ValueError("Recirculation mask must be scalar")
    map_data = validate_vtk_field_map(field_map) if field_map is not None else None
    cell_volumes = [float(volumes.GetTuple1(index)) for index in range(cell_count)]
    if any(not math.isfinite(value) or value <= 0 for value in cell_volumes):
        raise ValueError("Cannot summarize mapped VTK fields with invalid cell volumes")
    total_cell_volume = math.fsum(cell_volumes)
    imported_fields = {}
    unavailable_fields = []
    if map_data is not None:
        for array_name, definition in map_data["fields"].items():
            array = arrays.GetArray(array_name)
            if array is None:
                unavailable_fields.append({
                    "array_name": array_name,
                    **definition,
                    "reason": "not_present_in_vtk_cell_data",
                })
                continue
            components = array.GetNumberOfComponents()
            if components not in (1, 3) or array.GetNumberOfTuples() != grid.GetNumberOfCells():
                raise ValueError(
                    f"Mapped VTK array {array_name!r} must have one or three components per cell"
                )
            tuples = []
            columns = [[] for _ in range(components)]
            weighted_columns = [[] for _ in range(components)]
            for index in range(grid.GetNumberOfCells()):
                value = tuple(float(x) for x in array.GetTuple(index))
                if len(value) != components or not all(math.isfinite(x) for x in value):
                    raise ValueError(f"Mapped VTK array {array_name!r} has invalid value at cell {index}")
                tuples.append(value[0] if components == 1 else list(value))
                for component, number in enumerate(value):
                    columns[component].append(number)
                    weighted_value = cell_volumes[index] * number
                    if not math.isfinite(weighted_value):
                        raise ValueError(
                            f"Mapped VTK array {array_name!r} has an overflowing weighted value"
                        )
                    weighted_columns[component].append(weighted_value)
            try:
                summary = {
                    "minimum": [min(column) for column in columns],
                    "maximum": [max(column) for column in columns],
                    "mean": [
                        math.fsum(column) / total_cell_volume
                        for column in weighted_columns
                    ],
                    "mean_weighting": "cell_volume",
                }
            except (OverflowError, ValueError) as exc:
                raise ValueError(f"Mapped VTK array {array_name!r} has an overflowing summary") from exc
            imported_fields[definition["semantic"]] = {
                "array_name": array_name,
                "units": definition["units"],
                "units_source": "explicit_caller_field_map",
                "components": components,
                "values": tuples,
                "summary": summary,
            }
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
        if temp is not None:
            val=float(temp.GetTuple1(i))
            if not math.isfinite(val) or val<=0:
                raise ValueError(f"Cell {i}: invalid absolute temperature in K")
            cell["temperature_K"]=val
        if mask is not None:
            value=float(mask.GetTuple1(i))
            if value not in (0,1):
                raise ValueError(f"Cell {i}: recirculating must be exactly 0 or 1")
            cell["recirculating"]=bool(value)
        cells.append(cell)
    result={"cells":cells,"source_sha256":source_sha,"mesh_cells":len(cells),
            "has_contaminant_field":c is not None,
            "contaminant_array":contaminant_array if c is not None else None,
            "has_temperature_field":temp is not None,
            "temperature_field":({"array_name":temperature_array,"units":"K",
                                  "units_source":"explicit_caller_declaration"}
                                 if temp is not None else None),
            "has_recirculation_labels":mask is not None}
    if map_data is not None:
        result["field_map_schema"] = map_data["schema_version"]
        result["field_data"] = imported_fields
        result["unavailable_fields"] = unavailable_fields
    if include_mesh_fingerprint:
        result["mesh_geometry_sha256"] = _vtk_mesh_geometry_sha256(grid)
    return result

def populate_study_from_vtk(
    study, sources, *, solver_name, contaminant_array=None,
    temperature_array=None, temperature_units=None, field_map=None,
):
    if type(solver_name) is not str or not solver_name.strip():
        raise ValueError("solver_name must be nonempty")
    if set(sources)!={1,2,3}: raise ValueError("Provide three VTK source files (1, 2, 3)")
    updated=copy.deepcopy(study)
    cases={item.get("configuration"):item for item in updated.get("cases",[])}
    if set(cases)!={1,2,3} or len(updated["cases"])!=3:
        raise ValueError("Study must contain unique cases 1, 2, 3")
    manifest={}
    for cfg in (1,2,3):
        imported=import_vtk_case(
            sources[cfg], contaminant_array=contaminant_array,
            temperature_array=temperature_array, temperature_units=temperature_units,
            field_map=field_map,
        )
        case=cases[cfg]
        if case.get("cells"): raise ValueError(f"Case {cfg}: refuse to overwrite existing samples")
        case["cells"]=imported["cells"]
        case["solver"]={"name":solver_name,
                        "run_id":imported["source_sha256"][:24],
                        "mesh_cells":imported["mesh_cells"],
                        "source_reference":"sha256:"+imported["source_sha256"]}
        manifest[str(cfg)]={k:v for k,v in imported.items() if k!="cells"}
    validate_study(updated)
    analysis = analyze_cfd_study(updated)
    for result in analysis["cases"]:
        imported = manifest[str(result["configuration"])]
        result["fields"] = copy.deepcopy(imported.get("field_data", {}))
        result["unavailable_fields"] = copy.deepcopy(
            imported.get("unavailable_fields", [])
        )
    return {"study":updated,"import_manifest":manifest,
            "analysis":analysis}
