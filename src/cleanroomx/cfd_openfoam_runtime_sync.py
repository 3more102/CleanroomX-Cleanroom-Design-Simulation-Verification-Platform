"""Incrementally import stable OpenFOAM Foundation v10 result writes.

The synchronizer observes native time directories, waits for their selected
field files to stop changing, exports each accepted snapshot with
``foamToVTK`` in an isolated case view, validates the imported cell fields,
and atomically journals immutable, hash-bound results.  A successful import is
data-integrity evidence only; it does not establish solver convergence or
physical validity.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

from .cfd_vtk import (
    MAX_VTK_CELLS,
    OPENFOAM_VTK_ASCII_PRECISION,
    _read_vtk,
    _ascii_rounding_bound,
    _float32_rounding_bound,
    audit_openfoam_vtk_pressure,
    audit_openfoam_vtk_surface_flux,
    audit_openfoam_vtk_velocity,
    import_vtk_case,
)
from .cfd_vtk_time_selection import parse_foam_to_vtk_time_log


SCHEMA = "cleanroomx.openfoam-result-sync.v1"
DEFAULT_OPTIONAL_FIELDS = ("T", "k", "epsilon", "omega", "nut")
MAX_FIELD_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_TIME_DIRECTORIES = 10_000
MAX_OUTPUT_FILES = 10_000
MAX_LOG_STATUS_BYTES = 1024 * 1024
_TIME_NAME = re.compile(r"(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")
_FIELD_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_SIMULATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIMENSIONS = re.compile(r"\bdimensions\s*\[([^\]]+)\]\s*;")
_FOAM_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_FOAM_VECTOR = re.compile(
    rf"\(\s*({_FOAM_NUMBER})\s+({_FOAM_NUMBER})\s+({_FOAM_NUMBER})\s*\)"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _solver_log_status(path: Path) -> str:
    """Classify a solver log without treating an End token alone as success."""
    if path.is_symlink() or not path.is_file():
        return "missing_or_unsafe"
    try:
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - MAX_LOG_STATUS_BYTES))
            content = stream.read(MAX_LOG_STATUS_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return "unreadable"
    if re.search(r"FOAM FATAL ERROR|Fatal Error", content, re.IGNORECASE):
        return "fatal_error_detected"
    nonempty = [line.strip() for line in content.splitlines() if line.strip()]
    return "completed" if nonempty and nonempty[-1] == "End" else "no_terminal_end_marker"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _safe_hash(value: Any, name: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def hash_case_configuration(case_directory: str | Path) -> str:
    """Hash the static OpenFOAM case inputs, excluding solver time outputs."""
    root_candidate = Path(case_directory)
    if root_candidate.is_symlink() or not root_candidate.is_dir():
        raise ValueError("OpenFOAM case must be a regular, non-symlink directory")
    root = root_candidate.resolve(strict=True)
    records: dict[str, str] = {}
    total_bytes = 0
    for dirname in ("system", "constant", "0"):
        folder = root / dirname
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f"OpenFOAM case is missing a regular {dirname} directory")
        for current, directories, filenames in os.walk(folder, followlinks=False):
            current_path = Path(current)
            if current_path.is_symlink():
                raise ValueError("Static OpenFOAM input contains a symbolic directory")
            directories.sort()
            for name in directories:
                if (current_path / name).is_symlink():
                    raise ValueError("Static OpenFOAM input contains a symbolic directory")
            for name in sorted(filenames):
                source = current_path / name
                if source.is_symlink() or not source.is_file():
                    raise ValueError("Static OpenFOAM input contains a symbolic or non-file entry")
                size = source.stat().st_size
                if size > MAX_FIELD_BYTES:
                    raise ValueError("Static OpenFOAM input exceeds the per-file resource limit")
                total_bytes += size
                if total_bytes > MAX_SNAPSHOT_BYTES:
                    raise ValueError("Static OpenFOAM inputs exceed the resource limit")
                relative = source.relative_to(root).as_posix()
                records[relative] = _stable_file_record(source, max_bytes=MAX_FIELD_BYTES)["sha256"]
    if not records:
        raise ValueError("OpenFOAM case has no static input files")
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stable_file_record(path: Path, *, max_bytes: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular, non-symlink file: {path.name}")
    before = path.stat()
    if before.st_size <= 0 or before.st_size > max_bytes:
        raise ValueError(f"File size is empty or exceeds the configured limit: {path.name}")
    digest = hashlib.sha256()
    read_bytes = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            read_bytes += len(chunk)
            if read_bytes > max_bytes:
                raise ValueError(f"File exceeds the configured limit while reading: {path.name}")
            digest.update(chunk)
        after_fd = os.fstat(stream.fileno())
    after_path = path.stat()
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_fd = (after_fd.st_dev, after_fd.st_ino, after_fd.st_size, after_fd.st_mtime_ns)
    identity_after = (after_path.st_dev, after_path.st_ino, after_path.st_size, after_path.st_mtime_ns)
    if identity_before != identity_fd or identity_fd != identity_after or read_bytes != before.st_size:
        raise ValueError(f"File changed while being read: {path.name}")
    return {
        "sha256": digest.hexdigest(),
        "size_bytes": before.st_size,
        "signature": identity_before,
    }


def _field_metadata(path: Path, field_name: str) -> dict[str, Any]:
    record = _stable_file_record(path, max_bytes=MAX_FIELD_BYTES)
    raw = path.read_bytes()
    if len(raw) != record["size_bytes"]:
        raise ValueError(f"OpenFOAM field changed while parsing: {field_name}")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(f"Binary or non-ASCII OpenFOAM field is unsupported: {field_name}") from error
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\r\n]*", " ", text)
    classes = re.findall(r"\bclass\s+([A-Za-z][A-Za-z0-9_]*)\s*;", text)
    objects = re.findall(r"\bobject\s+([A-Za-z][A-Za-z0-9_]*)\s*;", text)
    dimensions = _DIMENSIONS.findall(text)
    if len(classes) != 1 or len(objects) != 1 or len(dimensions) != 1:
        raise ValueError(f"OpenFOAM field header is incomplete or ambiguous: {field_name}")
    field_class = classes[0]
    expected_classes = ("volVectorField",) if field_name == "U" else ("volScalarField", "volVectorField")
    if field_class not in expected_classes or objects[0] != field_name:
        raise ValueError(f"OpenFOAM field class or object name is invalid: {field_name}")
    dimension_tokens = dimensions[0].split()
    if len(dimension_tokens) != 7:
        raise ValueError(f"OpenFOAM field dimensions must contain seven exponents: {field_name}")
    try:
        dimension_values = [float(token) for token in dimension_tokens]
    except ValueError as error:
        raise ValueError(f"OpenFOAM field dimensions are malformed: {field_name}") from error
    if not all(math.isfinite(value) for value in dimension_values):
        raise ValueError(f"OpenFOAM field dimensions are non-finite: {field_name}")
    dimension_string = "[" + " ".join(dimension_tokens) + "]"
    if field_name == "U" and dimension_values != [0, 1, -1, 0, 0, 0, 0]:
        raise ValueError("OpenFOAM velocity U must use m/s dimensions [0 1 -1 0 0 0 0]")
    if field_name == "p" and dimension_values != [0, 2, -2, 0, 0, 0, 0]:
        raise ValueError("OpenFOAM p must use kinematic-pressure dimensions [0 2 -2 0 0 0 0]")
    internal = re.findall(r"\binternalField\s+(uniform|nonuniform)\b", text)
    if len(internal) != 1:
        raise ValueError(f"OpenFOAM field has no unique supported internalField: {field_name}")
    unit_names = {
        "[0 1 -1 0 0 0 0]": "m/s",
        "[0 0 0 1 0 0 0]": "K",
        "[0 2 -2 0 0 0 0]": "m^2/s^2",
        "[0 2 -3 0 0 0 0]": "m^2/s^3",
        "[0 0 -1 0 0 0 0]": "1/s",
        "[0 2 -1 0 0 0 0]": "m^2/s",
    }
    return {
        "field": field_name,
        "class": field_class,
        "components": 3 if field_class == "volVectorField" else 1,
        "uniform_internal_field": internal[0] == "uniform",
        "dimensions": dimension_string,
        "units": (
            "m^2/s^2 (kinematic pressure)" if field_name == "p"
            else unit_names.get(dimension_string, "OpenFOAM dimensions " + dimension_string)
        ),
        "sha256": record["sha256"],
        "size_bytes": record["size_bytes"],
    }


def _time_value(name: str) -> float:
    if _TIME_NAME.fullmatch(name) is None:
        raise ValueError(f"Unsupported OpenFOAM time directory name: {name!r}")
    number = float(name)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"OpenFOAM result time must be finite and greater than zero: {name!r}")
    return number


def _component_ranges(array, cell_count: int) -> list[dict[str, float]]:
    components = array.GetNumberOfComponents()
    tuples = array.GetNumberOfTuples()
    if components not in (1, 3) or tuples != cell_count:
        raise ValueError("VTK cell field has an unsupported shape or incomplete cell coverage")
    minima = [math.inf] * components
    maxima = [-math.inf] * components
    for index in range(tuples):
        values = array.GetTuple(index)
        for component, raw in enumerate(values):
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError("VTK cell field contains a non-finite value")
            minima[component] = min(minima[component], value)
            maxima[component] = max(maxima[component], value)
    return [{"min": minima[i], "max": maxima[i]} for i in range(components)]


def _read_native_volume_values(path: Path, field_metadata: dict[str, Any]) -> tuple[list[Any], str]:
    record = _stable_file_record(path, max_bytes=MAX_FIELD_BYTES)
    raw = path.read_bytes()
    if len(raw) != record["size_bytes"]:
        raise ValueError("OpenFOAM volume field changed while parsing")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Binary or non-ASCII OpenFOAM volume field is unsupported") from error
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\r\n]*", " ", text)
    field_name = field_metadata["field"]
    expected_type = "vector" if field_metadata["components"] == 3 else "scalar"
    uniform = re.findall(r"\binternalField\s+uniform\s+([^;]+);", text)
    nonuniform = re.findall(
        r"\binternalField\s+nonuniform\s+List\s*<\s*(vector|scalar)\s*>\s*"
        r"(\d+)\s*\((.*?)\)\s*;",
        text,
        flags=re.DOTALL,
    )
    if len(uniform) == 1 and not nonuniform:
        token = uniform[0].strip()
        if expected_type == "vector":
            match = _FOAM_VECTOR.fullmatch(token)
            if match is None:
                raise ValueError(f"OpenFOAM {field_name} uniform internal value is not a vector")
            value: Any = tuple(float(component) for component in match.groups())
        else:
            if re.fullmatch(_FOAM_NUMBER, token) is None:
                raise ValueError(f"OpenFOAM {field_name} uniform internal value is not a scalar")
            value = float(token)
        values = [value]
        uniform_value = True
    elif not uniform and len(nonuniform) == 1:
        value_type, count_text, body = nonuniform[0]
        count = int(count_text)
        if value_type != expected_type or not 0 < count <= MAX_VTK_CELLS:
            raise ValueError(f"OpenFOAM {field_name} internal field has invalid type or count")
        if expected_type == "vector":
            matches = list(_FOAM_VECTOR.finditer(body))
            if len(matches) != count or _FOAM_VECTOR.sub("", body).strip():
                raise ValueError(f"OpenFOAM {field_name} vector list does not match its count")
            values = [tuple(float(component) for component in match.groups()) for match in matches]
        else:
            tokens = re.findall(_FOAM_NUMBER, body)
            if len(tokens) != count or re.sub(_FOAM_NUMBER, "", body).strip():
                raise ValueError(f"OpenFOAM {field_name} scalar list does not match its count")
            values = [float(token) for token in tokens]
        uniform_value = False
    else:
        raise ValueError(f"OpenFOAM {field_name} internalField is missing or ambiguous")
    flat_values = (
        [component for value in values for component in value]
        if expected_type == "vector" else values
    )
    if not all(math.isfinite(float(value)) for value in flat_values):
        raise ValueError(f"OpenFOAM {field_name} internalField contains a non-finite value")
    if _stable_file_record(path, max_bytes=MAX_FIELD_BYTES)["sha256"] != record["sha256"]:
        raise ValueError(f"OpenFOAM {field_name} changed while parsing")
    if uniform_value:
        return values, record["sha256"]
    return values, record["sha256"]


def _audit_optional_volume_field(
    path: Path,
    metadata: dict[str, Any],
    vtk_array,
    cell_ids,
    cell_count: int,
) -> dict[str, Any]:
    native_values, native_sha = _read_native_volume_values(path, metadata)
    if len(native_values) == 1 and metadata.get("uniform_internal_field"):
        native_values = native_values * cell_count
    if len(native_values) != cell_count:
        raise ValueError(f"Native OpenFOAM {metadata['field']} cell count differs from VTK")
    components = metadata["components"]
    if vtk_array.GetNumberOfTuples() != cell_count or vtk_array.GetNumberOfComponents() != components:
        raise ValueError(f"Imported VTK {metadata['field']} field does not cover every cell")
    if vtk_array.GetDataTypeAsString() != "float":
        raise ValueError(f"Imported VTK {metadata['field']} is not the expected Foundation v10 float array")

    mapped: dict[int, int] = {}
    for vtk_index in range(cell_count):
        raw_id = float(cell_ids.GetTuple1(vtk_index))
        if not math.isfinite(raw_id) or not raw_id.is_integer():
            raise ValueError("Imported VTK cellID contains a non-integer value")
        cell_id = int(raw_id)
        if not 0 <= cell_id < cell_count or cell_id in mapped:
            raise ValueError("Imported VTK cellID is not a unique in-range permutation")
        mapped[cell_id] = vtk_index
    if len(mapped) != cell_count:
        raise ValueError("Imported VTK cellID does not cover every cell")

    maximum_absolute_error = 0.0
    maximum_relative_error = 0.0
    maximum_allowed_error = 0.0
    compared = 0
    for native_index, native_value in enumerate(native_values):
        native_components = native_value if components == 3 else (native_value,)
        vtk_values = vtk_array.GetTuple(mapped[native_index])
        for native_component, vtk_component_raw in zip(native_components, vtk_values):
            vtk_component = float(vtk_component_raw)
            native_component = float(native_component)
            if not math.isfinite(vtk_component):
                raise ValueError(f"Imported VTK {metadata['field']} contains a non-finite value")
            expected_float32, conversion_bound = _float32_rounding_bound(native_component)
            serialization_bound = _ascii_rounding_bound(
                expected_float32, OPENFOAM_VTK_ASCII_PRECISION
            )
            allowed_reader_error = conversion_bound + serialization_bound
            if abs(vtk_component - expected_float32) > allowed_reader_error + 4 * math.ulp(expected_float32):
                raise ValueError(f"Imported VTK {metadata['field']} differs from its native OpenFOAM field")
            error = abs(vtk_component - native_component)
            maximum_absolute_error = max(maximum_absolute_error, error)
            if native_component != 0:
                maximum_relative_error = max(maximum_relative_error, error / abs(native_component))
            maximum_allowed_error = max(
                maximum_allowed_error,
                conversion_bound + allowed_reader_error,
            )
            compared += 1
    return {
        "status": "PASS",
        "cell_count": cell_count,
        "components_compared": compared,
        "native_field_sha256": native_sha,
        "max_absolute_error_native_to_vtk": maximum_absolute_error,
        "max_relative_error_native_to_vtk": maximum_relative_error,
        "max_allowed_native_to_vtk_error": maximum_allowed_error,
        "tolerance_basis": (
            "Foundation v10 float32 conversion and VTK ASCII rounding bounds "
            f"({OPENFOAM_VTK_ASCII_PRECISION} significant digits)"
        ),
    }


def _validate_vtk_snapshot(
    native_paths: dict[str, Path],
    metadata: dict[str, dict[str, Any]],
    internal_vtk: Path,
    *,
    contaminant_field: str | None,
) -> dict[str, Any]:
    grid = _read_vtk(internal_vtk, require_cell_velocity=True)
    cell_count = grid.GetNumberOfCells()
    if not 0 < cell_count <= MAX_VTK_CELLS:
        raise ValueError("Imported VTK mesh is empty or exceeds CleanroomX cell limits")
    cell_data = grid.GetCellData()
    cell_ids = cell_data.GetArray("cellID")
    if cell_ids is None or cell_ids.GetNumberOfComponents() != 1 or cell_ids.GetNumberOfTuples() != cell_count:
        raise ValueError("Imported VTK dataset must include a complete cellID cell-data array")
    seen: set[int] = set()
    for index in range(cell_count):
        raw_id = float(cell_ids.GetTuple1(index))
        if not math.isfinite(raw_id) or not raw_id.is_integer():
            raise ValueError("Imported VTK cellID is not an integer")
        cell_id = int(raw_id)
        if not 0 <= cell_id < cell_count or cell_id in seen:
            raise ValueError("Imported VTK cellID is not a unique in-range permutation")
        seen.add(cell_id)
    if len(seen) != cell_count:
        raise ValueError("Imported VTK cellID does not cover every cell")

    summaries: dict[str, Any] = {}
    for name, field_metadata in metadata.items():
        array = cell_data.GetArray(name)
        if array is None:
            raise ValueError(f"foamToVTK omitted the requested volume field {name}")
        if array.GetNumberOfComponents() != field_metadata["components"]:
            raise ValueError(f"Imported VTK field component count differs for {name}")
        summaries[name] = {
            "components": field_metadata["components"],
            "units": field_metadata["units"],
            "dimensions": field_metadata["dimensions"],
            "component_ranges": _component_ranges(array, cell_count),
        }

    velocity_parity = audit_openfoam_vtk_velocity(native_paths["U"], internal_vtk)
    pressure_parity = audit_openfoam_vtk_pressure(native_paths["p"], internal_vtk)
    if velocity_parity.get("status") != "PASS" or pressure_parity.get("status") != "PASS":
        raise ValueError("Native OpenFOAM U/p fields did not reproduce in the VTK cell dataset")
    optional_parity = {}
    for name, field_metadata in metadata.items():
        if name in ("U", "p"):
            continue
        optional_parity[name] = _audit_optional_volume_field(
            native_paths[name], field_metadata, cell_data.GetArray(name), cell_ids, cell_count
        )
    analysis_import = import_vtk_case(
        internal_vtk,
        contaminant_array=contaminant_field or "__cleanroomx_no_contaminant_field__",
    )
    if analysis_import.get("mesh_cells") != cell_count:
        raise ValueError("CleanroomX analysis importer reported an inconsistent cell count")
    if contaminant_field is not None and not analysis_import.get("has_contaminant_field"):
        raise ValueError(
            f"Configured contaminant field {contaminant_field!r} is missing from imported VTK cell data"
        )
    return {
        "cell_count": cell_count,
        "fields": summaries,
        "native_vtk_parity": {"U": velocity_parity, "p": pressure_parity, **optional_parity},
        "cleanroomx_analysis_import": {
            "status": "PASS",
            "function": "cleanroomx.cfd_vtk.import_vtk_case",
            "cell_count": cell_count,
            "source_sha256": analysis_import["source_sha256"],
            "has_contaminant_field": analysis_import["has_contaminant_field"],
            "contaminant_field": contaminant_field if analysis_import["has_contaminant_field"] else None,
        },
    }


class OpenFOAMResultSynchronizer:
    """Poll one running case and publish each completed time snapshot once."""

    def __init__(
        self,
        case_directory: str | Path,
        output_directory: str | Path,
        *,
        simulation_id: str,
        configuration_hash: str,
        case_id: str | None = None,
        required_fields: tuple[str, ...] | list[str] = ("U", "p"),
        optional_fields: tuple[str, ...] | list[str] = DEFAULT_OPTIONAL_FIELDS,
        contaminant_field: str | None = None,
        expected_build: str | None = None,
        poll_interval_seconds: float = 1.0,
        settle_polls: int = 2,
        timeout_seconds: int = 600,
        max_field_bytes: int = MAX_FIELD_BYTES,
        max_snapshot_bytes: int = MAX_SNAPSHOT_BYTES,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        max_retries: int = 3,
    ) -> None:
        if type(simulation_id) is not str or _SIMULATION_ID.fullmatch(simulation_id) is None:
            raise ValueError("simulation_id must be a safe 1..128 character identifier")
        self.configuration_hash = _safe_hash(configuration_hash, "configuration_hash")
        if not (type(poll_interval_seconds) in (int, float) and math.isfinite(poll_interval_seconds)
                and 0.1 <= poll_interval_seconds <= 60):
            raise ValueError("poll_interval_seconds must be finite and in [0.1,60]")
        if type(settle_polls) is not int or not 2 <= settle_polls <= 10:
            raise ValueError("settle_polls must be an integer in [2,10]")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be an integer in [1,3600]")
        for name, value in (("max_field_bytes", max_field_bytes),
                            ("max_snapshot_bytes", max_snapshot_bytes),
                            ("max_output_bytes", max_output_bytes)):
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if type(max_retries) is not int or not 1 <= max_retries <= 10:
            raise ValueError("max_retries must be an integer in [1,10]")

        required = tuple(required_fields)
        optional = tuple(optional_fields)
        if contaminant_field is not None and contaminant_field not in optional:
            optional = (*optional, contaminant_field)
        if required != ("U", "p"):
            raise ValueError("Foundation v10 synchronization requires U and p as the primary fields")
        if len(set(optional)) != len(optional) or any(
            type(name) is not str or _FIELD_NAME.fullmatch(name) is None for name in optional
        ):
            raise ValueError("optional_fields must contain unique safe OpenFOAM field names")
        if set(required) & set(optional):
            raise ValueError("required_fields cannot also be optional")
        if "phi" in optional:
            raise ValueError("phi is a surface field and cannot be listed as an optional volume field")
        if contaminant_field is not None and (
            type(contaminant_field) is not str or _FIELD_NAME.fullmatch(contaminant_field) is None
        ):
            raise ValueError("contaminant_field must be a safe OpenFOAM field name")

        case_candidate = Path(case_directory)
        if case_candidate.is_symlink() or not case_candidate.is_dir():
            raise ValueError("OpenFOAM case must be a regular, non-symlink directory")
        self.case_directory = case_candidate.resolve(strict=True)
        for dirname in ("system", "constant"):
            directory = self.case_directory / dirname
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError(f"OpenFOAM case is missing a regular {dirname} directory")

        output_candidate = Path(output_directory)
        if output_candidate.is_symlink() or (output_candidate.exists() and not output_candidate.is_dir()):
            raise ValueError("Synchronization output must be a regular directory")
        self.output_directory = output_candidate.resolve(strict=False)
        if self.output_directory == self.case_directory or self.output_directory.is_relative_to(self.case_directory):
            raise ValueError("Synchronization output cannot be nested inside the OpenFOAM case")
        if not self.output_directory.exists():
            self.output_directory.mkdir(parents=True)
        if any(self.output_directory.iterdir()) and not (self.output_directory / "sync_manifest.json").is_file():
            raise ValueError("Refusing to initialize synchronization in a nonempty unrecognized directory")

        if os.environ.get("WM_PROJECT") != "OpenFOAM" or os.environ.get("WM_PROJECT_VERSION") != "10":
            raise RuntimeError("Expected OpenFOAM Foundation v10 (WM_PROJECT=OpenFOAM, WM_PROJECT_VERSION=10)")
        foam_to_vtk = shutil.which("foamToVTK")
        if foam_to_vtk is None:
            raise RuntimeError("foamToVTK is required for automatic OpenFOAM result synchronization")
        try:
            import vtk  # noqa: F401
        except ImportError as error:
            raise RuntimeError("pip install vtk to synchronize OpenFOAM result fields") from error

        self.simulation_id = simulation_id
        self.configuration_id = case_id or self.case_directory.name
        if type(self.configuration_id) is not str or not self.configuration_id or "\\" in self.configuration_id:
            raise ValueError("case_id must be a nonempty POSIX-style identifier")
        case_parts = Path(self.configuration_id).parts
        if Path(self.configuration_id).is_absolute() or any(part in ("", ".", "..") for part in case_parts):
            raise ValueError("case_id must be a safe relative identifier")
        self.case_id = Path(*case_parts).as_posix()
        self.required_fields = required
        self.optional_fields = optional
        self.allowed_fields = (*required, *optional)
        self.contaminant_field = contaminant_field
        self.expected_build = expected_build
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.settle_polls = settle_polls
        self.timeout_seconds = timeout_seconds
        self.max_field_bytes = max_field_bytes
        self.max_snapshot_bytes = max_snapshot_bytes
        self.max_output_bytes = max_output_bytes
        self.max_retries = max_retries
        self.foam_to_vtk = str(Path(foam_to_vtk).resolve(strict=True))
        self.manifest_path = self.output_directory / "sync_manifest.json"
        self.results_directory = self.output_directory / "results"
        self.results_directory.mkdir(exist_ok=True)
        if self.results_directory.is_symlink():
            raise ValueError("Synchronization results directory cannot be a symbolic link")
        self._observations: dict[str, tuple[tuple[Any, ...], int]] = {}
        self._attempts: dict[str, int] = {}
        self._manifest = self._load_or_create_manifest()
        for error in self._manifest["errors"]:
            if (isinstance(error.get("time_name"), str)
                    and error.get("status") == "not_imported"):
                name = error["time_name"]
                self._attempts[name] = max(self._attempts.get(name, 0), int(error.get("attempt", 0)))
        self._recover_orphans()
        self._output_bytes = self._output_size()
        if self._manifest.get("status") not in (
            "monitoring", "interrupted_resumable", "monitoring_checkpoint"
        ):
            self._manifest["status"] = "monitoring"
            self._manifest["resumed_at_utc"] = _utc_now()
            self._save_manifest()

    def _base_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "status": "monitoring",
            "interpretation": "solver_output_import_and_integrity_only",
            "scientific_validation": "BLOCKED",
            "simulation_id": self.simulation_id,
            "case_id": self.case_id,
            "configuration_hash": self.configuration_hash,
            "solver_release": "OpenFOAM Foundation v10",
            "solver_build": self.expected_build,
            "foamToVTK_executable": self.foam_to_vtk,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "contaminant_field": self.contaminant_field,
            "poll_interval_seconds": self.poll_interval_seconds,
            "settle_polls": self.settle_polls,
            "created_at_utc": _utc_now(),
            "updated_at_utc": _utc_now(),
            "records": {},
            "errors": [],
        }

    def _load_or_create_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            manifest = self._base_manifest()
            _atomic_json(self.manifest_path, manifest)
            return manifest
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise ValueError("Synchronization manifest must be a regular file")
        before = _stable_file_record(self.manifest_path, max_bytes=MAX_SNAPSHOT_BYTES)
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Synchronization manifest is malformed") from error
        if _stable_file_record(self.manifest_path, max_bytes=MAX_SNAPSHOT_BYTES)["sha256"] != before["sha256"]:
            raise ValueError("Synchronization manifest changed while being parsed")
        if (
            type(manifest) is not dict
            or manifest.get("schema_version") != SCHEMA
            or manifest.get("simulation_id") != self.simulation_id
            or manifest.get("case_id") != self.case_id
            or manifest.get("configuration_hash") != self.configuration_hash
            or manifest.get("required_fields") != list(self.required_fields)
            or manifest.get("optional_fields") != list(self.optional_fields)
            or manifest.get("contaminant_field") != self.contaminant_field
            or manifest.get("scientific_validation") != "BLOCKED"
            or type(manifest.get("records")) is not dict
            or type(manifest.get("errors")) is not list
        ):
            raise ValueError("Existing synchronization manifest does not match this simulation/configuration")
        if (self.expected_build is not None
                and manifest.get("solver_build") not in (None, self.expected_build)):
            raise ValueError("OpenFOAM solver build differs from the resumable synchronization manifest")
        if self.expected_build is None:
            self.expected_build = manifest.get("solver_build")
        elif manifest.get("solver_build") is None:
            manifest["solver_build"] = self.expected_build
        for time_name, record in manifest["records"].items():
            _time_value(time_name)
            self._validate_record_assets(record)
        return manifest

    def _asset_path(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
            raise ValueError("Unsafe synchronization asset path")
        candidate = self.output_directory.joinpath(*path.parts)
        current = self.output_directory
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Synchronization asset path contains a symlink")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self.output_directory):
            raise ValueError("Synchronization asset escaped its output directory")
        return resolved

    def _validate_record_assets(self, record: Any) -> None:
        if type(record) is not dict or type(record.get("assets")) is not list:
            raise ValueError("Synchronization record has no asset manifest")
        for asset in record["assets"]:
            if type(asset) is not dict:
                raise ValueError("Synchronization asset entry is malformed")
            path = self._asset_path(asset.get("path", ""))
            expected = _safe_hash(asset.get("sha256"), "asset sha256")
            observed = _stable_file_record(path, max_bytes=self.max_output_bytes)
            if observed["sha256"] != expected or observed["size_bytes"] != asset.get("size_bytes"):
                raise ValueError(f"Previously synchronized result is corrupt or outdated: {asset.get('path')}")
        receipt = record.get("receipt")
        if type(receipt) is not dict:
            raise ValueError("Synchronization record is missing its immutable receipt")
        receipt_path = self._asset_path(receipt.get("path", ""))
        if _stable_file_record(receipt_path, max_bytes=MAX_SNAPSHOT_BYTES)["sha256"] != _safe_hash(
            receipt.get("sha256"), "receipt sha256"
        ):
            raise ValueError("Previously synchronized receipt is corrupt")

    def _save_manifest(self) -> None:
        previous_size = self.manifest_path.stat().st_size if self.manifest_path.is_file() else 0
        self._manifest["updated_at_utc"] = _utc_now()
        _atomic_json(self.manifest_path, self._manifest)
        if hasattr(self, "_output_bytes"):
            self._output_bytes += self.manifest_path.stat().st_size - previous_size

    def _recover_orphans(self) -> None:
        if not self.results_directory.exists():
            return
        for directory in sorted(self.results_directory.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("Synchronization result tree contains a symbolic or non-directory entry")
            receipt_path = directory / "receipt.json"
            if receipt_path.is_symlink() or not receipt_path.is_file():
                raise ValueError(f"Unindexed synchronization result lacks a receipt: {directory.name}")
            receipt_file = _stable_file_record(receipt_path, max_bytes=MAX_SNAPSHOT_BYTES)
            try:
                receipt_doc = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("Unindexed synchronization receipt is malformed") from error
            if (
                type(receipt_doc) is not dict
                or receipt_doc.get("schema_version") != SCHEMA
                or receipt_doc.get("simulation_id") != self.simulation_id
                or receipt_doc.get("case_id") != self.case_id
                or receipt_doc.get("configuration_hash") != self.configuration_hash
                or type(receipt_doc.get("record")) is not dict
            ):
                raise ValueError("Unindexed synchronization receipt does not match this simulation")
            time_name = receipt_doc.get("time_name")
            _time_value(time_name)
            record = receipt_doc["record"]
            record["receipt"] = {
                "path": receipt_path.relative_to(self.output_directory).as_posix(),
                "sha256": receipt_file["sha256"],
            }
            self._validate_record_assets(record)
            previous = self._manifest["records"].get(time_name)
            if previous is not None and previous != record:
                raise ValueError("Unindexed result conflicts with a previously indexed time")
            if previous is None:
                self._manifest["records"][time_name] = record
                self._save_manifest()

    def _current_fields(self, time_directory: Path) -> tuple[dict[str, Path], tuple[Any, ...]] | None:
        native_paths: dict[str, Path] = {}
        for field_name in (*self.allowed_fields, "phi"):
            candidate = time_directory / field_name
            if candidate.is_symlink():
                raise ValueError(f"Refusing symbolic OpenFOAM result field: {field_name}")
            if not candidate.exists():
                continue
            if not candidate.is_file():
                raise ValueError(f"OpenFOAM result field is not a regular file: {field_name}")
            size = candidate.stat().st_size
            if size > self.max_field_bytes:
                raise ValueError(f"OpenFOAM result field exceeds the configured limit: {field_name}")
            native_paths[field_name] = candidate
        if not set(self.required_fields).issubset(native_paths):
            return None
        total = sum(path.stat().st_size for path in native_paths.values())
        if total > self.max_snapshot_bytes:
            raise ValueError("OpenFOAM result snapshot exceeds the configured byte limit")
        # Include field membership so a late optional field restarts the settle window.
        signature = tuple(
            (name, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
            for name, path in sorted(native_paths.items())
            for stat in (path.stat(),)
        )
        return native_paths, signature

    def _scan_times(self) -> list[tuple[str, float, Path, dict[str, Path], tuple[Any, ...]]]:
        candidates: list[tuple[str, float, Path, dict[str, Path], tuple[Any, ...]]] = []
        seen_values: dict[float, str] = {}
        count = 0
        for entry in self.case_directory.iterdir():
            if _TIME_NAME.fullmatch(entry.name) is None:
                continue
            if float(entry.name) == 0.0:
                continue
            count += 1
            if count > MAX_TIME_DIRECTORIES:
                raise ValueError("OpenFOAM case exceeds the time-directory resource limit")
            if entry.is_symlink():
                raise ValueError("Numeric OpenFOAM time directories cannot be symbolic links")
            if not entry.is_dir():
                continue
            time_value = _time_value(entry.name)
            if time_value in seen_values:
                raise ValueError(
                    f"OpenFOAM time names {seen_values[time_value]!r} and {entry.name!r} are numerically ambiguous"
                )
            seen_values[time_value] = entry.name
            observed = self._current_fields(entry)
            if observed is None:
                continue
            native_paths, signature = observed
            candidates.append((entry.name, time_value, entry, native_paths, signature))
        candidates.sort(key=lambda item: item[1])
        return candidates

    def _record_error(self, time_name: str, error: Exception) -> None:
        attempts = self._attempts.get(time_name, 0) + 1
        self._attempts[time_name] = attempts
        self._manifest["errors"].append({
            "time_name": time_name,
            "attempt": attempts,
            "error_type": type(error).__name__,
            "message": str(error)[:1000],
            "recorded_at_utc": _utc_now(),
            "status": "not_imported",
        })
        self._save_manifest()

    def _snapshot_metadata(self, native_paths: dict[str, Path]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        fields = {}
        source_records = {}
        total = 0
        for name, path in sorted(native_paths.items()):
            if name == "phi":
                record = _stable_file_record(path, max_bytes=self.max_field_bytes)
                raw = path.read_bytes()
                try:
                    text = raw.decode("ascii")
                except UnicodeDecodeError as error:
                    raise ValueError("Binary or non-ASCII surface flux phi is unsupported") from error
                clean = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
                clean = re.sub(r"//[^\r\n]*", " ", clean)
                if not re.search(r"\bclass\s+surfaceScalarField\s*;", clean):
                    raise ValueError("OpenFOAM phi must be a surfaceScalarField")
                if not re.search(r"\bobject\s+phi\s*;", clean):
                    raise ValueError("OpenFOAM surface field object must be phi")
                dimension_match = _DIMENSIONS.findall(clean)
                if len(dimension_match) != 1 or dimension_match[0].split() != ["0", "3", "-1", "0", "0", "0", "0"]:
                    raise ValueError("OpenFOAM phi must use volume-flux dimensions [0 3 -1 0 0 0 0]")
                fields[name] = {
                    "field": name,
                    "class": "surfaceScalarField",
                    "components": 1,
                    "dimensions": "[0 3 -1 0 0 0 0]",
                    "units": "m^3/s",
                    "sha256": record["sha256"],
                    "size_bytes": record["size_bytes"],
                }
            else:
                fields[name] = _field_metadata(path, name)
            record = _stable_file_record(path, max_bytes=self.max_field_bytes)
            if fields[name]["sha256"] != record["sha256"]:
                raise ValueError(f"OpenFOAM field changed while its snapshot was captured: {name}")
            total += record["size_bytes"]
            source_records[name] = {
                "path": path.relative_to(self.case_directory).as_posix(),
                "sha256": record["sha256"],
                "size_bytes": record["size_bytes"],
            }
        if total > self.max_snapshot_bytes:
            raise ValueError("OpenFOAM result snapshot exceeds the configured byte limit")
        return fields, source_records

    def _output_size(self) -> int:
        size = 0
        for current, directories, filenames in os.walk(self.output_directory, followlinks=False):
            current_path = Path(current)
            directories.sort()
            for name in directories:
                if (current_path / name).is_symlink():
                    raise ValueError("Synchronization output contains a symbolic directory")
            for name in filenames:
                path = current_path / name
                if path.is_symlink() or not path.is_file():
                    raise ValueError("Synchronization output contains a symbolic or non-file entry")
                size += path.stat().st_size
                if size > self.max_output_bytes:
                    raise ValueError("Synchronization output exceeds its configured storage limit")
        return size

    def _export_one(
        self,
        time_name: str,
        time_directory: Path,
        native_paths: dict[str, Path],
        stable_signature: tuple[Any, ...],
    ) -> dict[str, Any]:
        fields, source_records = self._snapshot_metadata(native_paths)
        current = self._current_fields(time_directory)
        if current is None or current[1] != stable_signature:
            raise ValueError("OpenFOAM field set changed after the settle window")
        before_records = {name: _stable_file_record(path, max_bytes=self.max_field_bytes) for name, path in native_paths.items()}

        selected_fields = [name for name in self.allowed_fields if name in native_paths]
        if "phi" in native_paths:
            # foamToVTK applies -fields to surfaceScalarFields too. Including
            # -surfaceFields alone does not select phi for export.
            selected_fields.append("phi")
        arguments = [
            self.foam_to_vtk,
            "-time", time_name,
            "-useTimeName",
            "-fields", "( " + " ".join(selected_fields) + " )",
            "-ascii",
            "-poly",
            "-noPointValues",
        ]
        if "phi" in native_paths:
            arguments.append("-surfaceFields")

        source_total = self._output_bytes
        with tempfile.TemporaryDirectory(prefix=".cleanroomx-sync-stage-", dir=self.output_directory) as temporary_name:
            temporary_root = Path(temporary_name)
            view = temporary_root / self.case_directory.name
            view.mkdir()
            for dirname in ("system", "constant", time_name):
                source = self.case_directory / dirname
                if source.is_symlink() or not source.is_dir():
                    raise ValueError(f"Cannot build isolated OpenFOAM view from {dirname}")
                (view / dirname).symlink_to(source, target_is_directory=True)
            try:
                result = subprocess.run(
                    arguments,
                    cwd=view,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise RuntimeError("foamToVTK snapshot export timed out") from error
            output = result.stdout or b""
            if isinstance(output, str):
                output = output.encode("utf-8", errors="replace")
            log_text = output.decode("utf-8", errors="replace")
            if result.returncode != 0:
                raise RuntimeError(f"foamToVTK returned {result.returncode}")
            from .cfd_openfoam import _foundation_v10_banner

            banner = _foundation_v10_banner(log_text)
            if not banner.get("is_foundation_v10"):
                raise ValueError("foamToVTK did not report an OpenFOAM Foundation v10 banner")
            recorded_build = self._manifest.get("solver_build")
            if recorded_build is not None and banner.get("build") != recorded_build:
                raise ValueError("foamToVTK build differs from the recorded OpenFOAM build")
            if self.expected_build is not None and banner.get("build") != self.expected_build:
                raise ValueError("foamToVTK build differs from the running solver build")
            if self.expected_build is None:
                self.expected_build = banner.get("build")
                self._manifest["solver_build"] = self.expected_build
            selected_times = parse_foam_to_vtk_time_log(log_text, [time_name])
            vtk_root = view / "VTK"
            if vtk_root.is_symlink() or not vtk_root.is_dir():
                raise ValueError("foamToVTK did not create a regular VTK output directory")
            internal_dataset = vtk_root / f"{self.case_directory.name}_{time_name}.vtk"
            if internal_dataset.is_symlink() or not internal_dataset.is_file():
                raise ValueError("foamToVTK did not create the expected internal-mesh dataset")

            validation = _validate_vtk_snapshot(
                native_paths,
                {name: value for name, value in fields.items() if name != "phi"},
                internal_dataset,
                contaminant_field=self.contaminant_field,
            )
            surface_flux_parity = None
            if "phi" in native_paths:
                surface_dataset = vtk_root / "surfaceFields" / f"surfaceFields_{time_name}.vtk"
                if surface_dataset.is_symlink() or not surface_dataset.is_file():
                    available = sorted(
                        path.relative_to(vtk_root).as_posix()
                        for path in vtk_root.rglob("*")
                        if path.is_file() and not path.is_symlink()
                    )[:20]
                    log_tail = " | ".join(log_text.splitlines()[-8:])[:500]
                    raise ValueError(
                        "foamToVTK omitted the requested surface flux phi dataset; "
                        f"available={available!r}; log_tail={log_tail!r}"
                    )
                surface_flux_parity = audit_openfoam_vtk_surface_flux(
                    native_paths["phi"],
                    self.case_directory / "constant" / "polyMesh",
                    surface_dataset,
                )
                if surface_flux_parity.get("status") != "PASS":
                    raise ValueError("Native phi and imported surface VTK flux did not match")

            after_records = {name: _stable_file_record(path, max_bytes=self.max_field_bytes) for name, path in native_paths.items()}
            if before_records != after_records:
                raise ValueError("OpenFOAM result fields changed during foamToVTK export")
            current_after = self._current_fields(time_directory)
            if current_after is None or current_after[1] != stable_signature:
                raise ValueError("OpenFOAM field set changed during foamToVTK export")

            output_files: list[dict[str, Any]] = []
            count = 0
            publish_stage = temporary_root / "publish"
            publish_stage.mkdir()
            for current_dir, directories, filenames in os.walk(vtk_root, followlinks=False):
                current_path = Path(current_dir)
                directories.sort()
                for name in directories:
                    if (current_path / name).is_symlink():
                        raise ValueError("foamToVTK output contains a symbolic directory")
                for name in sorted(filenames):
                    source = current_path / name
                    if source.is_symlink() or not source.is_file():
                        raise ValueError("foamToVTK output contains a symbolic or non-file entry")
                    count += 1
                    if count > MAX_OUTPUT_FILES:
                        raise ValueError("foamToVTK generated too many output files")
                    record = _stable_file_record(source, max_bytes=self.max_field_bytes)
                    relative = source.relative_to(vtk_root)
                    destination = publish_stage / "VTK" / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                    copied = _stable_file_record(destination, max_bytes=self.max_field_bytes)
                    if copied["sha256"] != record["sha256"] or copied["size_bytes"] != record["size_bytes"]:
                        raise ValueError("VTK dataset changed while copying to the result store")
                    output_files.append({
                        "path": (Path("results") / f"time_{time_name}" / "VTK" / relative).as_posix(),
                        "sha256": copied["sha256"],
                        "size_bytes": copied["size_bytes"],
                    })
            if not output_files:
                raise ValueError("foamToVTK produced no datasets")
            log_path = publish_stage / "foamToVTK.log"
            log_path.write_bytes(output)
            log_record = _stable_file_record(log_path, max_bytes=self.max_field_bytes)
            output_files.append({
                "path": (Path("results") / f"time_{time_name}" / "foamToVTK.log").as_posix(),
                "sha256": log_record["sha256"],
                "size_bytes": log_record["size_bytes"],
            })
            input_fingerprint = hashlib.sha256(
                json.dumps(source_records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            ).hexdigest()
            record = {
                "time_name": time_name,
                "selected_times": selected_times,
                "input_fingerprint_sha256": input_fingerprint,
                "source_fields": source_records,
                "fields": fields,
                "cell_count": validation["cell_count"],
                "imported_field_summary": validation["fields"],
                "native_vtk_parity": validation["native_vtk_parity"],
                "cleanroomx_analysis_import": validation["cleanroomx_analysis_import"],
                "surface_phi_parity": surface_flux_parity,
                "assets": output_files,
                "foamToVTK_log_sha256": log_record["sha256"],
                "import_status": "PASS_DIAGNOSTIC_ONLY",
                "scientific_validation": "BLOCKED",
            }
            receipt_doc = {
                "schema_version": SCHEMA,
                "simulation_id": self.simulation_id,
                "case_id": self.case_id,
                "configuration_hash": self.configuration_hash,
                "time_name": time_name,
                "record": record,
            }
            receipt_path = publish_stage / "receipt.json"
            _atomic_json(receipt_path, receipt_doc)
            receipt_record = _stable_file_record(receipt_path, max_bytes=MAX_SNAPSHOT_BYTES)
            staged_size = sum(item["size_bytes"] for item in output_files) + receipt_record["size_bytes"]
            if source_total + staged_size > self.max_output_bytes:
                raise ValueError("Synchronization output would exceed its configured storage limit")

            final_directory = self.results_directory / f"time_{time_name}"
            if final_directory.exists() or final_directory.is_symlink():
                raise FileExistsError("Refusing to overwrite an existing result time directory")
            final_directory.parent.mkdir(parents=True, exist_ok=True)
            os.replace(publish_stage, final_directory)
            self._output_bytes += staged_size

        record["receipt"] = {
            "path": (Path("results") / f"time_{time_name}" / "receipt.json").as_posix(),
            "sha256": receipt_record["sha256"],
        }
        self._validate_record_assets(record)
        existing = self._manifest["records"].get(time_name)
        if existing is not None and existing != record:
            raise ValueError("Result time conflicts with an existing synchronized record")
        self._manifest["records"][time_name] = record
        for error in self._manifest["errors"]:
            if error.get("time_name") == time_name and error.get("status") == "not_imported":
                error["status"] = "recovered_after_retry"
        self._save_manifest()
        return record

    def record_monitor_error(self, error: Exception) -> None:
        """Persist one de-duplicated polling failure without killing the solver."""
        message = str(error)[:1000]
        if any(item.get("status") == "monitor_error" and item.get("message") == message
               for item in self._manifest["errors"]):
            return
        self._manifest["errors"].append({
            "time_name": None,
            "attempt": 1,
            "error_type": type(error).__name__,
            "message": message,
            "recorded_at_utc": _utc_now(),
            "status": "monitor_error",
        })
        self._save_manifest()

    def mark_monitor_errors_recovered(self) -> None:
        """Retain prior monitor failures in the journal but clear their active state."""
        recovered = False
        for error in self._manifest["errors"]:
            if error.get("status") == "monitor_error":
                error["status"] = "recovered_after_retry"
                error["recovered_at_utc"] = _utc_now()
                recovered = True
        if recovered:
            self._save_manifest()

    def poll_once(self) -> dict[str, Any]:
        """Observe stable result writes and import any newly completed times."""
        imported: list[str] = []
        observed_count = 0
        candidates = self._scan_times()
        for time_name, _time_numeric, time_directory, native_paths, signature in candidates:
            observed_count += 1
            existing = self._manifest["records"].get(time_name)
            if existing is not None:
                _fields, current_source_records = self._snapshot_metadata(native_paths)
                if current_source_records != existing.get("source_fields"):
                    error = ValueError("Already synchronized OpenFOAM time changed; preserving the prior result")
                    self._record_error(time_name, error)
                    raise error
                continue
            previous = self._observations.get(time_name)
            stable_count = previous[1] + 1 if previous is not None and previous[0] == signature else 1
            self._observations[time_name] = (signature, stable_count)
            if stable_count < self.settle_polls or self._attempts.get(time_name, 0) >= self.max_retries:
                continue
            try:
                self._export_one(time_name, time_directory, native_paths, signature)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                self._record_error(time_name, error)
                continue
            imported.append(time_name)
            self._observations.pop(time_name, None)
        return {
            "status": self._manifest["status"],
            "observed_time_count": observed_count,
            "imported_times": imported,
            "failed_time_count": sum(1 for error in self._manifest["errors"]
                                      if error.get("attempt", 0) >= self.max_retries),
        }

    def finish(self, *, solver_returncode: int | None, solver_log: str | Path | None = None) -> dict[str, Any]:
        """Persist a terminal solver/synchronization classification."""
        log_status = "not_supplied"
        if solver_log is not None:
            log_status = _solver_log_status(Path(solver_log))
        records_count = len(self._manifest["records"])
        failed_times = {error.get("time_name") for error in self._manifest["errors"]
                        if error.get("status") != "recovered_after_retry"}
        if solver_returncode == 0 and log_status == "completed" and records_count > 0 and not failed_times:
            status = "results_synced"
        elif records_count == 0:
            status = "no_results_available"
        else:
            status = "incomplete"
        self._manifest["status"] = status
        self._manifest["solver_returncode"] = solver_returncode
        self._manifest["solver_log_status"] = log_status
        self._manifest["record_count"] = records_count
        self._manifest["failed_times"] = sorted(name for name in failed_times if isinstance(name, str))
        self._manifest["finished_at_utc"] = _utc_now()
        self._save_manifest()
        return self.summary()

    def summary(self) -> dict[str, Any]:
        manifest_sha = _stable_file_record(
            self.manifest_path,
            max_bytes=MAX_SNAPSHOT_BYTES,
        )["sha256"]
        return {
            "status": self._manifest["status"],
            "simulation_id": self.simulation_id,
            "case_id": self.case_id,
            "configuration_hash": self.configuration_hash,
            "manifest": str(self.manifest_path),
            "manifest_sha256": manifest_sha,
            "record_count": len(self._manifest["records"]),
            "times": sorted(self._manifest["records"], key=_time_value),
            "error_count": len(self._manifest["errors"]),
            "scientific_validation": "BLOCKED",
        }

    def watch(
        self,
        *,
        solver_log: str | Path | None = None,
        max_runtime_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Poll until a solver log ends cleanly, a runtime limit is reached, or interrupted."""
        if max_runtime_seconds is not None and (
            type(max_runtime_seconds) is not int or not 1 <= max_runtime_seconds <= 86400
        ):
            raise ValueError("max_runtime_seconds must be an integer in [1,86400]")
        started = time.monotonic()
        terminal = False

        def poll_safely() -> None:
            try:
                self.poll_once()
                self.mark_monitor_errors_recovered()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                self.record_monitor_error(error)

        try:
            while True:
                poll_safely()
                if solver_log is not None:
                    log_path = Path(solver_log)
                    log_status = _solver_log_status(log_path)
                    if log_status in ("completed", "fatal_error_detected"):
                        terminal = True
                if terminal:
                    break
                if max_runtime_seconds is not None and time.monotonic() - started >= max_runtime_seconds:
                    break
                time.sleep(self.poll_interval_seconds)
        except KeyboardInterrupt:
            self._manifest["status"] = "interrupted_resumable"
            self._manifest["interrupted_at_utc"] = _utc_now()
            self._save_manifest()
            return self.summary()
        if terminal:
            for index in range(self.settle_polls):
                poll_safely()
                if index + 1 < self.settle_polls:
                    time.sleep(self.poll_interval_seconds)
            log_path = Path(solver_log) if solver_log is not None else None
            log_status = _solver_log_status(log_path) if log_path is not None else "not_supplied"
            records_count = len(self._manifest["records"])
            failed = any(error.get("status") != "recovered_after_retry"
                         for error in self._manifest["errors"])
            if records_count and log_status == "completed" and not failed:
                status = "outputs_synced_process_status_unknown"
            elif log_status == "fatal_error_detected":
                status = "incomplete"
            elif records_count == 0:
                status = "no_results_available"
            else:
                status = "incomplete"
            self._manifest["status"] = status
            self._manifest["solver_returncode"] = None
            self._manifest["solver_log_status"] = log_status
            self._manifest["record_count"] = records_count
            self._manifest["finished_at_utc"] = _utc_now()
            self._save_manifest()
            return self.summary()
        self._manifest["status"] = "monitoring_checkpoint"
        self._manifest["checkpoint_at_utc"] = _utc_now()
        self._save_manifest()
        return self.summary()


