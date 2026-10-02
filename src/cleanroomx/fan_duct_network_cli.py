from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import dumps_strict_json, publish_cli_output
from .fan_duct_network import analyze_fan_duct_network
from .fan_duct_network_io import load_fan_duct_network_study
from .fan_duct_network_report import markdown_fan_duct_network_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-duct",
        description=(
            "CleanroomX fan-curve and duct-network operating-point solver"
        ),
    )
    parser.add_argument(
        "study",
        help="Path to fan/duct-network study JSON",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_fan_duct_network(
        load_fan_duct_network_study(args.study)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_fan_duct_network_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-fan-duct: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        if not publish_cli_output(
            "cleanroomx-fan-duct",
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
