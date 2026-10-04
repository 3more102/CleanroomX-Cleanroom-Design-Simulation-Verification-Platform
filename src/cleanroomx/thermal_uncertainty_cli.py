from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
from .thermal_uncertainty import analyze_thermal_uncertainty
from .thermal_uncertainty_io import load_thermal_uncertainty
from .thermal_uncertainty_report import markdown_thermal_uncertainty_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-thermal-uncertainty",
        description="Conservative thermal-load, capacity, and airflow uncertainty screening",
    )
    parser.add_argument("file", help="Path to thermal uncertainty JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


@cli_error_boundary("cleanroomx-thermal-uncertainty")
def main() -> int:
    args = build_parser().parse_args()
    result = analyze_thermal_uncertainty(load_cli_input(load_thermal_uncertainty, args.file))
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_thermal_uncertainty_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-thermal-uncertainty: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        if not publish_cli_output(
            "cleanroomx-thermal-uncertainty",
            args.output,
            text,
            protected_inputs=(args.file,),
        ):
            return 1
    else:
        print(text)

    if result["overall_status"] == "fail":
        return 2
    if result["overall_status"] == "indeterminate":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
