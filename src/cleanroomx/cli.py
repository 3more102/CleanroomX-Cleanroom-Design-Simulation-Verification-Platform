from __future__ import annotations

import argparse
import json
from pathlib import Path

from .calculations import decay_concentration, recovery_time_minutes
from .io import load_project, load_room
from .project_verification import verify_project
from .recovery import analyze_recovery_test
from .recovery_io import load_recovery_test
from .recovery_report import markdown_recovery_report
from .verification import verify_room


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cleanroomx")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser(
        "verify",
        help="Verify a room JSON file against configured project requirements",
    )
    verify.add_argument("file")

    verify_project_parser = sub.add_parser(
        "verify-project",
        help="Verify a multi-room project including configured pressure-cascade requirements",
    )
    verify_project_parser.add_argument("file")

    decay = sub.add_parser(
        "decay",
        help="Run the well-mixed first-order concentration decay screening model",
    )
    decay.add_argument("--initial", type=float, required=True)
    decay.add_argument("--ach", type=float, required=True)
    decay.add_argument("--minutes", type=float, required=True)
    decay.add_argument("--efficiency", type=float, default=1.0)

    recovery = sub.add_parser(
        "recovery",
        help="Estimate recovery time with the screening model",
    )
    recovery.add_argument("--initial", type=float, required=True)
    recovery.add_argument("--target", type=float, required=True)
    recovery.add_argument("--ach", type=float, required=True)
    recovery.add_argument("--efficiency", type=float, default=1.0)

    recovery_test = sub.add_parser(
        "recovery-test",
        help="Analyze a measured recovery-test concentration time series",
    )
    recovery_test.add_argument("file")
    recovery_test.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
    )
    recovery_test.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "verify":
        report = verify_room(load_room(args.file))
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 2
    if args.command == "verify-project":
        report = verify_project(load_project(args.file))
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 2
    if args.command == "decay":
        value = decay_concentration(
            args.initial,
            args.ach,
            args.minutes,
            args.efficiency,
        )
        print(json.dumps({"concentration_per_m3": value}, indent=2))
        return 0
    if args.command == "recovery":
        value = recovery_time_minutes(
            args.initial,
            args.target,
            args.ach,
            args.efficiency,
        )
        print(json.dumps({"recovery_time_minutes": value}, indent=2))
        return 0

    result = analyze_recovery_test(load_recovery_test(args.file))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_recovery_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 2 if result["passes_max_recovery_time"] is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
