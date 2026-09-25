from __future__ import annotations

import argparse
import json
from pathlib import Path

from .persistence import atomic_write_text
from .loop_network import solve_looped_network
from .loop_network_io import load_looped_flow_network
from .loop_network_report import markdown_looped_network_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-loop-flow",
        description="Fixed-resistance looped airflow-network solver",
    )
    parser.add_argument("network", help="Path to looped-network JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
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
    result = solve_looped_network(
        load_looped_flow_network(args.network),
        mass_balance_tolerance_m3_h=args.mass_balance_tolerance_m3_h,
        max_iterations=args.max_iterations,
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_looped_network_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
