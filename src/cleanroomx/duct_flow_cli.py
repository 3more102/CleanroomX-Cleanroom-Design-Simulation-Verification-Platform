from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import atomic_write_text
from .duct_flow import solve_parallel_branch_flows
from .duct_flow_io import load_parallel_flow_network
from .duct_flow_report import markdown_parallel_flow_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-duct-flow",
        description="CleanroomX parallel duct branch-flow solver",
    )
    parser.add_argument("network", help="Path to parallel-flow network JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_parallel_branch_flows(load_parallel_flow_network(args.network))
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_parallel_flow_report(result)
    )
    if args.output:
        atomic_write_text(args.output, text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
