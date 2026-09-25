from __future__ import annotations

import argparse
import json
from pathlib import Path

from .persistence import atomic_write_text
from .loop_network_io import load_looped_flow_network
from .variable_friction_loop import solve_variable_friction_looped_network
from .variable_friction_loop_report import (
    markdown_variable_friction_loop_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-loop-friction",
        description=(
            "Iterative looped airflow-network solver with automatic "
            "Darcy-friction updates"
        ),
    )
    parser.add_argument("network", help="Path to looped-network JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    parser.add_argument(
        "--resistance-relative-tolerance",
        type=float,
        default=1e-6,
        help="Relative closure tolerance for updated edge resistance",
    )
    parser.add_argument(
        "--relaxation",
        type=float,
        default=0.5,
        help="Outer resistance-update relaxation in (0, 1]",
    )
    parser.add_argument(
        "--near-zero-airflow-m3-h",
        type=float,
        default=1e-6,
        help=(
            "Automatic-friction edges at or below this absolute "
            "airflow retain their previous resistance"
        ),
    )
    parser.add_argument(
        "--max-outer-iterations",
        type=int,
        default=50,
        help="Maximum variable-friction outer iterations",
    )
    parser.add_argument(
        "--mass-balance-tolerance-m3-h",
        type=float,
        default=1e-6,
        help="Absolute node continuity tolerance for each inner solve",
    )
    parser.add_argument(
        "--max-newton-iterations",
        type=int,
        default=100,
        help="Maximum damped-Newton iterations per inner solve",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_variable_friction_looped_network(
        load_looped_flow_network(args.network),
        resistance_relative_tolerance=(
            args.resistance_relative_tolerance
        ),
        relaxation=args.relaxation,
        near_zero_airflow_m3_h=args.near_zero_airflow_m3_h,
        max_outer_iterations=args.max_outer_iterations,
        mass_balance_tolerance_m3_h=(
            args.mass_balance_tolerance_m3_h
        ),
        max_newton_iterations=args.max_newton_iterations,
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_variable_friction_loop_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
