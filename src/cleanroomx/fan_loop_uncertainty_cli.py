from __future__ import annotations

import argparse
import sys

from .cli_output import CLIOutputError, write_cli_output
import json

from .fan_loop_uncertainty import analyze_fan_loop_network_uncertainty
from .fan_loop_uncertainty_io import load_fan_loop_network_uncertainty
from .fan_loop_uncertainty_report import (
    markdown_fan_loop_network_uncertainty_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-loop-uncertainty",
        description="Bounded uncertainty analysis for fan-driven loop networks",
    )
    parser.add_argument("study", help="Path to fan/loop-network uncertainty JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_loop_network_uncertainty(
        load_fan_loop_network_uncertainty(args.study)
    )
    text = (
        json.dumps(result, indent=2)
        if args.format == "json"
        else markdown_fan_loop_network_uncertainty_report(result)
    )
    if args.output:
        try:
            write_cli_output(
                args.output,
                text,
                protected_inputs=(args.study,),
            )
        except CLIOutputError as exc:
            print(f"cleanroomx-fan-loop-uncertainty: error: {exc}", file=sys.stderr)
            return 1
    else:
        print(text)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
