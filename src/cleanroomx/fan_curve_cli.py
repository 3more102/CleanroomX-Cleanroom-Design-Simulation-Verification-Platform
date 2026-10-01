from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import atomic_write_cli_output, dumps_strict_json
from .fan_curve import solve_fan_operating_point
from .fan_curve_io import load_fan_operating_point_study
from .fan_curve_report import markdown_fan_operating_point_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-fan-curve",
        description="CleanroomX fan/system operating-point solver",
    )
    parser.add_argument("study", help="Path to fan/system curve JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_fan_operating_point(
        load_fan_operating_point_study(args.study)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_fan_operating_point_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-fan-curve: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        atomic_write_cli_output(
            args.output,
            text,
            protected_inputs=(args.study,),
        )
    else:
        print(text)
    return 0 if result["status"] == "solved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
