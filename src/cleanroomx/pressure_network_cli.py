from __future__ import annotations

import argparse
import json

from .pressure_network import solve_room_pressure_network
from .pressure_network_io import load_pressure_network
from .pressure_network_report import markdown_pressure_network_report
from .project import atomic_write_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-pressure-network",
        description=(
            "Steady-state cleanroom room-pressure/leakage network solver"
        ),
    )
    parser.add_argument(
        "network",
        help="Path to pressure-network JSON",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument(
        "--output",
        help="Optional output file",
    )
    parser.add_argument(
        "--mass-balance-tolerance-m3-h",
        type=float,
        default=1e-6,
        help="Absolute unknown-room continuity tolerance in m3/h",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum damped-Newton iterations",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_room_pressure_network(
        load_pressure_network(args.network),
        mass_balance_tolerance_m3_h=(
            args.mass_balance_tolerance_m3_h
        ),
        max_iterations=args.max_iterations,
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_pressure_network_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
