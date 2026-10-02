from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import write_cli_output_or_report_error, dumps_strict_json
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
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_fan_loop_network_uncertainty_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-fan-loop-uncertainty: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        if not write_cli_output_or_report_error(
            "cleanroomx-fan-loop-uncertainty",
            args.output,
            text,
            protected_inputs=(args.study,),
        ):
            return 1
    else:
        print(text)
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