def run_solver_with_sync(
    command: list[str],
    *,
    cwd: str | Path,
    log_path: str | Path,
    timeout_seconds: int,
    synchronizer: OpenFOAMResultSynchronizer,
) -> int:
    """Run a solver while polling output directories; retain a normal log file."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be an integer in [1,86400]")
    log = Path(log_path)
    if log.exists() or log.is_symlink():
        raise FileExistsError(f"Refusing to overwrite solver log: {log}")
    started = time.monotonic()
    returncode: int | None = None
    next_sync = started

    def poll_safely() -> None:
        try:
            synchronizer.poll_once()
            synchronizer.mark_monitor_errors_recovered()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            synchronizer.record_monitor_error(error)

    with log.open("xb") as output:
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
        except OSError as error:
            synchronizer.record_monitor_error(error)
            return 127
        try:
            while process.poll() is None:
                if time.monotonic() - started >= timeout_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    returncode = 124
                    break
                now = time.monotonic()
                if now >= next_sync:
                    poll_safely()
                    next_sync = time.monotonic() + synchronizer.poll_interval_seconds
                time.sleep(min(0.25, max(0.01, next_sync - time.monotonic())))
            if returncode is None:
                returncode = process.wait()
            for index in range(synchronizer.settle_polls):
                poll_safely()
                if index + 1 < synchronizer.settle_polls:
                    time.sleep(synchronizer.poll_interval_seconds)
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
    return returncode
