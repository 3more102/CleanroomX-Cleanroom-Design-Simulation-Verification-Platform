from __future__ import annotations

import argparse
import json

from .project import atomic_write_text
from .fan_loop_network import solve_fan_loop_network
from .fan_loop_network_io import load_fan_loop_network_study
from .fan_loop_network_report import markdown_fan_loop_network_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-loop",
        description="Bounded fan/loop-network operating-point solver",
    )
    parser.add_argument("study", help="Path to fan/loop-network JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_loop_network(load_fan_loop_network_study(args.study))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_loop_network_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
