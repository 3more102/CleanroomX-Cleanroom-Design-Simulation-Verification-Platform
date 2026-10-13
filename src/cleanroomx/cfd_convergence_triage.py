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
    rf"\s*,\s*Final residual\s*=\s*({_NUMBER})\s*,\s*No Iterations\s+(\d+)"
)
_TIME = re.compile(r"^Time\s*=\s*([^\s]+)", re.MULTILINE)
_CONTINUITY = re.compile(rf"time step continuity errors\s*:\s*sum local\s*=\s*({_NUMBER})"
                         rf"\s*,\s*global\s*=\s*({_NUMBER})"
                         rf"\s*,\s*cumulative\s*=\s*({_NUMBER})")
_BAD = re.compile(r"FOAM FATAL|Floating point exception|Segmentation fault|\b(?:nan|inf|infinity)\b", re.I)


def diagnose_log(path: str | Path, *, fields: tuple[str, ...] = ("Ux", "Uy", "Uz", "p"),
                 window: int = 5) -> dict:
    """Extract evidence without asserting that a run converged."""
    if window < 1 or window > 10000:
        raise ValueError("window must be between 1 and 10000")
    p = Path(path)
    if not p.is_file() or p.is_symlink():
        raise ValueError("missing or symlinked log")
    if p.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("log exceeds 64 MiB diagnostic limit")
    raw = p.read_bytes()
    data = raw.decode("utf-8")
    times = _TIME.findall(data)
    rows = {}
    for match in _SOLVE.finditer(data):
        field, initial, final, iterations = match.groups()
        a, b = float(initial), float(final)
        if not (math.isfinite(a) and math.isfinite(b)):
            continue
        rows.setdefault(field, []).append({
            "initial": a, "final": b, "iterations": int(iterations)
        })
    continuity = []
    for local, global_, cumulative in _CONTINUITY.findall(data):
        values = tuple(map(float, (local, global_, cumulative)))
        if all(math.isfinite(x) for x in values):
            continuity.append({"local": values[0], "global": values[1],
                               "cumulative": values[2]})
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
    clean_end = bool(data.rstrip().splitlines() and data.rstrip().splitlines()[-1].strip() == "End")
    problems = []
    if not times:
        problems.append("NO_TIME_STEPS")
    if not clean_end:
        problems.append("MISSING_TERMINAL_END")
    if _BAD.search(data):
        problems.append("FATAL_OR_NONFINITE_TOKEN")
    if any(item["missing"] for item in field_report.values()):
        problems.append("MISSING_REQUIRED_FIELD")
    if not continuity:
        problems.append("NO_CONTINUITY_RECORDS")
    return {
        "status": "DIAGNOSTIC_ONLY" if not problems else "INCOMPLETE_OR_INVALID",
        "scientific_validation": "BLOCKED",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "time_steps": len(times),
        "last_time": times[-1] if times else None,
        "terminal_end": clean_end,
        "fields": field_report,
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
    print(json.dumps(reports, indent=2, allow_nan=False, sort_keys=True))
    return 0 if all(r["status"] == "DIAGNOSTIC_ONLY" for r in reports.values()) else 3


if __name__ == "__main__":
    raise SystemExit(main())
