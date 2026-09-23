from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fan_loop_network import solve_fan_driven_loop_network
from .fan_loop_network_io import load_fan_driven_loop_network_study
from .fan_loop_network_report import markdown_fan_driven_loop_network_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-loop",
        description="Bounded fan operating point against a passive looped airflow network",
    )
    parser.add_argument("study", help="Path to fan/loop-network study JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    parser.add_argument(
        "--mass-balance-tolerance-m3-h",
        type=float,
        default=1e-6,
        help="Absolute loop-network continuity tolerance in m3/h",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=100,
        help="Maximum damped-Newton iterations for each loop solve",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_driven_loop_network(
        load_fan_driven_loop_network_study(args.study),
        mass_balance_tolerance_m3_h=args.mass_balance_tolerance_m3_h,
        max_iterations=args.max_iterations,
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_driven_loop_network_report(result)
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
