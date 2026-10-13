"""Conservative, read-only triage of OpenFOAM Foundation-style solver logs.

This is diagnostic evidence only; it never declares physical convergence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_SOLVE = re.compile(
    rf"Solving for\s+([A-Za-z][\w.]*)\s*,\s*Initial residual\s*=\s*({_NUMBER})"
    rf"\s*,\s*Final residual\s*=\s*({_NUMBER})\s*,\s*No Iterations\s+(\d{{1,12}})"
)
_TIME_LINE = re.compile(r"^\s*Time\s*=\s*(\S+)\s*$")
_TIME_START = re.compile(r"^\s*Time\s*=")
_END_LINE = re.compile(r"^\s*End\s*$")
_CONTINUITY = re.compile(rf"time step continuity errors\s*:\s*sum local\s*=\s*({_NUMBER})"
                         rf"\s*,\s*global\s*=\s*({_NUMBER})"
                         rf"\s*,\s*cumulative\s*=\s*({_NUMBER})")
_BAD = re.compile(r"FOAM FATAL|Floating point exception|Segmentation fault|\b(?:nan|inf|infinity)\b", re.I)


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
    if p.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("log exceeds 64 MiB diagnostic limit")
    raw = p.read_bytes()
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("log exceeds 64 MiB diagnostic limit")
    data = raw.decode("utf-8")

    times: list[str] = []
    previous_time: float | None = None
    bad_time = False
    malformed_time = False
    rows: dict[str, list[dict]] = {}
    continuity: list[dict] = []
    last_step_fields: set[str] = set()
    last_step_continuity = 0
    incomplete_prior_steps = 0
    orphan_records = 0
    invalid_residual = False
    malformed_solver = False
    malformed_continuity = False
    end_markers = 0

    for line in data.splitlines():
        time_match = _TIME_LINE.fullmatch(line)
        if time_match:
            if times and (set(fields) - last_step_fields or not last_step_continuity):
                incomplete_prior_steps += 1
            stamp = time_match.group(1)
            times.append(stamp)
            try:
                numeric_time = float(stamp)
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
                rows.setdefault(field, []).append({
                    "initial": a, "final": b, "iterations": int(iterations)
                })
            if times:
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
                continuity.append({
                    "local": values[0], "global": values[1], "cumulative": values[2]
                })
                if times:
                    last_step_continuity += 1
                else:
                    orphan_records += 1
            else:
                malformed_continuity = True

    field_report = {}
    for field in fields:
        samples = rows.get(field, [])
        recent = samples[-window:]
        field_report[field] = {
            "samples": len(samples),
            "recent_initial": [r["initial"] for r in recent],
            "recent_final": [r["final"] for r in recent],
            "last_initial": samples[-1]["initial"] if samples else None,
            "last_final": samples[-1]["final"] if samples else None,
            "missing": not samples,
        }

    last_nonblank_line = data.rstrip().splitlines()
    clean_end = bool(last_nonblank_line and last_nonblank_line[-1].strip() == "End")
    missing_last_fields = sorted(set(fields) - last_step_fields)
    problems = []
    if not times:
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
    if not continuity:
        problems.append("NO_CONTINUITY_RECORDS")
    if times and (missing_last_fields or not last_step_continuity):
        problems.append("INCOMPLETE_FINAL_TIME_STEP")

    return {
        "status": "DIAGNOSTIC_ONLY" if not problems else "INCOMPLETE_OR_INVALID",
        "scientific_validation": "BLOCKED",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "time_steps": len(times),
        "last_time": times[-1] if times else None,
        "time_sequence_monotonic": bool(times) and not (bad_time or malformed_time),
        "terminal_end": clean_end,
        "fields": field_report,
        "incomplete_prior_time_steps": incomplete_prior_steps,
        "last_step_missing_fields": missing_last_fields,
        "last_step_continuity_samples": last_step_continuity,
        "continuity_samples": len(continuity),
        "recent_global_continuity": [x["global"] for x in continuity[-window:]],
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
