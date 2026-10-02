from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import write_cli_output_or_report_error, dumps_strict_json
from .qualification import analyze_qualification_uncertainty
from .qualification_io import load_qualification_uncertainty
from .qualification_report import markdown_qualification_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-qualification",
        description="Uncertainty-aware cleanroom qualification screening",
    )
    parser.add_argument("file", help="Path to qualification uncertainty JSON")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = analyze_qualification_uncertainty(load_qualification_uncertainty(args.file))
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_qualification_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-qualification: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.output:
        if not write_cli_output_or_report_error(
            "cleanroomx-qualification",
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
