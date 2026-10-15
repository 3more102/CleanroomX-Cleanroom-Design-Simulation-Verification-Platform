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
_FOAM_INTERNAL_SCALAR_FIELD = re.compile(
    rf"\binternalField\s+nonuniform\s+List\s*<\s*scalar\s*>\s*(\d+)\s*\((.*?)\)\s*;",
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
        point_ids = [int(token) for token in re.findall(r"\d+", match.group(2))]
        if (
            len(point_ids) != face_count
            or face_count < 3
            or len(set(point_ids)) != face_count
            or any(point_id < 0 or point_id >= point_count for point_id in point_ids)
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
    tokens = re.findall(r"\d+", body)
    if count != face_count or len(tokens) != count or re.sub(r"\d+", "", body).strip():
        raise ValueError("OpenFOAM mesh owner list does not match its declared face count")
    return [int(token) for token in tokens], digest


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
