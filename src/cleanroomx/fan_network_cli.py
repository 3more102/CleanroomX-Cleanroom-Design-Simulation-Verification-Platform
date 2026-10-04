from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
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


@cli_error_boundary("cleanroomx-fan-network")
def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_driven_parallel_network(
        load_cli_input(load_fan_driven_parallel_network_study, args.study)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_fan_driven_parallel_network_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-fan-network: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        if not publish_cli_output(
            "cleanroomx-fan-network",
            args.output,
            text,
            protected_inputs=(args.study,),
        ):
            return 1
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
