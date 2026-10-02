from __future__ import annotations

import argparse
import sys

from .strict_json import StrictJSONError
from .cli_output import (
    CLI_OUTPUT_ERROR_EXIT_CODE,
    dumps_strict_json,
    publish_cli_output,
)
from .damper_study import solve_loop_damper_study
from .damper_study_io import load_loop_damper_study
from .damper_study_report import markdown_loop_damper_study_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-damper-study",
        description="CleanroomX explicit loop damper-resistance scenario study",
    )
    parser.add_argument("study", help="Path to damper-study JSON")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
    )
    parser.add_argument("--output", help="Optional output file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = solve_loop_damper_study(
        load_loop_damper_study(args.study)
    )
    try:
        text = (
            dumps_strict_json(result)
            if args.format == "json"
            else markdown_loop_damper_study_report(result)
        )
    except StrictJSONError as exc:
        print(
            f"cleanroomx-damper-study: error: analysis result is not strict JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if args.output:
        if not publish_cli_output(
            args.output,
            text,
            protected_inputs=(args.study,),
            program="cleanroomx-damper-study",
        ):
            return CLI_OUTPUT_ERROR_EXIT_CODE
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
