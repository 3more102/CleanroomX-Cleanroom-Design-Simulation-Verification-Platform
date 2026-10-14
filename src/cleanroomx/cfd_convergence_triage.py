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
_TIME_LINE = re.compile(rf"^\s*Time\s*=\s*({_NUMBER})(s?)\s*$")
_TIME_START = re.compile(r"^\s*Time\s*=")
_END_LINE = re.compile(r"^\s*End\s*$")
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

    lines = data.splitlines()
    for line in lines:
        time_match = _TIME_LINE.fullmatch(line)
        if time_match:
            if time_steps and (set(fields) - last_step_fields or not last_step_continuity):
                incomplete_prior_steps += 1
            stamp = "".join(time_match.groups())
            time_steps += 1
            last_time = stamp
            try:
                numeric_time = float(time_match.group(1))
            except ValueError:
                bad_time = True
            else:
                if not math.isfinite(numeric_time) or (
                    previous_time is not None and numeric_time <= previous_time
                ):
                    bad_time = True
                if math.isfinite(numeric_time):
                    previous_time = numeric_time
            last_step_fields.clear()
            last_step_continuity = 0
            continue

        if _TIME_START.match(line):
            malformed_time = True
            continue

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
                last_step_fields.add(field)
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
        "continuity_samples": continuity_samples,
        "recent_global_continuity": list(recent_global_continuity),
        "problems": problems,
        "note": "Linear solver residuals are not proof of physical convergence or mass balance.",
    }


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
