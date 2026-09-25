from __future__ import annotations

import argparse

from .jsonio import strict_json_dumps
from .calculations import decay_concentration, recovery_time_minutes
from .io import load_project, load_room
from .project_verification import verify_project
from .verification import verify_room


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cleanroomx")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="Verify a room JSON file against configured project requirements")
    verify.add_argument("file")

    verify_project_parser = sub.add_parser(
        "verify-project", help="Verify a multi-room project including configured pressure-cascade requirements"
    )
    verify_project_parser.add_argument("file")

    decay = sub.add_parser("decay", help="Run the well-mixed first-order concentration decay screening model")
    decay.add_argument("--initial", type=float, required=True)
    decay.add_argument("--ach", type=float, required=True)
    decay.add_argument("--minutes", type=float, required=True)
    decay.add_argument("--efficiency", type=float, default=1.0)

    recovery = sub.add_parser("recovery", help="Estimate recovery time with the screening model")
    recovery.add_argument("--initial", type=float, required=True)
    recovery.add_argument("--target", type=float, required=True)
    recovery.add_argument("--ach", type=float, required=True)
    recovery.add_argument("--efficiency", type=float, default=1.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "verify":
        report = verify_room(load_room(args.file))
        print(strict_json_dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 2
    if args.command == "verify-project":
        report = verify_project(load_project(args.file))
        print(strict_json_dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 2
    if args.command == "decay":
        value = decay_concentration(args.initial, args.ach, args.minutes, args.efficiency)
        print(strict_json_dumps({"concentration_per_m3": value}, indent=2))
        return 0
    value = recovery_time_minutes(args.initial, args.target, args.ach, args.efficiency)
    print(strict_json_dumps({"recovery_time_minutes": value}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
