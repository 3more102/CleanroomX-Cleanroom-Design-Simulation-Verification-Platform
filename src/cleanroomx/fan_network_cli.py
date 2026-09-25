from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import atomic_write_text
from .fan_network import solve_fan_driven_parallel_network
from .fan_network_io import load_fan_driven_parallel_network_study
from .fan_network_report import markdown_fan_driven_parallel_network_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-network",
        description="CleanroomX fan-driven passive parallel-network solver",
    )
    parser.add_argument("study", help="Path to fan/parallel-network JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_driven_parallel_network(
        load_fan_driven_parallel_network_study(args.study)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_driven_parallel_network_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
