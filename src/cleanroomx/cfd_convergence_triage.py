"""Conservative, read-only triage of OpenFOAM Foundation-style solver logs.

This is diagnostic evidence only; it never declares physical convergence.
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
                 window: int = 5) -> dict:
    """Extract step-aware solver diagnostics; never assert scientific convergence."""
    if window < 1 or window > 10000:
        raise ValueError("window must be between 1 and 10000")
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
    for field in fields:
        recent = recent_residuals[field]
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
                         window: int = 5) -> dict:
    """Read-only diagnostic matrix for the exact 3-configuration x 3-grid family.

    A complete report means all nine expected logs were distinct and
    structurally parseable. It does not mean the configured residual screen
    passed, and never advances scientific validation beyond BLOCKED.
    """
    if type(window) is not int or window < 1 or window > 10000:
        raise ValueError("window must be between 1 and 10000")
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
                report = diagnose_log(path, fields=fields, window=window)
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
        cases[case_id] = {"log_path": relative_log, **report}

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

    return {
        "status": "DIAGNOSTIC_ONLY" if complete else "INCOMPLETE_OR_INVALID",
        "scientific_validation": "BLOCKED",
        "solver_input_fingerprint_screen": audit_grid_family_inputs(raw_candidate),
        "case_count_expected": len(expected),
        "case_count_present": present,
        "cases": cases,
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
    parser = argparse.ArgumentParser(description="Read-only triage of all nine logs in a 3x3 OpenFOAM grid family")
    parser.add_argument("directory", help="Grid-family directory containing configuration_1..3/{coarse,medium,fine}")
    parser.add_argument("--fields", nargs="+", default=["Ux", "Uy", "Uz", "p"])
    parser.add_argument("--window", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = diagnose_grid_family(args.directory, fields=tuple(args.fields), window=args.window)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, allow_nan=False, sort_keys=True))
    return 0 if report["status"] == "DIAGNOSTIC_ONLY" else 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+")
    parser.add_argument("--fields", nargs="+", default=["Ux", "Uy", "Uz", "p"])
    parser.add_argument("--window", type=int, default=5)
    args = parser.parse_args()
    reports = {}
    for path in args.logs:
        try:
            reports[path] = diagnose_log(path, fields=tuple(args.fields), window=args.window)
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

