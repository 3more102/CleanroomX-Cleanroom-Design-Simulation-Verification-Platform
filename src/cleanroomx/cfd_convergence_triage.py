"""Conservative, read-only triage of OpenFOAM Foundation logs and flux fields.

These are diagnostic evidence only; they never declare physical convergence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import deque
from pathlib import Path
from statistics import median

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_SOLVE = re.compile(
    rf"Solving for\s+([A-Za-z][\w.]*)\s*,\s*Initial residual\s*=\s*({_NUMBER})"
    rf"\s*,\s*Final residual\s*=\s*({_NUMBER})\s*,\s*No Iterations\s+(\d{{1,12}})"
)
_TIME_LINE = re.compile(r"^\s*Time\s*=\s*(\S+)\s*$")
_TIME_VALUE = re.compile(rf"^({_NUMBER})(s?)$")
_TIME_START = re.compile(r"^\s*Time\s*=")
_END_LINE = re.compile(r"^\s*End\s*$")
_CONTROL_START = re.compile(r"^\s*SIMPLE:\s*Convergence criteria found\s*$")
_CONTROL_TOLERANCE = re.compile(
    rf"^\s*([A-Za-z][\w.]*)\s*:\s*tolerance\s+({_NUMBER})\s*$"
)
_CONTINUITY = re.compile(rf"time step continuity errors\s*:\s*sum local\s*=\s*({_NUMBER})"
                         rf"\s*,\s*global\s*=\s*({_NUMBER})"
                         rf"\s*,\s*cumulative\s*=\s*({_NUMBER})")
_BAD = re.compile(
    r"(?im)^\s*(?:FOAM FATAL(?: IO)? ERROR\b|Floating point exception\b|Segmentation fault\b)"
    r"|\b(?:nan|inf|infinity)\b",
    re.I,
)
_MAX_LOG_BYTES = 64 * 1024 * 1024


def diagnose_log(path: str | Path, *, fields: tuple[str, ...] = ("Ux", "Uy", "Uz", "p"),
                 window: int = 5, trend_window: int = 50) -> dict:
    """Extract step-aware solver diagnostics; never assert scientific convergence."""
    if window < 1 or window > 10000:
        raise ValueError("window must be between 1 and 10000")
    if type(trend_window) is not int or not 1 <= trend_window <= 10000:
        raise ValueError("trend_window must be an integer between 1 and 10000")
    if not fields or len(fields) > 32 or len(set(fields)) != len(fields) or any(
        not re.fullmatch(r"[A-Za-z][\w.]*", field) for field in fields
    ):
        raise ValueError("fields must contain 1-32 distinct valid solver field names")
    p = Path(path)
    if any(component.is_symlink() for component in (p, *p.parents)) or not p.is_file():
        raise ValueError("missing or symlinked log")
    before = p.stat()
    if before.st_size > _MAX_LOG_BYTES:
        raise ValueError("log exceeds 64 MiB diagnostic limit")
    # Bounded read remains bounded if the file grows after the initial stat.
    with p.open("rb") as stream:
        raw = stream.read(_MAX_LOG_BYTES + 1)
    if len(raw) > _MAX_LOG_BYTES:
        raise ValueError("log exceeds 64 MiB diagnostic limit")
    # A changed path, file size, or modification time invalidates this
    # diagnostic snapshot, even when the new bytes look like a valid log.
    after = p.stat()
    fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if fingerprint(before) != fingerprint(after) or any(
        component.is_symlink() for component in (p, *p.parents)
    ):
        raise ValueError("log changed during diagnostic read")
    data = raw.decode("utf-8")

    time_steps = 0
    last_time: str | None = None
    previous_time: float | None = None
    bad_time = False
    malformed_time = False
    # Retain only the requested recent window, not every solver iteration.
    sample_counts = {field: 0 for field in fields}
    recent_residuals = {field: deque(maxlen=window) for field in fields}
    first_residual_window = {field: [] for field in fields}
    tail_residual_window = {field: deque(maxlen=trend_window) for field in fields}
    continuity_samples = 0
    recent_global_continuity = deque(maxlen=window)
    last_step_fields: set[str] = set()
    last_step_continuity = 0
    incomplete_prior_steps = 0
    orphan_records = 0
    invalid_residual = False
    malformed_solver = False
    malformed_continuity = False
    end_markers = 0
    control_blocks = 0
    control_block_active = False
    control_tolerances: dict[str, float] = {}
    malformed_controls = False
    last_step_initials: dict[str, float] = {}
    duplicate_last_step_fields: set[str] = set()

    lines = data.splitlines()
    for line in lines:
        if _CONTROL_START.fullmatch(line):
            control_blocks += 1
            control_block_active = True
            if control_blocks > 1:
                malformed_controls = True
            continue

        time_match = _TIME_LINE.fullmatch(line)
        if time_match:
            if time_steps and (set(fields) - last_step_fields or not last_step_continuity):
                incomplete_prior_steps += 1
            stamp = time_match.group(1)
            time_steps += 1
            last_time = stamp
            value_match = _TIME_VALUE.fullmatch(stamp)
            if not value_match:
                bad_time = True
            else:
                numeric_time = float(value_match.group(1))
                if not math.isfinite(numeric_time) or (
                    previous_time is not None and numeric_time <= previous_time
                ):
                    bad_time = True
                if math.isfinite(numeric_time):
                    previous_time = numeric_time
            last_step_fields.clear()
            last_step_continuity = 0
            last_step_initials.clear()
            duplicate_last_step_fields.clear()
            control_block_active = False
            continue

        if _TIME_START.match(line):
            malformed_time = True
            continue

        if control_block_active:
            if "tolerance" in line.lower():
                control_match = _CONTROL_TOLERANCE.fullmatch(line)
                if control_match is None:
                    malformed_controls = True
                else:
                    field, raw_tolerance = control_match.groups()
                    tolerance = float(raw_tolerance)
                    if not math.isfinite(tolerance) or tolerance < 0 or field in control_tolerances:
                        malformed_controls = True
                    else:
                        control_tolerances[field] = tolerance

        if _END_LINE.fullmatch(line):
            end_markers += 1
        solve_match = _SOLVE.search(line)
        if "Solving for" in line and (
            solve_match is None
            or line[solve_match.end():].strip()
            or line.count("Solving for") > 1
        ):
            malformed_solver = True
        if solve_match:
            field, initial, final, iterations = solve_match.groups()
            a, b = float(initial), float(final)
            if not (math.isfinite(a) and math.isfinite(b)) or a < 0 or b < 0:
                invalid_residual = True
            else:
                if field in sample_counts:
                    sample_counts[field] += 1
                    recent_residuals[field].append((a, b))
                    if len(first_residual_window[field]) < trend_window:
                        first_residual_window[field].append(a)
                    tail_residual_window[field].append(a)
            if time_steps:
                if field in last_step_initials:
                    duplicate_last_step_fields.add(field)
                last_step_fields.add(field)
                if math.isfinite(a) and a >= 0:
                    last_step_initials[field] = a
            else:
                orphan_records += 1
        continuity_match = _CONTINUITY.search(line)
        if "time step continuity errors" in line.lower() and (
            continuity_match is None
            or line[continuity_match.end():].strip()
            or line.lower().count("time step continuity errors") > 1
        ):
            malformed_continuity = True
        if continuity_match:
            values = tuple(map(float, continuity_match.groups()))
            if all(math.isfinite(x) for x in values):
                continuity_samples += 1
                recent_global_continuity.append(values[1])
                if time_steps:
                    last_step_continuity += 1
                else:
                    orphan_records += 1
            else:
                malformed_continuity = True

    field_report = {}
    residual_trends = {}
    for field in fields:
        recent = recent_residuals[field]
        initial_values = first_residual_window[field]
        tail_values = list(tail_residual_window[field])
        # Keep the first and tail windows disjoint. For short logs, shrink both
        # windows equally rather than comparing overlapping samples.
        trend_samples = min(trend_window, sample_counts[field] // 2)
        if trend_samples < 1:
            trend_status = "INSUFFICIENT_SAMPLES"
            initial_median = None
            tail_median = None
            trend_ratio = None
        else:
            initial_median = median(initial_values[:trend_samples])
            tail_median = median(tail_values[-trend_samples:])
        if trend_samples >= 1 and initial_median == 0:
            trend_status = "ZERO_INITIAL_MEDIAN"
            trend_ratio = None
        elif trend_samples >= 1:
            trend_ratio = tail_median / initial_median
            if math.isfinite(trend_ratio):
                trend_status = "COMPUTED"
            else:
                trend_status = "NONFINITE_RATIO"
                trend_ratio = None
        residual_trends[field] = {
            "status": trend_status,
            "sample_count": sample_counts[field],
            "window_samples": trend_samples,
            "initial_window_median": initial_median,
            "tail_window_median": tail_median,
            "tail_to_initial_median_ratio": trend_ratio,
        }
        field_report[field] = {
            "samples": sample_counts[field],
            "recent_initial": [r[0] for r in recent],
            "recent_final": [r[1] for r in recent],
            "last_initial": recent[-1][0] if recent else None,
            "last_final": recent[-1][1] if recent else None,
            "missing": sample_counts[field] == 0,
        }

    last_nonblank_line = next((line.strip() for line in reversed(lines) if line.strip()), None)
    clean_end = last_nonblank_line == "End"
    missing_last_fields = sorted(set(fields) - last_step_fields)

    # OpenFOAM v10 prints convergence controls under SIMPLE as field names,
    # while vector U is commonly logged as Ux/Uy/Uz. The max component is a
    # conservative log proxy, not a reproduction of the solver's internal
    # residualControl calculation.
    control_screen: dict[str, dict] = {}
    controls_valid = control_blocks == 1 and bool(control_tolerances) and not malformed_controls
    control_screen_problem = (
        not controls_valid or not clean_end or end_markers != 1 or not time_steps
        or bad_time or malformed_time
        or bool(missing_last_fields) or bool(duplicate_last_step_fields)
        or not last_step_continuity or incomplete_prior_steps or orphan_records
        or malformed_solver or malformed_continuity or invalid_residual or bool(_BAD.search(data))
    )
    for field, tolerance in sorted(control_tolerances.items()):
        source_fields = ("Ux", "Uy", "Uz") if field == "U" else (field,)
        observed = [last_step_initials.get(name) for name in source_fields]
        if control_screen_problem or any(value is None for value in observed):
            control_screen[field] = {
                "status": "UNKNOWN",
                "tolerance": tolerance,
                "observed_initial_residual": None,
                "source_fields": list(source_fields),
            }
            continue
        if tolerance == 0:
            ratio = None
        else:
            ratio = max(observed) / tolerance
        control_screen[field] = {
            "status": "BELOW_TOLERANCE" if max(observed) < tolerance else "NOT_BELOW_TOLERANCE",
            "tolerance": tolerance,
            "observed_initial_residual": max(observed),
            "source_fields": list(source_fields),
            "component_initial_residuals": dict(zip(source_fields, observed)),
            "tolerance_ratio": ratio,
        }
    control_screen_complete = (
        not control_screen_problem
        and bool(control_screen)
        and all(item["status"] != "UNKNOWN" for item in control_screen.values())
    )
    problems = []
    if not time_steps:
        problems.append("NO_TIME_STEPS")
    if bad_time:
        problems.append("INVALID_OR_NONMONOTONIC_TIME_STEPS")
    if malformed_time:
        problems.append("MALFORMED_TIME_MARKER")
    if not clean_end:
        problems.append("MISSING_TERMINAL_END")
    if end_markers > 1:
        problems.append("MULTIPLE_END_MARKERS")
    if _BAD.search(data):
        problems.append("FATAL_OR_NONFINITE_TOKEN")
    if invalid_residual:
        problems.append("INVALID_RESIDUAL_VALUE")
    if malformed_solver:
        problems.append("MALFORMED_SOLVER_RECORD")
    if malformed_continuity:
        problems.append("MALFORMED_CONTINUITY_RECORD")
    if incomplete_prior_steps:
        problems.append("INCOMPLETE_PRIOR_TIME_STEP")
    if orphan_records:
        problems.append("ORPHAN_SOLVER_RECORDS")
    if any(item["missing"] for item in field_report.values()):
        problems.append("MISSING_REQUIRED_FIELD")
    if not continuity_samples:
        problems.append("NO_CONTINUITY_RECORDS")
    if time_steps and (missing_last_fields or not last_step_continuity):
        problems.append("INCOMPLETE_FINAL_TIME_STEP")

    return {
        "status": "DIAGNOSTIC_ONLY" if not problems else "INCOMPLETE_OR_INVALID",
        "scientific_validation": "BLOCKED",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "time_steps": time_steps,
        "last_time": last_time,
        "time_sequence_monotonic": bool(time_steps) and not (bad_time or malformed_time),
        "terminal_end": clean_end,
        "fields": field_report,
        "residual_trend": {
            "status": "DESCRIPTIVE_ONLY",
            "window_samples_requested": trend_window,
            "fields": residual_trends,
            "note": "For each requested field, compares medians of non-overlapping first and last bounded windows of logged initial linear residuals. Short logs use disjoint reduced windows; fewer than two samples, zero initial medians, and non-finite ratios are not divided. Ratios are descriptive only: a lower tail median does not establish nonlinear or physical convergence and is not an acceptance test.",
        },
        "incomplete_prior_time_steps": incomplete_prior_steps,
        "last_step_missing_fields": missing_last_fields,
        "last_step_continuity_samples": last_step_continuity,
        "terminal_residual_control_screen": {
            "status": "AVAILABLE" if control_screen_complete else "UNKNOWN",
            "criteria_blocks": control_blocks,
            "malformed_or_duplicate_criteria": malformed_controls,
            "fields": control_screen,
            "note": "Log-based linear initial-residual screen only; vector U uses the maximum logged component and does not reproduce OpenFOAM's internal residualControl calculation.",
        },
        "continuity_samples": continuity_samples,
        "recent_global_continuity": list(recent_global_continuity),
        "problems": problems,
        "note": "Linear solver residuals are not proof of physical convergence or mass balance.",
    }



_GRID_LEVELS = ("coarse", "medium", "fine")
_GRID_RESIDUAL_FIELDS = ("U", "p")
_GRID_CONDITION_INPUTS = (
    "0/U",
    "0/p",
    "constant/physicalProperties",
    "constant/momentumTransport",
    "system/controlDict",
    "system/fvSchemes",
    "system/fvSolution",
)
_GRID_MESH_INPUT = "system/blockMeshDict"
_MAX_GRID_DICTIONARY_BYTES = 16 * 1024 * 1024
_MAX_GRID_FLUX_BYTES = 64 * 1024 * 1024
_GRID_FLUX_PATCHES = ("inlet", "outlet", "walls")


def _sha256_grid_input(path: Path) -> str:
    """Hash one bounded, stable, non-symlinked grid-family input file."""
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise ValueError("missing or symlinked grid input")
    if not path.is_file():
        raise ValueError("missing or non-file grid input")
    before = path.stat()
    if before.st_size > _MAX_GRID_DICTIONARY_BYTES:
        raise ValueError("grid input exceeds 16 MiB diagnostic limit")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_GRID_DICTIONARY_BYTES + 1)
    if len(raw) > _MAX_GRID_DICTIONARY_BYTES:
        raise ValueError("grid input exceeds 16 MiB diagnostic limit")
    after = path.stat()
    fingerprint = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    if fingerprint(before) != fingerprint(after) or any(
        component.is_symlink() for component in (path, *path.parents)
    ):
        raise ValueError("grid input changed during diagnostic read")
    return hashlib.sha256(raw).hexdigest()


def _read_stable_grid_text(path: Path, root: Path, *, limit: int) -> tuple[bytes, str]:
    """Read one bounded UTF-8 file that remains inside the grid family."""
    if any(component.is_symlink() for component in (path, *path.parents)):
        raise ValueError("missing or symlinked solver-flux input")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("solver-flux input escaped the grid-family directory")
    before = resolved.stat()
    if before.st_size > limit:
        raise ValueError("solver-flux input exceeds the diagnostic size limit")
    with resolved.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("solver-flux input exceeds the diagnostic size limit")
    after = resolved.stat()
    fingerprint = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    if fingerprint(before) != fingerprint(after) or any(
        component.is_symlink() for component in (path, *path.parents)
    ):
        raise ValueError("solver-flux input changed during diagnostic read")
    return raw, raw.decode("utf-8")


def _balanced_section(text: str, start: int, opening: str, closing: str) -> tuple[str, int]:
    depth = 1
    for position in range(start, len(text)):
        if text[position] == opening:
            depth += 1
        elif text[position] == closing:
            depth -= 1
            if depth == 0:
                return text[start:position], position + 1
    raise ValueError("unclosed OpenFOAM dictionary section")


def _named_dictionary_blocks(text: str) -> dict[str, str]:
    blocks = {}
    for match in re.finditer(r"(?ms)^\s*([A-Za-z][\w.]*)\s*\{(.*?)^\s*\}", text):
        name = match.group(1)
        if name in blocks:
            raise ValueError("duplicate OpenFOAM patch entry: " + name)
        blocks[name] = match.group(2)
    return blocks


def _grid_poly_mesh_patch_counts(text: str) -> dict[str, int]:
    count_match = re.search(r"(?m)^\s*(\d+)\s*$", text)
    if count_match is None:
        raise ValueError("polyMesh boundary has no patch count")
    opening = text.find("(", count_match.end())
    if opening < 0:
        raise ValueError("polyMesh boundary has no patch list")
    body, _ = _balanced_section(text, opening + 1, "(", ")")
    blocks = _named_dictionary_blocks(body)
    if set(blocks) != set(_GRID_FLUX_PATCHES):
        raise ValueError("polyMesh boundary does not contain exactly inlet, outlet, and walls")
    counts = {}
    for patch, block in blocks.items():
        match = re.search(r"\bnFaces\s+(\d+)\s*;", block)
        if match is None:
            raise ValueError("polyMesh boundary is missing nFaces for " + patch)
        counts[patch] = int(match.group(1))
    return counts


def _grid_phi_patch_values(text: str, patch_counts: dict[str, int]) -> dict[str, list[float]]:
    dimensions = re.search(r"\bdimensions\s*\[([^\]]+)\]\s*;", text)
    if dimensions is None:
        raise ValueError("phi field is missing dimensions")
    try:
        dimension_values = tuple(int(value) for value in dimensions.group(1).split())
    except ValueError as exc:
        raise ValueError("phi field has invalid dimensions") from exc
    if dimension_values != (0, 3, -1, 0, 0, 0, 0):
        raise ValueError("phi field dimensions are not volumetric flow per face")
    boundary = re.search(r"\bboundaryField\s*\{", text)
    if boundary is None:
        raise ValueError("phi field is missing boundaryField")
    body, _ = _balanced_section(text, boundary.end(), "{", "}")
    blocks = _named_dictionary_blocks(body)
    if set(blocks) != set(patch_counts):
        raise ValueError("phi patch entries do not match polyMesh boundary patches")
    patch_values = {}
    for patch, block in blocks.items():
        value_matches = list(re.finditer(r"\bvalue\s+(uniform|nonuniform)\b", block))
        if len(value_matches) != 1:
            raise ValueError("phi patch must contain exactly one value for " + patch)
        value_match = value_matches[0]
        rest = block[value_match.end():]
        if value_match.group(1) == "uniform":
            scalar = re.match(rf"\s*({_NUMBER})\s*;", rest)
            if scalar is None:
                raise ValueError("invalid uniform phi value for " + patch)
            values = [float(scalar.group(1))] * patch_counts[patch]
        else:
            list_match = re.match(r"\s*List<scalar>\s+(\d+)\s*\(", rest)
            if list_match is None:
                raise ValueError("invalid nonuniform phi list for " + patch)
            listed_count = int(list_match.group(1))
            values_text, close_index = _balanced_section(rest, list_match.end(), "(", ")")
            if rest[close_index:].strip().removeprefix(";").strip():
                raise ValueError("unexpected text after phi value list for " + patch)
            tokens = values_text.split()
            if any(re.fullmatch(_NUMBER, token) is None for token in tokens):
                raise ValueError("invalid scalar in phi value list for " + patch)
            values = [float(token) for token in tokens]
            if listed_count != patch_counts[patch] or len(values) != listed_count:
                raise ValueError("phi face-value count differs from polyMesh boundary for " + patch)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("phi field contains a non-finite face flux")
        patch_values[patch] = values
    return patch_values


def diagnose_grid_flux(case_directory: str | Path, last_time: str, *,
                       family_root: str | Path | None = None) -> dict:
    """Measure signed final-time volumetric boundary fluxes from OpenFOAM ``phi``.

    The value is a diagnostic measurement with no pass/fail tolerance. The
    OpenFOAM Foundation v10 ``createPhi.H`` initializes ``phi`` from
    ``fvc::flux(U)``; input files and directory paths are checked before read.
    """
    candidate = Path(case_directory)
    raw_case = candidate if candidate.is_absolute() else Path.cwd() / candidate
    if any(component.is_symlink() for component in (raw_case, *raw_case.parents)):
        return {"status": "UNAVAILABLE", "problems": ["CASE_DIRECTORY_MISSING_OR_SYMLINKED"]}
    try:
        case = raw_case.resolve(strict=True)
    except OSError:
        return {"status": "UNAVAILABLE", "problems": ["CASE_DIRECTORY_MISSING_OR_UNREADABLE"]}
    if not case.is_dir():
        return {"status": "UNAVAILABLE", "problems": ["CASE_DIRECTORY_MISSING_OR_UNREADABLE"]}
    if family_root is None:
        root = case.parent.parent
    else:
        candidate_root = Path(family_root)
        if not candidate_root.is_absolute():
            candidate_root = Path.cwd() / candidate_root
        try:
            root = candidate_root.resolve(strict=True)
        except OSError:
            return {"status": "UNAVAILABLE", "problems": ["GRID_FAMILY_DIRECTORY_MISSING_OR_UNREADABLE"]}
    if not case.is_relative_to(root):
        return {"status": "UNAVAILABLE", "problems": ["CASE_DIRECTORY_OUTSIDE_GRID_FAMILY"]}
    match = _TIME_VALUE.fullmatch(last_time) if isinstance(last_time, str) else None
    if match is None:
        return {"status": "UNAVAILABLE", "problems": ["INVALID_LAST_SOLVER_TIME"]}
    target_time = float(match.group(1))
    if not math.isfinite(target_time) or target_time < 0:
        return {"status": "UNAVAILABLE", "problems": ["INVALID_LAST_SOLVER_TIME"]}
    matching_directories = []
    try:
        for entry in case.iterdir():
            time_match = _TIME_VALUE.fullmatch(entry.name)
            if time_match is None or float(time_match.group(1)) != target_time:
                continue
            if entry.is_symlink():
                return {"status": "UNAVAILABLE", "problems": ["FINAL_TIME_DIRECTORY_IS_SYMLINKED"]}
            if entry.is_dir():
                matching_directories.append(entry)
    except OSError:
        return {"status": "UNAVAILABLE", "problems": ["CASE_DIRECTORY_UNREADABLE"]}
    if len(matching_directories) != 1:
        return {"status": "UNAVAILABLE", "problems": [
            "FINAL_TIME_DIRECTORY_MISSING" if not matching_directories else "AMBIGUOUS_FINAL_TIME_DIRECTORY"
        ]}
    time_directory = matching_directories[0]
    try:
        boundary_raw, boundary_text = _read_stable_grid_text(
            case / "constant/polyMesh/boundary", root, limit=_MAX_GRID_FLUX_BYTES
        )
        phi_raw, phi_text = _read_stable_grid_text(
            time_directory / "phi", root, limit=_MAX_GRID_FLUX_BYTES
        )
        patch_counts = _grid_poly_mesh_patch_counts(boundary_text)
        patch_values = _grid_phi_patch_values(phi_text, patch_counts)
    except (OSError, UnicodeError, ValueError) as exc:
        return {"status": "UNAVAILABLE", "problems": [str(exc)]}

    inlet = patch_values["inlet"]
    outlet = patch_values["outlet"]
    walls = patch_values["walls"]
    gross_inlet = sum(max(-value, 0.0) for value in inlet)
    reverse_inlet = sum(max(value, 0.0) for value in inlet)
    net_inlet = -sum(inlet)
    gross_outlet = sum(max(value, 0.0) for value in outlet)
    reverse_outlet = sum(max(-value, 0.0) for value in outlet)
    net_outlet = sum(outlet)
    net_wall = sum(walls)
    net_boundary = sum(inlet) + net_outlet + net_wall
    if gross_inlet <= 0 or net_inlet <= 0:
        return {"status": "UNAVAILABLE", "problems": ["NO_POSITIVE_NET_INLET_FLOW"]}
    imbalance = abs(net_boundary)
    rounded = lambda value: float(f"{value:.12g}")
    case_id = case.relative_to(root).as_posix()
    return {
        "status": "MEASURED_DIAGNOSTIC_ONLY",
        "case_id": case_id,
        "last_solver_time": last_time,
        "phi_path": (time_directory / "phi").relative_to(root).as_posix(),
        "phi_sha256": hashlib.sha256(phi_raw).hexdigest(),
        "poly_mesh_boundary_sha256": hashlib.sha256(boundary_raw).hexdigest(),
        "patch_face_counts": patch_counts,
        "inlet": {
            "gross_inward_m3_s": rounded(gross_inlet),
            "reverse_outward_m3_s": rounded(reverse_inlet),
            "net_inward_m3_s": rounded(net_inlet),
        },
        "outlet": {
            "gross_outward_m3_s": rounded(gross_outlet),
            "reverse_inward_m3_s": rounded(reverse_outlet),
            "net_outward_m3_s": rounded(net_outlet),
        },
        "walls_net_outward_m3_s": rounded(net_wall),
        "net_boundary_outward_m3_s": rounded(net_boundary),
        "absolute_flux_imbalance_m3_s": rounded(imbalance),
        "relative_flux_imbalance_percent": rounded(100 * imbalance / gross_inlet),
        "flow_balance_assessment": "NO_PROJECT_ACCEPTANCE_CRITERION",
        "scientific_validation": "BLOCKED",
    }


def audit_grid_family_inputs(directory: str | Path) -> dict:
    """Compare solver-condition dictionary bytes across each 3-grid family.

    The seven declared condition inputs are compared byte-for-byte within a
    configuration. ``blockMeshDict`` is hashed separately and is not expected
    to match across grid levels. This is a static input-consistency screen,
    not a check of physical correctness or mesh equivalence.
    """
    candidate = Path(directory)
    raw_candidate = candidate if candidate.is_absolute() else Path.cwd() / candidate
    root = None
    root_problem = None
    try:
        if any(component.is_symlink() for component in (raw_candidate, *raw_candidate.parents)):
            root_problem = "GRID_FAMILY_DIRECTORY_MISSING_OR_SYMLINKED"
        elif not raw_candidate.is_dir():
            root_problem = "GRID_FAMILY_DIRECTORY_MISSING_OR_SYMLINKED"
        else:
            root = raw_candidate.resolve(strict=True)
    except OSError:
        root_problem = "GRID_FAMILY_DIRECTORY_MISSING_OR_UNREADABLE"

    configurations = {}
    for configuration in (1, 2, 3):
        config_id = f"configuration_{configuration}"
        levels = {}
        config_errors = [root_problem] if root_problem else []
        for level in _GRID_LEVELS:
            case_id = f"{config_id}/{level}"
            hashes = {}
            errors = []
            for relative in _GRID_CONDITION_INPUTS:
                try:
                    if root is None:
                        raise ValueError(root_problem or "grid family directory unavailable")
                    hashes[relative] = _sha256_grid_input(root / case_id / relative)
                except (OSError, ValueError) as exc:
                    errors.append({"path": relative, "problem": str(exc)})
            mesh_hash = None
            try:
                if root is None:
                    raise ValueError(root_problem or "grid family directory unavailable")
                mesh_hash = _sha256_grid_input(root / case_id / _GRID_MESH_INPUT)
            except (OSError, ValueError) as exc:
                errors.append({"path": _GRID_MESH_INPUT, "problem": str(exc)})
            if errors:
                config_errors.append(f"{case_id}: incomplete or unreadable input files")
            levels[level] = {
                "condition_files_sha256": hashes,
                "mesh_dictionary_sha256": mesh_hash,
                "errors": errors,
            }

        complete = all(
            len(record["condition_files_sha256"]) == len(_GRID_CONDITION_INPUTS)
            and record["mesh_dictionary_sha256"] is not None
            and not record["errors"]
            for record in levels.values()
        )
        differing = []
        if complete:
            for relative in _GRID_CONDITION_INPUTS:
                digests = {record["condition_files_sha256"][relative] for record in levels.values()}
                if len(digests) > 1:
                    differing.append(relative)
        if not complete:
            status = "INCOMPLETE_OR_UNREADABLE"
        elif differing:
            status = "DIFFERENT_ACROSS_GRID_LEVELS"
        else:
            status = "BYTE_IDENTICAL_ACROSS_GRID_LEVELS"
        fingerprint_sha256 = None
        if complete and not differing:
            common = {relative: levels["coarse"]["condition_files_sha256"][relative]
                      for relative in _GRID_CONDITION_INPUTS}
            canonical = json.dumps(common, sort_keys=True, separators=(",", ":")).encode("utf-8")
            fingerprint_sha256 = hashlib.sha256(canonical).hexdigest()
        configurations[config_id] = {
            "status": status,
            "differing_condition_files": differing,
            "condition_fingerprint_sha256": fingerprint_sha256,
            "levels": levels,
            "errors": config_errors,
        }

    statuses = [record["status"] for record in configurations.values()]
    if any(status == "INCOMPLETE_OR_UNREADABLE" for status in statuses):
        overall_status = "INCOMPLETE_OR_UNREADABLE"
    elif any(status == "DIFFERENT_ACROSS_GRID_LEVELS" for status in statuses):
        overall_status = "DIFFERENT_ACROSS_GRID_LEVELS"
    else:
        overall_status = "BYTE_IDENTICAL_ACROSS_GRID_LEVELS"
    return {
        "status": overall_status,
        "condition_inputs_compared": list(_GRID_CONDITION_INPUTS),
        "mesh_input_hashed_separately": _GRID_MESH_INPUT,
        "configurations": configurations,
        "note": "Byte identity of these solver inputs does not prove correct boundary conditions, actual patch areas or flow rates, geometry equivalence, independent executions, mesh independence, physical convergence, or model validity.",
    }


def diagnose_grid_family(directory: str | Path, *,
                         fields: tuple[str, ...] = ("Ux", "Uy", "Uz", "p"),
                         window: int = 5, trend_window: int = 50) -> dict:
    """Triage logs, input fingerprints, and available final-time fluxes for 3x3 cases.

    A complete report means all nine expected logs were distinct and
    structurally parseable. It does not mean the configured residual screen
    passed, and never advances scientific validation beyond BLOCKED.
    """
    if type(window) is not int or window < 1 or window > 10000:
        raise ValueError("window must be between 1 and 10000")
    if type(trend_window) is not int or not 1 <= trend_window <= 10000:
        raise ValueError("trend_window must be an integer between 1 and 10000")
    fields = tuple(fields)
    if not fields or len(fields) > 32 or len(set(fields)) != len(fields) or any(
        not re.fullmatch(r"[A-Za-z][\w.]*", field) for field in fields
    ):
        raise ValueError("fields must contain 1-32 distinct valid solver field names")

    candidate = Path(directory)
    raw_candidate = candidate if candidate.is_absolute() else Path.cwd() / candidate
    root = None
    root_problem = None
    try:
        if any(component.is_symlink() for component in (raw_candidate, *raw_candidate.parents)):
            root_problem = "GRID_FAMILY_DIRECTORY_MISSING_OR_SYMLINKED"
        elif not raw_candidate.is_dir():
            root_problem = "GRID_FAMILY_DIRECTORY_MISSING_OR_SYMLINKED"
        else:
            root = raw_candidate.resolve(strict=True)
    except OSError:
        root_problem = "GRID_FAMILY_DIRECTORY_MISSING_OR_UNREADABLE"

    expected = {}
    for configuration in (1, 2, 3):
        for level in _GRID_LEVELS:
            case_id = f"configuration_{configuration}/{level}"
            expected[case_id] = f"{case_id}/simpleFoam.log"

    found_paths = set()
    if root is not None:
        try:
            found_paths = {
                path.relative_to(root).as_posix()
                for path in root.rglob("simpleFoam.log")
            }
        except OSError:
            root_problem = "GRID_FAMILY_DIRECTORY_UNREADABLE"
            root = None

    expected_paths = set(expected.values())
    unexpected_paths = sorted(found_paths - expected_paths)
    cases = {}
    present = 0
    for case_id, relative_log in expected.items():
        path = (root / relative_log) if root is not None else raw_candidate / relative_log
        if path.is_file() or path.is_symlink():
            present += 1
            try:
                report = diagnose_log(
                    path, fields=fields, window=window, trend_window=trend_window
                )
            except (OSError, UnicodeError, ValueError) as exc:
                report = {
                    "status": "INCOMPLETE_OR_INVALID",
                    "scientific_validation": "BLOCKED",
                    "problems": [str(exc)],
                }
        else:
            report = {
                "status": "INCOMPLETE_OR_INVALID",
                "scientific_validation": "BLOCKED",
                "problems": ["MISSING_CASE_LOG"],
            }
        if root is not None and report.get("status") == "DIAGNOSTIC_ONLY" and report.get("last_time"):
            flux_report = diagnose_grid_flux(
                root / case_id, report["last_time"], family_root=root
            )
        else:
            flux_report = {
                "status": "UNAVAILABLE",
                "problems": ["SOLVER_LOG_NOT_DIAGNOSTIC"],
            }
        cases[case_id] = {"log_path": relative_log, **report,
                          "solver_flux_screen": flux_report}

    by_digest: dict[str, list[str]] = {}
    for case_id, report in cases.items():
        digest = report.get("source_sha256")
        if digest is not None:
            by_digest.setdefault(digest, []).append(case_id)
    duplicate_groups = []
    for case_ids in by_digest.values():
        if len(case_ids) > 1:
            duplicate_groups.append(case_ids)
            for case_id in case_ids:
                report = cases[case_id]
                report["status"] = "INCOMPLETE_OR_INVALID"
                report.setdefault("problems", []).append("DUPLICATE_LOG_BYTES")
                report["duplicate_log_cases"] = [other for other in case_ids if other != case_id]

    problems = []
    if root_problem:
        problems.append(root_problem)
    if present != len(expected):
        problems.append("MISSING_OR_UNREADABLE_CASE_LOGS")
    if unexpected_paths:
        problems.append("UNEXPECTED_SIMPLEFOAM_LOG_PATHS")
    if duplicate_groups:
        problems.append("DUPLICATE_LOG_BYTES")

    complete = (
        root is not None
        and not problems
        and all(item["status"] == "DIAGNOSTIC_ONLY" for item in cases.values())
    )

    residual_states = []
    if complete:
        for report in cases.values():
            control_fields = report.get("terminal_residual_control_screen", {}).get("fields", {})
            for field in _GRID_RESIDUAL_FIELDS:
                item = control_fields.get(field)
                residual_states.append(item.get("status") if item else "UNKNOWN")
    if not complete or any(state == "UNKNOWN" for state in residual_states):
        residual_status = "UNKNOWN"
    elif any(state == "NOT_BELOW_TOLERANCE" for state in residual_states):
        residual_status = "NOT_BELOW_TOLERANCE"
    elif residual_states and all(state == "BELOW_TOLERANCE" for state in residual_states):
        residual_status = "BELOW_TOLERANCE"
    else:
        residual_status = "UNKNOWN"

    flux_measured = sum(
        report.get("solver_flux_screen", {}).get("status") == "MEASURED_DIAGNOSTIC_ONLY"
        for report in cases.values()
    )
    if flux_measured == len(expected):
        flux_status = "MEASURED_DIAGNOSTIC_ONLY"
    elif flux_measured:
        flux_status = "PARTIAL_OR_UNAVAILABLE"
    else:
        flux_status = "UNAVAILABLE"

    return {
        "status": "DIAGNOSTIC_ONLY" if complete else "INCOMPLETE_OR_INVALID",
        "scientific_validation": "BLOCKED",
        "solver_input_fingerprint_screen": audit_grid_family_inputs(raw_candidate),
        "case_count_expected": len(expected),
        "case_count_present": present,
        "cases": cases,
        "solver_flux_balance_screen": {
            "status": flux_status,
            "case_count_measured": flux_measured,
            "case_count_expected": len(expected),
            "acceptance_criterion": "NOT_SET",
            "note": "Signed final-time incompressible phi fluxes are diagnostic measurements only; no project balance tolerance is defined and they do not establish convergence or scientific validation.",
        },
        "unexpected_simpleFoam_logs": unexpected_paths,
        "duplicate_log_case_groups": duplicate_groups,
        "configured_residual_screen": {
            "status": residual_status,
            "required_fields": list(_GRID_RESIDUAL_FIELDS),
            "note": "This is the logged Foundation residualControl screen only; it is not nonlinear or physical convergence.",
        },
        "problems": problems,
        "note": "A complete diagnostic report is not proof of independent execution, mass balance, mesh independence, model validity, or cleanroom performance.",
    }


def grid_family_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only log and final-time flux triage for a 3x3 OpenFOAM grid family")
    parser.add_argument("directory", help="Grid-family directory containing configuration_1..3/{coarse,medium,fine}")
    parser.add_argument("--fields", nargs="+", default=["Ux", "Uy", "Uz", "p"])
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--trend-window", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        report = diagnose_grid_family(
            args.directory, fields=tuple(args.fields), window=args.window,
            trend_window=args.trend_window,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, allow_nan=False, sort_keys=True))
    return 0 if report["status"] == "DIAGNOSTIC_ONLY" else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    parser.add_argument("--fields", nargs="+", default=["Ux", "Uy", "Uz", "p"])
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--trend-window", type=int, default=50)
    args = parser.parse_args()
    reports = {}
    for path in args.logs:
        try:
            reports[path] = diagnose_log(
                path, fields=tuple(args.fields), window=args.window,
                trend_window=args.trend_window,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            reports[path] = {"status": "INCOMPLETE_OR_INVALID",
                             "scientific_validation": "BLOCKED",
                             "problems": [str(exc)]}
    # Cross-file checks are diagnostic integrity guards, not authentication.
    # Identical bytes cannot distinguish independent executions.
    # Lexical path normalization detects aliases without following links.
    aliases: dict[str, list[str]] = {}
    for path in args.logs:
        normalized = os.path.normcase(os.path.abspath(path))
        aliases.setdefault(normalized, [])
        if path not in aliases[normalized]:
            aliases[normalized].append(path)
    for shared_paths in aliases.values():
        if len(shared_paths) > 1:
            for path in shared_paths:
                reports[path]["status"] = "INCOMPLETE_OR_INVALID"
                if "DUPLICATE_INPUT_PATH" not in reports[path]["problems"]:
                    reports[path]["problems"].append("DUPLICATE_INPUT_PATH")
                reports[path]["duplicate_input_paths"] = [
                    other for other in shared_paths if other != path
                ]
    counts: dict[str, int] = {}
    for path in args.logs:
        counts[path] = counts.get(path, 0) + 1
    for path, count in counts.items():
        if count > 1:
            reports[path]["status"] = "INCOMPLETE_OR_INVALID"
            reports[path]["problems"].append("DUPLICATE_INPUT_PATH")

    by_digest: dict[str, list[str]] = {}
    for path, report in reports.items():
        digest = report.get("source_sha256")
        if digest is not None:
            by_digest.setdefault(digest, []).append(path)
    for shared_paths in by_digest.values():
        if len(shared_paths) > 1:
            for path in shared_paths:
                reports[path]["status"] = "INCOMPLETE_OR_INVALID"
                reports[path]["problems"].append("DUPLICATE_LOG_BYTES")
                reports[path]["duplicate_log_paths"] = [
                    other for other in shared_paths if other != path
                ]

    print(json.dumps(reports, indent=2, allow_nan=False, sort_keys=True))
    return 0 if all(r["status"] == "DIAGNOSTIC_ONLY" for r in reports.values()) else 3


if __name__ == "__main__":
    raise SystemExit(main())

