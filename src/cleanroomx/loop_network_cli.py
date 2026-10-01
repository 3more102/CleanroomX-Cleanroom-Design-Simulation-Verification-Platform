from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import atomic_write_cli_output, dumps_strict_json
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
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_looped_network_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-loop-flow: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        atomic_write_cli_output(
            args.output,
            text,
            protected_inputs=(args.network,),
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
