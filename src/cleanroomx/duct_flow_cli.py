from __future__ import annotations

import argparse
import sys

from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
from .duct_flow import solve_parallel_branch_flows
from .duct_flow_io import load_parallel_flow_network
from .duct_flow_report import markdown_parallel_flow_report
from .strict_json import StrictJSONError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-duct-flow",
        description="CleanroomX parallel duct branch-flow solver",
    )
    parser.add_argument("network", help="Path to parallel-flow network JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


@cli_error_boundary("cleanroomx-duct-flow")
def main() -> int:
    args = build_parser().parse_args()
    result = solve_parallel_branch_flows(load_cli_input(load_parallel_flow_network, args.network))
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_parallel_flow_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-duct-flow: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        if not publish_cli_output(
            "cleanroomx-duct-flow",
            args.output,
            text,
            protected_inputs=(args.network,),
        ):
            return 1
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
