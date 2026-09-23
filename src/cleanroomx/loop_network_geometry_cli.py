from __future__ import annotations

import argparse
import json
from pathlib import Path

from .loop_network_geometry import solve_geometry_looped_network
from .loop_network_geometry_io import load_geometry_looped_flow_network
from .loop_network_geometry_report import (
    markdown_geometry_looped_network_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-loop-duct",
        description=(
            "Looped airflow-network solver with fixed resistance derived "
            "from explicit duct geometry and reference-flow friction"
        ),
    )
    parser.add_argument("network", help="Path to geometry-based loop-network JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    parser.add_argument(
        "--mass-balance-tolerance-m3-h",
        type=float,
        default=1e-6,
        help="Absolute node continuity tolerance in m3/h",
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
    result = solve_geometry_looped_network(
        load_geometry_looped_flow_network(args.network),
        mass_balance_tolerance_m3_h=args.mass_balance_tolerance_m3_h,
        max_iterations=args.max_iterations,
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_geometry_looped_network_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
