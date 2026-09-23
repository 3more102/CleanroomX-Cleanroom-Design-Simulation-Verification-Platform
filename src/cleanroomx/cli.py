from __future__ import annotations

import argparse
import json
import sys

from .calculations import decay_concentration, recovery_time_minutes
from .io import load_pressure_cascade, load_room
from .verification import verify_pressure_cascade, verify_room


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cleanroomx")
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="Verify a room JSON file against configured project requirements")
    verify.add_argument("file")

    cascade = sub.add_parser("cascade", help="Verify a multi-room directional pressure-cascade JSON file")
    cascade.add_argument("file")

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
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "verify":
            report = verify_room(load_room(args.file))
            print(json.dumps(report.to_dict(), indent=2))
            return 0 if report.passed else 2
        if args.command == "cascade":
            report = verify_pressure_cascade(load_pressure_cascade(args.file))
            print(json.dumps(report.to_dict(), indent=2))
            return 0 if report.passed else 2
        if args.command == "decay":
            value = decay_concentration(args.initial, args.ach, args.minutes, args.efficiency)
            print(json.dumps({"concentration_per_m3": value}, indent=2))
            return 0
        value = recovery_time_minutes(args.initial, args.target, args.ach, args.efficiency)
        print(json.dumps({"recovery_time_minutes": value}, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"cleanroomx: input error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
